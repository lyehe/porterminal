/**
 * Compose Input - Compose-then-send text input mode
 * Allows native mobile editing features (autocorrect, suggestions, selection)
 * before sending to terminal
 */

import { getComposeMode, setComposeMode } from '@/utils/storage';

export interface ComposeInputOptions {
    /** Server default for compose mode (used when user has no preference) */
    serverDefault?: boolean;
}

export interface ComposeInput {
    isEnabled(): boolean;
    setup(onSend: (text: string) => void): void;
}

/** Setup touch/click handler with deduplication */
function onTap(el: HTMLElement, handler: () => void): void {
    let touchUsed = false;
    el.addEventListener('touchstart', () => { touchUsed = true; }, { passive: true });
    el.addEventListener('touchend', (e) => { e.preventDefault(); handler(); }, { passive: false });
    el.addEventListener('click', () => { if (!touchUsed) handler(); touchUsed = false; });
}

export function createComposeInput(options: ComposeInputOptions = {}): ComposeInput {
    const container = document.getElementById('compose-container');
    const textarea = document.getElementById('compose-textarea') as HTMLTextAreaElement | null;
    const placeholder = document.getElementById('compose-placeholder');
    const sendBtn = document.getElementById('compose-send');
    const toggleBtn = document.getElementById('btn-compose');

    // Priority: localStorage preference > server default > false
    const localPref = getComposeMode();
    let enabled = localPref !== null ? localPref : (options.serverDefault ?? false);
    let onSendCallback: ((text: string) => void) | null = null;

    function updateUI(): void {
        if (!container || !toggleBtn) return;
        container.classList.toggle('hidden', !enabled);
        toggleBtn.classList.toggle('active', enabled);
    }

    function updatePlaceholder(): void {
        if (!placeholder || !textarea) return;
        // Hide placeholder when focused or has text
        const shouldHide = document.activeElement === textarea || textarea.value.length > 0;
        placeholder.classList.toggle('hidden', shouldHide);
    }

    function updateButtonState(): void {
        if (!sendBtn || !textarea) return;
        sendBtn.classList.toggle('has-text', textarea.value.length > 0);
        updatePlaceholder();
    }

    function handleSend(): void {
        if (!textarea || !onSendCallback) return;
        const text = textarea.value;
        const send = onSendCallback;
        if (text) {
            // Send text first, then Enter after short delay
            send(text);
            setTimeout(() => send('\r'), 50);
        } else {
            // Just send Enter if empty
            send('\r');
        }
        textarea.value = '';
        textarea.style.height = '';
        updateButtonState();
    }

    function setEnabled(value: boolean): void {
        enabled = value;
        setComposeMode(value);
        updateUI();
    }

    return {
        isEnabled: () => enabled,

        setup(onSend): void {
            onSendCallback = onSend;
            updateUI();

            // Stop events from bubbling to terminal handlers
            container?.addEventListener('pointerdown', (e) => e.stopPropagation(), { passive: true });
            container?.addEventListener('touchstart', (e) => e.stopPropagation(), { passive: true });

            if (textarea) {
                textarea.addEventListener('input', () => {
                    // Auto-resize
                    textarea.style.height = '';
                    textarea.style.height = `${Math.min(textarea.scrollHeight, 80)}px`;
                    updateButtonState();
                });

                textarea.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                    }
                });

                // Stop propagation to prevent terminal focus stealing
                textarea.addEventListener('focus', (e) => {
                    e.stopPropagation();
                    updatePlaceholder();
                });
                textarea.addEventListener('blur', () => {
                    // On blur, show placeholder if empty (don't check activeElement - we know it's not focused)
                    if (placeholder && textarea.value.length === 0) {
                        placeholder.classList.remove('hidden');
                    }
                });
                textarea.addEventListener('click', (e) => e.stopPropagation());
                textarea.addEventListener('touchstart', (e) => e.stopPropagation(), { passive: true });
            }

            if (toggleBtn) onTap(toggleBtn, () => setEnabled(!enabled));
            if (sendBtn) onTap(sendBtn, handleSend);
        },
    };
}
