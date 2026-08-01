"""Characterization tests for the application's public route contract."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import porterminal.app as app_module
from porterminal.app import create_app
from porterminal.composition import create_container
from porterminal.container import Container
from porterminal.infrastructure.web.routes import websocket_router


def test_public_route_inventory_is_stable():
    app = create_app()
    operations = {
        (path, method.upper())
        for path, path_operations in app.openapi()["paths"].items()
        for method in path_operations
        if method.lower() in {"get", "post", "delete", "put", "patch"}
    }
    expected_operations = {
        ("/", "GET"),
        ("/llms.txt", "GET"),
        ("/.well-known/mcp.json", "GET"),
        ("/.well-known/mcp/server.json", "GET"),
        ("/health", "GET"),
        ("/api/agent/run", "POST"),
        ("/api/agent/screen", "GET"),
        ("/api/agent/keys", "POST"),
        ("/api/agent/signal", "POST"),
        ("/api/agent/session", "DELETE"),
        ("/api/tabs", "GET"),
        ("/api/config", "GET"),
        ("/api/config/reload", "POST"),
        ("/api/settings", "GET"),
        ("/api/settings", "POST"),
        ("/api/buttons", "POST"),
        ("/api/buttons/{label}", "DELETE"),
        ("/api/password", "GET"),
        ("/api/password", "POST"),
        ("/api/password", "DELETE"),
        ("/api/password/require", "POST"),
        ("/api/shutdown", "POST"),
    }
    mount_paths = {getattr(route, "path", None) for route in app.routes}
    websocket_paths = {route.path for route in websocket_router.routes}

    assert expected_operations <= operations
    assert {"/mcp", "/static"} <= mount_paths
    assert websocket_paths == {"/ws/management", "/ws"}


@pytest.mark.asyncio
async def test_discovery_health_and_validation_responses(tmp_path):
    container = create_container(config_path=tmp_path / "missing.yaml")
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://tunnel.test") as client:
        index = await client.get("/")
        descriptor = await client.get("/.well-known/mcp.json", headers={"cf-ray": "test"})
        health = await client.get("/health")
        invalid_session = await client.get(
            "/api/agent/screen",
            params={"session_id": "made-up"},
        )
        reload_response = await client.post("/api/config/reload")

    assert index.status_code == 200
    assert "</llms.txt>" in index.headers["link"]
    assert descriptor.json()["remotes"] == [
        {"type": "streamable-http", "url": "https://tunnel.test/mcp"}
    ]
    assert health.json() == {"status": "healthy", "sessions": 0, "tabs": 0, "connections": 0}
    assert invalid_session.status_code == 400
    assert reload_response.status_code == 501


def test_environment_composition_preserves_cli_overrides(monkeypatch):
    sentinel = cast(Container, object())
    captured: dict = {}

    def fake_create_container(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setenv("PORTERMINAL_CWD", "C:/terminal-work")
    monkeypatch.setenv("PORTERMINAL_PASSWORD_HASH", "saved-hash")
    monkeypatch.setenv("PORTERMINAL_COMPOSE_MODE", "true")
    monkeypatch.setattr(app_module, "create_container", fake_create_container)

    assert app_module._container_from_environment() is sentinel
    assert captured == {
        "config_path": None,
        "cwd": "C:/terminal-work",
        "password_hash": b"saved-hash",
        "compose_mode_override": True,
    }


@pytest.mark.asyncio
async def test_lifespan_unwinds_services_after_partial_startup_failure():
    container = MagicMock()
    container.session_service.start = AsyncMock()
    container.session_service.stop = AsyncMock()
    container.agent_terminal_service.start = AsyncMock(side_effect=RuntimeError("startup failed"))
    container.agent_terminal_service.shutdown = AsyncMock()
    app = create_app(cast(Container, container))

    with pytest.raises(RuntimeError, match="startup failed"):
        async with app.router.lifespan_context(app):
            pass

    container.agent_terminal_service.shutdown.assert_awaited_once()
    container.session_service.stop.assert_awaited_once()
