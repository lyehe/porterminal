"""Human UI, health, and agent discovery routes."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from porterminal import __version__
from porterminal.infrastructure.web.mcp_adapter import McpAdapter

from .common import get_container

STATIC_DIR = Path(__file__).parents[3] / "static"
router = APIRouter()


def _request_base_url(request: Request) -> str:
    """Return a tunnel-aware absolute base URL."""
    host = request.headers.get("host") or request.url.netloc
    scheme = (
        "https"
        if request.headers.get("x-forwarded-proto") == "https" or request.headers.get("cf-ray")
        else request.url.scheme
    )
    return f"{scheme}://{host}"


@router.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(
            content=index_path.read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Link": (
                    '</.well-known/mcp.json>; rel="alternate"; type="application/json", '
                    '</llms.txt>; rel="alternate"; type="text/markdown", '
                    '</mcp>; rel="related", '
                    '</api/agent/run>; rel="related"'
                ),
            },
        )
    return JSONResponse({"error": "index.html not found"}, status_code=404)


@router.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt(request: Request):
    """Serve agent-facing connection and usage instructions."""
    base = _request_base_url(request)
    adapter: McpAdapter = request.app.state.mcp_adapter
    tools = "\n".join(f"- `{name}` - {desc}" for name, desc in adapter.tool_summaries())

    body = f"""# Porterminal - AI agent instructions

Porterminal is a terminal on this machine. A human uses the web UI at {base}/ ;
you (an AI agent) can control a real shell over MCP or the REST fallback API.

## Connect

MCP endpoint (Streamable HTTP): {base}/mcp
Machine-readable discovery: {base}/.well-known/mcp.json (MCP server.json)

Point any MCP client at that URL. Example client config:

    {{
      "mcpServers": {{
        "porterminal": {{ "url": "{base}/mcp" }}
      }}
    }}

After connecting, call `tools/list` to confirm the tools below.

## Tools

{tools}

Guidance: prefer `run_command` for ordinary commands (clean output + exit code).
If it returns `status: "waiting"`, the command is interactive - use `read_screen`
to see the prompt and `send_keys` / `send_signal` to drive it.

## REST fallback

Use this if your host cannot register/connect an MCP server but can make HTTP
requests. First call `run` without a session id; reuse the returned `session_id`
for subsequent calls:

    POST {base}/api/agent/run
    {{"command": "echo hello", "timeout": 30}}
    -> {{"session_id": "rest-...", "status": "completed", "exit_code": 0, "output": "hello"}}

    GET  {base}/api/agent/screen?session_id=rest-...
    POST {base}/api/agent/keys    {{"session_id": "rest-...", "text": "answer\r"}}
    POST {base}/api/agent/signal  {{"session_id": "rest-...", "signal": "int"}}
    DELETE {base}/api/agent/session?session_id=rest-...

REST uses the same visible agent tab and shell backend as MCP. The `session_id`
must come from a prior REST response.

If your HTTP client or local shell pretty-prints the REST response as a table,
long `output` fields may be visually truncated with an ellipsis. Treat that as
client-side display clipping: inspect the raw `output` field, or make the remote
command print JSON/plain text before relying on exact values.

## Browser fallback

If your environment cannot use MCP or REST, open {base}/ in a browser. Read the
element named "Terminal screen", type commands into "Terminal input", and press
Enter. This fallback is less reliable, but it is intentionally exposed as
ordinary page text for browser-driving agents.

## Example

    run_command(command="echo hello")
    -> {{"status": "completed", "exit_code": 0, "output": "hello"}}

## Notes

- Each MCP or REST agent session gets its own persistent shell, shown as a tab
  the human can watch and take over. MCP sessions are cleaned up when you
  disconnect; REST sessions close on DELETE, shell exit, or idle cleanup.
- Security: the URL is the only credential - there is no extra auth, and the
  shell runs non-elevated (it can't install software that requires admin).
"""
    return PlainTextResponse(body, media_type="text/markdown; charset=utf-8")


@router.get("/.well-known/mcp/server.json")
@router.get("/.well-known/mcp.json")
async def mcp_server_json(request: Request) -> dict:
    """Serve the MCP ``server.json`` discovery descriptor."""
    base = _request_base_url(request)
    return {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        "name": "io.github.lyehe.porterminal",
        "title": "Porterminal",
        "description": (
            "Web terminal + MCP agent terminal on this machine, exposed via a Cloudflare tunnel."
        ),
        "version": __version__,
        "repository": {"url": "https://github.com/lyehe/porterminal", "source": "github"},
        "remotes": [{"type": "streamable-http", "url": f"{base}/mcp"}],
    }


@router.get("/health")
async def health(request: Request):
    """Report process and in-memory service health."""
    container = get_container(request)
    return {
        "status": "healthy",
        "sessions": container.session_service.session_count(),
        "tabs": container.tab_service.tab_count(),
        "connections": container.connection_registry.total_connections(),
    }
