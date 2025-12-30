/**
 * Connection Status - Connection indicator dot
 * Single Responsibility: Connection status display
 */

export type ConnectionState = 'connected' | 'disconnected';

export interface ConnectionStatus {
    /** Set connection state */
    set(state: ConnectionState): void;
}

/**
 * Create a connection status controller
 */
export function createConnectionStatus(): ConnectionStatus {
    const dot = document.getElementById('connection-dot');

    return {
        set(state: ConnectionState): void {
            if (!dot) return;
            dot.className = state === 'connected' ? 'connected' : '';
        },
    };
}
