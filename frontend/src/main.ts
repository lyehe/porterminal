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

import { setupLifecycleHandlers } from '@/bootstrap/lifecycle';
import { wireTerminalScreenMirror } from '@/bootstrap/screenMirror';
import {
    applyButtonVisibility,
    renderCustomButtons,
    rerenderToolbarButtons,
    setupBackspaceButton,
    setupEscapeButton,
    setupHelpButton,
    setupModifierButtons,
    setupPasteButton,
    setupSettingsButton,
    setupShareAgentButton,
    setupShutdownButton,
    setupTextViewButton,
    setupToolButtons,
    updateModifierButton,
} from '@/bootstrap/toolbar';

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
import { createComposeInput } from '@/ui/ComposeInput';
import { createDisconnectOverlay } from '@/ui/DisconnectOverlay';
import { createAuthOverlay } from '@/ui/AuthOverlay';
import { createConnectionStatus } from '@/ui/ConnectionStatus';
import { createTextViewOverlay } from '@/ui/TextViewOverlay';
import { createTerminalScreenMirror } from '@/ui/TerminalScreenMirror';
import { createUpdateOverlay } from '@/ui/UpdateOverlay';
import { createSettingsOverlay } from '@/ui/SettingsOverlay';
import { renderToolbar } from '@/ui/Toolbar';

// Storage
import { getSavedPassword, savePassword, clearPassword } from '@/utils/storage';

// Types
import type { SwipeDirection, Tab } from '@/types';
import type { TabService } from '@/services/TabService';

/**
 * Perform fitAddon.fit() with scroll-to-bottom preservation.
 * Uses onRender callbacks to overcome xterm.js async reflow timing.
 */
function fitWithScrollToBottom(tab: Tab): void {
    tab.fitAddon.fit();

    // Immediate scroll
    tab.term.scrollToBottom();

    // onRender callbacks to catch async reflow
    let count = 0;
    const disposable = tab.term.onRender(() => {
        tab.term.scrollToBottom();
        if (++count >= 10) disposable.dispose();
    });

    // Timeout fallback
    setTimeout(() => {
        disposable.dispose();
        tab.term.scrollToBottom();
    }, 500);
}

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

    // Load configuration early so it's available for component initialization
    const config = await configService.load();

    // Create UI components
    const connectionStatus = createConnectionStatus();
    const disconnectOverlay = createDisconnectOverlay();
    const authOverlay = createAuthOverlay();
    const textViewOverlay = createTextViewOverlay();
    const terminalScreenMirror = createTerminalScreenMirror();
    const updateOverlay = createUpdateOverlay();
    const settingsOverlay = createSettingsOverlay();

    // Auth state
    let currentPassword = getSavedPassword();

    // Create clipboard manager
    const clipboardManager = createClipboardManager();

    // Create input components
    const keyMapper = createKeyMapper();
    const modifierManager = createModifierManager(eventBus);
    eventBus.on('modifier:changed', ({ modifier, state }) => {
        updateModifierButton(modifier, state);
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

    wireTerminalScreenMirror(eventBus, tabService, terminalScreenMirror);

    // Helper to send input to active tab
    const sendToActiveTab = (data: string): void => {
        const tab = tabService.activeTab;
        if (tab) {
            connectionService.sendInput(tab, data);
        }
    };

    // Create compose input (compose-then-send text input mode)
    const composeInput = createComposeInput({
        serverDefault: config.compose_mode,
        onToggle: (enabled) => {
            // Sync settings overlay when compose button is toggled
            settingsOverlay.syncComposeMode(enabled);
        },
    });
    composeInput.setup(sendToActiveTab);

    // Helper to focus terminal only when compose mode is disabled
    const focusTerminalIfNotComposing = (): void => {
        if (!composeInput.isEnabled()) {
            tabService.focusTerminal();
        }
    };

    // Create input handler
    const inputHandler = createInputHandler(
        keyMapper,
        modifierManager,
        { sendInput: sendToActiveTab }
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
            focusTerminal: focusTerminalIfNotComposing,
            scheduleFitAfterFontChange: () => {
                const tab = tabService.activeTab;
                if (tab) {
                    fitWithScrollToBottom(tab);
                }
            },
            setKeyboardEnabled: (enabled) => {
                tabService.setKeyboardEnabled(enabled);
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

    // Setup update overlay
    updateOverlay.setup();

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

    // Render custom buttons from config (supports multiple rows)
    renderCustomButtons(config.buttons);

    // Apply button visibility from localStorage (hide disabled buttons)
    applyButtonVisibility();

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
    setupToolButtons(inputHandler);

    // Setup agent share button
    setupShareAgentButton(clipboardManager);

    // Setup shutdown button
    setupShutdownButton(disconnectOverlay);

    // Setup help button
    setupHelpButton();

    // Mutable config reference for button updates
    let currentConfig = config;

    // Setup settings overlay
    settingsOverlay.setup(configService, managementService, {
        onComposeModeChange: (enabled) => {
            composeInput.setEnabled(enabled);
        },
        onButtonVisibilityChange: () => {
            applyButtonVisibility();
        },
        onButtonsChanged: (buttons) => {
            currentConfig = { ...currentConfig, buttons };
            rerenderToolbarButtons(buttons, inputHandler);
        },
    });
    setupSettingsButton(settingsOverlay, () => currentConfig);

    // Setup text view button
    textViewOverlay.setup();
    setupTextViewButton(
        textViewOverlay,
        () => tabService.activeTab?.term ?? null,
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

        // Use ResizeObserver to detect container size changes and refit terminal
        // This handles: compose toggle, visual viewport changes, window resize, etc.
        let resizeTimeout: ReturnType<typeof setTimeout>;
        const resizeObserver = new ResizeObserver(() => {
            // Debounce to avoid excessive refits
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                const tab = tabService.activeTab;
                if (tab) {
                    fitWithScrollToBottom(tab);
                }
            }, 50);
        });
        resizeObserver.observe(terminalContainer);
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

    setupLifecycleHandlers({
        modifierManager,
        managementService,
        connectionService,
        tabService,
        disconnectOverlay,
    });

    // Focus terminal on container click
    document.getElementById('terminal-container')?.addEventListener('click', focusTerminalIfNotComposing);

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

        // Always show version info on startup
        setTimeout(() => {
            updateOverlay.show({
                currentVersion: config.version || 'unknown',
                latestVersion: config.latest_version || null,
                upgradeCommand: config.upgrade_command || null,
                updateAvailable: config.update_available || false,
            });
        }, 500);
    } catch (e) {
        console.error('Failed to connect management WebSocket:', e);
        disconnectOverlay.show();
    }

    console.log('Porterminal initialized (backend-driven)');
}

// Start the app
document.addEventListener('DOMContentLoaded', () => {
    void init();
});
