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
}

/** Internal state for each tab's connection */
interface TabConnectionState {
    state: ConnectionState;
    pendingReconnect: ReturnType<typeof setTimeout> | null;
    earlyBuffer: string[];
    writeBuffer: string[];      // Buffer for rAF batching during connected state
    rafHandle: number | null;   // requestAnimationFrame handle for batched writes
}

// Server rejection codes that should NOT trigger reconnect
const REJECTION_CODES = {
    TAB_ID_REQUIRED: 4000,
    TAB_NOT_FOUND: 4004,
    SESSION_ENDED: 4005,
} as const;

/**
 * Filter terminal response sequences that shouldn't be sent to PTY.
 * xterm.js generates these in response to queries (DA, cursor position).
 * If sent to PTY, they get echoed back and displayed as garbage.
 */
const TERMINAL_RESPONSE_PATTERN = /\x1b\[\?[\d;]*c|\x1b\[[\d;]*R/g;

function filterTerminalResponses(data: string): string {
    if (!data.includes('\x1b[')) return data;
    return data.replace(TERMINAL_RESPONSE_PATTERN, '');
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

    function getTabState(tabId: number): TabConnectionState {
        if (!tabStates.has(tabId)) {
            tabStates.set(tabId, {
                state: 'disconnected',
                pendingReconnect: null,
                earlyBuffer: [],
                writeBuffer: [],
                rafHandle: null,
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
     * Schedule a batched write to the terminal.
     * Collects all data within an animation frame and flushes in single write.
     * This prevents flickering when backend sends rapid cursor/text updates.
     */
    function scheduleFlush(tab: Tab, state: TabConnectionState): void {
        if (state.rafHandle !== null) return;  // Already scheduled

        state.rafHandle = requestAnimationFrame(() => {
            state.rafHandle = null;
            if (state.writeBuffer.length === 0) return;

            const combined = state.writeBuffer.join('');
            state.writeBuffer = [];
            tab.term.write(combined);
        });
    }

    function cleanupWebSocket(tab: Tab): void {
        // Cancel any pending rAF flush
        const state = tabStates.get(tab.id);
        if (state && state.rafHandle !== null) {
            cancelAnimationFrame(state.rafHandle);
            state.rafHandle = null;
            state.writeBuffer = [];
        }

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

            const url = buildWebSocketUrl(tab.tabId, skipBuffer);
            const ws = new WebSocket(url);
            ws.binaryType = 'arraybuffer';
            tab.ws = ws;

            ws.onopen = () => {
                if (state.state !== 'connecting') {
                    ws.close();
                    return;
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
                requestAnimationFrame(() => {
                    if (state.state !== 'connecting') return;

                    try {
                        tab.fitAddon.fit();
                        // Send resize IMMEDIATELY after fit, before flushing buffer.
                        // This ensures server knows current dimensions before we render
                        // buffered output that may have wrong cursor position.
                        // Bypass the debounced scheduleResize to avoid race condition.
                        if (tab.ws?.readyState === WebSocket.OPEN) {
                            tab.ws.send(JSON.stringify({
                                type: 'resize',
                                cols: tab.term.cols,
                                rows: tab.term.rows,
                            }));
                        }
                    } finally {
                        state.state = 'connected';
                        // Flush buffered data
                        for (const text of state.earlyBuffer) {
                            tab.term.write(text);
                        }
                        state.earlyBuffer = [];
                    }
                });
            };

            ws.onmessage = (event: MessageEvent) => {
                if (event.data instanceof ArrayBuffer) {
                    const text = textDecoder.decode(event.data);
                    if (state.state === 'connecting') {
                        state.earlyBuffer.push(text);
                    } else if (state.state === 'connected') {
                        // Batch writes within animation frame to prevent flickering
                        // when backend sends rapid cursor/text updates
                        state.writeBuffer.push(text);
                        scheduleFlush(tab, state);
                    }
                } else {
                    // JSON control messages
                    try {
                        const msg = JSON.parse(event.data as string);
                        switch (msg.type) {
                            case 'session_info':
                                callbacks.onSessionInfo(tab, msg.session_id, msg.tab_id ?? null);
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
            // Filter terminal response sequences before sending
            const filtered = filterTerminalResponses(data);
            if (!filtered) return;
            tab.ws.send(textEncoder.encode(filtered));
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
            const state = tabStates.get(tabId);
            if (state && state.rafHandle !== null) {
                cancelAnimationFrame(state.rafHandle);
            }
            cancelPendingReconnect(tabId);
            tabStates.delete(tabId);
        },
    };

    return service;
}
