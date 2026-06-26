# Agent access (MCP + REST)

Porterminal exposes the same machine to **AI agents** over the [Model Context
Protocol (MCP)](https://modelcontextprotocol.io) and a plain REST fallback. You
hand out **one** tunnel URL: a human opens it in a browser and gets the touch
terminal; an agent uses MCP if its host supports it, or REST if it only has
HTTP/shell tools. Both see the same sessions.

## Discovery — how an agent finds it from the URL

You don't have to tell the agent anything beyond the base URL. Several signals
lead a client to the MCP endpoint:

- **`/.well-known/mcp.json`** (also `/.well-known/mcp/server.json`) — a
  machine-readable MCP `server.json` descriptor: server name, version, and a
  `remotes` entry pointing at the `streamable-http` `/mcp` endpoint. This is the
  MCP-native discovery surface that capable clients auto-detect. The well-known
  path is still being finalized upstream (SEPs #1649 / #1960), so we serve both
  spellings; a client that 404s falls back to being handed the `/mcp` URL.
- **`/llms.txt`** — a human/agent-readable prose page (the `llms.txt` convention)
  with MCP setup, REST fallback calls, and browser fallback instructions.
  `llms.txt` is popular but not reliably auto-fetched, so treat it as the
  readable companion to `server.json`, not the primary discovery.
- **A `Link:` response header** on the base page pointing at both, plus an inert
  `<link rel="alternate">` + HTML comment in the page `<head>`.
- **Accessibility-visible page text** on `/` that tells browser-driving agents
  to prefer `/mcp`, read `/llms.txt`, or use the fallback paths below.

The human UI at `/` stays compact. (We deliberately do **not**
content-negotiate the base URL, which would misfire for uptime monitors, link
unfurlers, and scanners.)

## Share from the CLI or phone

In the foreground CLI, press **`c`** to copy agent instructions and URL,
including the base URL, the `/mcp` endpoint, the REST `/api/agent/run`
endpoint, and `/llms.txt`. Press **`u`** to copy the URL only.

In the web terminal, the top-right copy button copies the same agent-ready share
message using the current browser URL. This is the phone-friendly path when you
want to paste the session into an agent chat from mobile.

## MCP

The MCP endpoint is **Streamable HTTP** at `<url>/mcp`. Point any MCP-capable
client at it:

```json
{
  "mcpServers": {
    "porterminal": { "url": "https://<your-tunnel>.trycloudflare.com/mcp" }
  }
}
```

After `initialize`, call `tools/list` to confirm the tools below.

## REST fallback

Use REST when the agent cannot register/connect an MCP server but can make HTTP
requests. First call `run` without a session id; reuse the returned `session_id`
for later calls.

```bash
curl -s -X POST https://<your-tunnel>.trycloudflare.com/api/agent/run \
  -H "content-type: application/json" \
  -d '{"command":"echo hello","timeout":30}'
```

Typical response:

```json
{
  "session_id": "rest-...",
  "status": "completed",
  "exit_code": 0,
  "output": "hello"
}
```

Endpoints:

| Endpoint | Purpose |
|----------|---------|
| `POST /api/agent/run` | Run a command. Body: `{ "command": "...", "timeout": 30, "session_id": "optional" }`. |
| `GET /api/agent/screen?session_id=rest-...` | Read the rendered terminal screen. |
| `POST /api/agent/keys` | Send raw keystrokes. Body: `{ "session_id": "rest-...", "text": "answer\\r" }`. |
| `POST /api/agent/signal` | Send `int` (Ctrl-C) or `eof`. |
| `DELETE /api/agent/session?session_id=rest-...` | Close the REST agent shell and visible tab. |

When calling REST from a local shell that pretty-prints objects, inspect the raw
response fields for long output. For example, PowerShell table formatting can
show `output` with an ellipsis even though the REST response still contains the
full string. For structured or exact values, make the remote command print
JSON/plain text, or parse the response's `output` field directly.

## Browser fallback

MCP and REST are the reliable paths. If an agent can only drive a browser, open
the base URL and use the page elements named **Terminal screen** and
**Terminal input**:

1. Read **Terminal screen** for the current terminal output.
2. Type commands into **Terminal input**.
3. Press Enter to submit.

This is intentionally exposed as ordinary DOM/accessibility text so agents do
not need screenshots or OCR just to read command output.

## Tools

| Tool | What it does |
|------|--------------|
| `run_command(command, timeout?)` | Runs a command in the persistent shell; returns `{ output, exit_code, status }`. The 90% case. |
| `read_screen()` | The rendered terminal screen as clean text + cursor position. For prompts / TUIs / REPLs. |
| `send_keys(text)` | Raw keystrokes (no automatic Enter; include `\r` to submit). Answer a prompt, drive `vim`. |
| `send_signal("int" \| "eof")` | Ctrl-C (`int`) or Ctrl-D (`eof`). Interrupt a runaway. |

**Two-level model:** prefer `run_command`. If it returns `status: "waiting"`, the
command didn't finish on its own (likely interactive) — use `read_screen` to see
the prompt, then `send_keys` / `send_signal` to respond.

```
run_command(command="echo hello")
-> { "status": "completed", "exit_code": 0, "output": "hello" }
```

## Sessions

- Each MCP connection or REST `session_id` gets **its own persistent shell**,
  created on first use and shown as a **🤖-badged tab** in the human's phone UI.
  The human can watch it live, type into it (take over), or close it.
- Shell state persists across tool calls (`cd`, env vars, activated venvs).
- MCP sessions are **reaped shortly after the agent disconnects**. REST sessions
  are closed by `DELETE /api/agent/session`, shell exit, phone tab close, or idle
  cleanup.

## Security & limits

- **No auth beyond the URL.** Whoever holds the tunnel URL has full shell access
  — for humans *and* agents. The URL is the credential. If you need real
  authentication, this is not the tool for it.
- **Non-elevated.** The shell runs as your user, not as administrator, so an
  agent can install user-scoped tools (e.g. `uv tool install ...`) but cannot
  silently update or install software that requires elevation/UAC.
- MCP `run_command` and REST `run` timeouts are capped below the Cloudflare Quick
  Tunnel idle limit; for long jobs, background them or poll the screen.

## See also

- Design and rationale: [`docs/superpowers/specs/2026-06-24-agent-terminal-access-design.md`](superpowers/specs/2026-06-24-agent-terminal-access-design.md)
- Architecture: [`docs/architecture.md`](architecture.md)
