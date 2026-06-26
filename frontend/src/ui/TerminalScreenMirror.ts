/**
 * Accessibility mirror of the active terminal screen.
 *
 * Browser-driving agents often rely on accessibility snapshots rather than
 * pixels. xterm renders the terminal visually, so this mirror exposes the same
 * screen text as ordinary DOM text without changing the human UI.
 */

import type { Terminal } from '@xterm/xterm';
import { getTerminalText } from '@/terminal/TerminalText';

const MAX_MIRROR_CHARS = 20000;

export interface TerminalScreenMirror {
    update(term: Terminal | null): void;
}

function trimForMirror(text: string): string {
    if (text.length <= MAX_MIRROR_CHARS) return text;
    return `[Earlier terminal output omitted]\n${text.slice(-MAX_MIRROR_CHARS)}`;
}

export function createTerminalScreenMirror(): TerminalScreenMirror {
    const element = document.getElementById('terminal-screen-text');

    return {
        update(term: Terminal | null): void {
            if (!element) return;
            const text = term ? trimForMirror(getTerminalText(term)) : '';
            if (element.textContent !== text) {
                element.textContent = text;
            }
        },
    };
}
