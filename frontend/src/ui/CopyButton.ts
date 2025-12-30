/**
 * Copy Button - Floating copy button for iOS clipboard access
 * Single Responsibility: Copy button UI and interaction
 */

import type { ClipboardManager } from '@/clipboard';

export interface CopyButton {
    /** Show the copy button with text at position */
    show(text: string, x?: number, y?: number): void;
    /** Hide the copy button */
    hide(): void;
    /** Setup event handlers */
    setup(): void;
}

/**
 * Create a copy button controller
 */
export function createCopyButton(
    clipboardManager: ClipboardManager,
    callbacks: {
        clearSelection: () => void;
    }
): CopyButton {
    const button = document.getElementById('copy-button') as HTMLButtonElement | null;
    let pendingText = '';

    function showResult(success: boolean): void {
        if (!button) return;

        button.textContent = success ? 'Copied!' : 'Failed';
        button.classList.add(success ? 'success' : 'error');

        setTimeout(() => {
            button.classList.remove('visible', 'success', 'error');
            button.textContent = 'Copy';
            callbacks.clearSelection();
        }, 400);
    }

    return {
        show(text: string, x?: number, y?: number): void {
            if (!button || !text) return;
            pendingText = text;

            // Position at release point if coordinates provided
            if (x !== undefined && y !== undefined) {
                // Offset slightly above the touch point
                const offsetY = 40;
                let posX = x;
                let posY = y - offsetY;

                // Keep button on screen
                const btnWidth = 80;
                const btnHeight = 36;
                const margin = 8;

                posX = Math.max(margin + btnWidth / 2, Math.min(window.innerWidth - margin - btnWidth / 2, posX));
                posY = Math.max(margin + btnHeight / 2, Math.min(window.innerHeight - margin - btnHeight / 2, posY));

                button.style.left = `${posX}px`;
                button.style.top = `${posY}px`;
            }

            button.classList.add('visible');
        },

        hide(): void {
            if (!button) return;
            pendingText = '';
            button.classList.remove('visible');
        },

        setup(): void {
            if (!button) return;

            button.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();

                if (!pendingText) {
                    this.hide();
                    return;
                }

                const textToCopy = pendingText;
                pendingText = '';

                // Fresh user gesture - clipboard should work
                if (navigator.clipboard?.writeText) {
                    navigator.clipboard.writeText(textToCopy).then(() => {
                        showResult(true);
                    }).catch(() => {
                        showResult(clipboardManager.copy(textToCopy, 'copyButton-fallback'));
                    });
                } else {
                    showResult(clipboardManager.copy(textToCopy, 'copyButton'));
                }
            });

            // Hide when tapping outside
            document.addEventListener('pointerdown', (e) => {
                if (e.target !== button && button.classList.contains('visible')) {
                    this.hide();
                    callbacks.clearSelection();
                }
            });
        },
    };
}
