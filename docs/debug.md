# Debug Notes

This document tracks features that were removed or modified during debugging.

**Do not re-implement these features.** They were removed intentionally after testing showed they added complexity without benefit.

## Removed Features

### 1. Scrollback Cleanup After Clear

**Location:** `frontend/src/services/ConnectionService.ts`

**What it did:**
- Detected when terminal was cleared (cursor at top + scrollback exists)
- Called `term.clear()` to remove stale scrollback
- Had "fast path" optimization to skip expensive `isVisibleAreaEmpty()` check

**Why removed:**
- Did not help with terminal rendering issues
- Added complexity without clear benefit
- Could interfere with TUI applications that manipulate scrollback

**Code removed:**
```typescript
function isVisibleAreaEmpty(term: Terminal): boolean {
    // Checked if all visible rows were blank or short prompts
}

// In writeToTerminal():
if (cursorNearTop && hasScrollback && isVisibleAreaEmpty(tab.term)) {
    tab.term.clear();
}
```

---

### 2. iOS Voice Input Debouncing

**Location:** `frontend/src/services/TabService.ts`

**What it did:**
- Buffered multi-character input on iOS for 150ms
- Aimed to handle voice dictation interim results
- Flushed buffer when user switched to keyboard input

**Why removed:**
- Suspected cause of issue #14 (terminal jumping to top on mobile)
- Added latency to all multi-character input on iOS
- Complex state management with timers per tab

**Code removed:**
```typescript
const voiceTimers = new Map<number, ReturnType<typeof setTimeout>>();
let voiceBuffer = '';
const VOICE_DEBOUNCE_MS = 150;

// Debouncing logic in terminal.onData() handler
if (isIOS && data.length > 1) {
    voiceBuffer = data;
    // ... timer logic
}
```

---

### 3. Alt-Screen Exit Detection for Buffer Restoration

**Location:** `frontend/src/services/ConnectionService.ts`

**What it did:**
- Detected alt-screen exit sequences (`\x1b[?1049l`, `\x1b[?47l`, `\x1b[?1047l`)
- Hid terminal during xterm.js buffer restoration
- Aimed to prevent visible freeze when exiting alt-screen apps

**Why removed:**
- Did not help with the freeze issue
- The freeze happens during xterm.js internal processing, not rendering
- Hiding the terminal doesn't prevent the main thread from blocking

**Code removed:**
```typescript
const ALT_SCREEN_EXIT_PATTERNS = ['\x1b[?1049l', '\x1b[?47l', '\x1b[?1047l'];

function containsAltScreenExit(data: string): boolean {
    return ALT_SCREEN_EXIT_PATTERNS.some(pattern => data.includes(pattern));
}

// In writeToTerminal():
if (containsAltScreenExit(data)) {
    tab.container.style.visibility = 'hidden';
    tab.term.write(data, () => {
        requestAnimationFrame(() => {
            tab.container.style.visibility = '';
        });
    });
}
```

**Also tried (not helpful):**
- Time-based write throttling (16ms minimum between writes)
- Scrollback reduction via query param (`?scrollback=N`)
- WebGL disable via query param (`?nowebgl`) - changed freeze to rapid scrolling
- Alt-screen ENTER detection (clear scrollback before save) - Claude Code doesn't use alt-screen

**Root cause identified:**
- Claude Code uses Ink (React for CLI), not alt-screen
- Ink sends mass escape sequences for full-screen redraws
- xterm.js throughput is only 5-35 MB/s, processes synchronously on main thread
- See "Scrollback Reduction + Write Pacing" below for the working solution

---

## Implemented Solutions

### 4. Watermark-Based Flow Control (Server-Side Backpressure)

**Location:** `frontend/src/services/ConnectionService.ts`, `porterminal/application/services/terminal_service.py`

**Problem:**
- xterm.js freezes when TUI apps like Claude Code (Ink) send heavy output
- xterm.js throughput is 5-35 MB/s, processes data synchronously on main thread
- Client-side pacing alone cannot solve the problem because data arrives faster than processing

**Research findings (from xterm.js source + VS Code):**
- xterm.js `WRITE_TIMEOUT_MS = 12ms` per processing cycle with internal yielding
- Multiple `write()` calls before first setTimeout ARE batched together
- VS Code uses watermark-based flow control with PTY pause/resume
- Root cause: Data arrival rate exceeds processing rate - only server-side control can fix this

**Solution: Watermark-based flow control**

The xterm.js recommended approach: track bytes in flight, pause server when overwhelmed.

**Frontend (ConnectionService.ts):**
```typescript
// Watermark-based flow control constants
const HIGH_WATERMARK = 100000;   // 100KB - send pause to server
const LOW_WATERMARK = 10000;     // 10KB - send ACK to server

interface TabConnectionState {
    watermark: number;        // Bytes written but not yet processed
    connectionGen: number;    // Detect stale callbacks after reconnect
    pauseSent: boolean;       // Track if we've sent pause to server
}

function writeWithFlowControl(tab, state, data) {
    const currentGen = state.connectionGen;
    state.watermark += data.length;

    tab.term.write(data, () => {
        if (currentGen !== state.connectionGen) return;  // Stale callback
        state.watermark = Math.max(0, state.watermark - data.length);

        // Resume server if caught up
        if (state.pauseSent && state.watermark < LOW_WATERMARK) {
            tab.ws.send(JSON.stringify({ type: 'ack' }));
            state.pauseSent = false;
        }
    });

    // Pause server if overwhelmed
    if (!state.pauseSent && state.watermark > HIGH_WATERMARK) {
        tab.ws.send(JSON.stringify({ type: 'pause' }));
        state.pauseSent = true;
    }
}
```

**Server (terminal_service.py):**
```python
@dataclass
class ConnectionFlowState:
    paused: bool = False
    pause_time: float | None = None

FLOW_PAUSE_TIMEOUT = 15.0  # Auto-resume after 15s

# In _send_to_connections:
for conn in connections:
    flow = self._flow_state.get(conn)
    if flow and flow.paused:
        # Auto-resume after timeout (dead client protection)
        if flow.pause_time and (time.time() - flow.pause_time) > FLOW_PAUSE_TIMEOUT:
            flow.paused = False
        else:
            continue  # Skip paused connection
    await conn.send_output(data)

# In _handle_json_message:
elif msg_type == "pause":
    flow.paused = True
    flow.pause_time = time.time()
elif msg_type == "ack":
    flow.paused = False
    flow.pause_time = None
```

**How it works:**
1. Client tracks watermark (bytes written to xterm.js but not yet processed)
2. When watermark exceeds 100KB, client sends `{type: "pause"}` to server
3. Server stops sending data to that connection (but continues reading PTY)
4. When watermark drops below 10KB, client sends `{type: "ack"}` to server
5. Server resumes sending to that connection
6. Auto-resume after 15s protects against dead clients

**Why this is the correct fix:**
- Addresses root cause: prevents data arrival rate from exceeding processing rate
- Same approach used by VS Code terminal
- xterm.js already has internal 12ms yielding - adding more client-side pacing doesn't help
- Server never pauses PTY reads - only pauses sends to slow clients

**Trade-offs:**
- Scrollback still reduced to 200 lines (for mobile)
- During bursts, terminal output may lag (but UI stays responsive)
- Server must track per-connection flow state

**What didn't work (Phase 1 attempts):**
- Sequential write pacing with rAF yielding - artificially limited throughput (~240KB/s)
- Client-side queue with 4KB chunks - doesn't prevent data arriving faster than processing
- Dropping oldest data in queue - loses output without solving root cause

---

## Related Issues

- **Issue #14:** Terminal jumps to top on mobile during input/output
  - Removing voice debouncing may help resolve this
  - Visual viewport handler was kept as it's needed for keyboard layout
