/** Toolbar rendering and interaction wiring. */

import type { Terminal } from '@xterm/xterm';

import type { ClipboardManager } from '@/clipboard/ClipboardManager';
import type { InputHandler } from '@/input/InputHandler';
import type { ModifierKey, ModifierManager } from '@/input/ModifierManager';
import type { AppConfig, ButtonConfig, ButtonSend, ModifierMode } from '@/types';
import type { DisconnectOverlay } from '@/ui/DisconnectOverlay';
import type { SettingsOverlay } from '@/ui/SettingsOverlay';
import type { TextViewOverlay } from '@/ui/TextViewOverlay';
import { buildAgentShareText, currentBaseUrl } from '@/utils/share';
import { getDisabledButtons } from '@/utils/storage';


function createToolbarRow(toolbar: HTMLElement, id: string): HTMLElement {
    const row = document.createElement('div');
    row.className = 'toolbar-row hidden';
    row.id = id;
    toolbar.appendChild(row);
    return row;
}


function createCustomButton(btn: { label: string; send: ButtonSend }): HTMLButtonElement {
    const button = document.createElement('button');
    button.className = 'tool-btn';
    button.textContent = btn.label;
    const send = btn.send || '';
    const sendArray = Array.isArray(send) ? send : [send];
    const encoded = sendArray.map(item =>
        typeof item === 'number' ? item : item
            .replace(/\r/g, '{CR}')
            .replace(/\n/g, '{LF}')
            .replace(/\x1b/g, '{ESC}')
    );
    button.dataset.send = JSON.stringify(encoded);
    return button;
}


export function renderCustomButtons(buttons: AppConfig['buttons']): void {
    if (!buttons?.length) return;

    const toolbar = document.getElementById('toolbar');
    if (!toolbar) return;

    const buttonsByRow = new Map<number, typeof buttons>();
    for (const button of buttons) {
        const row = button.row ?? 1;
        if (!buttonsByRow.has(row)) buttonsByRow.set(row, []);
        buttonsByRow.get(row)!.push(button);
    }

    for (const rowNum of [...buttonsByRow.keys()].sort((a, b) => a - b)) {
        const toolbarRowId = `toolbar-row${rowNum + 2}`;
        const toolbarRow = document.getElementById(toolbarRowId)
            ?? createToolbarRow(toolbar, toolbarRowId);

        for (const button of buttonsByRow.get(rowNum)!) {
            toolbarRow.appendChild(createCustomButton(button));
        }
        toolbarRow.classList.remove('hidden');
    }
}


export function rerenderToolbarButtons(buttons: ButtonConfig[], inputHandler: InputHandler): void {
    const toolbar = document.getElementById('toolbar');
    if (!toolbar) return;

    toolbar.querySelectorAll('[id^="toolbar-row"]:not(#toolbar-row1):not(#toolbar-row2)')
        .forEach(row => row.remove());
    renderCustomButtons(buttons);
    applyButtonVisibility();
    setupToolButtons(inputHandler);
}


export function updateModifierButton(modifier: ModifierKey, state: ModifierMode): void {
    const button = document.getElementById(`btn-${modifier}`);
    if (!button) return;

    button.classList.remove('sticky', 'locked');
    if (state === 'sticky') button.classList.add('sticky');
    if (state === 'locked') button.classList.add('locked');
}


export function setupModifierButtons(modifierManager: ModifierManager): void {
    for (const modifier of ['ctrl', 'alt', 'shift'] as const) {
        const button = document.getElementById(`btn-${modifier}`);
        if (!button) continue;

        let touchUsed = false;
        button.addEventListener('touchstart', event => {
            touchUsed = true;
            event.preventDefault();
        }, { passive: false });
        button.addEventListener('touchend', event => {
            event.preventDefault();
            modifierManager.handleTap(modifier);
        }, { passive: false });
        button.addEventListener('click', () => {
            if (!touchUsed) modifierManager.handleTap(modifier);
            touchUsed = false;
        });
    }
}


export function setupEscapeButton(inputHandler: InputHandler): void {
    const button = document.getElementById('btn-escape');
    if (!button) return;

    let touchUsed = false;
    let lastTapTime = 0;
    const handleTap = () => {
        const now = Date.now();
        inputHandler.sendInput(now - lastTapTime < 300 ? '\x1b\x1b' : '\x1b');
        lastTapTime = now;
    };

    button.addEventListener('touchstart', event => {
        touchUsed = true;
        event.preventDefault();
    }, { passive: false });
    button.addEventListener('touchend', event => {
        event.preventDefault();
        handleTap();
    }, { passive: false });
    button.addEventListener('click', () => {
        if (!touchUsed) handleTap();
        touchUsed = false;
    });
}


export function setupBackspaceButton(sendBackspace: () => void): void {
    const button = document.getElementById('btn-backspace');
    if (!button) return;

    let repeatTimer: ReturnType<typeof setInterval> | null = null;
    let initialTimer: ReturnType<typeof setTimeout> | null = null;
    let active = false;

    const startRepeat = () => {
        if (active) return;
        active = true;
        sendBackspace();
        initialTimer = setTimeout(() => {
            repeatTimer = setInterval(sendBackspace, 50);
        }, 400);
    };
    const stopRepeat = () => {
        active = false;
        if (initialTimer) clearTimeout(initialTimer);
        if (repeatTimer) clearInterval(repeatTimer);
        initialTimer = null;
        repeatTimer = null;
    };

    button.addEventListener('pointerdown', event => {
        event.preventDefault();
        startRepeat();
    }, { passive: false });
    button.addEventListener('pointerup', event => {
        event.preventDefault();
        stopRepeat();
    }, { passive: false });
    button.addEventListener('pointercancel', stopRepeat);
    button.addEventListener('pointerleave', stopRepeat);
    button.addEventListener('contextmenu', event => event.preventDefault());
}


function setupTapButton(
    buttonId: string,
    onAction: () => void | Promise<void>,
    options: { preventDefault?: boolean } = {},
): void {
    const button = document.getElementById(buttonId);
    if (!button) return;

    let touchUsed = false;
    const { preventDefault = true } = options;
    button.addEventListener('touchstart', event => {
        touchUsed = true;
        if (preventDefault) event.preventDefault();
    }, { passive: !preventDefault });
    button.addEventListener('touchend', event => {
        if (preventDefault) event.preventDefault();
        void onAction();
    }, { passive: !preventDefault });
    button.addEventListener('click', () => {
        if (!touchUsed) void onAction();
        touchUsed = false;
    });
}


export function setupPasteButton(doPaste: () => Promise<void>): void {
    setupTapButton('btn-paste', doPaste);
}


export function setupShareAgentButton(clipboardManager: ClipboardManager): void {
    setupTapButton('btn-share-agent', () => {
        const button = document.getElementById('btn-share-agent');
        const status = document.getElementById('share-agent-status');
        const copied = clipboardManager.copy(buildAgentShareText(currentBaseUrl()), 'agentShare');

        if (status) {
            status.textContent = copied ? 'Agent share link copied' : 'Agent share link was not copied';
        }
        if (button) {
            button.classList.toggle('copied', copied);
            window.setTimeout(() => button.classList.remove('copied'), 1500);
        }
    }, { preventDefault: false });
}


export function setupToolButtons(inputHandler: InputHandler): void {
    let touchUsed = false;

    document.querySelectorAll('.tool-btn').forEach(button => {
        const element = button as HTMLButtonElement;
        if (element.dataset.bound) return;
        element.dataset.bound = 'true';

        if (['btn-ctrl', 'btn-alt', 'btn-escape', 'btn-paste', 'btn-backspace', 'btn-shutdown']
            .includes(element.id)) return;

        const action = async () => {
            if (element.dataset.key) {
                inputHandler.handleKeyButton(element.dataset.key);
            } else if (element.dataset.send) {
                const items: Array<string | number> = JSON.parse(element.dataset.send);
                for (const item of items) {
                    if (typeof item === 'number') {
                        await new Promise(resolve => setTimeout(resolve, item));
                    } else {
                        inputHandler.sendInput(item
                            .replace(/\{CR\}/g, '\r')
                            .replace(/\{LF\}/g, '\n')
                            .replace(/\{ESC\}/g, '\x1b'));
                    }
                }
            }
        };

        let touchInside = false;
        element.addEventListener('touchstart', event => {
            touchUsed = true;
            touchInside = true;
            event.preventDefault();
        }, { passive: false });
        element.addEventListener('touchmove', event => {
            if (!touchInside) return;
            const touch = event.touches[0];
            if (!touch) return;
            const rect = element.getBoundingClientRect();
            if (touch.clientX < rect.left || touch.clientX > rect.right
                || touch.clientY < rect.top || touch.clientY > rect.bottom) {
                touchInside = false;
            }
        }, { passive: true });
        element.addEventListener('touchend', event => {
            event.preventDefault();
            if (touchInside) void action();
            touchInside = false;
        }, { passive: false });
        element.addEventListener('click', () => {
            if (!touchUsed) void action();
            touchUsed = false;
        });
    });
}


export function setupShutdownButton(disconnectOverlay: DisconnectOverlay): void {
    const button = document.getElementById('btn-shutdown');
    if (!button) return;

    button.addEventListener('click', async () => {
        (document.activeElement as HTMLElement)?.blur();
        if (!confirm('Shutdown server and tunnel?\n\nThis will terminate all sessions.')) return;

        try {
            const response = await fetch('/api/shutdown', { method: 'POST' });
            if (response.ok) {
                disconnectOverlay.setText('Server Shutdown');
                disconnectOverlay.show();
            }
        } catch (error) {
            console.error('Shutdown failed:', error);
        }
    });
}


export function setupHelpButton(): void {
    const button = document.getElementById('btn-info');
    const overlay = document.getElementById('help-overlay');
    const closeButton = document.getElementById('help-close');
    if (!button || !overlay) return;

    const show = () => overlay.classList.remove('hidden');
    const hide = () => overlay.classList.add('hidden');
    button.addEventListener('click', show);
    closeButton?.addEventListener('click', hide);
    overlay.addEventListener('click', event => {
        if (event.target === overlay) hide();
    });
}


export function setupSettingsButton(
    settingsOverlay: SettingsOverlay,
    getConfig: () => AppConfig,
): void {
    document.getElementById('btn-settings')?.addEventListener('click', () => {
        settingsOverlay.show(getConfig());
    });
}


export function applyButtonVisibility(): void {
    const disabledButtons = getDisabledButtons();
    document.querySelectorAll('.tool-btn[data-send]').forEach(button => {
        const element = button as HTMLElement;
        const label = element.textContent?.trim() || '';
        element.style.display = disabledButtons.includes(label) ? 'none' : '';
    });
}


export function setupTextViewButton(
    textViewOverlay: TextViewOverlay,
    getTerminal: () => Terminal | null,
    refreshTerminal: () => void,
): void {
    setupTapButton('btn-textview', () => {
        const terminal = getTerminal();
        if (terminal) textViewOverlay.show(terminal);
    }, { preventDefault: false });

    const onClose = () => {
        textViewOverlay.hide();
        refreshTerminal();
    };
    document.getElementById('textview-close')?.addEventListener('click', onClose);
    const overlay = document.getElementById('textview-overlay');
    overlay?.addEventListener('click', event => {
        if (event.target === overlay) onClose();
    });
}
