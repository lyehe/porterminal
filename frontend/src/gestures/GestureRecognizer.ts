/**
 * Gesture Recognizer - Orchestrates touch gesture handling
 * Single Responsibility: Gesture detection and dispatch
 */

import type { Terminal } from '@xterm/xterm';
import type { GestureState, SwipeDirection } from '@/types';
import type { EventBus } from '@/core/events';
import type { SwipeDetector } from './SwipeDetector';
import type { SelectionHandler } from './SelectionHandler';

/** Gesture timing constants */
const LONG_PRESS_MS = 250;
const DOUBLE_TAP_MS = 300;
const DOUBLE_TAP_DISTANCE = 30;
const MOVE_THRESHOLD = 20;
const MIN_FONT_SIZE = 10;
const MAX_FONT_SIZE = 24;

export interface GestureCallbacks {
    /** Get active terminal */
    getActiveTerminal: () => Terminal | null;
    /** Send arrow key */
    sendArrowKey: (direction: SwipeDirection) => void;
    /** Show copy button with text at position */
    showCopyButton: (text: string, x: number, y: number) => void;
    /** Focus terminal */
    focusTerminal: () => void;
    /** Schedule resize after font change */
    scheduleFitAfterFontChange: () => void;
}

export interface GestureRecognizer {
    /** Attach gesture handlers to container */
    attach(container: HTMLElement): void;
    /** Detach gesture handlers */
    detach(): void;
    /** Check if touch gesture is active */
    isGestureActive(): boolean;
}

/**
 * Create a gesture recognizer instance
 */
export function createGestureRecognizer(
    eventBus: EventBus,
    swipeDetector: SwipeDetector,
    selectionHandler: SelectionHandler,
    callbacks: GestureCallbacks
): GestureRecognizer {
    const state: GestureState = {
        initialDistance: 0,
        initialFontSize: 14,
        isSelecting: false,
        longPressTimer: null,
        startX: 0,
        startY: 0,
        startTime: 0,
        fontSizeChanged: false,
        lastTapTime: 0,
        lastTapX: 0,
        lastTapY: 0,
        selectAnchorCol: 0,
        selectAnchorRow: 0,
        pointerId: null,
    };

    let touchGestureActive = false;
    let attachedContainer: HTMLElement | null = null;

    // Event handler references for cleanup
    const handlers: {
        pointerdown?: (e: PointerEvent) => void;
        pointermove?: (e: PointerEvent) => void;
        pointerup?: (e: PointerEvent) => void;
        pointercancel?: (e: PointerEvent) => void;
        touchstart?: (e: TouchEvent) => void;
        touchmove?: (e: TouchEvent) => void;
        touchend?: (e: TouchEvent) => void;
        mousedown?: (e: MouseEvent) => void;
        mousemove?: (e: MouseEvent) => void;
        mouseup?: (e: MouseEvent) => void;
    } = {};

    function clearLongPressTimer(): void {
        if (state.longPressTimer) {
            clearTimeout(state.longPressTimer);
            state.longPressTimer = null;
        }
    }

    return {
        attach(container: HTMLElement): void {
            attachedContainer = container;

            // Pointer events (primary for iOS compatibility)
            handlers.pointerdown = (e: PointerEvent) => {
                if (e.pointerType === 'mouse') return;

                // Don't prevent default immediately - allow scrolling
                // Only capture pointer for tracking, not blocking

                touchGestureActive = true;
                state.startX = e.clientX;
                state.startY = e.clientY;
                state.startTime = Date.now();
                state.isSelecting = false;
                state.pointerId = e.pointerId;

                clearLongPressTimer();
                const startX = e.clientX;
                const startY = e.clientY;

                state.longPressTimer = setTimeout(() => {
                    const term = callbacks.getActiveTerminal();
                    if (term && touchGestureActive) {
                        state.isSelecting = true;
                        // Capture pointer only when entering selection mode
                        try {
                            container.setPointerCapture(e.pointerId);
                        } catch { /* ignore */ }

                        const pos = selectionHandler.touchToPosition(term, startX, startY);
                        state.selectAnchorCol = pos.col;
                        state.selectAnchorRow = pos.row;

                        selectionHandler.startSelection(term, pos.col, pos.row);
                    }
                }, LONG_PRESS_MS);
            };

            handlers.pointermove = (e: PointerEvent) => {
                if (e.pointerType === 'mouse') return;
                if (!touchGestureActive) return;

                const dx = Math.abs(e.clientX - state.startX);
                const dy = Math.abs(e.clientY - state.startY);
                const elapsed = Date.now() - state.startTime;

                // Cancel long-press if moved significantly
                if (!state.isSelecting && (dx > MOVE_THRESHOLD || dy > MOVE_THRESHOLD)) {
                    clearLongPressTimer();
                }

                // Detect fast horizontal swipe and prevent default
                // Only horizontal swipes trigger arrows; vertical swipes should scroll normally
                if (!state.isSelecting && elapsed < 300 && dx > 20 && dx > dy * 1.2) {
                    e.preventDefault();
                    e.stopPropagation();
                    return;
                }

                // Only prevent default and extend selection when in selection mode
                if (state.isSelecting) {
                    e.preventDefault();
                    e.stopPropagation();

                    const term = callbacks.getActiveTerminal();
                    if (term) {
                        const currentPos = selectionHandler.touchToPosition(term, e.clientX, e.clientY);
                        selectionHandler.extendSelection(
                            term,
                            state.selectAnchorCol,
                            state.selectAnchorRow,
                            currentPos.col,
                            currentPos.row
                        );
                    }
                }
                // Normal movement: allow scrolling (don't prevent default)
            };

            handlers.pointerup = (e: PointerEvent) => {
                if (e.pointerType === 'mouse') return;

                if (state.pointerId) {
                    try {
                        container.releasePointerCapture(state.pointerId);
                    } catch { /* ignore */ }
                    state.pointerId = null;
                }

                e.stopPropagation();
                clearLongPressTimer();

                const dx = Math.abs(e.clientX - state.startX);
                const dy = Math.abs(e.clientY - state.startY);
                const wasTap = dx < MOVE_THRESHOLD && dy < MOVE_THRESHOLD;
                const now = Date.now();
                const duration = now - state.startTime;

                const wasSelecting = state.isSelecting;
                state.isSelecting = false;

                const term = callbacks.getActiveTerminal();

                // Handle selection completion
                if (wasSelecting && term) {
                    const selection = selectionHandler.getSelection(term);
                    if (selection) {
                        callbacks.showCopyButton(selection, e.clientX, e.clientY);
                    }
                    setTimeout(() => { touchGestureActive = false; }, 100);
                    return;
                }

                // Check for swipe
                const swipeResult = swipeDetector.detect(
                    state.startX, state.startY,
                    e.clientX, e.clientY,
                    duration
                );

                if (swipeResult) {
                    callbacks.sendArrowKey(swipeResult.direction);
                    eventBus.emit('gesture:swipe', { direction: swipeResult.direction });
                    setTimeout(() => { touchGestureActive = false; }, 100);
                    return;
                }

                // Handle taps
                if (wasTap && term) {
                    const tapDistance = Math.hypot(
                        e.clientX - state.lastTapX,
                        e.clientY - state.lastTapY
                    );

                    if (now - state.lastTapTime < DOUBLE_TAP_MS && tapDistance < DOUBLE_TAP_DISTANCE) {
                        // Double-tap: select word
                        const pos = selectionHandler.touchToPosition(term, e.clientX, e.clientY);
                        const row = pos.row + Math.floor(term.buffer.active.viewportY);
                        selectionHandler.selectWordAt(term, pos.col, row);
                        state.lastTapTime = 0;

                        const wordSelection = selectionHandler.getSelection(term);
                        if (wordSelection) {
                            callbacks.showCopyButton(wordSelection, e.clientX, e.clientY);
                        }
                    } else {
                        if (selectionHandler.hasSelection(term)) {
                            selectionHandler.clearSelection(term);
                        }
                        state.lastTapTime = now;
                        state.lastTapX = e.clientX;
                        state.lastTapY = e.clientY;
                        callbacks.focusTerminal();
                    }
                }

                setTimeout(() => { touchGestureActive = false; }, 100);
            };

            handlers.pointercancel = (e: PointerEvent) => {
                if (e.pointerType === 'mouse') return;

                if (state.pointerId) {
                    try {
                        container.releasePointerCapture(state.pointerId);
                    } catch { /* ignore */ }
                    state.pointerId = null;
                }

                clearLongPressTimer();
                state.isSelecting = false;
                touchGestureActive = false;
            };

            // Touch events (for pinch-zoom only)
            handlers.touchstart = (e: TouchEvent) => {
                if (e.touches.length === 2) {
                    e.preventDefault();
                    e.stopPropagation();
                    clearLongPressTimer();
                    state.isSelecting = false;

                    const t0 = e.touches[0]!;
                    const t1 = e.touches[1]!;
                    const dx = t0.clientX - t1.clientX;
                    const dy = t0.clientY - t1.clientY;
                    state.initialDistance = Math.hypot(dx, dy);

                    const term = callbacks.getActiveTerminal();
                    state.initialFontSize = term?.options.fontSize ?? 14;
                }
            };

            handlers.touchmove = (e: TouchEvent) => {
                if (e.touches.length === 2 && state.initialDistance > 0) {
                    e.preventDefault();

                    const t0 = e.touches[0]!;
                    const t1 = e.touches[1]!;
                    const dx = t0.clientX - t1.clientX;
                    const dy = t0.clientY - t1.clientY;
                    const distance = Math.hypot(dx, dy);
                    const scale = distance / state.initialDistance;

                    let newSize = Math.round(state.initialFontSize * scale);
                    newSize = Math.max(MIN_FONT_SIZE, Math.min(MAX_FONT_SIZE, newSize));

                    const term = callbacks.getActiveTerminal();
                    if (term && newSize !== term.options.fontSize) {
                        term.options.fontSize = newSize;
                        // Force re-render to prevent text duplication artifacts
                        term.refresh(0, term.rows - 1);
                        state.fontSizeChanged = true;
                        eventBus.emit('gesture:pinch', { scale });
                    }
                }
            };

            handlers.touchend = () => {
                if (state.fontSizeChanged) {
                    callbacks.scheduleFitAfterFontChange();
                    state.fontSizeChanged = false;
                }
                state.initialDistance = 0;
            };

            // Block mouse events during touch
            handlers.mousedown = (e: MouseEvent) => {
                if (touchGestureActive) {
                    e.preventDefault();
                    e.stopPropagation();
                }
            };

            handlers.mousemove = (e: MouseEvent) => {
                if (touchGestureActive) {
                    e.preventDefault();
                    e.stopPropagation();
                }
            };

            handlers.mouseup = (e: MouseEvent) => {
                if (touchGestureActive) {
                    e.preventDefault();
                    e.stopPropagation();
                }
            };

            // Attach all handlers
            container.addEventListener('pointerdown', handlers.pointerdown, { passive: false, capture: true });
            container.addEventListener('pointermove', handlers.pointermove, { passive: false, capture: true });
            container.addEventListener('pointerup', handlers.pointerup, { passive: false, capture: true });
            container.addEventListener('pointercancel', handlers.pointercancel, { passive: false, capture: true });
            container.addEventListener('touchstart', handlers.touchstart, { passive: false, capture: true });
            container.addEventListener('touchmove', handlers.touchmove, { passive: false, capture: true });
            container.addEventListener('touchend', handlers.touchend, { passive: false, capture: true });
            container.addEventListener('mousedown', handlers.mousedown, { passive: false, capture: true });
            container.addEventListener('mousemove', handlers.mousemove, { passive: false, capture: true });
            container.addEventListener('mouseup', handlers.mouseup, { passive: false, capture: true });
        },

        detach(): void {
            if (!attachedContainer) return;

            if (handlers.pointerdown) {
                attachedContainer.removeEventListener('pointerdown', handlers.pointerdown, { capture: true });
            }
            if (handlers.pointermove) {
                attachedContainer.removeEventListener('pointermove', handlers.pointermove, { capture: true });
            }
            if (handlers.pointerup) {
                attachedContainer.removeEventListener('pointerup', handlers.pointerup, { capture: true });
            }
            if (handlers.pointercancel) {
                attachedContainer.removeEventListener('pointercancel', handlers.pointercancel, { capture: true });
            }
            if (handlers.touchstart) {
                attachedContainer.removeEventListener('touchstart', handlers.touchstart, { capture: true });
            }
            if (handlers.touchmove) {
                attachedContainer.removeEventListener('touchmove', handlers.touchmove, { capture: true });
            }
            if (handlers.touchend) {
                attachedContainer.removeEventListener('touchend', handlers.touchend, { capture: true });
            }
            if (handlers.mousedown) {
                attachedContainer.removeEventListener('mousedown', handlers.mousedown, { capture: true });
            }
            if (handlers.mousemove) {
                attachedContainer.removeEventListener('mousemove', handlers.mousemove, { capture: true });
            }
            if (handlers.mouseup) {
                attachedContainer.removeEventListener('mouseup', handlers.mouseup, { capture: true });
            }

            attachedContainer = null;
        },

        isGestureActive(): boolean {
            return touchGestureActive;
        },
    };
}
