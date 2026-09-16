"""MCP-only mode exposes no browser or REST terminal access."""

import sys
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from rich.text import Text
from starlette.websockets import WebSocketDisconnect

from porterminal.app import create_app
from porterminal.asgi import create_app_from_env
from porterminal.cli import display
from porterminal.cli import main as cli_main
from porterminal.cli.args import Args, parse_args
from porterminal.cli.clipboard import CopyResult
from porterminal.cli.share import build_agent_share_text

CODE = "McpOnlyAccess_12345678"
PREFIX = f"/{CODE}"


async def test_only_mcp_and_discovery_routes_are_available():
    app = create_app(access_code=CODE, mcp_only=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        for method, path in [
            ("GET", "/"),
            ("GET", "/static/index.html"),
            ("GET", "/api/tabs"),
            ("GET", "/api/config"),
            ("GET", "/api/settings"),
            ("POST", "/api/agent/run"),
            ("GET", "/api/agent/screen"),
            ("POST", "/api/agent/keys"),
            ("POST", "/api/agent/signal"),
            ("DELETE", "/api/agent/session"),
            ("GET", "/docs"),
            ("GET", "/redoc"),
            ("GET", "/openapi.json"),
        ]:
            response = await client.request(method, PREFIX + path)
            assert response.status_code == 404, path
        discovery = await client.get(PREFIX + "/.well-known/mcp.json")
        assert discovery.status_code == 200
        assert discovery.json()["remotes"][0]["url"].endswith(PREFIX + "/mcp")
        instructions = await client.get(PREFIX + "/llms.txt")
        assert instructions.status_code == 200
        assert "MCP-only mode" in instructions.text
        assert "/api/agent" not in instructions.text
        assert (await client.get("/llms.txt")).status_code == 404

    with TestClient(app) as client:
        assert client.get(PREFIX + "/health").status_code == 200
        for path in ["/ws", "/ws/management"]:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(PREFIX + path):
                    pytest.fail("Browser WebSocket accepted in MCP-only mode")


def test_mcp_only_cli_and_environment(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ptn", "--mcp-only"])
    args = parse_args()
    assert args.mcp_only
    monkeypatch.setenv("PORTERMINAL_ACCESS_CODE", CODE)
    monkeypatch.setenv("PORTERMINAL_MCP_ONLY", "true")
    assert create_app_from_env().state.mcp_only is True


@pytest.mark.parametrize("show_url", [True, False])
def test_mcp_only_never_generates_qr(monkeypatch, show_url):
    qr = Mock(side_effect=AssertionError("QR generation must be skipped"))
    monkeypatch.setattr(display, "get_qr_code", qr)
    monkeypatch.setattr(display, "get_qr_placeholder", qr)
    with display.console.capture() as capture:
        display.display_startup_screen("http://localhost/secret", mcp_only=True, show_url=show_url)
    assert "http://localhost/secret/mcp" in capture.get()
    qr.assert_not_called()


def test_mcp_only_share_text():
    text = build_agent_share_text("http://localhost/secret/", mcp_only=True)
    assert "http://localhost/secret/mcp" in text
    assert "/api/agent" not in text
    assert "visible terminal" not in text


def test_copy_prompt_failure_displays_usable_mcp_endpoint(monkeypatch):
    runtime = cli_main._Runtime(None, None, "http://localhost", "http://localhost/secret/", ".")
    state = cli_main._ForegroundState()
    monkeypatch.setattr(cli_main, "copy_to_clipboard", lambda _text: CopyResult.UNAVAILABLE)
    cli_main._copy_share_text(runtime, state, mcp_only=True)
    assert "http://localhost/secret/mcp" in state.copy_feedback
    assert state.copy_requested.is_set()


@pytest.mark.parametrize("no_tunnel", [False, True])
def test_local_ui_keeps_copy_keys_available(monkeypatch, no_tunnel):
    args = Args(mcp_only=True, no_tunnel=no_tunnel)
    runtime = cli_main._Runtime(None, None, "http://localhost", "http://localhost/secret/", ".")
    state = cli_main._ForegroundState()
    listener = Mock()
    clipboard = Mock(return_value=CopyResult.COPIED)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_main, "start_key_listener", listener)
    monkeypatch.setattr(cli_main, "copy_to_clipboard", clipboard)

    cli_main._start_interactive_listener(runtime, args, state)
    keys = listener.call_args.args[1]
    keys["c"]()
    prompt = clipboard.call_args.args[0]
    assert "Agent instructions:" in prompt
    assert "http://localhost/secret/mcp" in prompt
    keys["u"]()
    clipboard.assert_called_with("http://localhost/secret/mcp")
    keys["s"]()
    assert state.prompt_visible is True
    keys["q"]()
    assert state.prompt_visible is False

    with display.console.capture() as capture:
        cli_main._redraw(runtime, args, True, state.copy_feedback)
    screen = Text.from_ansi(capture.get()).plain
    assert "Press 'c':" in screen
    assert "Press 'u':" in screen
    assert "Press 's':" in screen
    assert "URL copied" in screen
    assert "http://localhost" not in screen
