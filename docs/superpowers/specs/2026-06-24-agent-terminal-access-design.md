# Agent Terminal Access via MCP — Design Spec

**Date:** 2026-06-24
**Status:** Approved (brainstorming) → ready for implementation planning
**Topic:** Give any MCP-capable AI agent full terminal control of the machine through the same running `ptn` server and tunnel that already serves the phone terminal.

---

## 1. Summary

Porterminal today gives a *human* a touch-friendly terminal on their phone over a Cloudflare Quick Tunnel. This feature adds a **second consumer of the same running server**: any **MCP-capable AI agent**.

You run `uvx ptn`. You get one tunnel URL. That URL serves:

- `/` — the phone terminal (humans, via QR)
- `/mcp` — agent control (agents, via copy-pasted URL)

You hand an agent the `/mcp` URL. Its MCP client calls `initialize` → `tools/list` (this *is* "find out the info from the URL"), then drives real terminal sessions on the machine with four clean, agent-friendly tools. Every agent shell shows up as a 🤖 tab on your phone that you can watch live, type into (take over), or close (kill).

**Headline experience:** `uvx ptn`, hand over a URL, the agent controls the PC. No tokens, no flags, no configuration.

---

## 2. Goals

- **Discover-from-URL.** Hand an agent one URL; MCP discovery does the rest. No custom integration or docs.
- **Reuse the existing machinery.** The agent is "just another client" of the existing multi-client `TerminalService` / `SessionService` / tab model. Minimal new surface.
- **Observable & interruptible from the phone.** Agent sessions are live-viewable, take-over-able, and closeable from the existing phone UI for free.
- **Dead simple.** Works with zero configuration via `uvx ptn`. On by default.
- **Cover both interaction modes.** The common case (run a command → output + exit code) *and* the interactive case (prompts, REPLs, TUIs like `vim`/`top`).

---

## 3. Non-Goals (explicitly out of scope)

- **Security / auth for the agent path.** The security model is the obscure tunnel URL — *identical* to the existing human terminal, which is already an unauthenticated full shell. No agent token, no trust levels, no guardrails/denylist, no per-command approval. **Anyone with the tunnel URL has full programmatic control of the machine, by design.** If a deployment needs real security, it should use a different tool. (This was a deliberate product decision: keep the command dead-simple and unconfusing.)
- **Multi-agent session-management tools, scrollback retrieval, named-key ergonomics.** Deferred to post-MVP.
- **Any change to the human terminal's behavior.**

> Note: the agent endpoint rides the same FastAPI app, so if a future user *has* set porterminal's existing optional password / Cloudflare Access, `/mcp` naturally sits behind it (so it can't be a bypass). That is a free side effect, not a feature we build or advertise here.

---

## 4. Key decisions & rationale

| Decision | Choice | Why |
|---|---|---|
| Agent ↔ session relationship | **Dedicated, isolated agent sessions**, observable as 🤖 tabs on the phone | Cleanest; maps onto the existing session/tab model; enables "watch your agent from your phone" |
| Interaction substrate | **Real PTY + two-level tools** (high-level `run_command`, low-level `read_screen`/`send_keys`/`send_signal`) | Clean `command → output` for the 90%, plus full interactive control (prompts, REPLs, TUIs) for the 10%; stateful; observable |
| Transport | **MCP over Streamable HTTP** at `/mcp`, on the running server, through the tunnel | MCP gives URL-based capability discovery for free; reuses the tunnel; remote-reachable |
| Auth | **None** — the tunnel URL is the secret, same as the human terminal | Deliberate simplicity; a separate token is redundant when the same URL already grants full control via the human terminal |
| Tool surface | **Four tools**, one implicit shell per agent connection | Minimal and obvious for the agent; "dead simple" extends to the agent's view too |
| Observability | **Agent shell = a 🤖 tab**; watch / take over / close on the phone | Reuses existing tab + multi-client broadcast; "close the tab" *is* the kill switch |

---

## 5. Architecture

### 5.1 The core insight: the agent is "just another client"

`TerminalService` already supports **multiple clients on one session**: a single PTY read loop broadcasts output to every attached `ConnectionPort`, and input from any client is written to the PTY. Today every `ConnectionPort` is a WebSocket. For the agent, we add a **non-WebSocket `ConnectionPort`** that bridges MCP's request/response tools onto that streaming model.

```
                          ┌──────────────── one PTY session ────────────────┐
                          │  single read loop (TerminalService)             │
   agent (MCP/HTTP) ──▶ AgentSessionConnection ──┐                          │
                          │   • feeds pyte screen  ├─◀ broadcast PTY output ─┤
   phone (WebSocket) ──▶ FastAPIWebSocketAdapter ─┘                          │
                          │        both write input ──▶ PTY                  │
                          └──────────────────────────────────────────────────┘
```

Because the agent and the phone are both just connections on the same session, **the human co-views and can take over the agent's shell with zero extra plumbing** — it falls out of the existing multi-client design.

### 5.2 `AgentSessionConnection` (new infrastructure adapter)

Implements `ConnectionPort` but talks to MCP tools instead of a socket:

- **`send_output(data)`** — feed bytes into a `pyte` stream (updates a rendered screen) **and** append ANSI-stripped text to a bounded rolling accumulator; signal a "new output" event. (Two consumers: `read_screen` reads the pyte screen; `run_command` scans the accumulator for its completion marker.)
- **`receive()`** — `await` an internal input queue; returns bytes that the existing input loop writes to the PTY. Tools push onto this queue.
- **`send_message(msg)`** — minimal/no-op (e.g. ignore heartbeat pings, `resize_sync`).
- **`is_connected()` / `close()`** — track MCP-session liveness; unblock `receive()` on close.

### 5.3 `AgentTerminalService` (new application service)

Orchestrates an agent session and exposes the operations the MCP tools call:

- On first contact for a new MCP session: create a `Session` (under the owner `UserId`) + a 🤖 `Tab`, build an `AgentSessionConnection`, register it for management broadcast (so the phone's tab list updates), and start `terminal_service.handle_session(session, agent_conn)` as a background task.
- `run_command`, `read_screen`, `send_keys`, `send_signal` — implemented against the connection's pyte screen / accumulator / input queue (see §7).
- Serialize tool calls per session with a lock (an agent should not overlap commands on one shell).
- On MCP-session end (or explicit close, or phone "close tab"): tear down session + tab.

### 5.4 MCP adapter (new infrastructure adapter)

A FastMCP (official `mcp` Python SDK) server defining the four tools as thin delegations to `AgentTerminalService`, mounted on the existing FastAPI app at `/mcp`. The MCP session id maps 1:1 to a PTY session.

### 5.5 Layer placement (hexagonal)

| Layer | Addition |
|---|---|
| Domain | `Tab` gains an `origin` field (`"human"` \| `"agent"`); surfaced in `to_dict()` |
| Application | `AgentTerminalService` (new); `TabService.create_tab` accepts `origin` |
| Infrastructure | `AgentSessionConnection`, MCP adapter (new); CLI display shows `/mcp` URL |
| Composition | wire `AgentTerminalService` + MCP adapter, add to `Container` |
| Reused as-is | `SessionService`, `TerminalService` (multi-client broadcast), `connection_registry`, env sanitization, session limits, rate limiting, PTY layer |

---

## 6. MCP tool surface (v1)

The agent operates on **its own auto-created shell**, one per MCP connection — no session-management tools in v1.

| Tool | Signature | Returns | Purpose |
|---|---|---|---|
| `run_command` | `(command: str, timeout?: float = 30)` | `{ output: str, exit_code: int \| null, status: "completed" \| "waiting" }` | Run a command, get clean output + exit code. The 90% case. |
| `read_screen` | `()` | `{ screen: str, cursor?: {row, col} }` | The rendered terminal screen as clean text. For prompts / TUIs / REPLs. |
| `send_keys` | `(text: str)` | `{ ok: true }` | Send raw keystrokes (incl. embedded control chars). Answer a prompt, drive `vim`. |
| `send_signal` | `(signal: "int" \| "eof")` | `{ ok: true }` | `int` → Ctrl-C (`\x03`), `eof` → Ctrl-D (`\x04`). Interrupt a runaway. |

Tool descriptions (shown to the agent via `tools/list`) will steer usage: prefer `run_command`; if it returns `status: "waiting"`, the command is probably interactive — use `read_screen` to see the prompt and `send_keys` / `send_signal` to respond.

---

## 7. Interaction model

### 7.1 `read_screen`

Returns `"\n".join(screen.display).rstrip()` from the `pyte` screen, which the broadcast loop keeps current via `AgentSessionConnection.send_output`. Best-effort cursor position included. The pyte screen is sized to the session dimensions (default e.g. 120×40).

### 7.2 `run_command` — completion detection (the main engineering risk)

1. Generate a random marker, e.g. `__PTN_<uuid4hex>__` (random → won't collide with real output).
2. Build a **shell-specific** payload that runs the command then prints `marker + exit_code` on its own line:
   - POSIX (`bash`/`zsh`/`sh`/`fish`): `<command>\n` then `printf '%s%s\n' '<marker>' "$?"\n`
   - PowerShell: `<command>\n` then `Write-Output "<marker>$LASTEXITCODE"\n`
   - `cmd.exe`: `<command>\r\n` then `echo <marker>%errorlevel%\r\n`

   The shell is known from `session.shell_id`.
3. Snapshot the accumulator offset; push the payload onto the input queue.
4. Await "new output" events, scanning newly-accumulated (ANSI-stripped) text for a line matching `^<marker>(-?\d+)$`.
5. **On match:** `output` = text between the echoed command and the marker line (strip the command echo and marker line); `exit_code` = parsed int; `status = "completed"`.
6. **On timeout:** `status = "waiting"`; `output` = current rendered screen (so the agent sees the prompt it is stuck on); `exit_code = null`. Agent falls back to `read_screen` / `send_keys`.

Known fiddly bits (documented, bounded by the timeout fallback): stripping the shell's command echo and prompt strings; multi-line commands; PowerShell's `$LASTEXITCODE` (native) vs `$?` (cmdlet) semantics. The random marker + timeout fallback + `read_screen` escape hatch keep this robust enough without trying to perfectly parse every shell.

### 7.3 `send_keys` / `send_signal`

`send_keys(text)` pushes UTF-8 bytes onto the input queue. `send_signal` pushes the corresponding control byte. Both go through the same input loop that writes to the PTY, so they interleave naturally with human input.

---

## 8. Session & identity lifecycle

- **Identity:** agent sessions are created under the **owner `UserId`** (the local user — `"local-user"` in the default no-auth case) so they appear in the human's tab list and broadcast channel. Single-user tool; no cross-user concerns.
- **One shell per MCP connection.** Created lazily on first tool call for a new MCP session id.
- **Tab:** created with `origin="agent"`; `tab_state_update("add", tab)` is broadcast so the phone shows the 🤖 tab immediately.
- **Teardown:** on MCP-session end, explicit close, or phone "close tab" → destroy session + tab (existing cascade). Consistent with porterminal's no-auto-timeout model; an agent-idle cleanup can be added later if lingering shells become a problem.

---

## 9. Transport

- **MCP Streamable HTTP**, request/response (POST) oriented. Our tools are agent-asks → server-answers, so we avoid long-lived SSE where possible — sidestepping Cloudflare Quick Tunnel idle-timeout quirks.
- Mounted on the existing uvicorn/FastAPI app; exposed through the existing tunnel with no new tunnel config.
- **The exact MCP Python SDK API** (FastMCP construction, ASGI mounting, accessing the MCP session id, lifespan integration) will be confirmed against current docs via Context7 at the start of implementation planning, rather than assumed here.

---

## 10. Phone UX

- Agent tabs render a **🤖 badge** (from `tab.origin === "agent"`). Minimal frontend change: a field in tab types + a badge in tab rendering.
- **Take over:** tap the tab → the phone opens its normal `/ws` data connection to that session → joins the multi-client broadcast → sees live output and can type. No new mechanism.
- **Kill:** the existing "close tab" destroys the session. No new mechanism.

---

## 11. Error handling

- **PTY dead / shell exited:** `run_command` / `read_screen` return a clear error status; the tab closes via the existing session-destroyed cascade.
- **Tool call on a torn-down session:** return an MCP tool error instructing the agent that the session ended.
- **Oversized input:** reuse `TerminalService`'s existing `MAX_INPUT_SIZE` guard.
- **Rate limiting:** reuse the existing token-bucket limiter on PTY writes.
- **Overlapping tool calls on one session:** serialized by a per-session lock; the second call waits.

---

## 12. Testing

Reuse existing patterns (`pytest-asyncio` auto mode, `FakePTY`, `MockConnection`, `fake_pty_factory`).

- **Unit:** `AgentSessionConnection` pyte rendering + accumulator from canned `FakePTY` bytes; `run_command` marker detection (feed bytes ending in the marker) and timeout→`waiting` fallback; `send_keys`/`send_signal` enqueue the right bytes; per-session lock serializes calls.
- **Application:** `AgentTerminalService` creates session + 🤖 tab, broadcasts the tab add, tears down on close.
- **Tool layer:** the four MCP tools delegate correctly and shape their return payloads.
- **Integration:** start the app, drive `/mcp` as an MCP client (or raw JSON-RPC POSTs) — `tools/list` returns four tools; `run_command("echo hi")` returns `output` containing `hi` and `exit_code 0`; assert a 🤖 tab appeared for the owner.
- **Cross-shell:** `run_command` marker logic for at least PowerShell (the dev's default on Windows 11) **and** bash.

---

## 13. MVP scope & phasing

**Phase 1 (MVP — this spec):**
- `/mcp` Streamable HTTP endpoint on the running server, on by default.
- One implicit shell per MCP connection.
- The four tools (§6) with pyte `read_screen` and sentinel+fallback `run_command`.
- Cross-shell `run_command` markers for **PowerShell + bash** at minimum.
- 🤖 tab badge + phone observability/take-over/close.
- Startup display shows the copyable `/mcp` URL (reusing the `c`-to-copy pattern; **no QR**).

**Phase 2 (later, not now):**
- Multi-session tools (`create_session` / `list_sessions` / `close_session`).
- Named-key ergonomics for `send_keys` (Enter/Tab/arrows/Esc as named keys), `resize` tool, scrollback retrieval.
- Optional `--no-agent` opt-out flag for phone-only mode.
- Agent-idle session cleanup.

---

## 14. Risks & open questions

| Risk | Mitigation |
|---|---|
| `run_command` completion detection across shells (primary risk) | Random marker + per-shell payload + `timeout`→`waiting` fallback + `read_screen` escape hatch |
| MCP Streamable HTTP through Cloudflare Quick Tunnel (SSE idle timeouts) | Lean on request/response POST mode; verify behavior; add keepalive only if needed |
| Exact MCP Python SDK API surface | Confirm via Context7 before coding; isolate in the MCP adapter |
| `pyte` fidelity on complex TUIs | `read_screen` is best-effort; agents mostly use `run_command`; acceptable |
| Lingering agent shells | Teardown on MCP-session end; defer idle-cleanup to Phase 2 |

---

## 15. Files to create / modify (to inform planning)

**Create**
- `porterminal/infrastructure/web/agent_connection.py` — `AgentSessionConnection(ConnectionPort)` (pyte + accumulator + input queue).
- `porterminal/infrastructure/web/mcp_adapter.py` — FastMCP server + four tools; mountable ASGI app.
- `porterminal/application/services/agent_terminal_service.py` — `AgentTerminalService`.
- Tests under `tests/` mirroring the above.

**Modify**
- `pyproject.toml` — add `mcp` and `pyte` dependencies.
- `porterminal/domain/entities/tab.py` (+ value/`to_dict`) — add `origin`.
- `porterminal/application/services/tab_service.py` — `create_tab(origin=...)`.
- `porterminal/application/services/__init__.py` — export `AgentTerminalService`.
- `porterminal/composition.py` — construct `AgentTerminalService` + MCP adapter; pass services.
- `porterminal/container.py` — hold the new service / mounted MCP app.
- `porterminal/app.py` — mount `/mcp`.
- `porterminal/cli/display.py` — show the copyable `/mcp` URL on startup.
- `frontend/src/services/TabService.ts`, `frontend/src/types/index.ts`, tab UI — 🤖 badge for `origin === "agent"`.
- `docs/architecture.md`, `docs/frontend_features.md`, `README.md` — document agent access.

---

## 16. Dependencies

- **`mcp`** — official MCP Python SDK (FastMCP + Streamable HTTP). Pure Python, cross-platform.
- **`pyte`** — pure-Python terminal emulator for server-side screen rendering. Cross-platform (Windows-safe).
