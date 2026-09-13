"""Helpers for sharing a Porterminal session URL."""

from __future__ import annotations


def _clean_base_url(url: str) -> str:
    """Return a base URL without trailing slashes."""
    return url.rstrip("/")


def build_agent_share_text(url: str, *, mcp_only: bool = False) -> str:
    """Build the text copied when sharing a tunnel URL with an AI agent.

    The base URL remains first-class for humans, while the MCP endpoint and
    /llms.txt instructions are explicit for agents that receive pasted text.
    """
    base = _clean_base_url(url)
    if mcp_only:
        return (
            "Control this computer through Porterminal MCP:\n"
            f"{base}/mcp\n\n"
            f"Agent instructions: {base}/llms.txt\n"
            "Connect using MCP (Streamable HTTP), then call tools/list.\n"
            "The shell runs behind the scenes; browser and REST access are disabled."
        )
    return (
        "Use this Porterminal link to control the remote computer:\n"
        f"{base}\n\n"
        "Agent instructions:\n"
        f"- First read {base}/llms.txt for the exact API.\n"
        f"- Use MCP at {base}/mcp if your runtime can connect remote MCP.\n"
        f"- If MCP is not already available, use REST at {base}/api/agent/run; "
        "do not ask the user to configure MCP.\n"
        f"- If browsing manually, open {base}/ and read the visible terminal screen.\n"
        '- If the user included a task, start using the terminal. If not, ask one short question: "What should I run?"'
    )
