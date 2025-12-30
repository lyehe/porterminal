/**
 * Key Mapper - Maps key names to escape sequences
 * Open/Closed Principle: Extensible via registerMapping
 */

import type { ModifierState } from '@/types';

/** Default key mappings */
export const DEFAULT_KEY_MAP: Record<string, string> = {
    'Tab': '\t',
    'ShiftTab': '\x1b[Z',
    'Enter': '\r',
    'Backspace': '\x7f',
    'Delete': '\x1b[3~',
    'Escape': '\x1b',
    'Space': ' ',
    'ArrowUp': '\x1b[A',
    'ArrowDown': '\x1b[B',
    'ArrowRight': '\x1b[C',
    'ArrowLeft': '\x1b[D',
    'Home': '\x1b[H',
    'End': '\x1b[F',
    'Ctrl+C': '\x03',
    'Ctrl+D': '\x04',
    'Ctrl+Z': '\x1a',
    'Ctrl+L': '\x0c',
    'Ctrl+R': '\x12',
    'Ctrl+A': '\x01',
    'Ctrl+E': '\x05',
    'Ctrl+W': '\x17',
    'Ctrl+U': '\x15',
};

export interface KeyMapper {
    /** Get the escape sequence for a key, considering modifiers */
    getSequence(key: string, modifiers: ModifierState): string | null;

    /** Register a custom key mapping */
    registerMapping(key: string, sequence: string): void;

    /** Check if a key has a mapping */
    hasMapping(key: string): boolean;
}

/**
 * Create a key mapper instance
 */
export function createKeyMapper(customMappings?: Record<string, string>): KeyMapper {
    const keyMap = { ...DEFAULT_KEY_MAP, ...customMappings };

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

        registerMapping(key: string, sequence: string): void {
            keyMap[key] = sequence;
        },

        hasMapping(key: string): boolean {
            return key in keyMap;
        },
    };
}
