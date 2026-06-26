/**
 * Plain-text extraction helpers for xterm.js buffers.
 */

import type { Terminal } from '@xterm/xterm';

/**
 * Detect and remove duplicated content in text.
 * xterm.js buffer can contain duplicates during rapid output or resize.
 */
function removeDuplicates(text: string): string {
    if (text.length < 100) return text;

    const len = text.length;
    for (let splitPoint = Math.floor(len / 2); splitPoint > len / 4; splitPoint--) {
        const firstHalf = text.slice(0, splitPoint);
        const secondHalf = text.slice(splitPoint, splitPoint * 2);

        if (firstHalf === secondHalf) {
            const remainder = text.slice(splitPoint * 2);
            return removeDuplicates(firstHalf + remainder);
        }
    }

    const lines = text.split('\n');
    if (lines.length < 6) return text;

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
            return lines.slice(0, splitIdx).join('\n');
        }
    }

    return text;
}

/**
 * Extract plain text from a terminal buffer.
 * Handles wrapped lines by joining continuations properly.
 */
export function getTerminalText(term: Terminal): string {
    const buffer = term.buffer.active;
    const logicalLines: string[] = [];
    let currentLine = '';

    const contentEnd = Math.min(buffer.length, buffer.baseY + term.rows);

    for (let i = 0; i < contentEnd; i++) {
        const line = buffer.getLine(i);
        if (!line) continue;

        const text = line.isWrapped
            ? line.translateToString(false)
            : line.translateToString(true);

        if (line.isWrapped) {
            currentLine += text;
        } else {
            if (currentLine) {
                logicalLines.push(currentLine.trimEnd());
            }
            currentLine = text;
        }
    }

    if (currentLine) {
        logicalLines.push(currentLine.trimEnd());
    }

    while (logicalLines.length > 0 && (logicalLines[logicalLines.length - 1] ?? '').trim() === '') {
        logicalLines.pop();
    }

    return removeDuplicates(logicalLines.join('\n'));
}
