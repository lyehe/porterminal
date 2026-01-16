/**
 * Compose Input - Compose-then-send text input mode
 * Allows native mobile editing features (autocorrect, suggestions, selection)
 * before sending to terminal
 */

import { getComposeMode, setComposeMode } from '@/utils/storage';

export interface ComposeInput {
    isEnabled(): boolean;
    isFocused(): boolean;
    setup(onSend: (text: string) => void): void;
}

/** Setup touch/click handler with deduplication */
function onTap(el: HTMLElement, handler: () => void): void {
    let touchUsed = false;
    el.addEventListener('touchstart', () => { touchUsed = true; }, { passive: true });
    el.addEventListener('touchend', (e) => { e.preventDefault(); handler(); }, { passive: false });
    el.addEventListener('click', () => { if (!touchUsed) handler(); touchUsed = false; });
}

export function createComposeInput(): ComposeInput {
    const container = document.getElementById('compose-container');
    const textarea = document.getElementById('compose-textarea') as HTMLTextAreaElement | null;
    const actionBtn = document.getElementById('compose-send');
    const toggleBtn = document.getElementById('btn-compose');

    let enabled = getComposeMode();
    let onSendCallback: ((text: string) => void) | null = null;

    function updateUI(): void {
        if (!container || !toggleBtn) return;
        container.classList.toggle('hidden', !enabled);
        toggleBtn.classList.toggle('active', enabled);
    }

    function updateButtonState(): void {
        if (!actionBtn || !textarea) return;
        actionBtn.classList.toggle('has-text', textarea.value.length > 0);
    }

    function handleAction(): void {
        if (!textarea || !onSendCallback) return;
        const text = textarea.value;
        if (text) {
            onSendCallback(text);
            textarea.value = '';
            textarea.style.height = '';
            updateButtonState();
        } else {
            onSendCallback('\r');
        }
    }

    function setEnabled(value: boolean): void {
        enabled = value;
        setComposeMode(value);
        updateUI();
    }

    return {
        isEnabled: () => enabled,
        isFocused: () => document.activeElement === textarea,

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
                        handleAction();
                    }
                });

                // Stop propagation to prevent terminal focus stealing
                textarea.addEventListener('focus', (e) => e.stopPropagation());
                textarea.addEventListener('click', (e) => e.stopPropagation());
                textarea.addEventListener('touchstart', (e) => e.stopPropagation(), { passive: true });
            }

            if (toggleBtn) onTap(toggleBtn, () => setEnabled(!enabled));
            if (actionBtn) onTap(actionBtn, handleAction);
        },
    };
}
