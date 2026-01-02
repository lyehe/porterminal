/**
 * Modifier Manager - State machine for Ctrl/Alt/Shift keys
 * Single Responsibility: Modifier key state transitions
 */

import type { ModifierState, ModifierMode } from '@/types';
import type { EventBus } from '@/core/events';

export type ModifierKey = 'ctrl' | 'alt' | 'shift';

export interface ModifierManager {
    /** Current modifier state (readonly) */
    readonly state: Readonly<ModifierState>;

    /** Handle a modifier key tap */
    handleTap(modifier: ModifierKey): void;

    /** Consume sticky modifiers (reset to off if sticky) */
    consumeSticky(): void;

    /** Reset all modifiers to off */
    reset(): void;

    /** Get state of a specific modifier */
    getState(modifier: ModifierKey): ModifierMode;
}

/** Double-tap detection time window */
const DOUBLE_TAP_MS = 300;

/**
 * Create a modifier manager instance
 */
export function createModifierManager(
    eventBus: EventBus,
    onUpdate?: (modifier: ModifierKey) => void
): ModifierManager {
    const state: ModifierState = {
        ctrl: 'off',
        alt: 'off',
        shift: 'off',
    };

    const lastTapTime: Record<ModifierKey, number> = {
        ctrl: 0,
        alt: 0,
        shift: 0,
    };

    function emitChange(modifier: ModifierKey): void {
        eventBus.emit('modifier:changed', { modifier, state: state[modifier] });
        onUpdate?.(modifier);
    }

    return {
        get state() {
            return state;
        },

        handleTap(modifier: ModifierKey): void {
            const now = Date.now();
            const lastTap = lastTapTime[modifier];
            lastTapTime[modifier] = now;

            if (now - lastTap < DOUBLE_TAP_MS) {
                // Double tap - toggle lock
                state[modifier] = state[modifier] === 'locked' ? 'off' : 'locked';
            } else {
                // Single tap - cycle: off -> sticky, sticky/locked -> off
                if (state[modifier] === 'off') {
                    state[modifier] = 'sticky';
                } else {
                    state[modifier] = 'off';
                }
            }

            emitChange(modifier);
        },

        consumeSticky(): void {
            const modifiers: ModifierKey[] = ['ctrl', 'alt', 'shift'];
            for (const mod of modifiers) {
                if (state[mod] === 'sticky') {
                    state[mod] = 'off';
                    emitChange(mod);
                }
            }
        },

        reset(): void {
            const modifiers: ModifierKey[] = ['ctrl', 'alt', 'shift'];
            for (const mod of modifiers) {
                if (state[mod] !== 'off') {
                    state[mod] = 'off';
                    emitChange(mod);
                }
            }
        },

        getState(modifier: ModifierKey): ModifierMode {
            return state[modifier];
        },
    };
}
