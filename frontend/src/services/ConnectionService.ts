/**
 * Connection Service - Terminal I/O Data Plane
 *
 * This service ONLY handles terminal WebSocket connections for data transfer.
 * It is NOT responsible for tab creation - that's ManagementService's job.
 *
 * Design principles:
 * - Requires valid tab_id (from server) to connect
 * - Only handles binary data and session_info/ping/pong messages
 * - Rejects stale/invalid tabs without attempting to create new ones
 * - Clean separation from control plane (ManagementService)
 */

import type { Tab, ConnectionState } from '@/types';
import type { EventBus } from '@/core/events';

export interface ConnectionConfig {
    maxReconnectAttempts: number;
    reconnectDelayMs: number;
    heartbeatMs: number;
}

export interface ConnectionService {
    /** Connect a tab's terminal WebSocket (tab must have valid tabId) */
    connect(tab: Tab, skipBuffer?: boolean): void;

    /** Disconnect a tab */
    disconnect(tab: Tab): void;

    /** Send binary input to a tab */
    sendInput(tab: Tab, data: string): void;

    /** Send a resize message */
    sendResize(tab: Tab, cols: number, rows: number): void;

    /** Check if a tab is connected */
    isConnected(tab: Tab): boolean;

    /** Get connection state for a tab */
    getState(tabId: number): ConnectionState;

    /** Clean up all state for a tab (call when tab is closed) */
    cleanupTabState(tabId: number): void;

    /** Set auth password for connections (null to clear) */
    setAuthPassword(password: string | null): void;
}

/** Internal state for each tab's connection */
interface TabConnectionState {
    state: ConnectionState;
    pendingReconnect: ReturnType<typeof setTimeout> | null;
    earlyBuffer: string[];
    // Watermark-based flow control (xterm.js recommended approach)
    watermark: number;        // Bytes queued in xterm.js render pipeline (written but not yet rendered)
    connectionGen: number;    // Detect stale callbacks after reconnect
    pauseSent: boolean;       // Track if we've sent pause to server
    // Emergency watermark reset tracking
    lastWatermarkActivity: number;  // Timestamp of last watermark change
    emergencyResetTimer: ReturnType<typeof setTimeout> | null;
    // Pause confirmation tracking
    pauseConfirmPending: boolean;
    pauseRetryTimer: ReturnType<typeof setTimeout> | null;
    // RAF-batched writes for high throughput
    writeBatch: string[];
    writeScheduled: boolean;
}

// Emergency reset timeout (ms) - reset watermark if no progress
const EMERGENCY_RESET_TIMEOUT = 5000;
// Maximum watermark before hard cap (500KB)
const MAX_WATERMARK = 500000;

// Server rejection codes that should NOT trigger reconnect
const REJECTION_CODES = {
    TAB_ID_REQUIRED: 4000,
    TAB_NOT_FOUND: 4004,
    SESSION_ENDED: 4005,
} as const;

// Buffer size limit for early buffer (data received before connected)
const MAX_EARLY_BUFFER_SIZE = 1024 * 1024;  // 1MB

// Watermark-based flow control constants (from xterm.js flow control guide)
// Keep HIGH_WATERMARK <= 500KB for responsive keystrokes
// Adaptive thresholds: lower for mobile/slow devices to prevent jamming
function getWatermarks(): { high: number; low: number } {
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    const isSlowDevice = typeof navigator.hardwareConcurrency === 'number' && navigator.hardwareConcurrency <= 4;
    if (isMobile || isSlowDevice) {
        return { high: 32000, low: 4000 };   // 32KB / 4KB for mobile/slow devices
    }
    return { high: 100000, low: 10000 };     // 100KB / 10KB for desktop
}
const { high: HIGH_WATERMARK, low: LOW_WATERMARK } = getWatermarks();

/** Calculate total size of string buffer */
function getBufferSize(buffer: string[]): number {
    return buffer.reduce((acc, s) => acc + s.length, 0);
}

/** Trim buffer from front until under size limit */
function trimBuffer(buffer: string[], maxSize: number): void {
    while (buffer.length > 1 && getBufferSize(buffer) > maxSize) {
        buffer.shift();
    }
}

/**
 * Create a connection service instance
 */
export function createConnectionService(
    eventBus: EventBus,
    config: ConnectionConfig,
    callbacks: {
        onSessionInfo: (tab: Tab, sessionId: string, tabId: string | null) => void;
        onDisconnect: () => void;
        onReconnectFailed: () => void;
    }
): ConnectionService {
    const textEncoder = new TextEncoder();
    const textDecoder = new TextDecoder();
    const tabStates = new Map<number, TabConnectionState>();

    // Auth password (set by main.ts after successful management auth)
    let authPassword: string | null = null;

    function getTabState(tabId: number): TabConnectionState {
        if (!tabStates.has(tabId)) {
            tabStates.set(tabId, {
                state: 'disconnected',
                pendingReconnect: null,
                earlyBuffer: [],
                watermark: 0,
                connectionGen: 0,
                pauseSent: false,
                lastWatermarkActivity: 0,
                emergencyResetTimer: null,
                pauseConfirmPending: false,
                pauseRetryTimer: null,
                writeBatch: [],
                writeScheduled: false,
            });
        }
        return tabStates.get(tabId)!;
    }

    function cancelPendingReconnect(tabId: number): void {
        const state = tabStates.get(tabId);
        if (state?.pendingReconnect) {
            clearTimeout(state.pendingReconnect);
            state.pendingReconnect = null;
        }
    }

    /**
     * Clear emergency reset timer for a tab state.
     */
    function clearEmergencyTimer(state: TabConnectionState): void {
        if (state.emergencyResetTimer) {
            clearTimeout(state.emergencyResetTimer);
            state.emergencyResetTimer = null;
        }
    }

    /**
     * Clear pause retry timer for a tab state.
     */
    function clearPauseRetryTimer(state: TabConnectionState): void {
        if (state.pauseRetryTimer) {
            clearTimeout(state.pauseRetryTimer);
            state.pauseRetryTimer = null;
        }
    }

    /**
     * Send pause message with retry and confirmation tracking.
     */
    function sendPauseWithRetry(tab: Tab, state: TabConnectionState): void {
        if (state.pauseConfirmPending) return;  // Already waiting for confirmation

        try {
            if (tab.ws?.readyState === WebSocket.OPEN) {
                tab.ws.send(JSON.stringify({ type: 'pause' }));
                state.pauseSent = true;
                state.pauseConfirmPending = true;

                // Retry if no confirmation in 500ms
                state.pauseRetryTimer = setTimeout(() => {
                    if (state.pauseConfirmPending && tab.ws?.readyState === WebSocket.OPEN) {
                        console.warn('Retrying pause message (no ack received)');
                        tab.ws.send(JSON.stringify({ type: 'pause' }));
                    }
                }, 500);
            }
        } catch (e) {
            console.warn('Failed to send flow control pause:', e);
        }
    }

    /**
     * Start emergency watermark reset timer.
     * If watermark doesn't decrease within timeout, reset it to prevent permanent jam.
     */
    function startEmergencyResetTimer(tab: Tab, state: TabConnectionState): void {
        clearEmergencyTimer(state);

        state.emergencyResetTimer = setTimeout(() => {
            if (state.pauseSent && (Date.now() - state.lastWatermarkActivity) > EMERGENCY_RESET_TIMEOUT) {
                console.warn('Emergency watermark reset - xterm.js callbacks stalled');
                state.watermark = 0;
                state.pauseSent = false;
                state.pauseConfirmPending = false;
                clearPauseRetryTimer(state);

                // Send ACK to resume server
                try {
                    if (tab.ws?.readyState === WebSocket.OPEN) {
                        tab.ws.send(JSON.stringify({ type: 'ack' }));
                    }
                } catch (e) {
                    console.warn('Failed to send emergency ack:', e);
                }
            }
        }, EMERGENCY_RESET_TIMEOUT);
    }

    /**
     * Write data to terminal with watermark-based flow control.
     *
     * This implements the xterm.js recommended flow control pattern with enhancements:
     * 1. RAF batching: coalesce multiple writes into single animation frame
     * 2. Track watermark (bytes written - bytes processed)
     * 3. When watermark exceeds HIGH_WATERMARK, send 'pause' to server with retry
     * 4. When watermark drops below LOW_WATERMARK, send 'ack' to server
     * 5. Emergency reset if watermark doesn't decrease within timeout
     * 6. Hard cap on watermark to prevent unbounded growth
     */
    function writeWithFlowControl(tab: Tab, state: TabConnectionState, data: string): void {
        // Add to write batch for RAF coalescing
        state.writeBatch.push(data);
        // Update watermark with hard cap to prevent unbounded growth
        state.watermark = Math.min(state.watermark + data.length, MAX_WATERMARK);
        state.lastWatermarkActivity = Date.now();

        // Schedule RAF-batched write if not already scheduled
        if (!state.writeScheduled) {
            state.writeScheduled = true;
            requestAnimationFrame(() => {
                if (state.writeBatch.length === 0) {
                    state.writeScheduled = false;
                    return;
                }

                const currentGen = state.connectionGen;
                const combined = state.writeBatch.join('');
                const batchLength = combined.length;
                state.writeBatch = [];
                state.writeScheduled = false;

                // Write batched data to xterm.js with callback for flow control
                tab.term.write(combined, () => {
                    // Ignore stale callbacks from previous connections
                    if (currentGen !== state.connectionGen) return;

                    // Decrease watermark - this data has been processed
                    state.watermark = Math.max(0, state.watermark - batchLength);
                    state.lastWatermarkActivity = Date.now();

                    // Clear emergency timer since we made progress
                    clearEmergencyTimer(state);

                    // Send ACK to resume server if watermark dropped below threshold
                    if (state.pauseSent && state.watermark < LOW_WATERMARK) {
                        try {
                            if (tab.ws?.readyState === WebSocket.OPEN) {
                                tab.ws.send(JSON.stringify({ type: 'ack' }));
                                state.pauseSent = false;
                                state.pauseConfirmPending = false;
                                clearPauseRetryTimer(state);
                            }
                        } catch (e) {
                            console.warn('Failed to send flow control ack:', e);
                            state.pauseSent = false;  // Reset to allow retry on next callback
                        }
                    }
                });

                // Send pause to server if watermark exceeds threshold
                if (!state.pauseSent && state.watermark > HIGH_WATERMARK) {
                    sendPauseWithRetry(tab, state);
                    // Start emergency reset timer in case xterm.js callbacks stall
                    startEmergencyResetTimer(tab, state);
                }
            });
        }
    }

    /**
     * Sync terminal size to match server dimensions.
     * Called when server sends dimensions (session_info or resize_sync).
     * This ensures all clients sharing a session have consistent dimensions.
     */
    function syncTerminalSize(tab: Tab, cols: number, rows: number): void {
        // Only resize if dimensions differ
        if (tab.term.cols !== cols || tab.term.rows !== rows) {
            console.log(`Syncing terminal size to ${cols}x${rows} (was ${tab.term.cols}x${tab.term.rows})`);
            tab.term.resize(cols, rows);
        }
    }

    function cleanupWebSocket(tab: Tab): void {
        if (tab.ws) {
            tab.ws.onopen = null;
            tab.ws.onmessage = null;
            tab.ws.onclose = null;
            tab.ws.onerror = null;
            if (tab.ws.readyState === WebSocket.OPEN || tab.ws.readyState === WebSocket.CONNECTING) {
                tab.ws.close();
            }
            tab.ws = null;
        }
        if (tab.heartbeatInterval) {
            clearInterval(tab.heartbeatInterval);
            tab.heartbeatInterval = null;
        }
    }

    function buildWebSocketUrl(tabId: string, skipBuffer?: boolean): string {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const params = new URLSearchParams({ tab_id: tabId });
        if (skipBuffer) {
            params.set('skip_buffer', '1');
        }
        return `${protocol}//${window.location.host}/ws?${params}`;
    }

    const service: ConnectionService = {
        connect(tab: Tab, skipBuffer?: boolean): void {
            const state = getTabState(tab.id);
            cancelPendingReconnect(tab.id);

            // Validate: tab must have server-assigned ID
            if (!tab.tabId) {
                console.error(`Tab ${tab.id} has no tabId - cannot connect without server confirmation`);
                eventBus.emit('connection:error', { tabId: tab.id, error: 'No tabId' });
                return;
            }

            // Clean up any existing connection
            if (state.state !== 'disconnected') {
                cleanupWebSocket(tab);
                state.state = 'disconnected';
            }

            state.state = 'connecting';
            state.earlyBuffer = [];
            // Reset flow control state for new connection
            state.connectionGen++;
            state.watermark = 0;
            state.pauseSent = false;
            state.lastWatermarkActivity = 0;
            state.pauseConfirmPending = false;
            state.writeBatch = [];
            state.writeScheduled = false;
            // Clear any pending timers
            clearEmergencyTimer(state);
            clearPauseRetryTimer(state);

            const url = buildWebSocketUrl(tab.tabId, skipBuffer);
            const ws = new WebSocket(url);
            ws.binaryType = 'arraybuffer';
            tab.ws = ws;

            ws.onopen = () => {
                if (state.state !== 'connecting') {
                    ws.close();
                    return;
                }

                // Send auth as first message if password is set
                if (authPassword) {
                    ws.send(JSON.stringify({ type: 'auth', password: authPassword }));
                }

                tab.reconnectAttempts = 0;
                eventBus.emit('connection:open', { tabId: tab.id });

                // Start heartbeat
                tab.heartbeatInterval = setInterval(() => {
                    if (tab.ws?.readyState === WebSocket.OPEN) {
                        tab.ws.send(JSON.stringify({ type: 'ping' }));
                    }
                }, config.heartbeatMs);

                // Fit terminal after layout, then mark connected
                // Use two rAF frames: first for fit + resize, second for buffer flush
                // This ensures xterm.js has time to complete layout before we write buffered data
                requestAnimationFrame(() => {
                    if (state.state !== 'connecting') return;

                    tab.fitAddon.fit();
                    // Send resize IMMEDIATELY after fit, before flushing buffer.
                    // This ensures server knows current dimensions before we render
                    // buffered output that may have wrong cursor position.
                    if (tab.ws?.readyState === WebSocket.OPEN) {
                        tab.ws.send(JSON.stringify({
                            type: 'resize',
                            cols: tab.term.cols,
                            rows: tab.term.rows,
                        }));
                    }

                    // Second rAF: give xterm.js a full frame to complete layout
                    requestAnimationFrame(() => {
                        if (state.state !== 'connecting') return;

                        state.state = 'connected';
                        // Flush buffered data and show terminal
                        if (state.earlyBuffer.length > 0) {
                            const combined = state.earlyBuffer.join('');
                            state.earlyBuffer = [];

                            // Terminal starts with opacity:0 (set in TabService).
                            // Write buffer while hidden, then show after rendering completes.
                            tab.term.write(combined, () => {
                                // Double rAF: first frame for xterm.js render, second for paint
                                requestAnimationFrame(() => {
                                    requestAnimationFrame(() => {
                                        tab.term.scrollToBottom();
                                        tab.container.style.opacity = '';

                                        // Use onRender to catch async buffer reflow
                                        let count = 0;
                                        const disposable = tab.term.onRender(() => {
                                            tab.term.scrollToBottom();
                                            if (++count >= 5) disposable.dispose();
                                        });
                                        setTimeout(() => disposable.dispose(), 300);
                                    });
                                });
                            });
                        } else {
                            // No buffer to flush - show terminal immediately
                            tab.term.scrollToBottom();
                            tab.container.style.opacity = '';

                            // Use onRender to catch async buffer reflow
                            let count = 0;
                            const disposable = tab.term.onRender(() => {
                                tab.term.scrollToBottom();
                                if (++count >= 5) disposable.dispose();
                            });
                            setTimeout(() => disposable.dispose(), 300);
                        }
                    });
                });
            };

            ws.onmessage = (event: MessageEvent) => {
                if (event.data instanceof ArrayBuffer) {
                    const text = textDecoder.decode(event.data);
                    if (state.state === 'connecting') {
                        state.earlyBuffer.push(text);
                        trimBuffer(state.earlyBuffer, MAX_EARLY_BUFFER_SIZE);
                    } else if (state.state === 'connected') {
                        // Write with watermark-based flow control
                        writeWithFlowControl(tab, state, text);
                    }
                } else {
                    // JSON control messages
                    try {
                        const msg = JSON.parse(event.data as string);
                        switch (msg.type) {
                            case 'session_info':
                                callbacks.onSessionInfo(tab, msg.session_id, msg.tab_id ?? null);
                                // Sync terminal dimensions if server provides them
                                // This ensures new clients adapt to existing session dimensions
                                if (msg.cols && msg.rows) {
                                    syncTerminalSize(tab, msg.cols, msg.rows);
                                }
                                break;
                            case 'resize_sync':
                                // Server rejected our resize or is syncing dimensions
                                // Resize local terminal to match session dimensions
                                if (msg.cols && msg.rows) {
                                    syncTerminalSize(tab, msg.cols, msg.rows);
                                }
                                break;
                            case 'ping':
                                if (tab.ws?.readyState === WebSocket.OPEN) {
                                    tab.ws.send(JSON.stringify({ type: 'pong' }));
                                }
                                break;
                            case 'error':
                                console.error('Server error:', msg.message);
                                tab.term.write(`\r\n\x1b[31mError: ${msg.message}\x1b[0m\r\n`);
                                eventBus.emit('connection:error', { tabId: tab.id, error: msg.message });
                                break;
                            case 'pause_ack':
                                // Server confirmed pause - stop retry timer
                                state.pauseConfirmPending = false;
                                clearPauseRetryTimer(state);
                                break;
                        }
                    } catch (e) {
                        console.error('Failed to parse message:', e);
                    }
                }
            };

            ws.onclose = (event: CloseEvent) => {
                if (state.state === 'disconnecting') {
                    state.state = 'disconnected';
                    return;
                }

                if (state.state === 'connecting' || state.state === 'connected') {
                    state.state = 'disconnected';
                }

                if (tab.heartbeatInterval) {
                    clearInterval(tab.heartbeatInterval);
                    tab.heartbeatInterval = null;
                }

                eventBus.emit('connection:close', { tabId: tab.id, code: event.code });

                // Server rejected connection - tab is stale, don't reconnect
                if (event.code === REJECTION_CODES.TAB_ID_REQUIRED ||
                    event.code === REJECTION_CODES.TAB_NOT_FOUND ||
                    event.code === REJECTION_CODES.SESSION_ENDED) {
                    console.log(`Tab ${tab.id} rejected (code ${event.code}) - removing stale tab`);
                    eventBus.emit('tab:stale', { tabId: tab.id, serverId: tab.tabId, code: event.code });
                    return;
                }

                // Normal disconnect - try to reconnect
                if (tab.reconnectAttempts < config.maxReconnectAttempts) {
                    tab.reconnectAttempts++;
                    const delay = config.reconnectDelayMs * Math.min(tab.reconnectAttempts, 5);
                    state.pendingReconnect = setTimeout(() => {
                        state.pendingReconnect = null;
                        service.connect(tab, true);
                    }, delay);
                } else {
                    callbacks.onReconnectFailed();
                }
            };

            ws.onerror = () => {
                if (state.state === 'connecting' || state.state === 'connected') {
                    callbacks.onDisconnect();
                }
            };
        },

        disconnect(tab: Tab): void {
            const state = getTabState(tab.id);
            cancelPendingReconnect(tab.id);

            if (state.state === 'disconnected') {
                return;
            }

            state.state = 'disconnecting';
            cleanupWebSocket(tab);
            state.state = 'disconnected';
        },

        sendInput(tab: Tab, data: string): void {
            const state = getTabState(tab.id);
            if (state.state !== 'connected' || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) {
                return;
            }
            // Terminal response filtering handled by backend
            tab.ws.send(textEncoder.encode(data));
        },

        sendResize(tab: Tab, cols: number, rows: number): void {
            const state = getTabState(tab.id);
            if (state.state !== 'connected' || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) {
                return;
            }
            tab.ws.send(JSON.stringify({ type: 'resize', cols, rows }));
        },

        isConnected(tab: Tab): boolean {
            const state = getTabState(tab.id);
            return state.state === 'connected' && tab.ws?.readyState === WebSocket.OPEN;
        },

        getState(tabId: number): ConnectionState {
            return getTabState(tabId).state;
        },

        cleanupTabState(tabId: number): void {
            cancelPendingReconnect(tabId);
            const state = tabStates.get(tabId);
            if (state) {
                clearEmergencyTimer(state);
                clearPauseRetryTimer(state);
            }
            tabStates.delete(tabId);
        },

        setAuthPassword(password: string | null): void {
            authPassword = password;
        },
    };

    return service;
}
