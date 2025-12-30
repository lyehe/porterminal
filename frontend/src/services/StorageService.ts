/**
 * Storage Service - Handles localStorage persistence
 * Single Responsibility: Only manages tab state persistence
 */

import type { SavedTab, SavedState } from '@/types';

export interface StorageService {
    /** Save tab state to localStorage */
    save(tabs: SavedTab[], activeTabId: number | null, tabCounter: number): void;

    /** Load tab state from localStorage */
    load(): SavedState | null;

    /** Clear stored state */
    clear(): void;
}

/**
 * Create a storage service instance
 */
export function createStorageService(storageKey: string): StorageService {
    return {
        save(tabs: SavedTab[], activeTabId: number | null, tabCounter: number): void {
            try {
                const state: SavedState = {
                    tabs,
                    activeTabId,
                    tabCounter,
                };
                localStorage.setItem(storageKey, JSON.stringify(state));
            } catch (e) {
                console.warn('Failed to save tabs to localStorage:', e);
            }
        },

        load(): SavedState | null {
            try {
                const stored = localStorage.getItem(storageKey);
                if (stored) {
                    return JSON.parse(stored) as SavedState;
                }
            } catch (e) {
                console.warn('Failed to load tabs from localStorage:', e);
            }
            return null;
        },

        clear(): void {
            try {
                localStorage.removeItem(storageKey);
            } catch (e) {
                console.warn('Failed to clear localStorage:', e);
            }
        },
    };
}
