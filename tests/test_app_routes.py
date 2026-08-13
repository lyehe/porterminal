"""Characterization tests for the application's public route contract."""

import asyncio
import threading
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import porterminal.app as app_module
from porterminal.app import create_app
from porterminal.composition import create_container
from porterminal.container import Container
from porterminal.infrastructure.web.routes import settings as settings_routes
from porterminal.infrastructure.web.routes import websocket_router

ACCESS_CODE = "RouteContract_123456"
PREFIX = f"/{ACCESS_CODE}"


def _create_app(container: Container | None = None):
    return create_app(container, access_code=ACCESS_CODE)


def _protected(path: str) -> str:
    return f"{PREFIX}{path}"


def test_public_route_inventory_is_stable():
    app = _create_app()
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


def test_state_changing_request_schemas_are_strict_and_non_nullable():
    schemas = _create_app().openapi()["components"]["schemas"]

    expected_properties = {
        "SettingsUpdateRequest": {
            "compose_mode": "boolean",
            "notify_on_startup": "boolean",
        },
        "ButtonCreateRequest": {
            "label": "string",
            "send": "string",
            "row": "integer",
        },
        "PasswordSetRequest": {"password": "string"},
        "PasswordRequirementRequest": {"require": "boolean"},
    }

    for schema_name, properties in expected_properties.items():
        schema = schemas[schema_name]
        assert schema["additionalProperties"] is False
        assert {
            field_name: schema["properties"][field_name]["type"] for field_name in properties
        } == properties


@pytest.mark.asyncio
async def test_discovery_health_and_validation_responses(tmp_path):
    container = create_container(config_path=tmp_path / "missing.yaml")
    app = _create_app(container)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://tunnel.test") as client:
        index = await client.get(_protected("/"))
        descriptor = await client.get(
            _protected("/.well-known/mcp.json"),
            headers={"cf-ray": "test"},
        )
        health = await client.get(_protected("/health"))
        invalid_session = await client.get(
            _protected("/api/agent/screen"),
            params={"session_id": "made-up"},
        )
        reload_response = await client.post(_protected("/api/config/reload"))

    assert index.status_code == 200
    assert f"<{PREFIX}/llms.txt>" in index.headers["link"]
    assert descriptor.json()["remotes"] == [
        {"type": "streamable-http", "url": f"http://tunnel.test{PREFIX}/mcp"}
    ]
    assert health.json() == {"status": "healthy", "sessions": 0, "tabs": 0, "connections": 0}
    assert invalid_session.status_code == 400
    assert reload_response.status_code == 501


@pytest.mark.asyncio
async def test_config_route_preserves_update_response_contract(tmp_path, monkeypatch):
    container = create_container(config_path=tmp_path / "missing.yaml")
    app = _create_app(container)
    transport = httpx.ASGITransport(app=app)
    monkeypatch.setattr(
        settings_routes,
        "check_for_updates",
        lambda *, use_cache: (use_cache, "9.9.9"),
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(_protected("/api/config"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["update_available"] is True
    assert payload["latest_version"] == "9.9.9"
    assert payload["upgrade_command"]


@pytest.mark.asyncio
async def test_config_route_does_not_block_event_loop_during_update_check(
    tmp_path,
    monkeypatch,
):
    container = create_container(config_path=tmp_path / "missing.yaml")
    app = _create_app(container)
    transport = httpx.ASGITransport(app=app)
    started = threading.Event()
    release = threading.Event()

    def slow_update_check(*, use_cache):
        assert use_cache is True
        started.set()
        assert release.wait(timeout=2)
        return False, None

    monkeypatch.setattr(settings_routes, "check_for_updates", slow_update_check)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        request = asyncio.create_task(client.get(_protected("/api/config")))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            await asyncio.sleep(0)
            assert not request.done()
        finally:
            release.set()
        response = await request

    assert response.status_code == 200
    assert response.json()["update_available"] is False


@pytest.mark.asyncio
async def test_settings_routes_reject_malformed_and_coercive_json(tmp_path):
    container = create_container(config_path=tmp_path / "settings.yaml")
    app = _create_app(container)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    cases = [
        ("/api/settings", []),
        ("/api/settings", {"compose_mode": "false"}),
        ("/api/settings", {"compose_mode": None}),
        ("/api/settings", {"unknown": True}),
        ("/api/buttons", 1),
        ("/api/buttons", {}),
        ("/api/buttons", {"label": "Run", "send": "echo ok", "row": True}),
        ("/api/password", []),
        ("/api/password", {}),
        ("/api/password/require", {}),
        ("/api/password/require", {"require": "false"}),
    ]

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [await client.post(_protected(path), json=body) for path, body in cases]
        responses.append(
            await client.post(
                _protected("/api/settings"),
                content="{",
                headers={"content-type": "application/json"},
            )
        )

    assert [response.status_code for response in responses] == [422] * len(responses)
    assert all("detail" in response.json() for response in responses)


@pytest.mark.asyncio
async def test_settings_routes_preserve_valid_boolean_values(tmp_path):
    container = create_container(config_path=tmp_path / "settings.yaml")
    app = _create_app(container)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        enabled = await client.post(
            _protected("/api/settings"),
            json={"compose_mode": True, "notify_on_startup": False},
        )
        disabled = await client.post(
            _protected("/api/settings"),
            json={"compose_mode": False},
        )
        unchanged = await client.post(_protected("/api/settings"), json={})

    assert enabled.status_code == 200
    assert enabled.json()["settings"]["notify_on_startup"] is False
    assert disabled.status_code == 200
    assert disabled.json()["settings"]["compose_mode"] is False
    assert unchanged.status_code == 200
    assert unchanged.json()["settings"]["compose_mode"] is False


@pytest.mark.asyncio
async def test_shutdown_rejects_spoofed_cloudflare_headers_from_remote_peer(
    tmp_path,
    monkeypatch,
):
    container = create_container(config_path=tmp_path / "settings.yaml")
    app = _create_app(container)
    scheduled = MagicMock()
    monkeypatch.setattr(settings_routes, "_schedule_shutdown", scheduled)
    remote = httpx.ASGITransport(app=app, client=("203.0.113.10", 4567))

    async with httpx.AsyncClient(transport=remote, base_url="http://test") as client:
        response = await client.post(
            _protected("/api/shutdown"),
            headers={
                "cf-ray": "spoofed",
                "cf-access-authenticated-user-email": "attacker@example.test",
                "x-forwarded-for": "127.0.0.1",
            },
        )

    assert response.status_code == 403
    scheduled.assert_not_called()


@pytest.mark.asyncio
async def test_shutdown_allows_a_direct_loopback_peer(tmp_path, monkeypatch):
    container = create_container(config_path=tmp_path / "settings.yaml")
    app = _create_app(container)
    scheduled = MagicMock()
    monkeypatch.setattr(settings_routes, "_schedule_shutdown", scheduled)
    loopback = httpx.ASGITransport(app=app, client=("127.0.0.1", 4567))

    async with httpx.AsyncClient(transport=loopback, base_url="http://test") as client:
        response = await client.post(_protected("/api/shutdown"))

    assert response.status_code == 200
    scheduled.assert_called_once_with()


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
    app = _create_app(cast(Container, container))

    with pytest.raises(RuntimeError, match="startup failed"):
        async with app.router.lifespan_context(app):
            pass

    container.agent_terminal_service.shutdown.assert_awaited_once()
    container.session_service.stop.assert_awaited_once()
