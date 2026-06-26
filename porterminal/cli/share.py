"""Helpers for sharing a Porterminal session URL."""

from __future__ import annotations


def _clean_base_url(url: str) -> str:
    """Return a base URL without trailing slashes."""
    return url.rstrip("/")


def build_agent_share_text(url: str) -> str:
    """Build the text copied when sharing a tunnel URL with an AI agent.

    The base URL remains first-class for humans, while the MCP endpoint and
    /llms.txt instructions are explicit for agents that receive pasted text.
    """
    base = _clean_base_url(url)
    return (
        "Use this Porterminal link to control the remote computer:\n"
        f"{base}\n\n"
        f"AI agents: prefer MCP at {base}/mcp.\n"
        f"If MCP is unavailable, use REST at {base}/api/agent/run.\n"
        f"If browsing manually, open {base}/llms.txt first."
    )
