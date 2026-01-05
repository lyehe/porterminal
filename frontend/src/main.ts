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
import { createAuthOverlay } from '@/ui/AuthOverlay';
import { createConnectionStatus } from '@/ui/ConnectionStatus';
import { createTextViewOverlay } from '@/ui/TextViewOverlay';
import { renderToolbar } from '@/ui/Toolbar';

// Auth storage
import { getSavedPassword, savePassword, clearPassword } from '@/utils/storage';

// Types
import type { SwipeDirection } from '@/types';
import type { TabService } from '@/services/TabService';

// Configuration (heartbeat matches backend HEARTBEAT_INTERVAL = 30s)
const CONFIG = {
    maxReconnectAttempts: 5,
    reconnectDelayMs: 1000,
    heartbeatMs: 30000,
};

/**
 * Initialize the application
 */
async function init(): Promise<void> {
    // Create core infrastructure
    const eventBus = createEventBus();

    // Create services
    const configService = createConfigService();

    // Create UI components
    const connectionStatus = createConnectionStatus();
    const disconnectOverlay = createDisconnectOverlay();
    const authOverlay = createAuthOverlay();
    const textViewOverlay = createTextViewOverlay();

    // Auth state
    let currentPassword = getSavedPassword();

    // Create clipboard manager
    const clipboardManager = createClipboardManager();

    // Create input components
    const keyMapper = createKeyMapper();
    const modifierManager = createModifierManager(eventBus, (modifier) => {
        updateModifierButton(modifier);
    });

    // Forward declaration for tabService
    let tabService: TabService;

    // Forward declaration for connectionService (needed in auth callbacks)
    let connectionService: ReturnType<typeof createConnectionService>;

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
            // Auto-auth if we have saved password
            if (currentPassword) {
                managementService.authenticate(currentPassword);
            }
        },
        onAuthRequired: () => {
            console.log('Authentication required');
            if (currentPassword) {
                // Try saved password first
                managementService.authenticate(currentPassword);
            } else {
                authOverlay.show();
            }
        },
        onAuthFailed: (attemptsRemaining, error) => {
            console.log('Authentication failed:', error, 'attempts remaining:', attemptsRemaining);
            clearPassword();
            currentPassword = null;
            connectionService?.setAuthPassword(null);
            if (attemptsRemaining > 0) {
                authOverlay.showError(error || `Invalid password. ${attemptsRemaining} attempts remaining.`);
            } else {
                authOverlay.showError(error || 'Too many failed attempts.');
            }
            authOverlay.clearInput();
            authOverlay.show();
        },
        onAuthSuccess: () => {
            console.log('Authentication successful');
            if (currentPassword) {
                savePassword(currentPassword);
                connectionService?.setAuthPassword(currentPassword);
            }
            authOverlay.hide();
        },
    });

    // Create connection service (data plane for terminal I/O)
    connectionService = createConnectionService(
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
                    setTimeout(() => {
                        // Flush pending writes before resize to prevent buffer corruption
                        connectionService.flushWriteBuffer(tab);
                        tab.fitAddon.fit();
                    }, 50);
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

    // Setup auth overlay
    authOverlay.setup((password) => {
        currentPassword = password;
        managementService.authenticate(password);
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

    // Render custom buttons from config (in third row)
    // send can be string or array of strings/numbers (numbers = wait ms)
    if (config.buttons && config.buttons.length > 0) {
        const toolbarRow3 = document.getElementById('toolbar-row3');
        if (toolbarRow3) {
            for (const btn of config.buttons) {
                const button = document.createElement('button');
                button.className = 'tool-btn';
                button.textContent = btn.label;
                // Normalize to array and encode for HTML storage
                const send = btn.send || '';
                const sendArray = Array.isArray(send) ? send : [send];
                const encoded = sendArray.map(item => {
                    if (typeof item === 'number') return item;
                    return item
                        .replace(/\r/g, '{CR}')
                        .replace(/\n/g, '{LF}')
                        .replace(/\x1b/g, '{ESC}');
                });
                button.dataset.send = JSON.stringify(encoded);
                toolbarRow3.appendChild(button);
            }
            toolbarRow3.classList.remove('hidden');
        }
    }

    // Render toolbar buttons from config
    renderToolbar();

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
    setupTextViewButton(
        textViewOverlay,
        () => tabService.activeTab?.term ?? null,
        () => {
            const tab = tabService.activeTab;
            if (tab) connectionService.flushWriteBuffer(tab);
        },
        () => {
            const tab = tabService.activeTab;
            if (tab) {
                // Force xterm.js to repaint all rows from buffer
                tab.term.refresh(0, tab.term.rows - 1);
            }
        }
    );

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
                connectionService.flushWriteBuffer(tab);
                tab.fitAddon.fit();
            }
        }, 50);
    });

    // Handle orientation change
    window.addEventListener('orientationchange', () => {
        setTimeout(() => {
            const tab = tabService.activeTab;
            if (tab) {
                connectionService.flushWriteBuffer(tab);
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
                    connectionService.flushWriteBuffer(tab);
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

/**
 * Setup a button with touch/click handling that prevents double-triggering.
 * NOT suitable for: hold-to-repeat, custom event types, or state machines.
 */
function setupTapButton(
    buttonId: string,
    onAction: () => void | Promise<void>,
    options: { preventDefault?: boolean } = {}
): void {
    const btn = document.getElementById(buttonId);
    if (!btn) return;

    let touchUsed = false;
    const { preventDefault = true } = options;

    btn.addEventListener('touchstart', (e) => {
        touchUsed = true;
        if (preventDefault) e.preventDefault();
    }, { passive: !preventDefault });

    btn.addEventListener('touchend', (e) => {
        if (preventDefault) e.preventDefault();
        void onAction();
    }, { passive: !preventDefault });

    btn.addEventListener('click', () => {
        if (!touchUsed) {
            void onAction();
        }
        touchUsed = false;
    });
}

function setupPasteButton(doPaste: () => Promise<void>): void {
    setupTapButton('btn-paste', doPaste);
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

        const action = async () => {
            if (el.dataset.key) {
                inputHandler.handleKeyButton(el.dataset.key);
            } else if (el.dataset.send) {
                // Parse JSON array of strings/numbers
                const items: Array<string | number> = JSON.parse(el.dataset.send);
                for (const item of items) {
                    if (typeof item === 'number') {
                        // Number = wait ms
                        await new Promise(r => setTimeout(r, item));
                    } else {
                        // String = decode and send
                        const decoded = item
                            .replace(/\{CR\}/g, '\r')
                            .replace(/\{LF\}/g, '\n')
                            .replace(/\{ESC\}/g, '\x1b');
                        inputHandler.sendInput(decoded);
                    }
                }
                focusTerminal();
            }
        };

        let touchInside = false;

        el.addEventListener('touchstart', (e) => {
            touchUsed = true;
            touchInside = true;
            e.preventDefault();
        }, { passive: false });

        el.addEventListener('touchmove', (e) => {
            if (!touchInside) return;
            const touch = e.touches[0];
            if (!touch) return;
            const rect = el.getBoundingClientRect();
            if (touch.clientX < rect.left || touch.clientX > rect.right ||
                touch.clientY < rect.top || touch.clientY > rect.bottom) {
                touchInside = false;
            }
        }, { passive: true });

        el.addEventListener('touchend', (e) => {
            e.preventDefault();
            if (touchInside) {
                action();
            }
            touchInside = false;
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
        // Hide keyboard on mobile
        (document.activeElement as HTMLElement)?.blur();

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
    getTerminal: () => import('@xterm/xterm').Terminal | null,
    flushWriteBuffer: () => void,
    refreshTerminal: () => void
): void {
    setupTapButton('btn-textview', () => {
        const term = getTerminal();
        if (term) {
            // Flush pending writes before reading terminal buffer
            // This ensures getTerminalText() sees the most up-to-date state
            flushWriteBuffer();
            textViewOverlay.show(term);
        }
    }, { preventDefault: false });

    // Force terminal refresh when overlay closes to repaint from buffer
    const closeBtn = document.getElementById('textview-close');
    const overlay = document.getElementById('textview-overlay');

    const onClose = () => {
        textViewOverlay.hide();
        refreshTerminal();
    };

    closeBtn?.addEventListener('click', onClose);
    overlay?.addEventListener('click', (e) => {
        if (e.target === overlay) onClose();
    });
}

// Start the app
document.addEventListener('DOMContentLoaded', () => {
    void init();
});
