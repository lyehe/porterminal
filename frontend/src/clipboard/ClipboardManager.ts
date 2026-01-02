/**
 * Clipboard Manager - Handles copy/paste with iOS workarounds
 * Single Responsibility: Clipboard operations
 */

export interface ClipboardManager {
    /** Copy text to clipboard with deduplication */
    copy(text: string, source: string): boolean;

    /** Paste from clipboard */
    paste(): Promise<string>;

    /** Reset deduplication state */
    reset(): void;
}

/** Deduplication window in milliseconds */
const DEDUPLICATION_WINDOW_MS = 300;

/**
 * Fallback copy using execCommand (works on iOS when Clipboard API fails)
 */
function fallbackCopy(text: string): boolean {
    // Create textarea - must be visible on iOS
    const textarea = document.createElement('textarea');
    textarea.value = text;

    // Position on-screen but tiny and transparent
    textarea.style.position = 'fixed';
    textarea.style.top = '50%';
    textarea.style.left = '50%';
    textarea.style.width = '1px';
    textarea.style.height = '1px';
    textarea.style.padding = '0';
    textarea.style.border = 'none';
    textarea.style.outline = 'none';
    textarea.style.boxShadow = 'none';
    textarea.style.background = 'transparent';
    textarea.style.color = 'transparent';
    textarea.style.fontSize = '1px';
    textarea.style.zIndex = '99999';
    textarea.contentEditable = 'true';

    document.body.appendChild(textarea);

    // iOS-specific selection method
    textarea.focus();
    textarea.select();

    // Additional iOS selection handling
    if (navigator.userAgent.match(/ipad|iphone/i)) {
        const range = document.createRange();
        range.selectNodeContents(textarea);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
    }

    textarea.setSelectionRange(0, text.length);

    let success = false;
    try {
        success = document.execCommand('copy');
    } catch (err) {
        console.error('execCommand copy failed:', err);
    }

    textarea.blur();
    document.body.removeChild(textarea);

    return success;
}

/**
 * Create a clipboard manager instance
 */
export function createClipboardManager(): ClipboardManager {

    let lastText = '';
    let lastTime = 0;

    const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

    return {
        copy(text: string, source: string): boolean {
            if (!text || !text.trim()) return false;

            const now = Date.now();

            // Prevent duplicate copies
            if (text === lastText && (now - lastTime) < DEDUPLICATION_WINDOW_MS) {
                return false;
            }

            let success = false;

            // On touch devices, use synchronous fallback first
            if (isTouchDevice) {
                success = fallbackCopy(text);
            }

            // Try modern Clipboard API
            if (!success && navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    // Success
                }).catch(err => {
                    console.warn(`Clipboard API failed (${source}):`, err);
                });

                if (!success) {
                    success = true; // Optimistically assume success
                }
            }

            // Final fallback for desktop
            if (!success) {
                success = fallbackCopy(text);
            }

            if (success) {
                lastText = text;
                lastTime = now;
                return true;
            } else {
                console.error(`Copy failed completely (${source})`);
                return false;
            }
        },

        async paste(): Promise<string> {
            try {
                if (!navigator.clipboard?.readText) {
                    console.warn('Clipboard API not available');
                    return '';
                }
                return await navigator.clipboard.readText();
            } catch (e) {
                console.error('Paste failed:', e);
                return '';
            }
        },

        reset(): void {
            lastText = '';
            lastTime = 0;
        },
    };
}
