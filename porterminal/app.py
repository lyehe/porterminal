"""FastAPI application composition and lifecycle."""

import ctypes
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from . import __version__
from .access_path import AccessPathMiddleware, route_path, validate_access_code
from .composition import create_container
from .container import Container
from .infrastructure.web import McpAdapter
from .infrastructure.web.routes import (
    STATIC_DIR,
    agent_router,
    discovery_router,
    settings_router,
    websocket_router,
)
from .logging_setup import setup_logging_from_env

logger = logging.getLogger(__name__)


def is_admin() -> bool:
    """Check whether the Windows process is elevated."""
    if sys.platform != "win32":
        return False
    try:
        windll = getattr(ctypes, "windll", None)
        return windll is not None and windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def security_preflight_checks() -> None:
    """Warn about unsafe process-level configuration."""
    if is_admin():
        logger.warning(
            "SECURITY WARNING: Running as Administrator is not recommended. "
            "This exposes excessive privileges to remote users."
        )


def _container_from_environment() -> Container:
    """Compose runtime dependencies from CLI-provided environment overrides."""
    password_hash = None
    if hash_string := os.environ.get("PORTERMINAL_PASSWORD_HASH"):
        password_hash = hash_string.encode()

    compose_mode_override = None
    if compose_string := os.environ.get("PORTERMINAL_COMPOSE_MODE"):
        compose_mode_override = compose_string.lower() == "true"

    return create_container(
        config_path=None,
        cwd=os.environ.get("PORTERMINAL_CWD"),
        password_hash=password_hash,
        compose_mode_override=compose_mode_override,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop session and MCP services as one lifecycle."""
    setup_logging_from_env()
    security_preflight_checks()

    container: Container | None = getattr(app.state, "container", None)
    if container is None:
        container = _container_from_environment()
        app.state.container = container

    async def on_session_destroyed(session_id, user_id):
        closed_tabs = container.tab_service.close_tabs_for_session(session_id)
        for tab in closed_tabs:
            message = container.tab_service.build_tab_closed_message(tab.tab_id, "session_ended")
            await container.connection_registry.broadcast(user_id, message)

    container.session_service.set_on_session_destroyed(on_session_destroyed)
    try:
        await container.session_service.start()
        mcp_adapter: McpAdapter = app.state.mcp_adapter
        mcp_adapter.bind(container.agent_terminal_service)
        try:
            await container.agent_terminal_service.start()
            async with mcp_adapter.session_manager.run():
                logger.info("Porterminal server started")
                yield
        finally:
            await container.agent_terminal_service.shutdown()
    finally:
        await container.session_service.stop()
        logger.info("Porterminal server stopped")


def create_app(
    container: Container | None = None,
    *,
    access_code: str,
) -> FastAPI:
    """Create the protected application and mount adapters and route groups."""
    access_code = validate_access_code(access_code)
    app = FastAPI(
        title="Porterminal",
        description="Web-based terminal accessible from phone via Cloudflare Tunnel",
        version=__version__,
        lifespan=lifespan,
    )
    if container is not None:
        app.state.container = container

    @app.middleware("http")
    async def no_cache_static_assets(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if route_path(request.scope).startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    mcp_adapter = McpAdapter()
    app.state.mcp_adapter = mcp_adapter
    app.mount("/mcp", mcp_adapter.streamable_http_app())

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.include_router(discovery_router)
    app.include_router(agent_router)
    app.include_router(settings_router)
    app.include_router(websocket_router)
    app.add_middleware(AccessPathMiddleware, access_code=access_code)
    return app
