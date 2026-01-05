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

    /** Flush pending writes immediately (call before resize operations) */
    flushWriteBuffer(tab: Tab): void;
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

// Buffer size limits to prevent memory exhaustion
const MAX_EARLY_BUFFER_SIZE = 1024 * 1024;  // 1MB
const MAX_WRITE_BUFFER_SIZE = 256 * 1024;   // 256KB

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

    /**
     * Flush pending writes immediately to prevent buffer corruption during resize.
     */
    function flushPendingWrites(tab: Tab): void {
        const state = tabStates.get(tab.id);
        if (!state) return;

        if (state.rafHandle !== null) {
            cancelAnimationFrame(state.rafHandle);
            state.rafHandle = null;
        }

        if (state.writeBuffer.length > 0) {
            const combined = state.writeBuffer.join('');
            state.writeBuffer = [];
            tab.term.write(combined);
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
            // Flush pending writes before resize to prevent buffer corruption
            flushPendingWrites(tab);
            console.log(`Syncing terminal size to ${cols}x${rows} (was ${tab.term.cols}x${tab.term.rows})`);
            tab.term.resize(cols, rows);
        }
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
                                    });
                                });
                            });
                        } else {
                            // No buffer to flush - show terminal immediately
                            tab.term.scrollToBottom();
                            tab.container.style.opacity = '';
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
                        // Batch writes within animation frame to prevent flickering
                        // when backend sends rapid cursor/text updates
                        state.writeBuffer.push(text);
                        trimBuffer(state.writeBuffer, MAX_WRITE_BUFFER_SIZE);
                        scheduleFlush(tab, state);
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
                                // Flush pending writes first to maintain message ordering
                                if (state.writeBuffer.length > 0) {
                                    const pending = state.writeBuffer.join('');
                                    state.writeBuffer = [];
                                    if (state.rafHandle !== null) {
                                        cancelAnimationFrame(state.rafHandle);
                                        state.rafHandle = null;
                                    }
                                    tab.term.write(pending);
                                }
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
            const state = tabStates.get(tabId);
            if (state && state.rafHandle !== null) {
                cancelAnimationFrame(state.rafHandle);
            }
            cancelPendingReconnect(tabId);
            tabStates.delete(tabId);
        },

        setAuthPassword(password: string | null): void {
            authPassword = password;
        },

        flushWriteBuffer(tab: Tab): void {
            flushPendingWrites(tab);
        },
    };

    return service;
}
