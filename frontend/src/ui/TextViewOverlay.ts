/**
 * Text View Overlay - Plain text view of terminal content
 * Single Responsibility: Extract and display terminal content as selectable text
 */

import type { Terminal } from '@xterm/xterm';

export interface TextViewOverlay {
    /** Show the overlay with terminal content */
    show(term: Terminal): void;
    /** Hide the overlay */
    hide(): void;
    /** Setup event handlers */
    setup(): void;
}

/** Font size limits */
const MIN_FONT_SIZE = 6;
const MAX_FONT_SIZE = 32;
const FONT_STEP = 1;

/**
 * Extract plain text from terminal buffer
 */
function getTerminalText(term: Terminal): string {
    const buffer = term.buffer.active;
    const lines: string[] = [];

    // Get all lines from scrollback + viewport
    for (let i = 0; i < buffer.length; i++) {
        const line = buffer.getLine(i);
        if (line) {
            lines.push(line.translateToString(true));
        }
    }

    // Trim trailing empty lines
    while (lines.length > 0 && (lines[lines.length - 1] ?? '').trim() === '') {
        lines.pop();
    }

    return lines.join('\n');
}

/**
 * Create a text view overlay controller
 */
export function createTextViewOverlay(): TextViewOverlay {
    const overlay = document.getElementById('textview-overlay');
    const closeBtn = document.getElementById('textview-close');
    const zoomInBtn = document.getElementById('textview-zoom-in');
    const zoomOutBtn = document.getElementById('textview-zoom-out');
    const body = document.getElementById('textview-body') as HTMLPreElement | null;

    let fontSize = 10; // Default font size in px
    let initialPinchDistance = 0;
    let initialFontSize = 10;

    function updateFontSize(): void {
        if (body) {
            body.style.fontSize = `${fontSize}px`;
        }
    }

    function setFontSize(size: number): void {
        fontSize = Math.max(MIN_FONT_SIZE, Math.min(MAX_FONT_SIZE, size));
        updateFontSize();
    }

    function zoomIn(): void {
        setFontSize(fontSize + FONT_STEP);
    }

    function zoomOut(): void {
        setFontSize(fontSize - FONT_STEP);
    }

    // Pinch zoom handlers
    function getTouchDistance(touches: TouchList): number {
        const t0 = touches[0];
        const t1 = touches[1];
        if (!t0 || !t1) return 0;
        const dx = t1.clientX - t0.clientX;
        const dy = t1.clientY - t0.clientY;
        return Math.hypot(dx, dy);
    }

    function handleTouchStart(e: TouchEvent): void {
        if (e.touches.length === 2) {
            initialPinchDistance = getTouchDistance(e.touches);
            initialFontSize = fontSize;
        }
    }

    function handleTouchMove(e: TouchEvent): void {
        if (e.touches.length === 2 && initialPinchDistance > 0) {
            e.preventDefault();
            const currentDistance = getTouchDistance(e.touches);
            const scale = currentDistance / initialPinchDistance;
            setFontSize(Math.round(initialFontSize * scale));
        }
    }

    function handleTouchEnd(): void {
        initialPinchDistance = 0;
    }

    return {
        show(term: Terminal): void {
            // Match terminal font size
            const termFontSize = term.options.fontSize ?? 14;
            setFontSize(termFontSize);

            if (body) {
                body.textContent = getTerminalText(term);
            }
            overlay?.classList.remove('hidden');
            // Scroll to bottom after layout completes
            requestAnimationFrame(() => {
                if (body) {
                    body.scrollTop = body.scrollHeight;
                }
            });
        },

        hide(): void {
            overlay?.classList.add('hidden');
            if (body) {
                body.textContent = '';
            }
        },

        setup(): void {
            closeBtn?.addEventListener('click', () => this.hide());
            zoomInBtn?.addEventListener('click', zoomIn);
            zoomOutBtn?.addEventListener('click', zoomOut);

            // Pinch zoom on body
            body?.addEventListener('touchstart', handleTouchStart, { passive: true });
            body?.addEventListener('touchmove', handleTouchMove, { passive: false });
            body?.addEventListener('touchend', handleTouchEnd, { passive: true });
        },
    };
}
