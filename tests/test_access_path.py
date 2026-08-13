"""Security contract for the per-launch capability path."""

import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from porterminal.access_path import (
    AccessPathMiddleware,
    access_path,
    build_access_url,
    generate_access_code,
    validate_access_code,
)
from porterminal.app import create_app
from porterminal.asgi import create_app_from_env
from porterminal.composition import create_container

ACCESS_CODE = "AccessCode_1234567890"
PREFIX = f"/{ACCESS_CODE}"


def test_application_factory_requires_a_valid_access_code():
    untyped_factory: Any = create_app

    with pytest.raises(TypeError, match="access_code"):
        untyped_factory()
    with pytest.raises(ValueError, match="Access code"):
        create_app(access_code="short")


def test_environment_factory_fails_closed_without_a_valid_access_code(monkeypatch):
    monkeypatch.delenv("PORTERMINAL_ACCESS_CODE", raising=False)
    with pytest.raises(RuntimeError, match="Missing per-launch access code"):
        create_app_from_env()

    monkeypatch.setenv("PORTERMINAL_ACCESS_CODE", "short")
    with pytest.raises(ValueError, match="Access code"):
        create_app_from_env()


def test_generated_access_codes_are_random_url_safe_128_bit_values():
    first = generate_access_code()
    second = generate_access_code()

    assert first != second
    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", first)
    assert validate_access_code(first) == first
    assert access_path(first) == f"/{first}"
    assert build_access_url("https://example.test/", first) == f"https://example.test/{first}/"


@pytest.mark.parametrize(
    "value",
    ["short", "contains/slash_123456", "contains space 123456", "a" * 129],
)
def test_invalid_access_codes_are_rejected(value):
    with pytest.raises(ValueError, match="Access code"):
        validate_access_code(value)


@pytest.mark.asyncio
async def test_only_the_exact_access_prefix_reaches_http_routes(tmp_path):
    container = create_container(config_path=tmp_path / "missing.yaml")
    app = create_app(container, access_code=ACCESS_CODE)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://tunnel.test",
        follow_redirects=False,
    ) as client:
        rejected = [
            await client.get("/"),
            await client.get("/health"),
            await client.get("/api/config"),
            await client.get("/mcp"),
            await client.get("/WrongAccessCode_123456/health"),
            await client.get(f"/{ACCESS_CODE}extra/health"),
        ]
        redirect = await client.get(PREFIX, params={"from": "qr"})
        index = await client.get(f"{PREFIX}/")
        health = await client.get(f"{PREFIX}/health")
        static = await client.get(f"{PREFIX}/static/icon.svg")
        descriptor = await client.get(
            f"{PREFIX}/.well-known/mcp.json",
            headers={"cf-ray": "test"},
        )

    assert [response.status_code for response in rejected] == [404] * len(rejected)
    assert all(response.headers["cache-control"] == "no-store" for response in rejected)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == f"{PREFIX}/?from=qr"

    assert index.status_code == 200
    assert f'<meta name="porterminal-base-path" content="{PREFIX}">' in index.text
    assert index.text.count('meta name="porterminal-base-path"') == 1
    assert f'href="{PREFIX}/static/icon.svg"' in index.text
    assert f'src="{PREFIX}/static/assets/' in index.text
    assert f"<{PREFIX}/llms.txt>" in index.headers["link"]
    assert index.headers["referrer-policy"] == "no-referrer"
    assert index.headers["x-content-type-options"] == "nosniff"

    assert health.json()["status"] == "healthy"
    assert static.status_code == 200
    assert descriptor.json()["remotes"] == [
        {"type": "streamable-http", "url": f"http://tunnel.test{PREFIX}/mcp"}
    ]


@pytest.mark.asyncio
async def test_discovery_does_not_send_the_access_path_to_an_untrusted_host(tmp_path):
    container = create_container(config_path=tmp_path / "missing.yaml")
    app = create_app(container, access_code=ACCESS_CODE)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 4567))

    async with httpx.AsyncClient(transport=transport, base_url="http://origin.test") as client:
        local = await client.get(
            f"{PREFIX}/.well-known/mcp.json",
            headers={"host": "attacker.example"},
        )
        tunnel = await client.get(
            f"{PREFIX}/.well-known/mcp.json",
            headers={
                "host": "known-subdomain.trycloudflare.com",
                "cf-ray": "trusted-edge-marker",
            },
        )

    local_url = local.json()["remotes"][0]["url"]
    tunnel_url = tunnel.json()["remotes"][0]["url"]
    assert local_url == f"http://origin.test{PREFIX}/mcp"
    assert "attacker.example" not in local_url
    assert tunnel_url == f"https://known-subdomain.trycloudflare.com{PREFIX}/mcp"


@pytest.mark.asyncio
async def test_discovery_preserves_a_loopback_listener_port(tmp_path):
    container = create_container(config_path=tmp_path / "missing.yaml")
    app = create_app(container, access_code=ACCESS_CODE)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8123",
    ) as client:
        descriptor = await client.get(f"{PREFIX}/.well-known/mcp.json")

    assert descriptor.json()["remotes"] == [
        {"type": "streamable-http", "url": f"http://127.0.0.1:8123{PREFIX}/mcp"}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "q=a+b",
        "next=https://example.test/a:b/c%2Fd?x=1%26y=two+words",
    ],
)
async def test_access_prefix_redirect_preserves_query_octets_and_semantics(query):
    async def wrapped(_scope, _receive, _send):
        raise AssertionError("The exact prefix should redirect before reaching the app")

    transport = httpx.ASGITransport(app=AccessPathMiddleware(wrapped, ACCESS_CODE))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://tunnel.test",
        follow_redirects=False,
    ) as client:
        response = await client.get(f"{PREFIX}?{query}")

    location = response.headers["location"]
    assert response.status_code == 307
    assert location == f"{PREFIX}/?{query}"
    assert parse_qs(urlsplit(location).query) == parse_qs(query)


@pytest.mark.asyncio
async def test_access_prefix_redirect_quotes_header_unsafe_query_bytes():
    sent = []

    async def wrapped(_scope, _receive, _send):
        raise AssertionError("The exact prefix should redirect before reaching the app")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = AccessPathMiddleware(wrapped, ACCESS_CODE)
    await middleware(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": PREFIX,
            "raw_path": PREFIX.encode("ascii"),
            "query_string": b"q=safe\r\nX-Injected:true",
            "root_path": "",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        },
        receive,
        send,
    )

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    headers = dict(response_start["headers"])
    assert headers[b"location"] == f"{PREFIX}/?q=safe%0D%0AX-Injected:true".encode()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_query"),
    [
        (b"q=\xc3\xa9", b"q=%C3%A9"),
        (b"q=\xff", b"q=%FF"),
        (b"q=a#fragment-like", b"q=a%23fragment-like"),
    ],
)
async def test_access_prefix_redirect_preserves_arbitrary_query_octets(
    query,
    expected_query,
):
    sent = []

    async def wrapped(_scope, _receive, _send):
        raise AssertionError("The exact prefix should redirect before reaching the app")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = AccessPathMiddleware(wrapped, ACCESS_CODE)
    await middleware(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": PREFIX,
            "raw_path": PREFIX.encode("ascii"),
            "query_string": query,
            "root_path": "",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        },
        receive,
        send,
    )

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    headers = dict(response_start["headers"])
    assert headers[b"location"] == f"{PREFIX}/?".encode() + expected_query


@pytest.mark.asyncio
async def test_wrong_websocket_path_is_closed_before_the_application():
    captured_scopes = []
    sent = []

    async def wrapped(scope, _receive, _send):
        captured_scopes.append(scope)

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    middleware = AccessPathMiddleware(wrapped, ACCESS_CODE)

    await middleware(
        {"type": "websocket", "path": "/ws", "root_path": ""},
        receive,
        send,
    )
    assert captured_scopes == []
    assert sent == [{"type": "websocket.close", "code": 1008}]

    sent.clear()
    await middleware(
        {"type": "websocket", "path": f"{PREFIX}/ws", "root_path": ""},
        receive,
        send,
    )
    assert sent == []
    assert captured_scopes[0]["root_path"] == PREFIX


def test_protected_management_websocket_reaches_the_real_route(tmp_path):
    container = create_container(config_path=tmp_path / "missing.yaml")
    app = create_app(container, access_code=ACCESS_CODE)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect("/ws/management"):
                pass
        assert rejected.value.code == 1008

        with client.websocket_connect(f"{PREFIX}/ws/management") as websocket:
            assert websocket.receive_json() == {"type": "tab_state_sync", "tabs": []}
