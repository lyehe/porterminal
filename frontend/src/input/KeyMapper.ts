/**
 * Key Mapper - Maps key names to escape sequences
 * Open/Closed Principle: Extensible via registerMapping
 */

import type { ModifierState } from '@/types';
import { buildKeyMap } from '@/config/keys';

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

                if (modifiers.ctrl === 'sticky' || modifiers.ctrl === 'locked') {
                    const code = char.toUpperCase().charCodeAt(0);
                    if (code >= 65 && code <= 90) {
                        char = String.fromCharCode(code - 64);
                    }
                }

                if (modifiers.alt === 'sticky' || modifiers.alt === 'locked') {
                    char = '\x1b' + char;
                }

                return char;
            }

            return null;
        },
    };
}
