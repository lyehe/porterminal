/**
 * Key Mapper - Maps key names to escape sequences
 * Open/Closed Principle: Extensible via registerMapping
 */

import type { ModifierState } from '@/types';
import { buildKeyMap } from '@/config/keys';

/**
 * Apply Ctrl/Alt modifiers to a single character.
 * Ctrl: A-Z becomes control codes (0x01-0x1A)
 * Alt: Prepends ESC (0x1B)
 */
export function applyModifiers(char: string, modifiers: ModifierState): string {
    const ctrlActive = modifiers.ctrl === 'sticky' || modifiers.ctrl === 'locked';
    const altActive = modifiers.alt === 'sticky' || modifiers.alt === 'locked';

    if (ctrlActive) {
        const code = char.toUpperCase().charCodeAt(0);
        if (code >= 65 && code <= 90) {
            char = String.fromCharCode(code - 64);
        }
    }

    if (altActive) {
        char = '\x1b' + char;
    }

    return char;
}

export interface KeyMapper {
    /** Get the escape sequence for a key, considering modifiers */
    getSequence(key: string, modifiers: ModifierState): string | null;
}

/**
 * Create a key mapper instance
 */
export function createKeyMapper(customMappings?: Record<string, string>): KeyMapper {
    const keyMap = { ...buildKeyMap(), ...customMappings };

    return {
        getSequence(key: string, modifiers: ModifierState): string | null {
            // Check direct mapping first
            if (keyMap[key]) {
                return keyMap[key]!;
            }

            // Handle single characters with modifiers
            if (key.length === 1) {
                let char = key;

                if (modifiers.shift === 'sticky' || modifiers.shift === 'locked') {
                    char = char.toUpperCase();
                }

                char = applyModifiers(char, modifiers);
                return char;
            }

            return null;
        },
    };
}
