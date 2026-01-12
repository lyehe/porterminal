# Touch Scrolling on Mobile Devices

## Problem

Touch scrolling (swipe up/down to scroll terminal history) was not working on mobile devices.

## Investigation

### Initial Assumptions (Wrong)

The code comments suggested that v0.2.0 had working touch scroll via:
- CSS `touch-action: pan-y` allowing native browser scroll
- xterm.js handling scrolling "via wheel events"

### Reality (Found via Git History Analysis)

**v0.2.0 never had working touch scroll.** Three-agent investigation revealed:

| Component | v0.2.0 State | Impact |
|-----------|--------------|--------|
| CSS `touch-action` | `none` on body, terminal-container, xterm-viewport | Blocked all native touch gestures |
| JS scroll handling | None - no `scrollLines()`, no wheel events | No fallback for touch |
| Code comments | "vertical swipes should scroll normally" | Intent, not reality |

The comment "xterm.js handles scrolling via wheel events" was misleading - wheel events work for mouse/trackpad, not touch.

## Root Cause

1. **CSS `touch-action: none`** blocks native browser touch scrolling
2. **xterm.js** doesn't provide touch scroll out-of-the-box when touch-action is disabled
3. **No JavaScript implementation** existed to handle touch scrolling programmatically

## Why Native CSS Approach Failed

We tried changing CSS to `touch-action: pan-y` to enable native scrolling:

```css
/* Attempted fix - didn't work */
#terminal .xterm-viewport {
    touch-action: pan-y;
    -webkit-overflow-scrolling: touch;
}
```

This failed because:
1. Parent elements with `touch-action: none` block children's touch-action
2. Even with correct CSS, `e.stopPropagation()` in GestureRecognizer blocked events from reaching xterm-viewport
3. xterm.js internal structure doesn't play well with native touch scroll

## Solution: JavaScript-based Touch Scrolling

Implemented manual scroll handling in `GestureRecognizer.ts`:

### Key Changes

```typescript
// New state variables
let isScrolling = false;
let lastScrollY = 0;
let scrollAccumulator = 0;

// In pointermove handler
if (isScrolling && !state.isSelecting) {
    const term = callbacks.getActiveTerminal();
    if (term) {
        const deltaY = lastScrollY - e.clientY;
        lastScrollY = e.clientY;

        // Accumulate and scroll by lines
        scrollAccumulator += deltaY * SCROLL_SENSITIVITY;
        const linesToScroll = Math.trunc(scrollAccumulator);
        if (linesToScroll !== 0) {
            term.scrollLines(linesToScroll);
            scrollAccumulator -= linesToScroll;
        }
    }
}
```

### Gesture Detection Logic

```
pointerdown
    ↓
pointermove (movement > 20px threshold)
    ↓
    ├── dy > dx → Enter SCROLL mode → term.scrollLines()
    └── dx > dy → Stay in SWIPE mode → Arrow keys on pointerup

Long press (250ms) without movement → Enter SELECTION mode
```

### Momentum/Acceleration Scrolling

When the user lifts their finger while scrolling, momentum continues with deceleration:

```typescript
// Velocity tracking during scroll
const now = performance.now();
const deltaY = lastScrollY - e.clientY;
const deltaTime = now - lastScrollTime;

if (deltaTime > 0) {
    const instantVelocity = deltaY / deltaTime * 16; // Normalize to ~60fps
    // Exponential moving average for smooth velocity
    scrollVelocity = scrollVelocity * 0.3 + instantVelocity * 0.7;
}

// Momentum animation on pointerup
function startMomentumScroll(): void {
    function animate(): void {
        scrollAccumulator += scrollVelocity * SCROLL_SENSITIVITY;
        const linesToScroll = Math.trunc(scrollAccumulator);
        if (linesToScroll !== 0) {
            term.scrollLines(linesToScroll);
            scrollAccumulator -= linesToScroll;
        }
        scrollVelocity *= SCROLL_DECELERATION; // Apply friction
        if (Math.abs(scrollVelocity) >= SCROLL_MIN_VELOCITY) {
            requestAnimationFrame(animate);
        }
    }
    requestAnimationFrame(animate);
}
```

### Configuration

```typescript
const SCROLL_SENSITIVITY = 0.15;    // Lines per pixel of movement
const SCROLL_DECELERATION = 0.95;   // Velocity multiplier per frame (0.95 = slow stop, 0.8 = fast stop)
const SCROLL_MIN_VELOCITY = 0.5;    // Stop momentum when velocity drops below this
const MOVE_THRESHOLD = 20;          // Pixels before gesture type is determined
```

## CSS Configuration

All touch handling disabled at CSS level, JS handles everything:

```css
html, body {
    touch-action: none;
    overscroll-behavior: none;
}

#terminal-container {
    touch-action: none;
}

#terminal .xterm-viewport {
    touch-action: none;
}
```

## Gesture Summary

| Gesture | Action |
|---------|--------|
| Vertical swipe | Scroll terminal history (with momentum) |
| Quick flick up/down | Fast scroll with momentum deceleration |
| Horizontal swipe | Send arrow key (left/right) |
| Tap | Focus terminal |
| Double-tap | Select word |
| Long press + drag | Text selection |
| Two-finger pinch | Font size zoom |
| Touch during momentum | Immediately stops momentum scroll |

## Files Modified

- `frontend/src/gestures/GestureRecognizer.ts` - Added scroll handling
- `frontend/src/styles/index.css` - Ensured `touch-action: none` everywhere

## Testing

1. Run terminal with some scrollback history (e.g., `ls -la` multiple times)
2. Touch and drag vertically - terminal should scroll
3. Verify other gestures still work (tap to focus, horizontal swipe for arrows)
