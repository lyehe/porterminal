"""Contract test guarding the private FastMCP internals the agent reaper reads.

`McpAdapter.bind()` builds a live-session probe over the SDK's
`StreamableHTTPSessionManager._server_instances` and
`StreamableHTTPServerTransport.is_terminated`. Those are private; if a `mcp`
upgrade renames them, the probe silently degrades to idle-only reaping
(disconnect cleanup stops working). These tests fail loudly on that drift so the
pinned `mcp` version stays honest.
"""

from mcp.server.streamable_http import StreamableHTTPServerTransport

from porterminal.infrastructure.web import McpAdapter


def test_reaper_probe_private_attrs_present():
    adapter = McpAdapter()
    adapter.streamable_http_app()  # creates the session manager
    sm = adapter.session_manager
    assert isinstance(getattr(sm, "_server_instances", None), dict), (
        "FastMCP StreamableHTTPSessionManager no longer exposes `_server_instances`; "
        "the agent reaper's live-session probe (McpAdapter.bind) is broken."
    )
    assert hasattr(StreamableHTTPServerTransport, "is_terminated"), (
        "StreamableHTTPServerTransport.is_terminated is gone; the reaper can no "
        "longer tell disconnected sessions from live ones."
    )


def test_reaper_probe_returns_empty_set_when_no_sessions():
    adapter = McpAdapter()
    adapter.streamable_http_app()
    captured: dict = {}

    class _Svc:
        def bind_live_probe(self, probe):
            captured["probe"] = probe

    adapter.bind(_Svc())
    assert captured["probe"]() == set()
