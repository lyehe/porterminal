"""MCP adapter - exposes agent terminal control over Streamable HTTP.

Builds a FastMCP server with four tools that delegate to
``AgentTerminalService``. Mounted on the main FastAPI app at ``/mcp``.

Wiring notes (verified against mcp==1.28.x):
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

from mcp.server.fastmcp import Context, FastMCP

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "Control a real terminal on the user's machine. Prefer run_command for "
    "ordinary commands (it returns clean output and an exit code). If "
    "run_command returns status='waiting', the command is interactive: call "
    "read_screen to see the prompt, then send_keys to respond or send_signal "
    "to interrupt. Each connection has its own persistent shell."
)


class McpAdapter:
    """Holds the FastMCP server and a lazily-bound AgentTerminalService."""

    def __init__(self) -> None:
        self._service: Any | None = None
        self.mcp = FastMCP(
            name="porterminal",
            instructions=_INSTRUCTIONS,
            json_response=True,
            stateless_http=False,
            streamable_http_path="/",
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
        return self.mcp.streamable_http_app()

    @property
    def session_manager(self):
        return self.mcp.session_manager

    # ------------------------------------------------------------------

    def _require(self) -> Any:
        if self._service is None:
            raise RuntimeError("Agent terminal service not bound")
        return self._service

    @staticmethod
    def _sid(ctx: Context) -> str:
        req = getattr(ctx.request_context, "request", None)
        sid = req.headers.get("mcp-session-id") if req is not None else None
        return sid or f"mcp-{id(ctx.session)}"

    def _register_tools(self) -> None:
        mcp = self.mcp
        adapter = self

        @mcp.tool(
            description=(
                "Run a shell command in the agent's persistent terminal and "
                "return {output, exit_code, status}. status='completed' on "
                "success; status='waiting' means it didn't finish (likely an "
                "interactive prompt) - use read_screen / send_keys."
            )
        )
        async def run_command(ctx: Context, command: str, timeout: float = 30) -> dict:
            return await adapter._require().run_command(adapter._sid(ctx), command, timeout)

        @mcp.tool(
            description=(
                "Return the current terminal screen as clean text plus cursor "
                "position. Use for interactive prompts, REPLs, and TUIs."
            )
        )
        async def read_screen(ctx: Context) -> dict:
            return await adapter._require().read_screen(adapter._sid(ctx))

        @mcp.tool(
            description=(
                "Send raw keystrokes to the terminal (no automatic Enter; "
                "include '\\r' to submit). Use to answer prompts or drive TUIs."
            )
        )
        async def send_keys(ctx: Context, text: str) -> dict:
            return await adapter._require().send_keys(adapter._sid(ctx), text)

        @mcp.tool(description="Send a control signal: 'int' (Ctrl-C) or 'eof' (Ctrl-D).")
        async def send_signal(ctx: Context, signal: str) -> dict:
            return await adapter._require().send_signal(adapter._sid(ctx), signal)
