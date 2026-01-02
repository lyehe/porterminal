/**
 * Connection Status - Connection indicator dot
 * Single Responsibility: Connection status display
 */

export interface ConnectionStatus {
    /** Set connection state */
    set(state: 'connected' | 'disconnected'): void;
}

/**
 * Create a connection status controller
 */
export function createConnectionStatus(): ConnectionStatus {
    const dot = document.getElementById('connection-dot');

    return {
        set(state: 'connected' | 'disconnected'): void {
            if (!dot) return;
            dot.className = state === 'connected' ? 'connected' : '';
        },
    };
}
