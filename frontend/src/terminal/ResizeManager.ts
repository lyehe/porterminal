/**
 * Resize Manager - Debounced terminal resize handling
 * Single Responsibility: Resize event debouncing and coordination
 */

import type { Tab } from '@/types';

export interface ResizeManager {
    /** Schedule a resize for a tab */
    scheduleResize(tab: Tab, delay?: number): void;

    /** Cancel pending resize for a tab */
    cancelResize(tabId: number): void;

    /** Get last sent dimensions for a tab */
    getLastDimensions(tabId: number): { cols: number; rows: number } | null;
}

/**
 * Create a resize manager instance
 */
export function createResizeManager(
    sendResize: (tab: Tab, cols: number, rows: number) => void
): ResizeManager {
    const pending = new Map<number, ReturnType<typeof setTimeout>>();
    const lastSent = new Map<number, { cols: number; rows: number; time: number }>();

    return {
        scheduleResize(tab: Tab, delay = 50): void {
            // Clear any pending resize
            const existingTimeout = pending.get(tab.id);
            if (existingTimeout) {
                clearTimeout(existingTimeout);
            }

            // Schedule new resize
            const timeout = setTimeout(() => {
                pending.delete(tab.id);

                const cols = tab.term.cols;
                const rows = tab.term.rows;

                // Check if dimensions actually changed
                const last = lastSent.get(tab.id);
                if (last && last.cols === cols && last.rows === rows) {
                    return;
                }

                // Send resize
                sendResize(tab, cols, rows);
                lastSent.set(tab.id, { cols, rows, time: Date.now() });
            }, delay);

            pending.set(tab.id, timeout);
        },

        cancelResize(tabId: number): void {
            const timeout = pending.get(tabId);
            if (timeout) {
                clearTimeout(timeout);
                pending.delete(tabId);
            }
        },

        getLastDimensions(tabId: number): { cols: number; rows: number } | null {
            const last = lastSent.get(tabId);
            return last ? { cols: last.cols, rows: last.rows } : null;
        },
    };
}
