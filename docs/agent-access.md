# Agent access (MCP)

Porterminal exposes the same machine to **AI agents** over the [Model Context
Protocol (MCP)](https://modelcontextprotocol.io). You hand out **one** tunnel
URL: a human opens it in a browser and gets the touch terminal; an agent points
an MCP client at it and drives a real shell. Both see the same sessions.

## Discovery — how an agent finds it from the URL

You don't have to tell the agent anything beyond the base URL. Three signals,
all invisible to humans, lead it to the instructions:

- **`/llms.txt`** — a plain-text usage page (the emerging `llms.txt` convention).
  This is the canonical "how to use this host" page for agents.
- **A `Link:` response header** on the base page:
  `Link: </llms.txt>; rel="alternate"; type="text/markdown", </mcp>; rel="related"`.
- **An inert `<link rel="alternate" href="/llms.txt">`** (plus an HTML comment)
  in the page `<head>` — visible to an agent that fetches the page, ignored by
  browsers.

The human UI at `/` is never changed by any of this. (We deliberately do **not**
content-negotiate the base URL, which would misfire for uptime monitors, link
unfurlers, and scanners.)

## Connect

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

- Each MCP connection gets **its own persistent shell**, created on first use
  and shown as a **🤖-badged tab** in the human's phone UI. The human can watch
  it live, type into it (take over), or close it.
- Shell state persists across tool calls (`cd`, env vars, activated venvs).
- The session is **reaped shortly after the agent disconnects** (or can be
  closed from the phone).

## Security & limits

- **No auth beyond the URL.** Whoever holds the tunnel URL has full shell access
  — for humans *and* agents. The URL is the credential. If you need real
  authentication, this is not the tool for it.
- **Non-elevated.** The shell runs as your user, not as administrator, so an
  agent can install user-scoped tools (e.g. `uv tool install ...`) but cannot
  silently update or install software that requires elevation/UAC.
- `run_command`'s timeout is capped below the Cloudflare Quick Tunnel idle limit;
  for long jobs, background them or poll with `read_screen`.

## See also

- Design and rationale: [`docs/superpowers/specs/2026-06-24-agent-terminal-access-design.md`](superpowers/specs/2026-06-24-agent-terminal-access-design.md)
- Architecture: [`docs/architecture.md`](architecture.md)
