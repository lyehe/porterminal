# Frontend Features & Design Patterns

This document details the special designs and architectural patterns in the Porterminal frontend.

## Architecture Overview

The frontend uses a **factory + dependency injection** pattern with an event-driven architecture. All services are created via `createXxxService()` factories with dependencies passed as arguments.

```
main.ts (Bootstrap)
├── EventBus (core messaging)
├── ConfigService (server config)
├── ManagementService (control plane)
├── ConnectionService (data plane)
├── TabService (terminal rendering)
├── ResizeManager (debounced resize)
├── InputHandler (keyboard dispatch)
├── GestureRecognizer (touch dispatch)
├── ClipboardManager (copy/paste)
└── UI Components (overlays, buttons)
```

---

## 1. Dual WebSocket Architecture

Two separate WebSocket connections with distinct responsibilities:

| Connection | Endpoint | Purpose |
|------------|----------|---------|
| Control Plane | `/ws/management` | Tab lifecycle, auth, state sync |
| Data Plane | `/ws?tab_id=...&session_id=...` | Binary terminal I/O only |

**Custom Close Codes:**
- `4000` - TAB_ID_REQUIRED
- `4004` - TAB_NOT_FOUND
- `4005` - SESSION_ENDED

Backend-driven architecture: server controls tab state, frontend renders what server tells it.

---

## 2. Gesture Recognition System

Location: `frontend/src/gestures/`

### Supported Gestures

| Gesture | Threshold | Behavior |
|---------|-----------|----------|
| Long-press | 250ms | Start text selection mode |
| Double-tap | 300ms window, 30px distance | Word selection |
| Horizontal swipe | 25px min, 300ms max, 1.2x ratio | Arrow key navigation |
| Pinch-zoom | 2-finger touch | Font size adjustment (10-24px) |
| Momentum scroll | 0.95 deceleration per frame | Physics-based smooth scrolling |
| Single tap | - | Clear selection, focus terminal |

### Momentum Scroll Algorithm

```typescript
// Velocity smoothing with exponential moving average
scrollVelocity = scrollVelocity * 0.3 + instantVelocity * 0.7;

// Accumulator pattern for fractional scrolling
scrollAccumulator += deltaY * SCROLL_SENSITIVITY;  // 0.15 lines/pixel
const lines = Math.trunc(scrollAccumulator);
terminal.scrollLines(lines);
scrollAccumulator -= lines;  // Keep remainder
```

### Pinch-Zoom Strategy

1. During pinch: Apply CSS `transform: scale()` (visual only, no reflow)
2. On touchend: Apply actual `fontSize` change
3. If user was at bottom: Restore scroll position via `requestAnimationFrame`

---

## 3. Three-State Modifier System

Location: `frontend/src/input/ModifierManager.ts`

Each modifier (Ctrl, Alt, Shift) has three states:

```
┌─────────────────────────────────────────────┐
│  off ──single tap──► sticky ──keystroke──► off  │
│   │                                              │
│   └──double tap──► locked ──single tap──► off   │
└─────────────────────────────────────────────┘
```

- **off**: Modifier inactive
- **sticky**: Active for one keystroke, then auto-resets
- **locked**: Active until explicitly toggled off

Visual feedback via CSS classes: `.sticky`, `.locked`

---

## 4. Write Batching with requestAnimationFrame

Location: `frontend/src/services/ConnectionService.ts`

### Buffer Strategy

| Buffer | Max Size | Purpose |
|--------|----------|---------|
| Early buffer | 1MB | Data during `connecting` state |
| Write buffer | 256KB | Data during `connected` state |

All writes within one animation frame are combined into a single `terminal.write()` call.

### Multi-Frame Connection Handshake

```
Frame 0: Fit terminal + send resize
Frame 1: xterm.js layout completion
Frame 2: Flush buffered data (hidden)
Frame 3: Show terminal (remove opacity:0)
```

---

## 5. iOS-Specific Workarounds

### Delete Key Handling
iOS sends `beforeinput` event with `deleteContentBackward` type. Intercepted and converted to `\x7f` (backspace).

### Clipboard Fallback
Uses `document.execCommand('copy')` with a visible textarea (iOS requires on-screen element).

### Safari 18+ Predictions
Sets `writingsuggestions="false"` attribute to disable inline predictions.

### Virtual Keyboard Detection
Monitors `window.visualViewport` resize events to detect keyboard appearance and adjust layout.

---

## 6. Touch/Click Deduplication

Every interactive button uses the `touchUsed` flag pattern:

```typescript
button.addEventListener('touchstart', (e) => {
    touchUsed = true;
    e.preventDefault();
    handleAction();
}, { passive: false });

button.addEventListener('click', () => {
    if (touchUsed) { touchUsed = false; return; }
    handleAction();
});
```

Prevents double-firing from touch event followed by synthetic click event.

---

## 7. Hold-to-Repeat (Backspace)

Uses pointer events for cross-device compatibility:

- **Initial delay**: 400ms before repeat starts
- **Repeat interval**: 50ms between repeats
- **Cancellation**: `pointerup`, `pointerleave`, `pointercancel`

---

## 8. Hold-to-Close (Tabs)

Prevents accidental tab closure:

- **Hold duration**: 400ms
- **Visual feedback**: `holding` class → `ready` class
- **Cancellation**: `pointerleave` (swipe away gesture)

---

## 9. Text Selection Engine

Location: `frontend/src/gestures/SelectionHandler.ts`

### Coordinate Conversion
```typescript
const cellWidth = rect.width / terminal.cols;
const cellHeight = rect.height / terminal.rows;
const col = Math.floor(x / cellWidth);
const row = Math.floor(y / cellHeight);
```

### Features
- Multi-line selection with anchor tracking
- Word boundary expansion on double-tap
- Viewport offset handling for scrollback
- Floating copy button at touch release point

---

## 10. Text View Overlay

Location: `frontend/src/ui/TextViewOverlay.ts`

Provides readable text extraction from terminal buffer:

- Handles wrapped lines (joins without newlines)
- **Deduplication algorithm**: Removes xterm.js reflow artifacts
- Pinch-zoom with font range 6-32px
- Zoom buttons for single-finger adjustment

### Deduplication Logic
Detects and removes repeated content blocks that appear from terminal reflow operations.

---

## 11. Centralized Key Configuration

Location: `frontend/src/config/keys.ts`

All button definitions in one place:

```typescript
const TOOLBAR_ROW1: KeyConfig[] = [
    { key: 'Escape', label: 'Esc', sequence: '\x1b' },
    { key: '1', label: '1', sequence: '1' },
    // ...
];
```

Custom buttons from server config support complex sequences:
```typescript
// String, array of strings, or numbers (delay in ms)
send: ['echo hello', 100, '\r']  // Type, wait 100ms, press enter
```

Special tokens: `{CR}`, `{LF}`, `{ESC}`

---

## 12. Connection Resilience

### Reconnection Strategy
- Exponential backoff with max 5 attempts
- Base delay 1000ms, multiplied by attempt count
- Server rejection codes (4xxx) prevent reconnection

### Heartbeat
30-second ping/pong interval to keep connection alive.

### Visibility Change Handling
1. Reset modifier states
2. Reconnect management WebSocket first
3. Wait for state sync
4. Reconnect data plane connections

---

## 13. Resize Coordination

Location: `frontend/src/terminal/ResizeManager.ts`

### Debouncing
- Per-tab debounce timers (50ms default)
- Dimension deduplication (skip if unchanged)
- Buffer flush before any resize operation

### Triggers
- Window resize (50ms debounce)
- Orientation change (100ms delay for layout)
- Visual viewport change (keyboard appearance)
- Font size change (pinch-zoom)

---

## 14. Clipboard Management

Location: `frontend/src/clipboard/ClipboardManager.ts`

### Copy Strategy (Priority Order)
1. On touch devices: Try fallback `execCommand` first
2. Try `navigator.clipboard.writeText()`
3. Fallback to `execCommand('copy')`

### Deduplication
300ms window prevents duplicate copies of same text.

### iOS Fallback Requirements
- Textarea must be visible on-screen (not `display: none`)
- Uses Range API + `setSelectionRange()` for iOS selection model
- Cleanup: blur and remove element after copy

---

## 15. Typed Event Bus

Location: `frontend/src/core/events.ts`

TypeScript-enforced event/payload mapping:

```typescript
interface EventMap {
    'tab:created': { tab: Tab };
    'tab:switched': { tabId: number; tab: Tab };
    'modifier:changed': { modifier: ModifierKey; state: ModifierMode };
    'gesture:swipe': { direction: SwipeDirection };
    // ...
}
```

Features:
- Error isolation per handler (exceptions don't break other handlers)
- Unsubscribe function returned from `on()`
- `once()` for one-time subscriptions

---

## 16. Password Storage

Location: `frontend/src/utils/storage.ts`

Origin-hashed storage key using DJB2 hash:
```typescript
key = `ptn_auth_${hash(window.location.origin).toString(36)}`
```

Different tunnel URLs get separate credential storage. Graceful fallback when localStorage unavailable (private browsing).

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Gesture types | 6 |
| iOS workarounds | 4 |
| Buffer strategies | 3 |
| State machines | 3 |
| Deduplication patterns | 3 |
| WebSocket connections | 2 |

---

## File Index

| Path | Purpose |
|------|---------|
| `frontend/src/main.ts` | Bootstrap and service wiring |
| `frontend/src/services/ConnectionService.ts` | Data plane WebSocket |
| `frontend/src/services/ManagementService.ts` | Control plane WebSocket |
| `frontend/src/services/TabService.ts` | Terminal rendering |
| `frontend/src/gestures/GestureRecognizer.ts` | Touch gesture handling |
| `frontend/src/gestures/SelectionHandler.ts` | Text selection |
| `frontend/src/gestures/SwipeDetector.ts` | Swipe detection |
| `frontend/src/input/ModifierManager.ts` | Modifier state machine |
| `frontend/src/input/KeyMapper.ts` | Key sequence mapping |
| `frontend/src/config/keys.ts` | Button configuration |
| `frontend/src/clipboard/ClipboardManager.ts` | Copy/paste operations |
| `frontend/src/terminal/ResizeManager.ts` | Resize coordination |
| `frontend/src/core/events.ts` | Event bus |
| `frontend/src/ui/*.ts` | UI overlay components |
