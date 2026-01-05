# Frontend Design Fixes

This document details 5 design issues identified through Six Thinking Hats analysis and their fixes.

## Overview

| Issue | Type | Severity | File |
|-------|------|----------|------|
| [Error bypass buffer](#1-error-bypass-buffer) | Bug | High | ConnectionService.ts |
| [tab before declaration](#2-tab-before-declaration) | Refactor | Medium | TabService.ts |
| [setTimeout+rAF pattern](#3-settimeoutraf-pattern) | Refactor | Medium | ConnectionService.ts |
| [Voice timer leak](#4-voice-timer-leak) | Bug | Low | TabService.ts |
| [Buffer size limits](#5-buffer-size-limits) | Enhancement | Low | ConnectionService.ts |

---

## 1. Error Bypass Buffer

### Problem

Error messages wrote directly to terminal, bypassing the `writeBuffer` system:

```typescript
// BEFORE: ConnectionService.ts:328
case 'error':
    tab.term.write(`\r\n\x1b[31mError: ${msg.message}\x1b[0m\r\n`);
```

This caused **wrong message ordering**:

1. Binary data arrives → pushed to `writeBuffer`
2. Error JSON arrives → writes directly to terminal
3. rAF fires → flushes `writeBuffer` AFTER error

**Result**: Error appeared before the buffered content that preceded it chronologically.

### Fix

Flush the write buffer before displaying error:

```typescript
// AFTER: ConnectionService.ts:326-340
case 'error':
    console.error('Server error:', msg.message);
    // Flush pending writes first to maintain message ordering
    if (state.writeBuffer.length > 0) {
        const pending = state.writeBuffer.join('');
        state.writeBuffer = [];
        if (state.rafHandle !== null) {
            cancelAnimationFrame(state.rafHandle);
            state.rafHandle = null;
        }
        tab.term.write(pending);
    }
    tab.term.write(`\r\n\x1b[31mError: ${msg.message}\x1b[0m\r\n`);
    eventBus.emit('connection:error', { tabId: tab.id, error: msg.message });
    break;
```

---

## 2. tab Before Declaration

### Problem

iOS event handlers referenced `tab` before it was declared:

```typescript
// BEFORE: TabService.ts
// Line 276 - tab used in callback
textarea.addEventListener('beforeinput', (e) => {
    connectionService.sendInput(tab, '\x7f');  // tab not yet declared!
});

// Line 296 - tab declared here
const tab: Tab = { ... };
```

**Why it worked**: JavaScript closures capture variables by reference, and the callback only executes after `tab` is initialized.

**Why it's bad**:
- Confusing to read
- Maintenance hazard
- Could break if code is refactored

### Fix

Restructured `createLocalRender()` to declare `tab` before adding event listeners:

```typescript
// AFTER: TabService.ts:282-310

// 1. Create tab FIRST
const tab: Tab = {
    id,
    tabId: serverTab.id,
    // ...
};

// 2. NOW add iOS event handlers (tab is defined)
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
if (isIOS && textarea) {
    textarea.addEventListener('beforeinput', (e: InputEvent) => {
        if (e.inputType === 'deleteContentBackward') {
            e.preventDefault();
            connectionService.sendInput(tab, '\x7f');
        }
    }, { capture: true });
    // ...
}
```

---

## 3. setTimeout+rAF Pattern

### Problem

Triple-nested async pattern for showing terminal after buffer flush:

```typescript
// BEFORE: ConnectionService.ts:271-280
tab.term.write(combined, () => {
    setTimeout(() => {
        requestAnimationFrame(() => {
            tab.term.scrollToBottom();
            tab.container.style.opacity = '';
        });
    }, 0);
});
```

**Issues**:
- `setTimeout(0)` can be throttled to 1000ms in background tabs
- Semantically unclear why setTimeout is needed
- Relies on fragile timing assumptions

### Analysis

The xterm.js `write()` callback fires after **parsing**, not after **rendering**. The pattern was trying to wait for render completion, but `setTimeout(0)` doesn't guarantee anything about xterm's render cycle.

### Fix

Replaced with double-rAF which is semantically clearer:

```typescript
// AFTER: ConnectionService.ts:271-279
tab.term.write(combined, () => {
    // Double rAF: first frame for xterm.js render, second for paint
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            tab.term.scrollToBottom();
            tab.container.style.opacity = '';
        });
    });
});
```

**Why this works**:
- First rAF: queued after xterm.js's internal rAF (if any)
- Second rAF: guaranteed to be in the NEXT frame after xterm renders
- Not affected by setTimeout throttling in background tabs

---

## 4. Voice Timer Leak

### Problem

Voice debounce timer was a local variable with no cleanup on tab close:

```typescript
// BEFORE: TabService.ts (inside createLocalRender)
let voiceTimer: ReturnType<typeof setTimeout> | null = null;

// Timer set in onData handler:
voiceTimer = setTimeout(() => {
    processAndSend(voiceBuffer);
}, 150);

// removeLocalRender() had NO cleanup for voiceTimer
```

**Consequence**: If tab closed while timer pending, callback fires with disposed tab, potentially causing errors or sending to wrong connection.

### Fix

Store voice timers in a Map for proper cleanup:

```typescript
// AFTER: TabService.ts

// 1. Add Map at module level (line 106)
const voiceTimers = new Map<number, ReturnType<typeof setTimeout>>();

// 2. Use Map in onData handler (lines 341-353)
const existingTimer = voiceTimers.get(tab.id);
if (existingTimer) {
    clearTimeout(existingTimer);
}
const timer = setTimeout(() => {
    // ...
    voiceTimers.delete(tab.id);
}, VOICE_DEBOUNCE_MS);
voiceTimers.set(tab.id, timer);

// 3. Cleanup in removeLocalRender (lines 412-417)
const voiceTimer = voiceTimers.get(tab.id);
if (voiceTimer) {
    clearTimeout(voiceTimer);
    voiceTimers.delete(tab.id);
}
```

---

## 5. Buffer Size Limits

### Problem

Neither `earlyBuffer` nor `writeBuffer` had size limits:

```typescript
// BEFORE: ConnectionService.ts
if (state.state === 'connecting') {
    state.earlyBuffer.push(text);  // Unbounded!
}
```

**Risk**: A malicious or malfunctioning server could send megabytes of data during connection, causing browser memory exhaustion.

### Fix

Added size limits with oldest-data eviction:

```typescript
// AFTER: ConnectionService.ts:68-82

// Constants
const MAX_EARLY_BUFFER_SIZE = 1024 * 1024;  // 1MB
const MAX_WRITE_BUFFER_SIZE = 256 * 1024;   // 256KB

// Helper functions
function getBufferSize(buffer: string[]): number {
    return buffer.reduce((acc, s) => acc + s.length, 0);
}

function trimBuffer(buffer: string[], maxSize: number): void {
    while (buffer.length > 1 && getBufferSize(buffer) > maxSize) {
        buffer.shift();  // Remove oldest entries
    }
}

// Usage (lines 309-315)
if (state.state === 'connecting') {
    state.earlyBuffer.push(text);
    trimBuffer(state.earlyBuffer, MAX_EARLY_BUFFER_SIZE);
} else if (state.state === 'connected') {
    state.writeBuffer.push(text);
    trimBuffer(state.writeBuffer, MAX_WRITE_BUFFER_SIZE);
    scheduleFlush(tab, state);
}
```

---

## Analysis Method: Six Thinking Hats

These issues were identified using parallel agent analysis with six perspectives:

| Hat | Focus | Key Findings |
|-----|-------|--------------|
| White (Facts) | Data & research | xterm.js callback fires after parse, not render. setTimeout can be throttled. |
| Red (Emotions) | Gut reactions | Code felt fragile, "controlled chaos", nervous to modify |
| Black (Risks) | Problems | Memory exhaustion, wrong ordering, timer leaks, maintenance hazards |
| Yellow (Benefits) | Value | Each pattern solved real problems (flicker, iOS voice, etc.) |
| Green (Creativity) | Alternatives | Double-rAF, state machines, priority queues, Maps for cleanup |
| Blue (Process) | Synthesis | Scoring framework, prioritization, final decisions |

---

## Testing

After fixes:
- `npm run build` in frontend/ - **Pass**
- `uv run pytest` - **174 passed, 10 skipped**

## Files Modified

- `frontend/src/services/ConnectionService.ts`
- `frontend/src/services/TabService.ts`
