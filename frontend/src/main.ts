/**
 * Porterminal - Web-based terminal client
 * Main entry point - Application bootstrap and wiring
 */

// Styles
import '@xterm/xterm/css/xterm.css';
import './styles/index.css';

// Core
import { createEventBus } from '@/core/events';

// Services
import { createStorageService } from '@/services/StorageService';
import { createConfigService } from '@/services/ConfigService';
import { createConnectionService } from '@/services/ConnectionService';
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

// Types
import type { SwipeDirection } from '@/types';

// Configuration
const CONFIG = {
    storageKey: 'porterminal-tabs',
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
    const storageService = createStorageService(CONFIG.storageKey);
    const configService = createConfigService();

    // Create UI components
    const connectionStatus = createConnectionStatus();
    const disconnectOverlay = createDisconnectOverlay();

    // Create clipboard manager
    const clipboardManager = createClipboardManager();

    // Create input components
    const keyMapper = createKeyMapper();
    const modifierManager = createModifierManager(eventBus, (modifier) => {
        updateModifierButton(modifier);
    });

    // Create connection service (needs callbacks)
    let tabService: ReturnType<typeof createTabService>;

    const connectionService = createConnectionService(
        eventBus,
        {
            maxReconnectAttempts: CONFIG.maxReconnectAttempts,
            reconnectDelayMs: CONFIG.reconnectDelayMs,
            heartbeatMs: CONFIG.heartbeatMs,
        },
        {
            onSessionInfo: (tab, sessionId) => {
                tab.sessionId = sessionId;
                tabService.save();
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

    // Create tab service
    tabService = createTabService(
        eventBus,
        storageService,
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
                    connectionService.sendInput(tab, '\x1b[A'); // Up arrow
                    if (navigator.vibrate) navigator.vibrate(20);
                } else if (direction === 'down') {
                    connectionService.sendInput(tab, '\x1b[B'); // Down arrow
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
    disconnectOverlay.setup(() => {
        // Retry all disconnected tabs
        for (const tab of tabService.tabs) {
            if (!connectionService.isConnected(tab)) {
                tab.reconnectAttempts = 0;
                connectionService.connect(tab, undefined, true);
            }
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

        // Handle shell change - proper sequence without arbitrary delay
        shellSelect.addEventListener('change', () => {
            const shellId = shellSelect.value;
            const tab = tabService.activeTab;
            if (shellId && tab) {
                // 1. Disconnect first (cancels pending reconnects via state machine)
                connectionService.disconnect(tab);

                // 2. Clear state AFTER disconnect
                tab.sessionId = null;
                tab.term.reset();
                tab.shellId = shellId;

                // 3. Connect immediately (state machine handles if already connecting)
                connectionService.connect(tab, shellId);
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

    // Attach gesture recognizer
    const terminalContainer = document.getElementById('terminal-container');
    if (terminalContainer) {
        gestureRecognizer.attach(terminalContainer);
    }

    // Connection events
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

    // Restore or create tabs
    const stored = storageService.load();
    if (stored && stored.tabs && stored.tabs.length > 0) {
        for (const savedTab of stored.tabs) {
            tabService.createTab(undefined, savedTab);
        }
        if (stored.activeTabId) {
            const tab = tabService.getTab(stored.activeTabId);
            if (tab) {
                tabService.switchToTab(stored.activeTabId);
            }
        }
    } else {
        tabService.createTab();
    }

    // Handle visibility change
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            // Reset modifiers when page becomes visible (prevent stuck keys)
            modifierManager.reset();

            // Reconnect disconnected tabs
            for (const tab of tabService.tabs) {
                if (!connectionService.isConnected(tab)) {
                    connectionService.connect(tab, undefined, true);
                }
            }
        } else {
            // Page is hidden - reset modifiers to prevent stuck state
            modifierManager.reset();
        }
    });

    // Handle window blur - reset modifiers
    window.addEventListener('blur', () => {
        modifierManager.reset();
    });

    // Clean up resize timers when tabs are closed
    eventBus.on('tab:closed', ({ tabId }) => {
        resizeManager.cancelResize(tabId);
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

    console.log('Porterminal initialized');
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
    // Store reference for updateModifierButton
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

        // Skip special buttons
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

// Register service worker
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js')
        .catch((e) => console.warn('SW registration failed:', e));
}

// Start the app
document.addEventListener('DOMContentLoaded', () => {
    void init();
});
