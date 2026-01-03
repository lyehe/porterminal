"""FastAPI application with security checks and WebSocket endpoint."""

import asyncio
import ctypes
import logging
import os
import signal
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from . import __version__
from .composition import create_container
from .container import Container
from .domain import UserId
from .infrastructure.auth import authenticate_connection, validate_auth_message
from .infrastructure.web import FastAPIWebSocketAdapter
from .logging_setup import setup_logging_from_env

logger = logging.getLogger(__name__)

# Path to static files (inside package)
STATIC_DIR = Path(__file__).parent / "static"


def is_admin() -> bool:
    """Check if running as administrator (Windows)."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def security_preflight_checks() -> None:
    """Run security checks before starting the application."""
    # Check not running as admin
    if is_admin():
        logger.warning(
            "SECURITY WARNING: Running as Administrator is not recommended. "
            "This exposes excessive privileges to remote users."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    setup_logging_from_env()
    security_preflight_checks()

    # Create DI container with all wired dependencies
    # config_path=None uses find_config_file() to search standard locations
    cwd = os.environ.get("PORTERMINAL_CWD")

    # Get password hash from environment if set
    password_hash = None
    if hash_str := os.environ.get("PORTERMINAL_PASSWORD_HASH"):
        password_hash = hash_str.encode()

    container = create_container(config_path=None, cwd=cwd, password_hash=password_hash)
    app.state.container = container

    # Wire up cascade: when session is destroyed, close associated tabs and broadcast
    async def on_session_destroyed(session_id, user_id):
        closed_tabs = container.tab_service.close_tabs_for_session(session_id)
        for tab in closed_tabs:
            message = container.tab_service.build_tab_closed_message(tab.tab_id, "session_ended")
            await container.connection_registry.broadcast(user_id, message)

    container.session_service.set_on_session_destroyed(on_session_destroyed)

    await container.session_service.start()

    logger.info("Porterminal server started")

    yield

    # Shutdown
    await container.session_service.stop()
    logger.info("Porterminal server stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Porterminal",
        description="Web-based terminal accessible from phone via Cloudflare Tunnel",
        version=__version__,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def no_cache_static_assets(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Disable caching for static assets to ensure live updates during development."""
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Serve the main page."""
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            content = index_path.read_text(encoding="utf-8")
            return HTMLResponse(
                content=content,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        return JSONResponse(
            {"error": "index.html not found"},
            status_code=404,
        )

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        container: Container = app.state.container
        return {
            "status": "healthy",
            "sessions": container.session_service.session_count(),
            "tabs": container.tab_service.tab_count(),
            "connections": container.connection_registry.total_connections(),
        }

    @app.get("/api/tabs")
    async def list_tabs(request: Request):
        """List all tabs for the current user."""
        container: Container = app.state.container
        user_id = UserId(request.headers.get("cf-access-authenticated-user-email", "local-user"))
        tabs = container.tab_service.get_user_tabs(user_id)
        return {
            "tabs": [tab.to_dict() for tab in tabs],
        }

    @app.get("/api/config")
    async def get_client_config():
        """Get client configuration (shells and buttons)."""
        container: Container = app.state.container
        return {
            "shells": [{"id": s.id, "name": s.name} for s in container.available_shells],
            "buttons": container.buttons,
            "default_shell": container.default_shell_id,
        }

    @app.post("/api/config/reload")
    async def reload_configuration():
        """Reload configuration from file.

        Note: With the new DI architecture, hot-reload requires server restart.
        """
        return JSONResponse(
            {"status": "info", "message": "Config reload requires server restart"},
            status_code=501,
        )

    @app.post("/api/shutdown")
    async def shutdown_server(request: Request):
        """Shutdown the server and tunnel.

        Allowed from:
        - Localhost (direct access)
        - Cloudflare Tunnel (cf-ray header present)
        - Cloudflare Access authenticated users
        """
        # Check if request is from localhost
        client_host = request.client.host if request.client else None
        is_localhost = client_host in ("127.0.0.1", "::1", "localhost")

        # Check for Cloudflare Tunnel (has cf-ray header)
        is_cloudflare_tunnel = request.headers.get("cf-ray") is not None

        # Check for Cloudflare Access authentication
        cf_user = request.headers.get("cf-access-authenticated-user-email")

        if not is_localhost and not is_cloudflare_tunnel and not cf_user:
            logger.warning(
                "Unauthorized shutdown attempt from %s",
                client_host,
            )
            return JSONResponse(
                {"error": "Unauthorized - must be localhost or via Cloudflare Tunnel"},
                status_code=403,
            )

        source = cf_user or ("tunnel" if is_cloudflare_tunnel else client_host)
        logger.info("Shutdown requested via API by %s", source)

        # Send response before shutting down
        asyncio.get_running_loop().call_later(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM))

        return {"status": "ok", "message": "Server shutting down..."}

    @app.websocket("/ws/management")
    async def websocket_management(websocket: WebSocket):
        """Management WebSocket for tab operations and state sync.

        This is the control plane for tab management. Clients send requests
        (create_tab, close_tab, rename_tab) and receive responses + state updates.
        """
        await websocket.accept()

        container: Container = websocket.app.state.container
        management_service = container.management_service
        connection_registry = container.connection_registry

        # Get user ID from headers (Cloudflare Access)
        user_id = UserId(websocket.headers.get("cf-access-authenticated-user-email", "local-user"))
        connection = FastAPIWebSocketAdapter(websocket)

        logger.info(
            "Management WebSocket connected client=%s user_id=%s",
            getattr(websocket.client, "host", None),
            user_id,
        )

        try:
            # Authentication phase if password is set
            if container.password_hash is not None:
                authenticated = await authenticate_connection(
                    connection,
                    container.password_hash,
                    max_attempts=container.max_auth_attempts,
                )
                if not authenticated:
                    await websocket.close(code=4001, reason="Auth failed")
                    return

            # Register for broadcasts
            await connection_registry.register(user_id, connection)

            # Send initial state sync
            state_sync = management_service.build_state_sync(user_id)
            await connection.send_message(state_sync)

            # Handle messages
            while connection.is_connected():
                try:
                    message = await connection.receive()
                    if isinstance(message, dict):
                        await management_service.handle_message(user_id, connection, message)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.warning("Management message error: %s", e)
                    break

        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Management WebSocket error user_id=%s", user_id)
        finally:
            await connection_registry.unregister(user_id, connection)
            logger.info("Management WebSocket disconnected user_id=%s", user_id)

    @app.websocket("/ws")
    async def websocket_terminal(
        websocket: WebSocket,
        skip_buffer: str | None = Query(None),
        tab_id: str | None = Query(None),
    ):
        """WebSocket endpoint for terminal I/O only.

        This endpoint REQUIRES a valid tab_id. Tabs must be created via
        /ws/management first. This endpoint only handles terminal I/O
        for existing tabs.
        """
        logger.info(
            "WebSocket connect attempt client=%s tab_id=%s",
            getattr(websocket.client, "host", None),
            tab_id,
        )

        # Get dependencies from container
        container: Container = websocket.app.state.container
        session_service = container.session_service
        tab_service = container.tab_service
        terminal_service = container.terminal_service
        connection_registry = container.connection_registry

        # Get user ID from headers (Cloudflare Access)
        user_id = UserId(websocket.headers.get("cf-access-authenticated-user-email", "local-user"))

        # Validate tab_id is provided
        if not tab_id:
            logger.warning("WebSocket rejected - no tab_id provided user_id=%s", user_id)
            await websocket.close(code=4000, reason="tab_id required")
            return

        # Validate tab exists and belongs to user
        tab = tab_service.get_tab(tab_id)
        if not tab or str(tab.user_id) != str(user_id):
            logger.warning(
                "WebSocket rejected - tab not found or unauthorized user_id=%s tab_id=%s",
                user_id,
                tab_id,
            )
            await websocket.close(code=4004, reason="Tab not found")
            return

        # Get the session for this tab
        session = await session_service.reconnect_session(tab.session_id, user_id)
        if not session:
            # Session died - close tab and reject connection
            logger.warning(
                "WebSocket rejected - session ended user_id=%s tab_id=%s session_id=%s",
                user_id,
                tab_id,
                tab.session_id,
            )
            closed_tab = tab_service.close_tab(tab_id, user_id)
            if closed_tab:
                # Accept briefly to send error, then close
                await websocket.accept()
                connection = FastAPIWebSocketAdapter(websocket)
                await connection_registry.register(user_id, connection)
                await connection_registry.broadcast(
                    user_id,
                    tab_service.build_tab_closed_message(tab_id, "session_ended"),
                )
                await connection_registry.unregister(user_id, connection)
            await websocket.close(code=4005, reason="Session ended")
            return

        # Accept the connection
        await websocket.accept()
        connection = FastAPIWebSocketAdapter(websocket)

        logger.info(
            "WebSocket accepted client=%s user_id=%s tab_id=%s session_id=%s",
            getattr(websocket.client, "host", None),
            user_id,
            tab_id,
            session.session_id,
        )

        # Authentication check if password is set
        if container.password_hash is not None:
            if not await validate_auth_message(connection, container.password_hash):
                logger.warning("Terminal WebSocket auth failed user_id=%s", user_id)
                await websocket.close(code=4001, reason="Auth failed")
                return

        # Update tab access time
        tab_service.touch_tab(tab_id, user_id)

        try:
            # Register connection for broadcasts
            await connection_registry.register(user_id, connection)

            # Send session info including current dimensions
            # New clients should adapt to existing dimensions to prevent rendering issues
            await connection.send_message(
                {
                    "type": "session_info",
                    "session_id": session.session_id,
                    "shell": session.shell_id,
                    "tab_id": tab.tab_id,
                    "cols": session.dimensions.cols,
                    "rows": session.dimensions.rows,
                }
            )

            # Handle terminal I/O
            await terminal_service.handle_session(
                session, connection, skip_buffer=bool(skip_buffer)
            )

        except WebSocketDisconnect:
            logger.info("Client disconnected user_id=%s tab_id=%s", user_id, tab_id)

        except Exception:
            logger.exception("WebSocket error user_id=%s tab_id=%s", user_id, tab_id)
            with suppress(Exception):
                await connection.close(code=1011)
        finally:
            # Unregister connection
            await connection_registry.unregister(user_id, connection)

            if session:
                session_service.disconnect_session(session.id)
            logger.info(
                "WebSocket handler finished user_id=%s tab_id=%s session_id=%s",
                user_id,
                tab_id,
                session.session_id if session else None,
            )

    return app


# Create the app instance
app = create_app()
