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
