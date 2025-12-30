/**
 * Selection Handler - Handles text selection in terminal
 * Single Responsibility: Terminal text selection
 */

import type { Terminal } from '@xterm/xterm';
import type { TerminalPosition } from '@/types';

export interface SelectionHandler {
    /** Convert touch coordinates to terminal position */
    touchToPosition(terminal: Terminal, clientX: number, clientY: number): TerminalPosition;

    /** Start selection at a position */
    startSelection(terminal: Terminal, col: number, row: number): void;

    /** Extend selection from anchor to current position */
    extendSelection(
        terminal: Terminal,
        anchorCol: number,
        anchorRow: number,
        currentCol: number,
        currentRow: number
    ): void;

    /** Select word at position */
    selectWordAt(terminal: Terminal, col: number, row: number): void;

    /** Get current selection text */
    getSelection(terminal: Terminal): string;

    /** Clear selection */
    clearSelection(terminal: Terminal): void;

    /** Check if terminal has selection */
    hasSelection(terminal: Terminal): boolean;
}

/**
 * Create a selection handler instance
 */
export function createSelectionHandler(): SelectionHandler {
    return {
        touchToPosition(terminal: Terminal, clientX: number, clientY: number): TerminalPosition {
            const rect = terminal.element?.getBoundingClientRect();
            if (!rect) return { col: 0, row: 0 };

            const x = clientX - rect.left;
            const y = clientY - rect.top;

            const cellWidth = rect.width / terminal.cols;
            const cellHeight = rect.height / terminal.rows;

            const col = Math.floor(x / cellWidth);
            const row = Math.floor(y / cellHeight);

            return {
                col: Math.max(0, Math.min(col, terminal.cols - 1)),
                row: Math.max(0, Math.min(row, terminal.rows - 1)),
            };
        },

        startSelection(terminal: Terminal, col: number, row: number): void {
            const bufferRow = row + Math.floor(terminal.buffer.active.viewportY);
            terminal.select(col, bufferRow, 1);
        },

        extendSelection(
            terminal: Terminal,
            anchorCol: number,
            anchorRow: number,
            currentCol: number,
            currentRow: number
        ): void {
            const viewportY = Math.floor(terminal.buffer.active.viewportY);
            let startCol: number, startRow: number, length: number;

            if (currentRow === anchorRow) {
                startCol = Math.min(anchorCol, currentCol);
                startRow = anchorRow;
                length = Math.abs(currentCol - anchorCol) + 1;
            } else if (currentRow > anchorRow) {
                startCol = anchorCol;
                startRow = anchorRow;
                length = (terminal.cols - anchorCol) +
                    (currentRow - anchorRow - 1) * terminal.cols +
                    currentCol + 1;
            } else {
                startCol = currentCol;
                startRow = currentRow;
                length = (terminal.cols - currentCol) +
                    (anchorRow - currentRow - 1) * terminal.cols +
                    anchorCol + 1;
            }

            terminal.select(startCol, startRow + viewportY, length);
        },

        selectWordAt(terminal: Terminal, col: number, row: number): void {
            const line = terminal.buffer.active.getLine(row);
            if (!line) return;

            let startCol = col;
            let endCol = col;

            // Expand left
            while (startCol > 0) {
                const cell = line.getCell(startCol - 1);
                if (!cell || /\s/.test(cell.getChars())) break;
                startCol--;
            }

            // Expand right
            while (endCol < terminal.cols - 1) {
                const cell = line.getCell(endCol + 1);
                if (!cell || /\s/.test(cell.getChars())) break;
                endCol++;
            }

            const length = endCol - startCol + 1;
            if (length > 0) {
                terminal.select(startCol, row, length);
            }
        },

        getSelection(terminal: Terminal): string {
            return terminal.getSelection();
        },

        clearSelection(terminal: Terminal): void {
            terminal.clearSelection();
        },

        hasSelection(terminal: Terminal): boolean {
            return terminal.hasSelection();
        },
    };
}
