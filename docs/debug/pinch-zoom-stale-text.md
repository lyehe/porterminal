# Pinch Zoom Stale Text Issue

## Problem

When pinch zooming (in or out) on mobile devices, xterm.js displays stale text from previously cleared sessions. This happens after running `/clear` in Claude Code or the shell `clear` command.

## Root Cause

When font size changes during pinch zoom, xterm.js performs an **internal async buffer reflow**. This reflow has no public API to signal completion. The viewport position can drift unpredictably during this async operation, exposing old scrollback content.

```
Before clear:          After clear:           After pinch zoom:
┌─────────────┐        ┌─────────────┐        ┌─────────────┐
│ old output  │←scroll │             │        │ old output  │←exposed!
│ old output  │ back   │             │        │ old output  │
│ old output  │        │             │        ├─────────────┤
├─────────────┤        │             │        │ $ prompt    │
│ $ prompt    │        │ $ prompt    │←cursor │             │
│             │        │             │        │             │
└─────────────┘        └─────────────┘        └─────────────┘
```

Why the shell `clear` command exposes this:
1. **ANSI clear only clears visible screen** - ESC[2J + ESC[H clears display and moves cursor home
2. **Scrollback buffer is preserved** - xterm.js intentionally keeps history
3. **Font size change triggers async buffer reflow** - xterm.js recalculates dimensions
4. **Viewport drifts during async reflow** - no way to synchronize with completion

## Failed Attempts (v0.4.0)

The following timing-based workarounds were tried but **failed** because xterm.js's internal async operations don't align with browser rendering frames:

### 1. "Near bottom" detection (5-line tolerance)
```typescript
const nearBottom = buffer.baseY - buffer.viewportY <= 5;
```
**Why it failed:** Doesn't address the timing issue - viewport still drifts during reflow.

### 2. scrollToBottom during pinch touchmove with rAF
```typescript
if (pinchStartedAtBottom) {
    requestAnimationFrame(() => term.scrollToBottom());
}
```
**Why it failed:** rAF fires before xterm.js finishes its internal async buffer update.

### 3. Triple rAF + setTimeout after fit()
```typescript
requestAnimationFrame(() => {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            scrollToBottom();
            setTimeout(scrollToBottom, 50);
        });
    });
});
```
**Why it failed:** Arbitrary timing - xterm.js async operations don't align with rAF frames. Sometimes the reflow takes longer than 3 frames + 50ms, sometimes it's faster.

**Core problem:** All these are timing heuristics trying to win a race against an unpredictable async operation. This is fundamentally unreliable.

## Potential Solutions

### Option A: CSS Transform Zoom (Recommended)

Instead of changing `term.options.fontSize` during pinch, use CSS transforms for visual scaling:

```typescript
// During pinch touchmove:
container.style.transform = `scale(${scale})`;
container.style.transformOrigin = `${centerX}px ${centerY}px`;

// On touchend: apply actual font size and reset transform
term.options.fontSize = newSize;
container.style.transform = '';
fit();
```

**Pros:** No buffer reflow during gesture - smooth visual zoom
**Cons:** Slight quality loss during gesture (pixels are scaled, not re-rendered)

### Option B: Listen to xterm.js onRender

Wait for xterm.js `onRender` callback instead of guessing timing:

```typescript
const onRenderDisposable = term.onRender(() => {
    term.scrollToBottom();
    onRenderDisposable.dispose();
});
term.options.fontSize = newSize;
```

**Pros:** Synchronized with xterm.js rendering
**Cons:** May need multiple cycles for complete buffer stabilization

### Option C: Clear Scrollback on Screen Clear

Detect screen clear escape sequences and call `term.clear()`:

```typescript
term.onData((data) => {
    if (data.includes('\x1b[2J') || data.includes('\x1b[3J')) {
        term.clear(); // Actually clears scrollback
    }
});
```

**Pros:** Eliminates stale content entirely
**Cons:** Loses legitimate history users may want

### Option D: Throttle Font Changes

Only apply font size changes at the end of pinch, not during:

```typescript
// touchmove: just track target size, don't apply
targetFontSize = Math.round(state.initialFontSize * scale);

// touchend: apply final size once
if (targetFontSize !== term.options.fontSize) {
    term.options.fontSize = targetFontSize;
    fit();
}
```

**Pros:** Single reflow at end, easier to synchronize
**Cons:** No visual feedback during pinch gesture

## Current Status

**UNRESOLVED** - The onResize approach failed.

### Failed Attempt: onResize callback (v0.4.0)

```typescript
if (wasAtBottom) {
    const disposable = tab.term.onResize(() => {
        tab.term.scrollToBottom();
        disposable.dispose();
    });
}
tab.fitAddon.fit();
```

**Why it failed:** `onResize` fires **synchronously** when `resize()` is called, **BEFORE** buffer reflow completes. The actual sequence is:

```
fit() → resize(cols, rows) → onResize fires → [ASYNC] buffer reflow → render
                              ↑
                              scrollToBottom() called here, but buffer
                              position will be overwritten by reflow
```

The buffer reflow is an internal async operation that recalculates line wrapping after dimensions change. During this reflow, the viewport position may drift, overwriting any scroll position we set.

### Actual Root Cause

Two factors combine to cause this issue:

1. **Shell `clear` doesn't clear scrollback** - The ANSI sequence ESC[2J only clears the visible screen. The scrollback buffer (old content) is preserved by design.

2. **Buffer reflow exposes hidden content** - When font size changes, xterm.js recalculates line wrapping. This async operation can change the relationship between content and viewport, exposing old scrollback.

### Solution: onRender with persistence

Use `onRender` instead of `onResize`, and scroll repeatedly to overcome the async reflow:

```typescript
if (wasAtBottom) {
    let count = 0;
    const disposable = tab.term.onRender(() => {
        tab.term.scrollToBottom();
        if (++count >= 5) disposable.dispose();
    });
    // Fallback timeout in case onRender doesn't fire enough
    setTimeout(() => {
        disposable.dispose();
        tab.term.scrollToBottom();
    }, 200);
}
```

`onRender` fires after each render cycle, so scrolling on every render until the buffer stabilizes keeps the viewport at bottom.

## Implementation (Current) - FAILED

1. **CSS transform during pinch** (GestureRecognizer.ts):
   - touchstart: Record pinchStartedAtBottom, get container ref
   - touchmove: Apply CSS `scale()` transform (no buffer reflow)
   - touchend: Reset transform, apply final fontSize, call scheduleFitAfterFontChange(wasAtBottom)

2. **onRender with persistence** (main.ts):
   - If wasAtBottom, attach onRender listener
   - Scroll to bottom on each render (up to 5 times)
   - Fallback timeout after 200ms ensures cleanup

### Why onRender ALSO Failed

The onRender approach was added but **still fails** because:

1. **Scope too narrow**: Only applied to `scheduleFitAfterFontChange` (pinch zoom). Other resize triggers don't have viewport restoration:
   - `window.addEventListener('resize')` → calls `fit()` without scrollToBottom
   - `visualViewport.addEventListener('resize')` → calls `fit()` without scrollToBottom
   - `orientationchange` → calls `fit()` without scrollToBottom
   - `switchToTab` → has scrollToBottom but BEFORE fit completes

2. **Focus now triggers stale text** because:
   - User taps terminal → focus event
   - iOS keyboard appears → `visualViewport` resize fires
   - `fit()` called after 50ms debounce → buffer reflow
   - Viewport drifts, old scrollback exposed
   - **No scrollToBottom in this path!**

3. **onRender timing is still unreliable**: Even when onRender fires, the buffer reflow may not be complete. xterm.js internal async operations don't align with render callbacks.

## Actual Root Cause Analysis

The issue stems from **two independent problems**:

### Problem 1: Shell `clear` only clears visible screen
```
ESC[2J + ESC[H = Clear display + cursor home
```
This does NOT touch the scrollback buffer. Old content remains in memory.

### Problem 2: Multiple unprotected resize paths

Every place that calls `fitAddon.fit()` can trigger buffer reflow:

| Location | Has viewport restoration? |
|----------|---------------------------|
| scheduleFitAfterFontChange | ✅ onRender (but unreliable) |
| window resize | ❌ No |
| visualViewport resize | ❌ No |
| orientationchange | ❌ No |
| switchToTab | ⚠️ scrollToBottom before fit completes |
| ConnectionService onopen | ✅ In callback |

**Focus exposes stale text because keyboard show/hide triggers visualViewport resize, which has NO viewport restoration.**

## Proposed Fix: Centralized Smart Resize

Instead of sprinkling timing hacks everywhere, create a single function that handles all resizes:

```typescript
function performResize(tab: Tab): void {
    // 1. Check if at bottom BEFORE resize
    const buffer = tab.term.buffer.active;
    const wasAtBottom = buffer.baseY - buffer.viewportY <= 2;

    // 2. Flush pending writes
    connectionService.flushWriteBuffer(tab);

    // 3. Do the resize
    tab.fitAddon.fit();

    // 4. If was at bottom, aggressively restore position
    if (wasAtBottom) {
        // Immediate scroll
        tab.term.scrollToBottom();

        // onRender scroll (catches async reflow)
        let count = 0;
        const disposable = tab.term.onRender(() => {
            tab.term.scrollToBottom();
            if (++count >= 10) disposable.dispose();
        });

        // Longer timeout for slow reflows
        setTimeout(() => {
            disposable.dispose();
            tab.term.scrollToBottom();
        }, 500);
    }
}
```

Then replace ALL instances of `tab.fitAddon.fit()` with `performResize(tab)`.

## FAILED FIX #1: Escape sequence detection (pattern matching)

Attempted to detect screen clear sequences (`ESC[2J`) and clear scrollback:

```typescript
const CLEAR_SCREEN_PATTERN = /\x1b\[2J|\x1b\[3J/;
function writeToTerminal(tab, data, callback) {
    if (CLEAR_SCREEN_PATTERN.test(data)) {
        tab.term.clear();
    }
    tab.term.write(data, callback);
}
```

**Why it failed:**

1. **Escape sequence splitting**: WebSocket messages can split escape sequences across chunks.
2. **Race condition**: Resize can trigger BEFORE the rAF flush processes the clear sequence.
3. **Pattern variations**: Different shells/systems output different sequences.

---

## NEW INSIGHT: Issue is NOT just resize

The stale text issue is triggered by **any operation that causes viewport recalculation**, not just resize:

- Typing `/` in Claude Code shows a guide menu
- The escape sequences to draw the guide trigger viewport drift
- Old scrollback becomes visible

This means resize-focused fixes are insufficient. The problem is fundamental to how xterm.js handles viewport position during certain write operations.

## CURRENT FIX: Post-write buffer state detection

Instead of detecting escape sequences (unreliable), detect the **result** - an empty visible area:

```typescript
function isVisibleAreaEmpty(term: Terminal): boolean {
    const buffer = term.buffer.active;
    for (let y = 0; y < term.rows; y++) {
        const line = buffer.getLine(buffer.baseY + y);
        if (line) {
            const content = line.translateToString().trim();
            if (content.length > 4) return false; // Allow short prompts
        }
    }
    return true;
}

function writeToTerminal(tab: Tab, data: string, callback?: () => void): void {
    tab.term.write(data, () => {
        // After write completes, check if visible area is now empty
        const buffer = tab.term.buffer.active;
        const hasScrollback = buffer.baseY > 0;

        if (hasScrollback && isVisibleAreaEmpty(tab.term)) {
            // Screen was just cleared - remove stale scrollback
            tab.term.clear();
        }

        callback?.();
    });
}
```

**Why this should work:**

1. Checks buffer state AFTER write completes (no race condition)
2. Detects the result (empty screen) not the cause (escape sequence)
3. Runs synchronously in write callback before next operation
4. Clears scrollback immediately when screen becomes empty

---

# Deep Dive: xterm.js Rendering Architecture

## Single Source of Truth

The **Buffer** is the single source of truth for what appears on screen.

```
┌─────────────────────────────────────────────────────────────┐
│                     terminal.buffer.active                   │
├─────────────────────────────────────────────────────────────┤
│  lines[0]      │ "$ ls -la"                    │ scrollback │
│  lines[1]      │ "total 128"                   │ scrollback │
│  lines[2]      │ "drwxr-xr-x  5 user ..."     │ scrollback │
│  ...           │ ...                           │ scrollback │
│  lines[999]    │ "file.txt"                    │ scrollback │
├─────────────────────────────────────────────────────────────┤
│  lines[1000]   │ "$ "          ← baseY=1000   │ visible    │
│  lines[1001]   │ ""                            │ visible    │
│  ...           │ ""                            │ visible    │
│  lines[1023]   │ ""                            │ visible    │
└─────────────────────────────────────────────────────────────┘
                        ↑
                   viewportY=1000 (what's shown on screen)
```

### Key Properties

| Property | Description |
|----------|-------------|
| `buffer.lines` | Array of all rows (scrollback + visible) |
| `buffer.baseY` | Index where active content starts (end of scrollback) |
| `buffer.viewportY` | Index of top visible row |
| `buffer.cursorY` | Cursor row relative to viewport |
| `term.rows` | Number of visible rows |

### Invariants

- At bottom: `viewportY === baseY`
- Scrolled up: `viewportY < baseY`
- Scrollback size: `baseY` rows
- Visible area: `viewportY` to `viewportY + rows - 1`

## Rendering Pipeline

```
1. Data arrives (WebSocket)
         ↓
2. term.write(data)
         ↓
3. Parser processes escape sequences
         ↓
4. Buffer modified (lines[], cursor position)
         ↓
5. Renderer notified
         ↓
6. Renderer reads buffer[viewportY : viewportY+rows]
         ↓
7. Paints to canvas/DOM
```

## What Happens During Resize (fit())

```
Before: 80 cols, 24 rows
┌──────────────────────────────────────────────────────────────┐
│ Long line that wraps to multiple rows in 80 column terminal  │ ← 1 logical line
│ but is really just one line of text                          │   = 2 physical rows
└──────────────────────────────────────────────────────────────┘

After: 120 cols, 30 rows
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Long line that wraps to multiple rows in 80 column terminal but is really just one   │ ← same line
│ line of text                                                                          │   = 2 rows still
└──────────────────────────────────────────────────────────────────────────────────────┘

OR if line fits now:
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Long line that wraps to multiple rows in 80 column terminal but is really just one line of text │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                                                                         ↑ 1 row now!
```

### Reflow Process

1. New dimensions set on terminal
2. All lines re-evaluated for wrapping
3. Physical row count may CHANGE
4. `baseY` recalculated based on new row count
5. `viewportY` adjusted to maintain "relative" position
6. **This adjustment is IMPRECISE** - viewport can drift

## Why Stale Text Appears

After `clear` command:

```
Buffer State:
┌─────────────────────────────────────────────────────────────┐
│  lines[0-999]  │ OLD CONTENT (scrollback preserved!)        │
├─────────────────────────────────────────────────────────────┤
│  lines[1000]   │ "$ "                          ← baseY=1000 │
│  lines[1001+]  │ "" (empty)                                 │
└─────────────────────────────────────────────────────────────┘
                   viewportY=1000 (showing empty screen + prompt)
```

**The scrollback STILL EXISTS.** ESC[2J only clears visible area.

During resize/reflow:
1. Scrollback rows reflow (width changes)
2. Total row count might change (800 rows → 750 rows after less wrapping)
3. `viewportY` adjustment has rounding/edge cases
4. `viewportY` might become 998 instead of staying at effective "bottom"
5. Now showing `lines[998-1021]` which includes OLD scrollback content!

```
After resize (viewport drifted):
┌─────────────────────────────────────────────────────────────┐
│  lines[998]    │ "some old command output"    ← NOW VISIBLE │
│  lines[999]    │ "more old stuff"             ← NOW VISIBLE │
│  lines[1000]   │ "$ "                                       │
│  lines[1001+]  │ ""                                         │
└─────────────────────────────────────────────────────────────┘
```

## The REAL Fix: Buffer State Detection

Instead of detecting escape sequences (unreliable), detect the **buffer state**:

```typescript
function isVisibleAreaEmpty(term: Terminal): boolean {
    const buffer = term.buffer.active;
    for (let y = 0; y < term.rows; y++) {
        const line = buffer.getLine(buffer.baseY + y);
        if (line) {
            const content = line.translateToString().trim();
            // Allow prompt-only lines ($ or similar)
            if (content.length > 4) return false;
        }
    }
    return true;
}

function performResize(tab: Tab): void {
    const buffer = tab.term.buffer.active;
    const wasAtBottom = buffer.baseY - buffer.viewportY <= 2;

    connectionService.flushWriteBuffer(tab);

    // KEY: If at bottom AND visible area is empty, clear scrollback
    // This targets the post-clear state specifically
    if (wasAtBottom && isVisibleAreaEmpty(tab.term)) {
        tab.term.clear();
    }

    tab.fitAddon.fit();

    if (wasAtBottom) {
        tab.term.scrollToBottom();
    }
}
```

**Why this works:**

1. Checks buffer state, not escape sequences
2. Only clears scrollback when:
   - User was at bottom (normal use, not scrolled up reading history)
   - Visible area is empty (post-clear state)
3. Runs BEFORE fit(), so no race condition
4. Preserves history during normal usage

**Trade-off:** Loses scrollback when resizing with empty visible area. This is acceptable because empty visible area typically means user just cleared.

## Files Changed

- `frontend/src/services/ConnectionService.ts` - Post-write buffer state detection
- `frontend/src/main.ts` - Simplified scheduleFitAfterFontChange
- `docs/debug/pinch-zoom-stale-text.md` - This analysis document
