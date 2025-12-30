/**
 * Connection Service - Manages WebSocket connections with state machine
 * Single Responsibility: WebSocket lifecycle, messaging, reconnection
 */

import type { Tab, WebSocketMessage, ResizeMessage, ConnectionState } from '@/types';
import type { EventBus } from '@/core/events';

export interface ConnectionConfig {
    maxReconnectAttempts: number;
    reconnectDelayMs: number;
    heartbeatMs: number;
}

export interface ConnectionService {
    /** Connect a tab to the server */
    connect(tab: Tab, shellId?: string, skipBuffer?: boolean): void;

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
    earlyBuffer: string[];  // Buffer for data arriving before terminal is ready
}

// Terminal response pattern - filter these from input
const TERMINAL_RESPONSE_PATTERN = /\x1b\[\?[\d;]*c|\x1b\[[\d;]*R/g;

function filterTerminalResponses(data: string): string {
    if (!data.includes('\x1b[')) return data;
    return data.replace(TERMINAL_RESPONSE_PATTERN, '');
}

/**
 * Create a connection service instance with state machine
 */
export function createConnectionService(
    eventBus: EventBus,
    config: ConnectionConfig,
    callbacks: {
        onSessionInfo: (tab: Tab, sessionId: string) => void;
        onDisconnect: () => void;
        onReconnectFailed: () => void;
    }
): ConnectionService {
    const textEncoder = new TextEncoder();
    const textDecoder = new TextDecoder();

    // State machine per tab
    const tabStates = new Map<number, TabConnectionState>();

    function getTabState(tabId: number): TabConnectionState {
        if (!tabStates.has(tabId)) {
            tabStates.set(tabId, { state: 'disconnected', pendingReconnect: null, earlyBuffer: [] });
        }
        return tabStates.get(tabId)!;
    }

    /**
     * Cancel any pending reconnect timeout for a tab
     */
    function cancelPendingReconnect(tabId: number): void {
        const state = tabStates.get(tabId);
        if (state?.pendingReconnect) {
            clearTimeout(state.pendingReconnect);
            state.pendingReconnect = null;
        }
    }

    /**
     * Clean up WebSocket and heartbeat
     */
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

    function buildWebSocketUrl(tab: Tab, shellId?: string, skipBuffer?: boolean): string {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        let url = `${protocol}//${window.location.host}/ws`;

        const params = new URLSearchParams();
        if (tab.sessionId) {
            params.set('session_id', tab.sessionId);
        }
        if (shellId) {
            params.set('shell', shellId);
        }
        if (skipBuffer) {
            params.set('skip_buffer', '1');
        }

        if (params.toString()) {
            url += '?' + params.toString();
        }
        return url;
    }

    function handleMessage(tab: Tab, msg: WebSocketMessage): void {
        switch (msg.type) {
            case 'session_info':
                callbacks.onSessionInfo(tab, msg.session_id);
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
    }

    const service: ConnectionService = {
        connect(tab: Tab, shellId?: string, skipBuffer?: boolean): void {
            const state = getTabState(tab.id);

            // Cancel any pending reconnect first
            cancelPendingReconnect(tab.id);

            // State machine: can only connect from disconnected state
            if (state.state !== 'disconnected') {
                // If connecting/connected, clean up first
                cleanupWebSocket(tab);
                state.state = 'disconnected';
            }

            state.state = 'connecting';
            state.earlyBuffer = [];  // Clear any stale buffered data

            const url = buildWebSocketUrl(tab, shellId, skipBuffer);
            const ws = new WebSocket(url);
            ws.binaryType = 'arraybuffer';
            tab.ws = ws;

            ws.onopen = () => {
                // Only proceed if we're still in connecting state
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

                // Fit terminal after browser layout, then set connected state
                // This ensures terminal is properly sized before accepting data
                requestAnimationFrame(() => {
                    tab.fitAddon.fit();
                    state.state = 'connected';
                    // Flush any data that arrived during setup
                    if (state.earlyBuffer.length > 0) {
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
                    // Buffer data if terminal isn't ready yet (still in connecting state)
                    if (state.state === 'connecting') {
                        state.earlyBuffer.push(text);
                    } else if (state.state === 'connected') {
                        tab.term.write(text);
                    }
                } else if (state.state === 'connected' || state.state === 'connecting') {
                    // JSON messages can be handled immediately
                    try {
                        const msg = JSON.parse(event.data as string) as WebSocketMessage;
                        handleMessage(tab, msg);
                    } catch (e) {
                        console.error('Failed to parse message:', e);
                    }
                }
            };

            ws.onclose = (event: CloseEvent) => {
                // If we're intentionally disconnecting, don't auto-reconnect
                if (state.state === 'disconnecting') {
                    state.state = 'disconnected';
                    return;
                }

                // If we were connecting or connected, transition to disconnected
                if (state.state === 'connecting' || state.state === 'connected') {
                    state.state = 'disconnected';
                }

                if (tab.heartbeatInterval) {
                    clearInterval(tab.heartbeatInterval);
                    tab.heartbeatInterval = null;
                }

                eventBus.emit('connection:close', { tabId: tab.id, code: event.code });

                // Handle session not found
                if (event.code === 4004) {
                    console.log(`Session ${tab.sessionId} not found, creating new session`);
                    tab.sessionId = null;
                    tab.reconnectAttempts = 0;
                    state.pendingReconnect = setTimeout(() => {
                        state.pendingReconnect = null;
                        service.connect(tab, tab.shellId);
                    }, 500);
                    return;
                }

                // Auto-reconnect with exponential backoff
                if (tab.reconnectAttempts < config.maxReconnectAttempts) {
                    tab.reconnectAttempts++;
                    const delay = config.reconnectDelayMs * Math.min(tab.reconnectAttempts, 5);
                    state.pendingReconnect = setTimeout(() => {
                        state.pendingReconnect = null;
                        service.connect(tab, undefined, true);
                    }, delay);
                } else {
                    callbacks.onReconnectFailed();
                }
            };

            ws.onerror = () => {
                // Only handle if we're still in a valid state
                if (state.state === 'connecting' || state.state === 'connected') {
                    callbacks.onDisconnect();
                }
            };
        },

        disconnect(tab: Tab): void {
            const state = getTabState(tab.id);

            // Cancel any pending reconnect
            cancelPendingReconnect(tab.id);

            // Only disconnect if not already disconnected
            if (state.state === 'disconnected') {
                return;
            }

            // Set state to disconnecting to prevent onclose from auto-reconnecting
            state.state = 'disconnecting';
            cleanupWebSocket(tab);
            state.state = 'disconnected';
        },

        sendInput(tab: Tab, data: string): void {
            const state = getTabState(tab.id);
            if (state.state !== 'connected' || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) {
                return;
            }

            const filtered = filterTerminalResponses(data);
            if (!filtered) return;

            tab.ws.send(textEncoder.encode(filtered));
        },

        sendResize(tab: Tab, cols: number, rows: number): void {
            const state = getTabState(tab.id);
            if (state.state !== 'connected' || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) {
                return;
            }

            const msg: ResizeMessage = { type: 'resize', cols, rows };
            tab.ws.send(JSON.stringify(msg));
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
            tabStates.delete(tabId);
        },
    };

    return service;
}
