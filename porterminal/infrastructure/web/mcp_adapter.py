"""MCP adapter - exposes agent terminal control over Streamable HTTP.

Builds an MCP server with four tools that delegate to
``AgentTerminalService``. Mounted on the main FastAPI app at ``/mcp``.

Wiring notes (verified against mcp==2.x):
- ``streamable_http_app()`` returns a Starlette app to ``Mount("/mcp", ...)``;
  ``streamable_http_path="/"`` so the endpoint is exactly ``/mcp``.
- ``json_response=True`` -> request/response JSON (no long-lived SSE), which
  keeps it friendly to the Cloudflare Quick Tunnel.
- ``session_manager.run()`` MUST be entered inside the parent app's lifespan.
- The service is *bound at lifespan startup* (the mounted sub-app does not
  share the parent app's state, and the container is created in lifespan).
- The per-agent session id comes from the ``Mcp-Session-Id`` request header.
"""

import logging
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "Control a real terminal on the user's machine. Prefer run_command for "
    "ordinary commands (it returns clean output and an exit code). If "
    "run_command returns status='waiting', the command is interactive: call "
    "read_screen to see the prompt, then send_keys to respond or send_signal "
    "to interrupt. Each connection has its own persistent shell."
)

# Single source of truth for the agent tool descriptions. The @mcp.tool
# decorators below AND the /llms.txt discovery page both render from this, so
# what an agent reads at /llms.txt never drifts from what tools/list advertises.
AGENT_TOOLS: dict[str, str] = {
    "run_command": (
        "Run a shell command in the agent's persistent terminal and return "
        "{output, exit_code, status}. status='completed' on success; "
        "status='waiting' means it didn't finish (likely an interactive "
        "prompt) - use read_screen / send_keys."
    ),
    "read_screen": (
        "Return the current terminal screen as clean text plus cursor "
        "position. Use for interactive prompts, REPLs, and TUIs."
    ),
    "send_keys": (
        "Send raw keystrokes to the terminal (no automatic Enter; include "
        "'\\r' to submit). Use to answer prompts or drive TUIs."
    ),
    "send_signal": (
        "Send a control signal. 'int' (Ctrl-C) interrupts the running command. "
        "'eof' (Ctrl-D) ends input on POSIX shells but is a no-op on Windows."
    ),
}


class McpAdapter:
    """Holds the MCP server and a lazily-bound AgentTerminalService."""

    def __init__(self) -> None:
        self._service: Any | None = None
        self.mcp = MCPServer(
            name="porterminal",
            instructions=_INSTRUCTIONS,
        )
        self._register_tools()

    def bind(self, service: Any) -> None:
        """Bind the AgentTerminalService and give it a probe over the live MCP
        session ids, so it can reap sessions whose client has disconnected.

        Reads the transport's private session map (no public hook exists);
        a disconnected session lingers in the map but flips ``is_terminated``,
        so we treat only non-terminated sessions as live. Guarded so a future
        SDK rename degrades to idle-only reaping.
        """
        self._service = service

        def live_sessions() -> set[str]:
            instances = getattr(self.session_manager, "_server_instances", {}) or {}
            return {sid for sid, t in instances.items() if not getattr(t, "is_terminated", False)}

        service.bind_live_probe(live_sessions)

    def streamable_http_app(self):
        return self.mcp.streamable_http_app(
            streamable_http_path="/",
            json_response=True,
            stateless_http=False,
        )

    @property
    def session_manager(self):
        return self.mcp.session_manager

    @staticmethod
    def tool_summaries() -> list[tuple[str, str]]:
        """(name, description) for each agent tool — the same text tools/list
        advertises. Rendered into /llms.txt so discovery never drifts."""
        return list(AGENT_TOOLS.items())

    # ------------------------------------------------------------------

    def _require(self) -> Any:
        if self._service is None:
            raise RuntimeError("Agent terminal service not bound")
        return self._service

    @staticmethod
    def _sid(ctx: Context) -> str:
        headers = ctx.headers
        sid = headers.get("mcp-session-id") if headers is not None else None
        return sid or f"mcp-{id(ctx.session)}"

    def _register_tools(self) -> None:
        mcp = self.mcp
        adapter = self

        @mcp.tool(description=AGENT_TOOLS["run_command"])
        async def run_command(ctx: Context, command: str, timeout: float = 30) -> dict:
            return await adapter._require().run_command(adapter._sid(ctx), command, timeout)

        @mcp.tool(description=AGENT_TOOLS["read_screen"])
        async def read_screen(ctx: Context) -> dict:
            return await adapter._require().read_screen(adapter._sid(ctx))

        @mcp.tool(description=AGENT_TOOLS["send_keys"])
        async def send_keys(ctx: Context, text: str) -> dict:
            return await adapter._require().send_keys(adapter._sid(ctx), text)

        @mcp.tool(description=AGENT_TOOLS["send_signal"])
        async def send_signal(ctx: Context, signal: str) -> dict:
            return await adapter._require().send_signal(adapter._sid(ctx), signal)
