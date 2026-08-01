"""Browser configuration, settings, and administration routes."""

import asyncio
import logging
import os
import signal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from porterminal import __version__
from porterminal.domain import UserId
from porterminal.updater import check_for_updates, get_upgrade_command

from .common import get_container

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/tabs")
async def list_tabs(request: Request):
    """List all tabs for the current user."""
    container = get_container(request)
    user_id = UserId(request.headers.get("cf-access-authenticated-user-email", "local-user"))
    tabs = container.tab_service.get_user_tabs(user_id)
    return {"tabs": [tab.to_dict() for tab in tabs]}


@router.get("/api/config")
async def get_client_config(request: Request):
    """Get shells, buttons, UI defaults, and version information."""
    container = get_container(request)
    update_available, latest_version = check_for_updates(use_cache=True)
    settings = await container.config_service.get_settings()

    return {
        "shells": [{"id": shell.id, "name": shell.name} for shell in container.available_shells],
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


@router.post("/api/config/reload")
async def reload_configuration():
    """Explain that configuration reload currently requires restart."""
    return JSONResponse(
        {"status": "info", "message": "Config reload requires server restart"},
        status_code=501,
    )


@router.get("/api/settings")
async def get_settings(request: Request):
    """Get current settings from the config file."""
    return await get_container(request).config_service.get_settings()


@router.post("/api/settings")
async def update_settings(request: Request):
    """Update compose-mode and update-notification settings."""
    container = get_container(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    allowed_keys = {"compose_mode", "notify_on_startup"}
    invalid_keys = set(body.keys()) - allowed_keys
    if invalid_keys:
        return JSONResponse(
            {"error": f"Invalid settings keys: {invalid_keys}"},
            status_code=400,
        )

    settings, requires_restart = await container.config_service.update_settings(body)
    return {"settings": settings, "requires_restart": requires_restart}


@router.post("/api/buttons")
async def add_button(request: Request):
    """Add a custom terminal button."""
    container = get_container(request)
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
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)


@router.delete("/api/buttons/{label:path}")
async def remove_button(label: str, request: Request):
    """Remove a custom terminal button by label."""
    try:
        buttons = await get_container(request).config_service.remove_button(label)
        return {"buttons": buttons}
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=404)


@router.get("/api/password")
async def get_password_status(request: Request):
    """Get saved and active password status."""
    container = get_container(request)
    status = await container.config_service.get_password_status()
    status["currently_protected"] = container.password_hash is not None
    return status


@router.post("/api/password")
async def set_password(request: Request):
    """Save a password; restart is required before it becomes active."""
    container = get_container(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    password = body.get("password")
    if not password or not isinstance(password, str):
        return JSONResponse({"error": "password required"}, status_code=400)

    settings = await container.config_service.set_password(password)
    return {
        "settings": settings,
        "requires_restart": True,
        "message": "Password saved. Restart server for changes to take effect.",
    }


@router.delete("/api/password")
async def clear_password(request: Request):
    """Clear the saved password and disable the requirement."""
    settings = await get_container(request).config_service.clear_password()
    return {
        "settings": settings,
        "requires_restart": True,
        "message": "Password cleared. Restart server for changes to take effect.",
    }


@router.post("/api/password/require")
async def set_require_password(request: Request):
    """Persist whether startup should require a password."""
    container = get_container(request)
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


@router.post("/api/shutdown")
async def shutdown_server(request: Request):
    """Shut down when requested locally or through Cloudflare."""
    client_host = request.client.host if request.client else None
    is_localhost = client_host in ("127.0.0.1", "::1", "localhost")
    is_cloudflare_tunnel = request.headers.get("cf-ray") is not None
    cf_user = request.headers.get("cf-access-authenticated-user-email")

    if not is_localhost and not is_cloudflare_tunnel and not cf_user:
        logger.warning("Unauthorized shutdown attempt from %s", client_host)
        return JSONResponse(
            {"error": "Unauthorized - must be localhost or via Cloudflare Tunnel"},
            status_code=403,
        )

    source = cf_user or ("tunnel" if is_cloudflare_tunnel else client_host)
    logger.info("Shutdown requested via API by %s", source)
    asyncio.get_running_loop().call_later(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM))
    return {"status": "ok", "message": "Server shutting down..."}
