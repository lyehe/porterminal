/**
 * Tab Service - Manages terminal tab rendering (backend-driven)
 *
 * This service is purely reactive - it renders what the backend tells it.
 * Tab creation/deletion is requested via ManagementService.
 */

import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebglAddon } from '@xterm/addon-webgl';
import { WebLinksAddon } from '@xterm/addon-web-links';

import type { Tab, ModifierState, ServerTab, TabChange } from '@/types';
import type { EventBus } from '@/core/events';
import type { ConnectionService } from './ConnectionService';
import type { ManagementService } from './ManagementService';

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

    /** Request tab creation (async - waits for server) */
    requestCreateTab(shellId?: string): Promise<Tab>;

    /** Request tab close (async - waits for server) */
    requestCloseTab(tabId: number): Promise<void>;

    /** Switch to a tab (local-only, no server call) */
    switchToTab(tabId: number): void;

    /** Apply full state sync from server */
    applyStateSync(serverTabs: ServerTab[]): void;

    /** Apply incremental state update from server */
    applyStateUpdate(changes: TabChange[]): void;

    /** Get a tab by local ID */
    getTab(tabId: number): Tab | undefined;

    /** Get a tab by server-assigned UUID */
    getTabByServerId(serverId: string): Tab | undefined;

    /** Focus the active terminal */
    focusTerminal(): void;

    /** Get default shell ID */
    getDefaultShellId(): string;
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
 * Create a tab service instance (backend-driven)
 */
export function createTabService(
    eventBus: EventBus,
    managementService: ManagementService,
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
    const serverIdToTab = new Map<string, Tab>();
    let activeTabId: number | null = null;
    let tabCounter = 0;

    function getActiveTab(): Tab | null {
        return tabs.find(t => t.id === activeTabId) ?? null;
    }

    function getNextLocalId(): number {
        const usedIds = new Set(tabs.map(t => t.id));
        let id = 1;
        while (usedIds.has(id)) {
            id++;
        }
        if (id > tabCounter) {
            tabCounter = id;
        }
        return id;
    }

    function renderTabs(): void {
        const tabBar = document.getElementById('tab-bar');
        const shellSelector = document.getElementById('shell-selector');
        if (!tabBar || !shellSelector) return;

        // Remove existing tab buttons
        tabBar.querySelectorAll('.tab-btn').forEach(btn => btn.remove());

        // Create tab buttons
        tabs.forEach((tab, index) => {
            const tabBtn = document.createElement('button');
            tabBtn.className = 'tab-btn' + (tab.id === activeTabId ? ' active' : '');

            const label = document.createElement('span');
            label.className = 'tab-label';
            // Display position (1-based) for stable ordering across reloads
            label.textContent = `${index + 1}`;
            tabBtn.appendChild(label);

            if (tabs.length > 1) {
                const closeBtn = document.createElement('span');
                closeBtn.className = 'tab-close';
                closeBtn.textContent = '×';

                // Hold-to-close: prevents accidental tab closure
                const HOLD_DURATION_MS = 400;
                let holdTimer: ReturnType<typeof setTimeout> | null = null;
                let isClosing = false;

                const startHold = (e: Event) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (isClosing) return;

                    closeBtn.classList.add('holding');
                    holdTimer = setTimeout(() => {
                        isClosing = true;
                        closeBtn.classList.remove('holding');
                        closeBtn.classList.add('ready');
                        service.requestCloseTab(tab.id).catch(console.error);
                    }, HOLD_DURATION_MS);
                };

                const cancelHold = () => {
                    if (holdTimer) {
                        clearTimeout(holdTimer);
                        holdTimer = null;
                    }
                    closeBtn.classList.remove('holding');
                };

                // Pointer events for unified touch/mouse handling
                closeBtn.addEventListener('pointerdown', startHold);
                closeBtn.addEventListener('pointerup', cancelHold);
                closeBtn.addEventListener('pointercancel', cancelHold);
                closeBtn.addEventListener('pointerleave', cancelHold);

                // Prevent click from switching tabs
                closeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                });

                tabBtn.appendChild(closeBtn);
            }

            tabBtn.addEventListener('click', () => service.switchToTab(tab.id));
            tabBar.insertBefore(tabBtn, shellSelector);
        });

        // Add tab button - async request
        const addBtn = document.createElement('button');
        addBtn.className = 'tab-btn tab-add';
        addBtn.textContent = '+';
        addBtn.addEventListener('click', () => {
            service.requestCreateTab().catch(console.error);
        });
        tabBar.insertBefore(addBtn, shellSelector);
    }

    /**
     * Create local tab rendering from server tab info
     */
    function createLocalRender(serverTab: ServerTab): Tab {
        const id = getNextLocalId();
        const shell = serverTab.shell_id;

        // Create container
        const container = document.createElement('div');
        container.id = `terminal-${id}`;
        container.className = 'terminal-instance';
        container.style.display = 'none';
        document.getElementById('terminal')?.appendChild(container);

        // Create terminal
        const terminal = new Terminal({
            cursorBlink: true,
            fontSize: config.isMobile ? 10 : 10,
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
            allowTransparency: false,
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

        // Try WebGL for best performance
        try {
            const webglAddon = new WebglAddon();
            webglAddon.onContextLoss(() => webglAddon.dispose());
            terminal.loadAddon(webglAddon);
        } catch {
            // DOM renderer is automatic fallback
        }

        const tab: Tab = {
            id,
            tabId: serverTab.id,
            shellId: shell,
            term: terminal,
            fitAddon,
            container,
            ws: null,
            sessionId: serverTab.session_id,
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

        // Add to collections
        tabs.push(tab);
        serverIdToTab.set(serverTab.id, tab);

        // Connect terminal WebSocket for I/O (tab has valid tabId from server)
        connectionService.connect(tab);

        eventBus.emit('tab:created', { tab });

        return tab;
    }

    /**
     * Remove local tab rendering
     */
    function removeLocalRender(serverId: string): void {
        const tab = serverIdToTab.get(serverId);
        if (!tab) return;

        const index = tabs.indexOf(tab);
        if (index === -1) return;

        // Cleanup
        connectionService.disconnect(tab);
        connectionService.cleanupTabState(tab.id);
        tab.term.dispose();
        tab.container.remove();

        // Remove from collections
        tabs.splice(index, 1);
        serverIdToTab.delete(serverId);

        eventBus.emit('tab:closed', { tabId: tab.id });

        // Switch to another tab if we closed the active one
        if (activeTabId === tab.id && tabs.length > 0) {
            const nextTab = tabs[Math.max(0, index - 1)];
            if (nextTab) {
                service.switchToTab(nextTab.id);
            }
        }
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

        async requestCreateTab(shellId?: string): Promise<Tab> {
            const shell = shellId ?? this.getDefaultShellId();

            // Request from server
            const serverTab = await managementService.createTab(shell);

            // Server confirmed - create local rendering
            const tab = createLocalRender(serverTab);

            // Switch to new tab
            this.switchToTab(tab.id);

            renderTabs();

            return tab;
        },

        async requestCloseTab(tabId: number): Promise<void> {
            const tab = tabs.find(t => t.id === tabId);
            if (!tab || !tab.tabId) {
                throw new Error('Tab not found or has no server ID');
            }

            // If this is the last tab, create a new one first
            if (tabs.length === 1) {
                await this.requestCreateTab();
            }

            // 1. Disconnect data plane FIRST to avoid race condition
            connectionService.disconnect(tab);

            // 2. Request close from server
            await managementService.closeTab(tab.tabId);

            // 3. Server confirmed - remove local rendering
            removeLocalRender(tab.tabId);

            renderTabs();
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

            eventBus.emit('tab:switched', { tabId, tab });
        },

        applyStateSync(serverTabs: ServerTab[]): void {
            const serverIds = new Set(serverTabs.map(t => t.id));

            // Remove tabs that no longer exist on server
            for (const [serverId] of serverIdToTab) {
                if (!serverIds.has(serverId)) {
                    removeLocalRender(serverId);
                }
            }

            // Add tabs that exist on server but not locally
            for (const serverTab of serverTabs) {
                if (!serverIdToTab.has(serverTab.id)) {
                    createLocalRender(serverTab);
                }
            }

            // If we have tabs but none active, activate the first one
            if (tabs.length > 0 && (activeTabId === null || !tabs.find(t => t.id === activeTabId))) {
                const firstTab = tabs[0];
                if (firstTab) {
                    this.switchToTab(firstTab.id);
                }
            }

            renderTabs();
        },

        applyStateUpdate(changes: TabChange[]): void {
            for (const change of changes) {
                switch (change.action) {
                    case 'add':
                        if (change.tab && !serverIdToTab.has(change.tab_id)) {
                            createLocalRender(change.tab);
                        }
                        break;

                    case 'remove':
                        if (serverIdToTab.has(change.tab_id)) {
                            removeLocalRender(change.tab_id);
                        }
                        break;

                    case 'update':
                        // Could update tab name, etc.
                        break;
                }
            }

            // If we have no tabs after updates, we need to request a new one
            if (tabs.length === 0) {
                this.requestCreateTab().catch(console.error);
            }

            renderTabs();
        },

        getTab(tabId: number): Tab | undefined {
            return tabs.find(t => t.id === tabId);
        },

        getTabByServerId(serverId: string): Tab | undefined {
            return serverIdToTab.get(serverId);
        },

        focusTerminal(): void {
            const tab = getActiveTab();
            if (tab) {
                tab.term.focus();
            }
        },

        getDefaultShellId(): string {
            const shellSelect = document.getElementById('shell-select') as HTMLSelectElement | null;
            return shellSelect?.value ?? 'default';
        },
    };

    return service;
}
