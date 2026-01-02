/**
 * Toolbar - Renders toolbar buttons from centralized config
 */

import { TOOLBAR_ROW1, TOOLBAR_ROW2, type KeyConfig } from '@/config/keys';

// Explicit layout order for row 1 (between Esc and Enter, relative to Backspace)
const ROW1_BEFORE_BACKSPACE = ['1', '2', '3', 'Tab', '/', 'Delete'];
const ROW1_AFTER_BACKSPACE = ['Home', 'ArrowUp', 'End'];

// Keys to exclude from row 2 (moved to row 1)
const ROW2_EXCLUDE = new Set(['Tab']);

// Insert Paste before this key in row 2
const ROW2_PASTE_BEFORE = 'ArrowLeft';

/**
 * Find config by key from either row
 */
function findConfig(key: string): KeyConfig | undefined {
    return TOOLBAR_ROW1.find(c => c.key === key)
        || TOOLBAR_ROW2.find(c => c.key === key);
}

/**
 * Render a single button from config
 */
function renderButton(config: KeyConfig): HTMLButtonElement {
    const btn = document.createElement('button');
    btn.className = 'tool-btn';
    if (config.className) {
        btn.className += ' ' + config.className;
    }
    btn.dataset.key = config.key;
    btn.textContent = config.label;
    return btn;
}

/**
 * Render toolbar rows
 * Row 1: Esc, 1, 2, 3, ⇥, /, Del, ⌫, Hm, ↑, Ed, ↵
 * Row 2: Sft⇥, ^B, ^C, Paste, ←, ↓, →, \↵
 */
export function renderToolbar(): void {
    const row1 = document.getElementById('toolbar-row1');
    const row2 = document.getElementById('toolbar-row2');
    const backspaceBtn = document.getElementById('btn-backspace');
    const pasteBtn = document.getElementById('btn-paste');

    if (!row1 || !row2 || !backspaceBtn) return;

    // Row 1: Insert buttons before Backspace
    for (const key of ROW1_BEFORE_BACKSPACE) {
        const config = findConfig(key);
        if (config) row1.insertBefore(renderButton(config), backspaceBtn);
    }

    // Row 1: Insert buttons after Backspace
    let lastBtn: Element = backspaceBtn;
    for (const key of ROW1_AFTER_BACKSPACE) {
        const config = findConfig(key);
        if (config) {
            const btn = renderButton(config);
            lastBtn.insertAdjacentElement('afterend', btn);
            lastBtn = btn;
        }
    }

    // Row 1: Enter at the end
    const enterConfig = findConfig('Enter');
    if (enterConfig) row1.appendChild(renderButton(enterConfig));

    // Row 2: All buttons except excluded, with Paste insertion
    for (const config of TOOLBAR_ROW2) {
        if (ROW2_EXCLUDE.has(config.key)) continue;
        if (config.key === ROW2_PASTE_BEFORE && pasteBtn) {
            row2.appendChild(pasteBtn);
        }
        row2.appendChild(renderButton(config));
    }
}
