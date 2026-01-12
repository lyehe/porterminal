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
 * Detect and remove duplicated content in text.
 * xterm.js buffer can contain duplicates during rapid output or resize.
 *
 * Strategy: Find the longest repeated suffix and remove it.
 * If text is "ABC...XYZ...ABC...XYZ", we want "ABC...XYZ".
 */
function removeDuplicates(text: string): string {
    if (text.length < 100) return text;

    // Check if the second half is a repeat of the first half
    const len = text.length;
    for (let splitPoint = Math.floor(len / 2); splitPoint > len / 4; splitPoint--) {
        const firstHalf = text.slice(0, splitPoint);
        const secondHalf = text.slice(splitPoint, splitPoint * 2);

        if (firstHalf === secondHalf) {
            // Found duplicate - return first half plus any remainder
            const remainder = text.slice(splitPoint * 2);
            return removeDuplicates(firstHalf + remainder);
        }
    }

    // Also check for repeated blocks at line level
    const lines = text.split('\n');
    if (lines.length < 6) return text;

    // Look for point where content starts repeating
    for (let splitIdx = Math.floor(lines.length / 2); splitIdx > lines.length / 4; splitIdx--) {
        let isRepeat = true;
        const blockSize = Math.min(splitIdx, lines.length - splitIdx);

        for (let j = 0; j < blockSize; j++) {
            if (lines[j] !== lines[splitIdx + j]) {
                isRepeat = false;
                break;
            }
        }

        if (isRepeat) {
            // Content from splitIdx onwards is a repeat
            return lines.slice(0, splitIdx).join('\n');
        }
    }

    return text;
}

/**
 * Extract plain text from terminal buffer
 * Handles wrapped lines by joining continuations properly.
 *
 * Note: buffer.length can exceed actual content during reflow.
 * We use baseY + cursorY to find the actual content end.
 */
function getTerminalText(term: Terminal): string {
    const buffer = term.buffer.active;
    const logicalLines: string[] = [];
    let currentLine = '';

    // Calculate actual content length:
    // - baseY is the scroll offset (how many lines are in scrollback above viewport)
    // - cursorY is cursor position within viewport (0-indexed)
    // - Total content lines = baseY + cursorY + 1 (include cursor line)
    // But we also need to account for content below cursor, so use buffer.length
    // but cap it at a reasonable limit based on scrollback settings
    const contentEnd = Math.min(
        buffer.length,
        buffer.baseY + term.rows  // scrollback + viewport
    );

    // Get all lines from scrollback + viewport
    // Handle wrapped lines: isWrapped=true means continuation of previous line
    for (let i = 0; i < contentEnd; i++) {
        const line = buffer.getLine(i);
        if (!line) continue;

        // translateToString(true) trims trailing whitespace
        // translateToString(false) preserves whitespace for wrapped continuations
        const text = line.isWrapped
            ? line.translateToString(false)  // preserve whitespace for wrapped lines
            : line.translateToString(true);

        if (line.isWrapped) {
            // Continuation of previous line - join without newline
            currentLine += text;
        } else {
            // Start of new logical line
            if (currentLine) {
                logicalLines.push(currentLine.trimEnd());
            }
            currentLine = text;
        }
    }

    // Push the last line
    if (currentLine) {
        logicalLines.push(currentLine.trimEnd());
    }

    // Trim trailing empty lines
    while (logicalLines.length > 0 && (logicalLines[logicalLines.length - 1] ?? '').trim() === '') {
        logicalLines.pop();
    }

    // Remove any duplicated content caused by xterm.js buffer issues
    return removeDuplicates(logicalLines.join('\n'));
}

/**
 * Create a text view overlay controller
 */
export function createTextViewOverlay(): TextViewOverlay {
    const overlay = document.getElementById('textview-overlay');
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
            // Note: close button handler is set up in main.ts to enable terminal refresh on close
            zoomInBtn?.addEventListener('click', zoomIn);
            zoomOutBtn?.addEventListener('click', zoomOut);

            // Pinch zoom on body
            body?.addEventListener('touchstart', handleTouchStart, { passive: true });
            body?.addEventListener('touchmove', handleTouchMove, { passive: false });
            body?.addEventListener('touchend', handleTouchEnd, { passive: true });
        },
    };
}
