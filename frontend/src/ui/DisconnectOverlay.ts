/**
 * Disconnect Overlay - Connection lost UI
 * Single Responsibility: Disconnect overlay visibility and retry
 */

export interface DisconnectOverlay {
    /** Show the overlay */
    show(): void;
    /** Hide the overlay */
    hide(): void;
    /** Set custom text */
    setText(text: string): void;
    /** Setup event handlers */
    setup(onRetry: () => void): void;
}

/**
 * Create a disconnect overlay controller
 */
export function createDisconnectOverlay(): DisconnectOverlay {
    const overlay = document.getElementById('disconnect-overlay');
    const textElement = document.getElementById('disconnect-text');
    const retryButton = document.getElementById('disconnect-retry');

    return {
        show(): void {
            overlay?.classList.remove('hidden');
        },

        hide(): void {
            overlay?.classList.add('hidden');
        },

        setText(text: string): void {
            if (textElement) {
                textElement.textContent = text;
            }
        },

        setup(onRetry: () => void): void {
            retryButton?.addEventListener('click', () => {
                this.hide();
                onRetry();
            });
        },
    };
}
