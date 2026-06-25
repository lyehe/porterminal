"""End-to-end test: a real MCP client drives a real terminal over /mcp.

Spins up the actual FastAPI app under uvicorn (so the MCP session manager
runs and the agent service is bound exactly as in production), then connects
with the official MCP client and exercises the four tools against a live PTY.
No mocks - this is the agent-in-the-loop path.
"""

import asyncio
import json
import socket
import threading
import uuid

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from porterminal.app import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _payload(result) -> dict:
    """Extract the tool's dict result across SDK result shapes."""
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        return sc.get("result", sc)
    for c in getattr(result, "content", []) or []:
        text = getattr(c, "text", None)
        if text:
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                return {"output": text}
    return {}


@pytest.fixture
async def mcp_url():
    """Run the real app under uvicorn in a background thread; yield /mcp URL."""
    app = create_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:
        raise RuntimeError("uvicorn did not start")

    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


async def test_agent_discovers_tools_and_controls_terminal(mcp_url):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discovery: "find out the info from the URL"
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"run_command", "read_screen", "send_keys", "send_signal"} <= names

            # run_command round-trip against a real shell
            token = uuid.uuid4().hex[:8]
            res = await session.call_tool(
                "run_command", {"command": f"echo AGENT_OK_{token}", "timeout": 25}
            )
            data = _payload(res)
            assert data.get("status") == "completed", data
            assert data.get("exit_code") == 0, data
            assert f"AGENT_OK_{token}" in data.get("output", ""), data

            # read_screen returns clean text from the same live session
            screen = _payload(await session.call_tool("read_screen", {}))
            assert isinstance(screen.get("screen"), str)
            assert f"AGENT_OK_{token}" in screen["screen"], screen

            # send_keys drives input; the typed text shows up on screen
            token2 = uuid.uuid4().hex[:8]
            await session.call_tool("send_keys", {"text": f"echo TYPED_{token2}\r"})
            await asyncio.sleep(1.0)
            screen2 = _payload(await session.call_tool("read_screen", {}))
            assert f"TYPED_{token2}" in screen2["screen"], screen2


async def test_run_command_reports_nonzero_exit(mcp_url):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # `exit 3` style differs per shell; use a portable failing command.
            res = await session.call_tool(
                "run_command", {"command": "cd __no_such_dir_ptn__", "timeout": 25}
            )
            data = _payload(res)
            assert data.get("status") == "completed", data
            assert data.get("exit_code") != 0, data


async def test_llms_txt_and_discovery_hints(mcp_url):
    base = mcp_url.removesuffix("/mcp")
    async with httpx.AsyncClient() as c:
        # /llms.txt advertises the MCP endpoint and all four tools.
        r = await c.get(f"{base}/llms.txt")
        assert r.status_code == 200
        assert "text/markdown" in r.headers.get("content-type", "")
        body = r.text
        assert "/mcp" in body
        for tool in ("run_command", "read_screen", "send_keys", "send_signal"):
            assert tool in body, f"missing tool in llms.txt: {tool}"

        # The base page points agents to /llms.txt + /mcp via a Link header,
        # while the human HTML body is still served unchanged.
        r2 = await c.get(f"{base}/")
        link = r2.headers.get("link", "")
        assert "/llms.txt" in link and "/mcp" in link, link
        assert "<!DOCTYPE html>" in r2.text or "<html" in r2.text


@pytest.fixture
async def base_url_fast(monkeypatch):
    """Same server, but with a 1s reaper so disconnect cleanup is testable."""
    monkeypatch.setenv("PORTERMINAL_AGENT_REAP_INTERVAL", "1")
    app = create_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:
        raise RuntimeError("uvicorn did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


async def test_agent_session_reaped_on_disconnect(base_url_fast):
    base = base_url_fast

    async def tab_count() -> int:
        async with httpx.AsyncClient() as c:
            return (await c.get(f"{base}/health")).json()["tabs"]

    # Connect, create an agent tab, confirm it exists.
    async with streamablehttp_client(f"{base}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("run_command", {"command": "echo hi", "timeout": 25})
            assert await tab_count() == 1

    # Client has now disconnected (context exit sends DELETE). The reaper
    # should notice the session left the transport and tear the tab down.
    for _ in range(30):
        if await tab_count() == 0:
            break
        await asyncio.sleep(0.5)
    assert await tab_count() == 0, "agent tab was not reaped after disconnect"


async def test_dead_shell_is_reaped_while_connected(base_url_fast):
    base = base_url_fast

    async def session_count() -> int:
        async with httpx.AsyncClient() as c:
            return (await c.get(f"{base}/health")).json()["sessions"]

    # Stay connected the whole time; the agent ends its own shell with `exit`.
    async with streamablehttp_client(f"{base}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("run_command", {"command": "echo hi", "timeout": 25})
            assert await session_count() == 1

            # Exit the shell from inside (no disconnect). The PTY dies; the
            # reaper should reap the dead-PTY session promptly.
            await session.call_tool("send_keys", {"text": "exit\r"})
            for _ in range(30):
                if await session_count() == 0:
                    break
                await asyncio.sleep(0.5)
            assert await session_count() == 0, "dead-PTY agent session was not reaped"
