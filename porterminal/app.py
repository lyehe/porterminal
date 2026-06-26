"""FastAPI application with security checks and WebSocket endpoint."""

import asyncio
import ctypes
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from . import __version__
from .composition import create_container
from .container import Container
from .domain import UserId
from .infrastructure.auth import authenticate_connection, validate_auth_message
from .infrastructure.web import FastAPIWebSocketAdapter, McpAdapter
from .logging_setup import setup_logging_from_env
from .updater import check_for_updates, get_upgrade_command

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

    # Get compose mode override from environment if set (CLI passes this)
    compose_mode_override = None
    if compose_str := os.environ.get("PORTERMINAL_COMPOSE_MODE"):
        compose_mode_override = compose_str.lower() == "true"

    container = create_container(
        config_path=None,
        cwd=cwd,
        password_hash=password_hash,
        compose_mode_override=compose_mode_override,
    )
    app.state.container = container

    # Wire up cascade: when session is destroyed, close associated tabs and broadcast
    async def on_session_destroyed(session_id, user_id):
        closed_tabs = container.tab_service.close_tabs_for_session(session_id)
        for tab in closed_tabs:
            message = container.tab_service.build_tab_closed_message(tab.tab_id, "session_ended")
            await container.connection_registry.broadcast(user_id, message)

    container.session_service.set_on_session_destroyed(on_session_destroyed)

    await container.session_service.start()

    # Wire up agent (MCP) access: bind the service to the adapter mounted in
    # create_app(), and run the MCP session manager for the app's lifetime
    # (required by the SDK - it is not started by FastAPI's Mount).
    mcp_adapter: McpAdapter = app.state.mcp_adapter
    mcp_adapter.bind(container.agent_terminal_service)
    await container.agent_terminal_service.start()

    async with mcp_adapter.session_manager.run():
        logger.info("Porterminal server started")

        yield

        # Shutdown
        await container.agent_terminal_service.shutdown()
        await container.session_service.stop()
        logger.info("Porterminal server stopped")


def _request_base_url(request: Request) -> str:
    """Best-effort absolute base URL from the request (tunnel-aware)."""
    host = request.headers.get("host") or request.url.netloc
    scheme = (
        "https"
        if request.headers.get("x-forwarded-proto") == "https" or request.headers.get("cf-ray")
        else request.url.scheme
    )
    return f"{scheme}://{host}"


class AgentRunRequest(BaseModel):
    command: str
    timeout: float = 30
    session_id: str | None = None


class AgentKeysRequest(BaseModel):
    session_id: str
    text: str


class AgentSignalRequest(BaseModel):
    session_id: str
    signal: str


def _new_rest_agent_session_id() -> str:
    return f"rest-{uuid.uuid4().hex}"


def _valid_rest_agent_session_id(session_id: str | None) -> bool:
    return bool(session_id and session_id.startswith("rest-"))


def _bad_agent_session_id() -> JSONResponse:
    return JSONResponse(
        {"error": "session_id must come from a prior REST agent API response"},
        status_code=400,
    )


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

    # Mount the agent (MCP) endpoint at /mcp. The adapter is stashed on app
    # state so the lifespan can run its session manager and bind the service
    # at startup (the container, and thus the service, is created in lifespan).
    mcp_adapter = McpAdapter()
    app.state.mcp_adapter = mcp_adapter
    app.mount("/mcp", mcp_adapter.streamable_http_app())

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
                    # Invisible to humans; points AI agents at machine-readable
                    # discovery (server.json), the usage page, and the MCP
                    # endpoint (the human UI is otherwise untouched).
                    "Link": (
                        '</.well-known/mcp.json>; rel="alternate"; type="application/json", '
                        '</llms.txt>; rel="alternate"; type="text/markdown", '
                        '</mcp>; rel="related", '
                        '</api/agent/run>; rel="related"'
                    ),
                },
            )
        return JSONResponse(
            {"error": "index.html not found"},
            status_code=404,
        )

    @app.get("/llms.txt", response_class=PlainTextResponse)
    async def llms_txt(request: Request):
        """Agent-facing usage instructions (the `llms.txt` convention).

        Invisible to humans (they get the UI at `/`); this tells an AI agent the
        host runs an MCP terminal and how to drive it. Public by design - the
        tunnel URL is the credential, and the endpoint path isn't sensitive.
        """
        base = _request_base_url(request)

        adapter: McpAdapter = app.state.mcp_adapter
        tools = "\n".join(f"- `{name}` - {desc}" for name, desc in adapter.tool_summaries())

        body = f"""# Porterminal - AI agent instructions

Porterminal is a terminal on this machine. A human uses the web UI at {base}/ ;
you (an AI agent) can control a real shell over MCP or the REST fallback API.

## Connect

MCP endpoint (Streamable HTTP): {base}/mcp
Machine-readable discovery: {base}/.well-known/mcp.json (MCP server.json)

Point any MCP client at that URL. Example client config:

    {{
      "mcpServers": {{
        "porterminal": {{ "url": "{base}/mcp" }}
      }}
    }}

After connecting, call `tools/list` to confirm the tools below.

## Tools

{tools}

Guidance: prefer `run_command` for ordinary commands (clean output + exit code).
If it returns `status: "waiting"`, the command is interactive - use `read_screen`
to see the prompt and `send_keys` / `send_signal` to drive it.

## REST fallback

Use this if your host cannot register/connect an MCP server but can make HTTP
requests. First call `run` without a session id; reuse the returned `session_id`
for subsequent calls:

    POST {base}/api/agent/run
    {{"command": "echo hello", "timeout": 30}}
    -> {{"session_id": "rest-...", "status": "completed", "exit_code": 0, "output": "hello"}}

    GET  {base}/api/agent/screen?session_id=rest-...
    POST {base}/api/agent/keys    {{"session_id": "rest-...", "text": "answer\\r"}}
    POST {base}/api/agent/signal  {{"session_id": "rest-...", "signal": "int"}}
    DELETE {base}/api/agent/session?session_id=rest-...

REST uses the same visible agent tab and shell backend as MCP. The `session_id`
must come from a prior REST response.

## Browser fallback

If your environment cannot use MCP or REST, open {base}/ in a browser. Read the
element named "Terminal screen", type commands into "Terminal input", and press
Enter. This fallback is less reliable, but it is intentionally exposed as
ordinary page text for browser-driving agents.

## Example

    run_command(command="echo hello")
    -> {{"status": "completed", "exit_code": 0, "output": "hello"}}

## Notes

- Each MCP or REST agent session gets its own persistent shell, shown as a tab
  the human can watch and take over. MCP sessions are cleaned up when you
  disconnect; REST sessions close on DELETE, shell exit, or idle cleanup.
- Security: the URL is the only credential - there is no extra auth, and the
  shell runs non-elevated (it can't install software that requires admin).
"""
        return PlainTextResponse(body, media_type="text/markdown; charset=utf-8")

    @app.get("/.well-known/mcp/server.json")
    @app.get("/.well-known/mcp.json")
    async def mcp_server_json(request: Request) -> dict:
        """MCP server descriptor (`server.json`) for client/agent auto-discovery.

        Follows the Model Context Protocol `server.json` schema used by the MCP
        Registry. Served at both `/.well-known/mcp/server.json` (as Replicate
        does) and `/.well-known/mcp.json`, because the well-known discovery path
        is still being finalized (SEPs #1649/#1960). Machine-readable companion
        to /llms.txt; a client that 404s here falls back to being handed /mcp.
        """
        base = _request_base_url(request)
        return {
            "$schema": (
                "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
            ),
            "name": "io.github.lyehe/porterminal",
            "title": "Porterminal",
            "description": (
                "Web terminal + MCP agent terminal on this machine, exposed via a Cloudflare tunnel."
            ),
            "version": __version__,
            "repository": {"url": "https://github.com/lyehe/porterminal", "source": "github"},
            "remotes": [{"type": "streamable-http", "url": f"{base}/mcp"}],
        }

    @app.post("/api/agent/run")
    async def agent_rest_run(body: AgentRunRequest):
        """Run a command through the REST fallback agent API.

        This is the low-friction path for agents that can make HTTP requests
        but cannot register/connect an MCP client. It reuses the same agent
        terminal service as /mcp, with server-minted REST session ids.
        """
        command = body.command.strip()
        if not command:
            return JSONResponse({"error": "command is required"}, status_code=400)

        session_id = body.session_id or _new_rest_agent_session_id()
        if not _valid_rest_agent_session_id(session_id):
            return _bad_agent_session_id()

        container: Container = app.state.container
        result = await container.agent_terminal_service.run_command(
            session_id,
            command,
            body.timeout,
            reap_on_disconnect=False,
        )
        return {"session_id": session_id, **result}

    @app.get("/api/agent/screen")
    async def agent_rest_screen(session_id: str = Query(...)):
        """Read the current rendered screen for a REST agent session."""
        if not _valid_rest_agent_session_id(session_id):
            return _bad_agent_session_id()

        container: Container = app.state.container
        result = await container.agent_terminal_service.read_screen(
            session_id,
            reap_on_disconnect=False,
        )
        return {"session_id": session_id, **result}

    @app.post("/api/agent/keys")
    async def agent_rest_keys(body: AgentKeysRequest):
        """Send raw keystrokes to a REST agent session."""
        if not _valid_rest_agent_session_id(body.session_id):
            return _bad_agent_session_id()

        container: Container = app.state.container
        result = await container.agent_terminal_service.send_keys(
            body.session_id,
            body.text,
            reap_on_disconnect=False,
        )
        return {"session_id": body.session_id, **result}

    @app.post("/api/agent/signal")
    async def agent_rest_signal(body: AgentSignalRequest):
        """Send a control signal to a REST agent session."""
        if not _valid_rest_agent_session_id(body.session_id):
            return _bad_agent_session_id()

        container: Container = app.state.container
        result = await container.agent_terminal_service.send_signal(
            body.session_id,
            body.signal,
            reap_on_disconnect=False,
        )
        return {"session_id": body.session_id, **result}

    @app.delete("/api/agent/session")
    async def agent_rest_close(session_id: str = Query(...)):
        """Close a REST agent session and its visible agent tab."""
        if not _valid_rest_agent_session_id(session_id):
            return _bad_agent_session_id()

        container: Container = app.state.container
        closed = await container.agent_terminal_service.close_session(session_id)
        return {"session_id": session_id, "closed": closed}

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
        """Get client configuration (shells, buttons, UI defaults, and version info)."""
        container: Container = app.state.container

        # Check for updates (uses cache, non-blocking)
        update_available, latest_version = check_for_updates(use_cache=True)

        # Get settings from config file (for notify_on_startup)
        settings = await container.config_service.get_settings()

        return {
            "shells": [{"id": s.id, "name": s.name} for s in container.available_shells],
            "buttons": container.buttons,
            "default_shell": container.default_shell_id,
            "compose_mode": container.compose_mode_default,
            "version": __version__,
            "update_available": update_available,
            "latest_version": latest_version,
            "upgrade_command": get_upgrade_command() if update_available else None,
            "password_protected": container.password_hash is not None,
            "notify_on_startup": settings.get("notify_on_startup", True),
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

    @app.get("/api/settings")
    async def get_settings():
        """Get current settings from config file."""
        container: Container = app.state.container
        settings = await container.config_service.get_settings()
        return settings

    @app.post("/api/settings")
    async def update_settings(request: Request):
        """Update settings in config file.

        Accepts JSON body with settings to update:
        - compose_mode: bool
        - notify_on_startup: bool

        Returns the updated settings and whether a restart is required.
        """
        container: Container = app.state.container
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "Invalid JSON body"},
                status_code=400,
            )

        # Validate that only allowed keys are present
        allowed_keys = {"compose_mode", "notify_on_startup"}
        invalid_keys = set(body.keys()) - allowed_keys
        if invalid_keys:
            return JSONResponse(
                {"error": f"Invalid settings keys: {invalid_keys}"},
                status_code=400,
            )

        settings, requires_restart = await container.config_service.update_settings(body)
        return {
            "settings": settings,
            "requires_restart": requires_restart,
        }

    @app.post("/api/buttons")
    async def add_button(request: Request):
        """Add a new button. Body: {label, send, row?}"""
        container: Container = app.state.container
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        label = body.get("label")
        send = body.get("send")
        row = body.get("row", 1)

        if not label or not send:
            return JSONResponse({"error": "label and send required"}, status_code=400)

        try:
            buttons = await container.config_service.add_button(label, send, row)
            return {"buttons": buttons}
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.delete("/api/buttons/{label:path}")
    async def remove_button(label: str):
        """Remove a button by label."""
        container: Container = app.state.container
        try:
            buttons = await container.config_service.remove_button(label)
            return {"buttons": buttons}
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=404)

    @app.get("/api/password")
    async def get_password_status():
        """Get password status.

        Returns:
        - password_saved: Whether a password is saved in config
        - require_password: Whether password is required at startup
        - currently_protected: Whether current session has password protection
        """
        container: Container = app.state.container
        status = await container.config_service.get_password_status()
        status["currently_protected"] = container.password_hash is not None
        return status

    @app.post("/api/password")
    async def set_password(request: Request):
        """Set or change password.

        Body: {password: string}

        Note: Requires server restart to take effect.
        """
        container: Container = app.state.container
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        password = body.get("password")
        if not password or not isinstance(password, str):
            return JSONResponse({"error": "password required"}, status_code=400)

        if len(password) < 1:
            return JSONResponse({"error": "password cannot be empty"}, status_code=400)

        settings = await container.config_service.set_password(password)
        return {
            "settings": settings,
            "requires_restart": True,
            "message": "Password saved. Restart server for changes to take effect.",
        }

    @app.delete("/api/password")
    async def clear_password():
        """Clear password and disable password requirement.

        Note: Requires server restart to take effect.
        """
        container: Container = app.state.container
        settings = await container.config_service.clear_password()
        return {
            "settings": settings,
            "requires_restart": True,
            "message": "Password cleared. Restart server for changes to take effect.",
        }

    @app.post("/api/password/require")
    async def set_require_password(request: Request):
        """Set whether password is required at startup.

        Body: {require: boolean}

        Note: Requires server restart to take effect.
        """
        container: Container = app.state.container
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        require = body.get("require")
        if require is None or not isinstance(require, bool):
            return JSONResponse({"error": "require (boolean) required"}, status_code=400)

        settings = await container.config_service.set_require_password(require)
        return {
            "settings": settings,
            "requires_restart": True,
            "message": f"Password requirement {'enabled' if require else 'disabled'}. "
            "Restart server for changes to take effect.",
        }

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

            # Signal first connection (for hiding QR code in CLI)
            # Use a marker that drain_process_output can detect
            if not hasattr(app.state, "_first_connection_signaled"):
                app.state._first_connection_signaled = True
                print("@@CONNECTED@@", flush=True)

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
