/**
 * Porterminal - Web-based terminal client
 * Main entry point - Application bootstrap and wiring
 *
 * Architecture: Backend-driven tab management
 * - ManagementService handles control plane (/ws/management)
 * - ConnectionService handles data plane (/ws for terminal I/O)
 * - TabService renders what the server tells it
 */

// Styles
import '@xterm/xterm/css/xterm.css';
import './styles/index.css';

// Core
import { createEventBus } from '@/core/events';

// Services
import { createConfigService } from '@/services/ConfigService';
import { createConnectionService } from '@/services/ConnectionService';
import { createManagementService } from '@/services/ManagementService';
import { createTabService } from '@/services/TabService';

// Input
import { createKeyMapper } from '@/input/KeyMapper';
import { createModifierManager } from '@/input/ModifierManager';
import { createInputHandler } from '@/input/InputHandler';

// Gestures
import { createSwipeDetector } from '@/gestures/SwipeDetector';
import { createSelectionHandler } from '@/gestures/SelectionHandler';
import { createGestureRecognizer } from '@/gestures/GestureRecognizer';

// Clipboard
import { createClipboardManager } from '@/clipboard/ClipboardManager';

// Terminal
import { createResizeManager } from '@/terminal/ResizeManager';

// UI
import { createCopyButton } from '@/ui/CopyButton';
import { createDisconnectOverlay } from '@/ui/DisconnectOverlay';
import { createConnectionStatus } from '@/ui/ConnectionStatus';
import { createTextViewOverlay } from '@/ui/TextViewOverlay';

// Types
import type { SwipeDirection } from '@/types';
import type { TabService } from '@/services/TabService';

// Configuration
const CONFIG = {
    maxReconnectAttempts: 5,
    reconnectDelayMs: 1000,
    heartbeatMs: 25000,
};

/**
 * Initialize the application
 */
async function init(): Promise<void> {
    // Detect mobile
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

    // Create core infrastructure
    const eventBus = createEventBus();

    // Create services
    const configService = createConfigService();

    // Create UI components
    const connectionStatus = createConnectionStatus();
    const disconnectOverlay = createDisconnectOverlay();
    const textViewOverlay = createTextViewOverlay();

    // Create clipboard manager
    const clipboardManager = createClipboardManager();

    // Create input components
    const keyMapper = createKeyMapper();
    const modifierManager = createModifierManager(eventBus, (modifier) => {
        updateModifierButton(modifier);
    });

    // Forward declaration for tabService
    let tabService: TabService;

    // Create management service (control plane)
    const managementService = createManagementService({
        onStateSync: (serverTabs) => {
            console.log('Received state sync:', serverTabs.length, 'tabs');
            tabService.applyStateSync(serverTabs);
        },
        onStateUpdate: (changes) => {
            console.log('Received state update:', changes);
            tabService.applyStateUpdate(changes);
        },
        onDisconnect: () => {
            console.log('Management WebSocket disconnected');
            connectionStatus.set('disconnected');
            disconnectOverlay.show();
        },
        onConnect: () => {
            console.log('Management WebSocket connected');
            disconnectOverlay.hide();
        },
    });

    // Create connection service (data plane for terminal I/O)
    const connectionService = createConnectionService(
        eventBus,
        {
            maxReconnectAttempts: CONFIG.maxReconnectAttempts,
            reconnectDelayMs: CONFIG.reconnectDelayMs,
            heartbeatMs: CONFIG.heartbeatMs,
        },
        {
            onSessionInfo: (tab, sessionId, tabId) => {
                // Update tab with server-assigned IDs
                tab.sessionId = sessionId;
                if (tabId) {
                    tab.tabId = tabId;
                }
            },
            onDisconnect: () => {
                connectionStatus.set('disconnected');
            },
            onReconnectFailed: () => {
                disconnectOverlay.show();
            },
        }
    );

    // Create resize manager
    const resizeManager = createResizeManager((tab, cols, rows) => {
        connectionService.sendResize(tab, cols, rows);
    });

    // Create tab service (render-only, backend-driven)
    tabService = createTabService(
        eventBus,
        managementService,
        connectionService,
        { isMobile },
        modifierManager.state,
        {
            onInputSend: () => {
                modifierManager.consumeSticky();
            },
            onSelectionCopy: (text) => {
                clipboardManager.copy(text, 'selectionChange');
            },
            scheduleResize: (tab) => {
                resizeManager.scheduleResize(tab);
            },
        }
    );

    // Create input handler
    const inputHandler = createInputHandler(
        eventBus,
        keyMapper,
        modifierManager,
        {
            sendInput: (data) => {
                const tab = tabService.activeTab;
                if (tab) {
                    connectionService.sendInput(tab, data);
                }
            },
            focusTerminal: () => {
                tabService.focusTerminal();
            },
        }
    );

    // Create copy button
    const copyButton = createCopyButton(
        clipboardManager,
        {
            clearSelection: () => {
                const tab = tabService.activeTab;
                if (tab) {
                    tab.term.clearSelection();
                }
            },
        }
    );

    // Create gesture components
    const swipeDetector = createSwipeDetector();
    const selectionHandler = createSelectionHandler();
    const gestureRecognizer = createGestureRecognizer(
        eventBus,
        swipeDetector,
        selectionHandler,
        {
            getActiveTerminal: () => tabService.activeTab?.term ?? null,
            sendArrowKey: (direction: SwipeDirection) => {
                const tab = tabService.activeTab;
                if (!tab) return;

                if (direction === 'up') {
                    connectionService.sendInput(tab, '\x1b[A');
                    if (navigator.vibrate) navigator.vibrate(20);
                } else if (direction === 'down') {
                    connectionService.sendInput(tab, '\x1b[B');
                    if (navigator.vibrate) navigator.vibrate(20);
                }
            },
            showCopyButton: (text, x, y) => {
                copyButton.show(text, x, y);
            },
            focusTerminal: () => {
                tabService.focusTerminal();
            },
            scheduleFitAfterFontChange: () => {
                const tab = tabService.activeTab;
                if (tab) {
                    setTimeout(() => tab.fitAddon.fit(), 50);
                }
            },
        }
    );

    // Setup UI components
    copyButton.setup();
    disconnectOverlay.setup(async () => {
        try {
            // 1. Reconnect management and wait for state sync
            if (!managementService.isConnected()) {
                await managementService.connect();
            }

            // 2. Connect data plane for synced tabs
            for (const tab of tabService.tabs) {
                if (!connectionService.isConnected(tab)) {
                    tab.reconnectAttempts = 0;
                    connectionService.connect(tab, true);
                }
            }

            disconnectOverlay.hide();
        } catch (e) {
            console.error('Retry failed:', e);
        }
    });

    // Load configuration
    const config = await configService.load();

    // Populate shell selector
    const shellSelect = document.getElementById('shell-select') as HTMLSelectElement | null;
    if (shellSelect) {
        shellSelect.innerHTML = '';
        for (const shell of config.shells) {
            const option = document.createElement('option');
            option.value = shell.id;
            option.textContent = shell.name;
            if (shell.id === config.default_shell) {
                option.selected = true;
            }
            shellSelect.appendChild(option);
        }

        // Handle shell change - close current tab and create new one with new shell
        shellSelect.addEventListener('change', async () => {
            const shellId = shellSelect.value;
            const currentTab = tabService.activeTab;
            if (shellId && currentTab) {
                try {
                    // Create new tab with selected shell first
                    await tabService.requestCreateTab(shellId);
                    // Then close the old tab
                    await tabService.requestCloseTab(currentTab.id);
                } catch (e) {
                    console.error('Failed to switch shell:', e);
                }
            }
        });
    }

    // Render custom buttons from config
    if (config.buttons && config.buttons.length > 0) {
        const toolbarRow = document.querySelector('.toolbar-row:last-child');
        if (toolbarRow) {
            for (const btn of config.buttons) {
                const button = document.createElement('button');
                button.className = 'tool-btn';
                button.textContent = btn.label;
                button.dataset.send = btn.send;
                toolbarRow.appendChild(button);
            }
        }
    }

    // Setup modifier buttons
    setupModifierButtons(modifierManager);

    // Setup escape button
    setupEscapeButton(inputHandler);

    // Setup backspace button
    setupBackspaceButton(() => {
        const tab = tabService.activeTab;
        if (tab) {
            connectionService.sendInput(tab, '\x7f');
        }
    });

    // Setup paste button
    setupPasteButton(async () => {
        const text = await clipboardManager.paste();
        if (text) {
            const tab = tabService.activeTab;
            if (tab) {
                connectionService.sendInput(tab, text);
                if (navigator.vibrate) navigator.vibrate(30);
            }
        }
        tabService.focusTerminal();
    });

    // Setup tool buttons
    setupToolButtons(inputHandler, tabService.focusTerminal.bind(tabService));

    // Setup shutdown button
    setupShutdownButton(disconnectOverlay);

    // Setup help button
    setupHelpButton();

    // Setup text view button
    textViewOverlay.setup();
    setupTextViewButton(textViewOverlay, () => tabService.activeTab?.term ?? null);

    // Attach gesture recognizer
    const terminalContainer = document.getElementById('terminal-container');
    if (terminalContainer) {
        gestureRecognizer.attach(terminalContainer);
    }

    // Connection events for terminal WebSockets
    eventBus.on('connection:open', ({ tabId }) => {
        if (tabId === tabService.activeTabId) {
            connectionStatus.set('connected');
            disconnectOverlay.hide();
        }
    });

    eventBus.on('connection:close', ({ tabId }) => {
        if (tabId === tabService.activeTabId) {
            connectionStatus.set('disconnected');
        }
    });

    // Clean up resize timers when tabs are closed
    eventBus.on('tab:closed', ({ tabId }) => {
        resizeManager.cancelResize(tabId);
    });

    // Handle visibility change - sync first, then reconnect
    document.addEventListener('visibilitychange', async () => {
        if (document.visibilityState === 'visible') {
            modifierManager.reset();

            try {
                // 1. Reconnect management WebSocket and wait for state sync
                if (!managementService.isConnected()) {
                    await managementService.connect();
                    // After connect() resolves, applyStateSync has been called
                    // tabService.tabs now reflects server state
                }

                // 2. Connect data plane for synced tabs only
                for (const tab of tabService.tabs) {
                    if (!connectionService.isConnected(tab)) {
                        connectionService.connect(tab, true);
                    }
                }
            } catch (e) {
                console.error('Failed to reconnect:', e);
                disconnectOverlay.show();
            }
        } else {
            modifierManager.reset();
        }
    });

    // Handle window blur
    window.addEventListener('blur', () => {
        modifierManager.reset();
    });

    // Handle window resize
    let resizeDebounce: ReturnType<typeof setTimeout>;
    window.addEventListener('resize', () => {
        clearTimeout(resizeDebounce);
        resizeDebounce = setTimeout(() => {
            const tab = tabService.activeTab;
            if (tab) {
                tab.fitAddon.fit();
            }
        }, 50);
    });

    // Handle orientation change
    window.addEventListener('orientationchange', () => {
        setTimeout(() => {
            const tab = tabService.activeTab;
            if (tab) {
                tab.fitAddon.fit();
            }
        }, 100);
    });

    // Handle visual viewport (mobile keyboard)
    if (window.visualViewport) {
        const app = document.getElementById('app');
        let viewportTimeout: ReturnType<typeof setTimeout>;
        window.visualViewport.addEventListener('resize', () => {
            if (app) {
                app.style.height = `${window.visualViewport!.height}px`;
            }
            clearTimeout(viewportTimeout);
            viewportTimeout = setTimeout(() => {
                const tab = tabService.activeTab;
                if (tab) {
                    tab.fitAddon.fit();
                }
            }, 50);
        });
    }

    // Focus terminal on container click
    document.getElementById('terminal-container')?.addEventListener('click', () => {
        tabService.focusTerminal();
    });

    // Connect management WebSocket first
    // Server will send tab_state_sync with existing tabs
    try {
        await managementService.connect();

        // If no tabs after sync, request one
        // Give a short delay for state sync to be processed
        setTimeout(async () => {
            if (tabService.tabs.length === 0) {
                console.log('No tabs from server, creating one');
                await tabService.requestCreateTab();
            }
        }, 100);
    } catch (e) {
        console.error('Failed to connect management WebSocket:', e);
        disconnectOverlay.show();
    }

    console.log('Porterminal initialized (backend-driven)');
}

// Helper functions for button setup

function updateModifierButton(modifier: string): void {
    const btn = document.getElementById(`btn-${modifier}`);
    if (!btn) return;

    const modifierManager = (window as unknown as { _modifierManager?: ReturnType<typeof createModifierManager> })._modifierManager;
    if (!modifierManager) return;

    btn.classList.remove('sticky', 'locked');
    const state = modifierManager.getState(modifier as 'ctrl' | 'alt' | 'shift');
    if (state === 'sticky') {
        btn.classList.add('sticky');
    } else if (state === 'locked') {
        btn.classList.add('locked');
    }
}

function setupModifierButtons(modifierManager: ReturnType<typeof createModifierManager>): void {
    (window as unknown as { _modifierManager?: ReturnType<typeof createModifierManager> })._modifierManager = modifierManager;

    for (const mod of ['ctrl', 'alt', 'shift'] as const) {
        const btn = document.getElementById(`btn-${mod}`);
        if (!btn) continue;

        let touchUsed = false;

        btn.addEventListener('touchstart', (e) => {
            touchUsed = true;
            e.preventDefault();
        }, { passive: false });

        btn.addEventListener('touchend', (e) => {
            e.preventDefault();
            modifierManager.handleTap(mod);
        }, { passive: false });

        btn.addEventListener('click', () => {
            if (!touchUsed) {
                modifierManager.handleTap(mod);
            }
            touchUsed = false;
        });
    }
}

function setupEscapeButton(inputHandler: ReturnType<typeof createInputHandler>): void {
    const btn = document.getElementById('btn-escape');
    if (!btn) return;

    let touchUsed = false;
    let lastTapTime = 0;
    const DOUBLE_TAP_MS = 300;

    const handleTap = () => {
        const now = Date.now();
        if (now - lastTapTime < DOUBLE_TAP_MS) {
            inputHandler.sendInput('\x1b\x1b');
        } else {
            inputHandler.sendInput('\x1b');
        }
        lastTapTime = now;
    };

    btn.addEventListener('touchstart', (e) => {
        touchUsed = true;
        e.preventDefault();
    }, { passive: false });

    btn.addEventListener('touchend', (e) => {
        e.preventDefault();
        handleTap();
    }, { passive: false });

    btn.addEventListener('click', () => {
        if (!touchUsed) {
            handleTap();
        }
        touchUsed = false;
    });
}

function setupBackspaceButton(sendBackspace: () => void): void {
    const btn = document.getElementById('btn-backspace');
    if (!btn) return;

    const INITIAL_DELAY = 400;
    const REPEAT_INTERVAL = 50;

    let repeatTimer: ReturnType<typeof setInterval> | null = null;
    let initialTimer: ReturnType<typeof setTimeout> | null = null;
    let isActive = false;

    const startRepeat = () => {
        if (isActive) return;
        isActive = true;
        sendBackspace();

        initialTimer = setTimeout(() => {
            repeatTimer = setInterval(sendBackspace, REPEAT_INTERVAL);
        }, INITIAL_DELAY);
    };

    const stopRepeat = () => {
        isActive = false;
        if (initialTimer) {
            clearTimeout(initialTimer);
            initialTimer = null;
        }
        if (repeatTimer) {
            clearInterval(repeatTimer);
            repeatTimer = null;
        }
    };

    btn.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        startRepeat();
    }, { passive: false });

    btn.addEventListener('pointerup', (e) => {
        e.preventDefault();
        stopRepeat();
    }, { passive: false });

    btn.addEventListener('pointercancel', stopRepeat);
    btn.addEventListener('pointerleave', stopRepeat);
    btn.addEventListener('contextmenu', (e) => e.preventDefault());
}

function setupPasteButton(doPaste: () => Promise<void>): void {
    const btn = document.getElementById('btn-paste');
    if (!btn) return;

    let touchUsed = false;

    btn.addEventListener('touchstart', (e) => {
        touchUsed = true;
        e.preventDefault();
    }, { passive: false });

    btn.addEventListener('touchend', (e) => {
        e.preventDefault();
        void doPaste();
    }, { passive: false });

    btn.addEventListener('click', () => {
        if (!touchUsed) {
            void doPaste();
        }
        touchUsed = false;
    });
}

function setupToolButtons(
    inputHandler: ReturnType<typeof createInputHandler>,
    focusTerminal: () => void
): void {
    let touchUsed = false;

    document.querySelectorAll('.tool-btn').forEach(btn => {
        const el = btn as HTMLButtonElement;
        if (el.dataset.bound) return;
        el.dataset.bound = 'true';

        if (el.id === 'btn-ctrl' || el.id === 'btn-alt' ||
            el.id === 'btn-escape' || el.id === 'btn-paste' ||
            el.id === 'btn-backspace' || el.id === 'btn-shutdown') {
            return;
        }

        const action = () => {
            if (el.dataset.key) {
                inputHandler.handleKeyButton(el.dataset.key);
            } else if (el.dataset.send) {
                inputHandler.sendInput(el.dataset.send);
                focusTerminal();
            }
        };

        el.addEventListener('touchstart', (e) => {
            touchUsed = true;
            e.preventDefault();
        }, { passive: false });

        el.addEventListener('touchend', (e) => {
            e.preventDefault();
            action();
        }, { passive: false });

        el.addEventListener('click', () => {
            if (!touchUsed) {
                action();
            }
            touchUsed = false;
        });
    });
}

function setupShutdownButton(disconnectOverlay: ReturnType<typeof createDisconnectOverlay>): void {
    const btn = document.getElementById('btn-shutdown');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        if (confirm('Shutdown server and tunnel?\n\nThis will terminate all sessions.')) {
            try {
                const response = await fetch('/api/shutdown', { method: 'POST' });
                if (response.ok) {
                    disconnectOverlay.setText('Server Shutdown');
                    disconnectOverlay.show();
                }
            } catch (e) {
                console.error('Shutdown failed:', e);
            }
        }
    });
}

function setupHelpButton(): void {
    const btn = document.getElementById('btn-info');
    const overlay = document.getElementById('help-overlay');
    const closeBtn = document.getElementById('help-close');

    if (!btn || !overlay) return;

    const show = () => overlay.classList.remove('hidden');
    const hide = () => overlay.classList.add('hidden');

    btn.addEventListener('click', show);
    closeBtn?.addEventListener('click', hide);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) hide();
    });
}

function setupTextViewButton(
    textViewOverlay: ReturnType<typeof createTextViewOverlay>,
    getTerminal: () => import('@xterm/xterm').Terminal | null
): void {
    const btn = document.getElementById('btn-textview');
    if (!btn) return;

    btn.addEventListener('click', () => {
        const term = getTerminal();
        if (term) {
            textViewOverlay.show(term);
        }
    });
}

// Register service worker
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js')
        .catch((e) => console.warn('SW registration failed:', e));
}

// Start the app
document.addEventListener('DOMContentLoaded', () => {
    void init();
});
