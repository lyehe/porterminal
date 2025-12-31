/**
 * Management Service - Control plane for tab operations
 *
 * Handles communication with /ws/management WebSocket for:
 * - Tab creation requests
 * - Tab close requests
 * - Tab rename requests
 * - State sync from server
 */

import type {
    ServerTab,
    TabChange,
    ManagementMessage,
} from '@/types';

export interface ManagementService {
    /** Connect to management WebSocket */
    connect(): Promise<void>;

    /** Disconnect from management WebSocket */
    disconnect(): void;

    /** Request tab creation (returns Promise that resolves when server confirms) */
    createTab(shellId: string): Promise<ServerTab>;

    /** Request tab close */
    closeTab(tabId: string): Promise<void>;

    /** Request tab rename */
    renameTab(tabId: string, name: string): Promise<ServerTab>;

    /** Check if connected */
    isConnected(): boolean;

    /** Send ping to keep connection alive */
    ping(): void;
}

export interface ManagementCallbacks {
    /** Called when server sends full state sync */
    onStateSync: (tabs: ServerTab[]) => void;

    /** Called when server sends incremental state update */
    onStateUpdate: (changes: TabChange[]) => void;

    /** Called when connection is lost */
    onDisconnect: () => void;

    /** Called when connection is established */
    onConnect?: () => void;
}

interface PendingRequest {
    resolve: (value: unknown) => void;
    reject: (error: Error) => void;
    timeout: ReturnType<typeof setTimeout>;
}

const REQUEST_TIMEOUT_MS = 10000;

export function createManagementService(
    callbacks: ManagementCallbacks
): ManagementService {
    let ws: WebSocket | null = null;
    const pendingRequests = new Map<string, PendingRequest>();
    let heartbeatInterval: ReturnType<typeof setInterval> | null = null;
    let initialSyncResolver: (() => void) | null = null;

    function generateRequestId(): string {
        return `req_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
    }

    function handleMessage(event: MessageEvent): void {
        try {
            const msg = JSON.parse(event.data) as ManagementMessage;

            switch (msg.type) {
                case 'tab_state_sync':
                    callbacks.onStateSync(msg.tabs);
                    // Resolve initial sync promise if waiting
                    if (initialSyncResolver) {
                        initialSyncResolver();
                        initialSyncResolver = null;
                    }
                    break;

                case 'tab_state_update':
                    callbacks.onStateUpdate(msg.changes);
                    break;

                case 'create_tab_response': {
                    const pending = pendingRequests.get(msg.request_id);
                    if (pending) {
                        clearTimeout(pending.timeout);
                        pendingRequests.delete(msg.request_id);
                        if (msg.success && msg.tab) {
                            pending.resolve(msg.tab);
                        } else {
                            pending.reject(new Error(msg.error || 'Failed to create tab'));
                        }
                    }
                    break;
                }

                case 'close_tab_response': {
                    const pending = pendingRequests.get(msg.request_id);
                    if (pending) {
                        clearTimeout(pending.timeout);
                        pendingRequests.delete(msg.request_id);
                        if (msg.success) {
                            pending.resolve(undefined);
                        } else {
                            pending.reject(new Error(msg.error || 'Failed to close tab'));
                        }
                    }
                    break;
                }

                case 'rename_tab_response': {
                    const pending = pendingRequests.get(msg.request_id);
                    if (pending) {
                        clearTimeout(pending.timeout);
                        pendingRequests.delete(msg.request_id);
                        if (msg.success && msg.tab) {
                            pending.resolve(msg.tab);
                        } else {
                            pending.reject(new Error(msg.error || 'Failed to rename tab'));
                        }
                    }
                    break;
                }

                case 'pong':
                    // Heartbeat response - nothing to do
                    break;
            }
        } catch (e) {
            console.error('Failed to parse management message:', e);
        }
    }

    function cleanup(): void {
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
            heartbeatInterval = null;
        }

        // Reject all pending requests
        for (const [requestId, pending] of pendingRequests) {
            clearTimeout(pending.timeout);
            pending.reject(new Error('Connection closed'));
            pendingRequests.delete(requestId);
        }
    }

    return {
        /**
         * Connect to management WebSocket.
         * Resolves AFTER receiving initial tab_state_sync from server.
         * This ensures state is synchronized before any data plane connections.
         */
        connect(): Promise<void> {
            return new Promise((resolve, reject) => {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const url = `${protocol}//${window.location.host}/ws/management`;

                ws = new WebSocket(url);

                // Store resolver for initial sync
                initialSyncResolver = resolve;

                ws.onopen = () => {
                    console.log('Management WebSocket connected, waiting for state sync...');

                    // Start heartbeat
                    heartbeatInterval = setInterval(() => {
                        if (ws?.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({ type: 'ping' }));
                        }
                    }, 25000);

                    callbacks.onConnect?.();
                    // Don't resolve here - wait for tab_state_sync
                };

                ws.onerror = (error) => {
                    console.error('Management WebSocket error:', error);
                    initialSyncResolver = null;
                    reject(new Error('Connection failed'));
                };

                ws.onmessage = handleMessage;

                ws.onclose = () => {
                    console.log('Management WebSocket disconnected');
                    // Reject if we were waiting for sync
                    if (initialSyncResolver) {
                        initialSyncResolver = null;
                        reject(new Error('Connection closed before sync'));
                    }
                    cleanup();
                    ws = null;
                    callbacks.onDisconnect();
                };
            });
        },

        disconnect(): void {
            if (ws) {
                cleanup();
                ws.close();
                ws = null;
            }
        },

        async createTab(shellId: string): Promise<ServerTab> {
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                throw new Error('Not connected to management WebSocket');
            }

            const requestId = generateRequestId();

            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    pendingRequests.delete(requestId);
                    reject(new Error('Request timeout'));
                }, REQUEST_TIMEOUT_MS);

                pendingRequests.set(requestId, {
                    resolve: resolve as (value: unknown) => void,
                    reject,
                    timeout,
                });

                ws!.send(JSON.stringify({
                    type: 'create_tab',
                    request_id: requestId,
                    shell_id: shellId,
                }));
            });
        },

        async closeTab(tabId: string): Promise<void> {
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                throw new Error('Not connected to management WebSocket');
            }

            const requestId = generateRequestId();

            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    pendingRequests.delete(requestId);
                    reject(new Error('Request timeout'));
                }, REQUEST_TIMEOUT_MS);

                pendingRequests.set(requestId, {
                    resolve: resolve as (value: unknown) => void,
                    reject,
                    timeout,
                });

                ws!.send(JSON.stringify({
                    type: 'close_tab',
                    request_id: requestId,
                    tab_id: tabId,
                }));
            });
        },

        async renameTab(tabId: string, name: string): Promise<ServerTab> {
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                throw new Error('Not connected to management WebSocket');
            }

            const requestId = generateRequestId();

            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    pendingRequests.delete(requestId);
                    reject(new Error('Request timeout'));
                }, REQUEST_TIMEOUT_MS);

                pendingRequests.set(requestId, {
                    resolve: resolve as (value: unknown) => void,
                    reject,
                    timeout,
                });

                ws!.send(JSON.stringify({
                    type: 'rename_tab',
                    request_id: requestId,
                    tab_id: tabId,
                    name: name,
                }));
            });
        },

        isConnected(): boolean {
            return ws?.readyState === WebSocket.OPEN;
        },

        ping(): void {
            if (ws?.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        },
    };
}
