/**
 * Tab Service - Manages terminal tab lifecycle
 * Single Responsibility: Tab creation, switching, closing
 */

import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebglAddon } from '@xterm/addon-webgl';
import { WebLinksAddon } from '@xterm/addon-web-links';

import type { Tab, SavedTab, ModifierState } from '@/types';
import type { EventBus } from '@/core/events';
import type { StorageService } from './StorageService';
import type { ConnectionService } from './ConnectionService';

export interface TabServiceConfig {
    isMobile: boolean;
}

export interface TabService {
    /** All tabs */
    readonly tabs: readonly Tab[];

    /** Currently active tab */
    readonly activeTab: Tab | null;

    /** Active tab ID */
    readonly activeTabId: number | null;

    /** Tab counter for generating IDs */
    readonly tabCounter: number;

    /** Create a new tab */
    createTab(shellId?: string, savedTab?: SavedTab): Tab;

    /** Switch to a tab */
    switchToTab(tabId: number): void;

    /** Close a tab */
    closeTab(tabId: number): void;

    /** Get a tab by ID */
    getTab(tabId: number): Tab | undefined;

    /** Focus the active terminal */
    focusTerminal(): void;

    /** Save current state to storage */
    save(): void;
}

/**
 * Configure textarea for mobile devices
 */
function configureTerminalTextarea(textarea: HTMLTextAreaElement): void {
    textarea.setAttribute('autocomplete', 'terminal');
    textarea.setAttribute('type', 'text');
    textarea.setAttribute('name', 'xterm');
    textarea.setAttribute('autocorrect', 'on');
    textarea.setAttribute('autocapitalize', 'none');
    textarea.setAttribute('spellcheck', 'false');
    textarea.setAttribute('inputmode', 'text');
    textarea.setAttribute('enterkeyhint', 'send');
    textarea.setAttribute('role', 'textbox');
    textarea.setAttribute('aria-label', 'Terminal input');
    textarea.setAttribute('aria-multiline', 'false');
    textarea.removeAttribute('aria-hidden');
    textarea.setAttribute('data-form-type', 'other');
    textarea.setAttribute('data-lpignore', 'true');
    textarea.setAttribute('data-1p-ignore', 'true');
    textarea.setAttribute('data-bwignore', 'true');
    textarea.setAttribute('data-protonpass-ignore', 'true');
    textarea.setAttribute('data-dashlane-ignore', 'true');
    textarea.style.setProperty('-webkit-text-security', 'none', 'important');
}

/**
 * Read CSS variable from document
 */
function getCSSVar(name: string, fallback: string): string {
    const styles = getComputedStyle(document.documentElement);
    return styles.getPropertyValue(name).trim() || fallback;
}

/**
 * Create a tab service instance
 */
export function createTabService(
    eventBus: EventBus,
    storageService: StorageService,
    connectionService: ConnectionService,
    config: TabServiceConfig,
    modifiers: ModifierState,
    callbacks: {
        onInputSend: (data: string) => void;
        onSelectionCopy: (text: string) => void;
        scheduleResize: (tab: Tab) => void;
    }
): TabService {
    const tabs: Tab[] = [];
    let activeTabId: number | null = null;
    let tabCounter = 0;

    function getActiveTab(): Tab | null {
        return tabs.find(t => t.id === activeTabId) ?? null;
    }

    function saveState(): void {
        const savedTabs: SavedTab[] = tabs.map(tab => ({
            id: tab.id,
            shellId: tab.shellId,
            sessionId: tab.sessionId,
        }));
        storageService.save(savedTabs, activeTabId, tabCounter);
    }

    function renderTabs(): void {
        const tabBar = document.getElementById('tab-bar');
        const shellSelector = document.getElementById('shell-selector');
        if (!tabBar || !shellSelector) return;

        // Remove existing tab buttons
        tabBar.querySelectorAll('.tab-btn').forEach(btn => btn.remove());

        // Create tab buttons
        tabs.forEach(tab => {
            const tabBtn = document.createElement('button');
            tabBtn.className = 'tab-btn' + (tab.id === activeTabId ? ' active' : '');

            const label = document.createElement('span');
            label.className = 'tab-label';
            label.textContent = `${tab.shellId} ${tab.id}`;
            tabBtn.appendChild(label);

            if (tabs.length > 1) {
                const closeBtn = document.createElement('span');
                closeBtn.className = 'tab-close';
                closeBtn.textContent = '×';
                closeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    service.closeTab(tab.id);
                });
                tabBtn.appendChild(closeBtn);
            }

            tabBtn.addEventListener('click', () => service.switchToTab(tab.id));
            tabBar.insertBefore(tabBtn, shellSelector);
        });

        // Add tab button
        const addBtn = document.createElement('button');
        addBtn.className = 'tab-btn tab-add';
        addBtn.textContent = '+';
        addBtn.addEventListener('click', () => service.createTab());
        tabBar.insertBefore(addBtn, shellSelector);
    }

    const service: TabService = {
        get tabs() {
            return tabs;
        },

        get activeTab() {
            return getActiveTab();
        },

        get activeTabId() {
            return activeTabId;
        },

        get tabCounter() {
            return tabCounter;
        },

        createTab(shellId?: string, savedTab?: SavedTab): Tab {
            const id = savedTab?.id ?? ++tabCounter;
            if (savedTab?.id && savedTab.id > tabCounter) {
                tabCounter = savedTab.id;
            }

            const shell = savedTab?.shellId ?? shellId ??
                (document.getElementById('shell-select') as HTMLSelectElement)?.value ?? 'default';

            // Create container
            const container = document.createElement('div');
            container.id = `terminal-${id}`;
            container.className = 'terminal-instance';
            container.style.display = 'none';
            document.getElementById('terminal')?.appendChild(container);

            // Create terminal
            const terminal = new Terminal({
                cursorBlink: true,
                fontSize: config.isMobile ? 12 : 12,
                fontFamily: 'Menlo, Monaco, Consolas, monospace',
                theme: {
                    background: getCSSVar('--bg-primary', '#1e1e1e'),
                    foreground: getCSSVar('--text-primary', '#cccccc'),
                    cursor: getCSSVar('--cursor-color', '#aeafad'),
                    cursorAccent: getCSSVar('--bg-primary', '#1e1e1e'),
                    selectionBackground: getCSSVar('--selection-bg', 'rgba(38, 79, 120, 0.5)'),
                    black: '#000000',
                    red: '#cd3131',
                    green: '#0dbc79',
                    yellow: '#e5e510',
                    blue: '#2472c8',
                    magenta: '#bc3fbc',
                    cyan: '#11a8cd',
                    white: '#e5e5e5',
                    brightBlack: '#666666',
                    brightRed: '#f14c4c',
                    brightGreen: '#23d18b',
                    brightYellow: '#f5f543',
                    brightBlue: '#3b8eea',
                    brightMagenta: '#d670d6',
                    brightCyan: '#29b8db',
                    brightWhite: '#e5e5e5',
                },
                scrollback: 5000,
                convertEol: true,
                allowProposedApi: true,
                rightClickSelectsWord: true,
                altClickMovesCursor: false,
                smoothScrollDuration: 0,
                scrollSensitivity: 1,
                fastScrollSensitivity: 5,
            });

            const fitAddon = new FitAddon();
            terminal.loadAddon(fitAddon);

            const webLinksAddon = new WebLinksAddon();
            terminal.loadAddon(webLinksAddon);

            terminal.open(container);

            // Configure textarea for mobile
            const textarea = container.querySelector('.xterm-helper-textarea') as HTMLTextAreaElement | null;
            if (textarea) {
                configureTerminalTextarea(textarea);

                // iOS fix for delete key
                if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {
                    textarea.addEventListener('beforeinput', (e: InputEvent) => {
                        if (e.inputType === 'deleteContentBackward') {
                            e.preventDefault();
                            connectionService.sendInput(tab, '\x7f');
                        }
                    }, { capture: true });
                }
            }

            // Try WebGL on desktop
            if (!config.isMobile) {
                try {
                    const webglAddon = new WebglAddon();
                    webglAddon.onContextLoss(() => webglAddon.dispose());
                    terminal.loadAddon(webglAddon);
                } catch (e) {
                    console.warn('WebGL not available');
                }
            }

            const tab: Tab = {
                id,
                shellId: shell,
                term: terminal,
                fitAddon,
                container,
                ws: null,
                sessionId: savedTab?.sessionId ?? null,
                heartbeatInterval: null,
                reconnectAttempts: 0,
            };

            // Handle terminal input
            terminal.onData((data: string) => {
                if (terminal.hasSelection()) {
                    terminal.clearSelection();
                }

                let processed = data;

                // Apply modifiers
                if (data.length === 1 && data.charCodeAt(0) >= 32 && data.charCodeAt(0) < 127) {
                    const ctrlActive = modifiers.ctrl === 'sticky' || modifiers.ctrl === 'locked';
                    const altActive = modifiers.alt === 'sticky' || modifiers.alt === 'locked';

                    if (ctrlActive || altActive) {
                        let char = data;

                        if (ctrlActive) {
                            const code = char.toUpperCase().charCodeAt(0);
                            if (code >= 65 && code <= 90) {
                                char = String.fromCharCode(code - 64);
                            }
                        }

                        if (altActive) {
                            char = '\x1b' + char;
                        }

                        processed = char;
                    }
                }

                connectionService.sendInput(tab, processed);
                callbacks.onInputSend(processed);
            });

            // Auto-copy on selection
            terminal.onSelectionChange(() => {
                const selection = terminal.getSelection();
                if (selection && selection.length > 0) {
                    callbacks.onSelectionCopy(selection);
                }
            });

            // Handle resize
            terminal.onResize(() => {
                callbacks.scheduleResize(tab);
            });

            tabs.push(tab);
            renderTabs();
            this.switchToTab(id);
            connectionService.connect(tab, shell);
            saveState();

            eventBus.emit('tab:created', { tab });

            return tab;
        },

        switchToTab(tabId: number): void {
            const tab = tabs.find(t => t.id === tabId);
            if (!tab) return;

            // Hide all terminals
            tabs.forEach(t => {
                t.container.style.display = 'none';
            });

            // Show selected
            tab.container.style.display = 'block';
            activeTabId = tabId;

            // Update shell selector
            const shellSelect = document.getElementById('shell-select') as HTMLSelectElement | null;
            if (shellSelect) {
                shellSelect.value = tab.shellId;
            }

            // Focus and fit
            tab.term.focus();
            setTimeout(() => {
                tab.fitAddon.fit();
            }, 50);

            renderTabs();
            saveState();

            eventBus.emit('tab:switched', { tabId, tab });
        },

        closeTab(tabId: number): void {
            const index = tabs.findIndex(t => t.id === tabId);
            if (index === -1) return;

            const tab = tabs[index];
            if (!tab) return;

            // Cleanup
            connectionService.disconnect(tab);
            connectionService.cleanupTabState(tabId);  // Remove state machine entry
            tab.term.dispose();
            tab.container.remove();

            tabs.splice(index, 1);
            saveState();

            eventBus.emit('tab:closed', { tabId });

            // Switch to another tab or create new
            if (tabs.length === 0) {
                this.createTab();
            } else if (activeTabId === tabId) {
                const nextTab = tabs[Math.max(0, index - 1)];
                if (nextTab) {
                    this.switchToTab(nextTab.id);
                }
            }

            renderTabs();
        },

        getTab(tabId: number): Tab | undefined {
            return tabs.find(t => t.id === tabId);
        },

        focusTerminal(): void {
            const tab = getActiveTab();
            if (tab) {
                tab.term.focus();
            }
        },

        save(): void {
            saveState();
        },
    };

    return service;
}
