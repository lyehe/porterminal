/**
 * Centralized key configuration
 * Single source of truth for toolbar buttons and key mappings
 */

export interface KeyConfig {
    /** Key identifier (used as data-key and in keyMap) */
    key: string;
    /** Display label on button */
    label: string;
    /** Escape sequence to send */
    sequence: string;
    /** Additional CSS class (e.g., "danger", "icon", "arrow") */
    className?: string;
}

/**
 * Row 1: Navigation and editing keys
 */
export const TOOLBAR_ROW1: KeyConfig[] = [
    // Escape handled separately (has double-tap behavior)
    { key: '1', label: '1', sequence: '1' },
    { key: '2', label: '2', sequence: '2' },
    { key: 'ArrowUp', label: '↑', sequence: '\x1b[A', className: 'arrow' },
    { key: '3', label: '3', sequence: '3' },
    { key: '/', label: '/', sequence: '/' },
    { key: 'Home', label: 'Hm', sequence: '\x1b[H' },
    { key: 'End', label: 'Ed', sequence: '\x1b[F' },
    // Backspace handled separately (has repeat behavior)
    { key: 'Delete', label: 'Del', sequence: '\x1b[3~' },
    { key: 'Enter', label: '↵', sequence: '\r', className: 'icon enter' },
];

/**
 * Row 2: Modifiers, shortcuts, and characters
 */
export const TOOLBAR_ROW2: KeyConfig[] = [
    // Modifiers (Ctrl, Alt, Shift) handled separately (have sticky/locked behavior)
    { key: 'ShiftTab', label: 'Sft⇥', sequence: '\x1b[Z' },
    { key: 'Ctrl+B', label: '^B', sequence: '\x02', className: 'tmux' },
    { key: 'Ctrl+C', label: '^C', sequence: '\x03', className: 'danger' },
    // Paste handled separately (async clipboard)
    { key: 'Tab', label: '⇥', sequence: '\t', className: 'icon' },
    { key: 'ArrowLeft', label: '←', sequence: '\x1b[D', className: 'arrow' },
    { key: 'ArrowDown', label: '↓', sequence: '\x1b[B', className: 'arrow' },
    { key: 'ArrowRight', label: '→', sequence: '\x1b[C', className: 'arrow' },
    { key: '\\Enter', label: '\\↵', sequence: '\\\r' },
];

/**
 * Additional Ctrl key mappings (not shown as buttons but available via modifier)
 */
export const CTRL_KEYS: KeyConfig[] = [
    { key: 'Ctrl+A', label: '^A', sequence: '\x01' },
    { key: 'Ctrl+D', label: '^D', sequence: '\x04' },
    { key: 'Ctrl+E', label: '^E', sequence: '\x05' },
    { key: 'Ctrl+L', label: '^L', sequence: '\x0c' },
    { key: 'Ctrl+R', label: '^R', sequence: '\x12' },
    { key: 'Ctrl+U', label: '^U', sequence: '\x15' },
    { key: 'Ctrl+W', label: '^W', sequence: '\x17' },
    { key: 'Ctrl+Z', label: '^Z', sequence: '\x1a' },
];

/**
 * Special keys with custom behavior (not in toolbar config)
 */
export const SPECIAL_KEYS: KeyConfig[] = [
    { key: 'Escape', label: 'Esc', sequence: '\x1b' },
    { key: 'Backspace', label: '⌫', sequence: '\x7f' },
    { key: 'Space', label: ' ', sequence: ' ' },
];

/**
 * Build key map from all configurations
 */
export function buildKeyMap(): Record<string, string> {
    const map: Record<string, string> = {};

    for (const config of [...TOOLBAR_ROW1, ...TOOLBAR_ROW2, ...CTRL_KEYS, ...SPECIAL_KEYS]) {
        map[config.key] = config.sequence;
    }

    return map;
}
