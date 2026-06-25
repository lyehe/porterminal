# Agent Terminal Access via MCP — Design Spec

**Date:** 2026-06-24
**Status:** MVP implemented and validated end-to-end (agent-in-the-loop) — see §17.
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

- **`send_output(data)`** — feed raw PTY **bytes** into a `pyte.ByteStream` (its incremental decoder correctly handles UTF-8 / escape sequences split across reads — do **not** `bytes.decode()` per chunk) **and** append the raw bytes to a bounded rolling capture buffer; set an asyncio "new output" event. Two consumers: `read_screen` reads `screen.display`; `run_command` scans the (ANSI-stripped) capture buffer for its completion marker.
- **`receive()`** — `await` an internal input queue; returns bytes the existing input loop writes to the PTY. Tools push onto this queue, **chunked to ≤ `MAX_INPUT_SIZE` (4096)** so the per-write size guard never rejects a large command/paste.
- **`send_message(msg)`** — **capture** control/error messages (`error`, rate-limit, `pause_ack`) into last-error state so tools can surface them; otherwise ignore (heartbeat `ping`, `resize_sync`). Must **not** silently drop errors — see §11.
- **`is_connected()` / `close()`** — track MCP-session liveness; unblock `receive()` on close.

> **Relaxed rate limit for agent sessions.** The existing input limiter is **byte-based — 1 KB/s sustained, 16 KB burst** (the architecture doc's "100 messages/second" is stale) — and on overflow it *drops* input rather than delaying it. That exists to throttle an *unauthenticated human* client; for a trusted, explicitly-authorized agent it would silently truncate bulk input. Agent sessions therefore run with an effectively-unlimited `RateLimitConfig`. This requires `TerminalService` to accept a per-session/per-connection rate config (or a second instance dedicated to agent sessions).

### 5.3 `AgentTerminalService` (new application service)

Orchestrates an agent session and exposes the operations the MCP tools call:

- On first contact for a new MCP session: create a `Session` (under the owner `UserId`) + a 🤖 `Tab`, build an `AgentSessionConnection`, register it for management broadcast (so the phone's tab list updates), and start `terminal_service.handle_session(session, agent_conn)` as a background task.
- `run_command`, `read_screen`, `send_keys`, `send_signal` — implemented against the connection's pyte screen / accumulator / input queue (see §7).
- Serialize tool calls per session with a lock (an agent should not overlap commands on one shell).
- On MCP-session end (or explicit close, or phone "close tab"): tear down session + tab.

### 5.4 MCP adapter (new infrastructure adapter)

An MCP server (official `mcp` Python SDK) defining the four tools as thin delegations to `AgentTerminalService`. Integration shape **verified against the SDK docs** (see §17):

- Mount the tool server's ASGI app: `Mount("/mcp", app=server.streamable_http_app(json_response=True, streamable_http_path="/"))`. `json_response=True` → request/response JSON, no long-lived SSE (tunnel-friendly).
- **The session manager must be run inside the parent FastAPI `lifespan`** — `async with server.session_manager.run(): ...` (via `AsyncExitStack`). Without this the endpoint does not function; the SDK enters it **once** at startup and shares it across requests.
- A tool reads its HTTP request context for the **`Mcp-Session-Id`** header (the SDK exposes the Starlette `Request` to tool handlers); that id maps 1:1 to a PTY session.
- Tools reach `AgentTerminalService` via a reference **bound at lifespan startup** — the mounted sub-app does **not** share the parent's `app.state`, and the container is created during `lifespan`, so construction-time injection won't work.
- **Pin the `mcp` version** — exact class/import names differ across releases (`FastMCP` vs `MCPServer` vs lowlevel `Server`); the concepts above are stable.

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

**Timeout is capped** below the Cloudflare Quick Tunnel idle limit (≈100 s) — default 30 s, hard max ~60 s — because with `json_response=True` the HTTP POST is held open with no bytes until the tool returns, and a longer silent hold risks a tunnel cut. For genuinely long operations the agent backgrounds the command (or polls `read_screen`); the tool description says so.

**First-command readiness:** `run_command` snapshots the capture-buffer offset immediately before sending, so the shell's startup banner/prompt is excluded; a brief initial-prompt quiescence wait at session creation further reduces contamination of the first command's output.

### 7.3 `send_keys` / `send_signal`

`send_keys(text)` pushes UTF-8 bytes onto the input queue. `send_signal` pushes the corresponding control byte. Both go through the same input loop that writes to the PTY, so they interleave naturally with human input.

---

## 8. Session & identity lifecycle

- **Identity:** agent sessions are created under the **owner `UserId`** so they appear in the human's tab list and broadcast channel. Defaults to `"local-user"` (the default no-auth case). ⚠️ With Cloudflare Access enabled the phone's identity is the user's email, not `"local-user"`, so the owner identity must be **configurable** — otherwise agent tabs won't appear on the phone. CF-Access co-view is otherwise out of scope; the single-user assumption holds.
- **One shell per MCP connection.** Created lazily on first tool call for a new MCP session id.
- **Tab:** created with `origin="agent"`; `tab_state_update("add", tab)` is broadcast so the phone shows the 🤖 tab immediately.
- **Teardown:** on MCP-session end, explicit close, or phone "close tab" → destroy session + tab (existing cascade). Consistent with porterminal's no-auto-timeout model; an agent-idle cleanup can be added later if lingering shells become a problem.

---

## 9. Transport

- **MCP Streamable HTTP with `json_response=True`** — request/response JSON, no long-lived SSE. Verified as a real SDK option (§5.4, §17). Sidesteps Cloudflare Quick Tunnel idle-timeout quirks for the common case.
- Mounted on the existing uvicorn/FastAPI app; exposed through the existing tunnel with no new tunnel config. The session manager runs inside the parent `lifespan` (§5.4).
- **Held-POST caveat:** each tool response is held open until it returns, so a `run_command` silent for longer than the tunnel idle limit (≈100 s) risks a cut. Mitigated by capping `run_command` timeout (§7.2); long operations are backgrounded/polled.

---

## 10. Phone UX

- Agent tabs render a **🤖 badge** (from `tab.origin === "agent"`). Minimal frontend change: a field in tab types + a badge in tab rendering.
- **Take over:** tap the tab → the phone opens its normal `/ws` data connection to that session → joins the multi-client broadcast → sees live output and can type. No new mechanism.
- **Kill:** the existing "close tab" destroys the session. No new mechanism.

---

## 11. Error handling

- **Never silently drop.** The input loop replies to oversize/rate-limit violations via `send_message`; the agent connection **captures** those (§5.2) so a tool returns the error instead of hanging to timeout.
- **Oversized input:** the agent connection **chunks** writes to ≤ `MAX_INPUT_SIZE` (4096), so the guard isn't tripped in the first place.
- **Rate limiting:** agent sessions use an effectively-unlimited `RateLimitConfig` (§5.2) — the human-abuse limiter is inappropriate for a trusted agent and would drop bulk input.
- **PTY dead / shell exited:** `run_command` / `read_screen` return a clear error status; the tab closes via the existing session-destroyed cascade.
- **Tool call on a torn-down session:** return an MCP tool error telling the agent the session ended.
- **Overlapping tool calls on one session:** serialized by a per-session lock; the second waits.

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
| Long/silent `run_command` cut by tunnel idle (~100 s) with held-POST | Cap timeout (default 30 s, max ~60 s); background or poll long ops (§7.2) |
| MCP SDK class/import names differ by version | **Verified** mount + lifespan + `json_response` shape (§17); **pin** `mcp`; isolate in the adapter |
| Agent input silently dropped by size/rate guards | Chunk to ≤4096; relaxed rate limit; capture `send_message` errors (§5.2, §11) |
| `pyte` byte handling (UTF-8 / escape split across reads) | Feed via `pyte.ByteStream` incremental decoder, never per-chunk `decode()` (§5.2) |
| `pyte` fidelity on complex TUIs; `TERM` mismatch | `read_screen` best-effort; agents mostly use `run_command`; acceptable |
| Lingering agent shells | **Resolved:** a reaper closes sessions on client disconnect (transport `is_terminated`) **or dead PTY** (agent ran `exit`), with an idle-timeout backstop; phone-close always works. No explicit `close_session`/`reset` tool - termination is via `exit` or disconnect, keeping the 4-tool surface minimal (deliberate AX/UX call). |

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
- `porterminal/app.py` — mount `/mcp` **and enter the MCP session manager in `lifespan`** (`AsyncExitStack`); bind `AgentTerminalService` after container creation.
- `porterminal/application/services/terminal_service.py` — accept a per-session/per-connection `RateLimitConfig` so agent sessions can relax the limiter.
- `porterminal/cli/display.py` — show the copyable `/mcp` URL on startup.
- `frontend/src/services/TabService.ts`, `frontend/src/types/index.ts`, tab UI — 🤖 badge for `origin === "agent"`.
- `docs/architecture.md`, `docs/frontend_features.md`, `README.md` — document agent access.

---

## 16. Dependencies

- **`mcp`** (**pinned** to a known-good version) — official MCP Python SDK (Streamable HTTP). Pure Python, cross-platform. Class names vary by release, so pin and confirm imports at implementation time.
- **`pyte`** — pure-Python terminal emulator for server-side screen rendering. Cross-platform (Windows-safe). Use `pyte.Screen` + `pyte.ByteStream`.

---

## 17. Technical review (verified 2026-06-24)

The architecture was reviewed against the live codebase and current library docs (MCP Python SDK `/modelcontextprotocol/python-sdk`, pyte `/selectel/pyte`). **The design holds; no blocking issues.** Verified facts and the fixes folded into this spec:

**Verified sound (no change):**
- Mounting an MCP Streamable HTTP app at `/mcp` on the existing FastAPI/Starlette app works (`Mount` + `streamable_http_app(...)`).
- `json_response=True` is a real SDK option giving request/response (no long-lived SSE) — the tunnel-friendly mode this spec assumed.
- The "agent = just another client" model is valid: `TerminalService` already broadcasts one PTY read loop to all `ConnectionPort`s and accepts input from any, so the phone co-views/takes-over the agent's shell for free.
- `connection_registry.broadcast(...)`, `tab_service.create_tab(...)`, and `build_tab_state_update("add", tab)` exist and suffice to surface the 🤖 tab on the phone.
- The CLI already owns the tunnel URL, so showing `/mcp` is a pure display change (no server round-trip).

**Issues found and resolved in this spec:**
1. **MCP session manager must run in the parent lifespan** (`async with server.session_manager.run()` via `AsyncExitStack`) — was under-specified. → §5.4, §15.
2. **Tools can't use the parent `app.state`** (mounted sub-app); the service is **bound at lifespan startup**; MCP session id + headers come from the tool request context. → §5.4.
3. **pyte must consume bytes via `ByteStream`**, not per-chunk `decode()` (split UTF-8/escape sequences) — latent corruption bug. → §5.2.
4. **Input guards silently drop agent input:** `MAX_INPUT_SIZE` (4096) and the **byte** rate limiter (**1 KB/s / 16 KB burst**, not the doc's "100 msg/s") reject (don't delay) bulk input, and the error went to a no-op `send_message`. → chunk writes, relax the limiter for agent sessions, and capture errors. §5.2, §11; also requires a `TerminalService` rate-config change (§15).
5. **Held-POST vs tunnel idle:** cap `run_command` timeout below ≈100 s. → §7.2, §9.
6. **Owner identity** must be configurable so agent tabs show on the phone under Cloudflare Access (default `"local-user"`). → §8.
7. **SDK version churn:** pin `mcp`; confirm class names at implementation. → §16.

**Stale doc to fix while here:** `docs/architecture.md` states rate limiting is "100 messages/second, burst 500"; the real config is **1 KB/s sustained, 16 KB burst** (`RateLimitConfig`). Correct it as part of this work.

### Live validation (agent-in-the-loop)

The MVP was implemented and driven end-to-end by a real MCP agent against a live `pwsh` PTY — automated in `tests/e2e/test_agent_mcp_e2e.py` (uvicorn + the official `mcp` client, no mocks) and dogfooded interactively via `scripts/agent_drive.py`. Confirmed working: tool discovery; `run_command` with clean output and correct exit codes; **persistent shell state across separate tool calls** (`cd` and shell variables survive); `read_screen`; `send_keys`; `send_signal` (Ctrl-C); and driving an interactive Python REPL. The exit-code marker's echo-avoidance trick (scan `marker\d+`; the shell's echo contains the *expression*, not digits) held up on PowerShell.

**Finding:** the interactive path is timing-sensitive on Windows ConPTY — the first tool call pays session-warmup latency, so an agent should pace `send_keys`→`read_screen` (and `read_screen` now does a brief settle so it never returns a blank/mid-draw snapshot). `run_command` (the 90% path) was solid throughout.
