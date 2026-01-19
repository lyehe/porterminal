/**
 * Shared type definitions for Porterminal
 */

import type { Terminal } from '@xterm/xterm';
import type { FitAddon } from '@xterm/addon-fit';

/** Tab state */
export interface Tab {
    id: number;                  // Local numeric ID for UI
    tabId: string | null;        // Server-assigned UUID
    shellId: string;
    term: Terminal;
    fitAddon: FitAddon;
    container: HTMLElement;
    ws: WebSocket | null;
    sessionId: string | null;
    heartbeatInterval: ReturnType<typeof setInterval> | null;
    reconnectAttempts: number;
}

/** Server tab info from tab_list message */
export interface ServerTab {
    id: string;                  // Server UUID
    session_id: string;
    shell_id: string;
    name: string;
    created_at: string;
    last_accessed: string;
}

/** Connection state machine */
export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'disconnecting';

/** Modifier key state */
export type ModifierMode = 'off' | 'sticky' | 'locked';

export interface ModifierState {
    ctrl: ModifierMode;
    alt: ModifierMode;
    shift: ModifierMode;
}

/** Shell configuration from server */
export interface ShellConfig {
    id: string;
    name: string;
}

/** Button send value: string or array of strings/numbers (numbers = wait ms) */
export type ButtonSend = string | Array<string | number>;

/** App configuration from /api/config */
export interface AppConfig {
    shells: ShellConfig[];
    default_shell: string;
    buttons?: Array<{ label: string; send: ButtonSend; row?: number }>;
    compose_mode?: boolean;  // Server default for compose mode
    // Version and update info
    version?: string;
    update_available?: boolean;
    latest_version?: string | null;
    upgrade_command?: string | null;
}

/** Gesture state for touch handling */
export interface GestureState {
    initialDistance: number;
    initialFontSize: number;
    isSelecting: boolean;
    longPressTimer: ReturnType<typeof setTimeout> | null;
    startX: number;
    startY: number;
    startTime: number;
    fontSizeChanged: boolean;
    lastTapTime: number;
    lastTapX: number;
    lastTapY: number;
    selectAnchorCol: number;
    selectAnchorRow: number;
    pointerId: number | null;
}

/** Swipe direction */
export type SwipeDirection = 'up' | 'down' | 'left' | 'right';

/** Swipe detection result */
export interface SwipeResult {
    direction: SwipeDirection;
}

/** Terminal position */
export interface TerminalPosition {
    col: number;
    row: number;
}

/** WebSocket message types */
export interface SessionInfoMessage {
    type: 'session_info';
    session_id: string;
    shell?: string;
    tab_id?: string | null;
}

export interface PingMessage {
    type: 'ping';
}

export interface PongMessage {
    type: 'pong';
}

export interface ErrorMessage {
    type: 'error';
    message: string;
}

export interface ResizeMessage {
    type: 'resize';
    cols: number;
    rows: number;
}

/** Tab sync messages from server */
export interface TabListMessage {
    type: 'tab_list';
    tabs: ServerTab[];
    timestamp: string;
}

export interface TabCreatedMessage {
    type: 'tab_created';
    tab: ServerTab;
}

export interface TabClosedMessage {
    type: 'tab_closed';
    tab_id: string;
    reason: string;
}

/** Management WebSocket message types */

/** Tab state change */
export interface TabChange {
    action: 'add' | 'remove' | 'update';
    tab_id: string;
    tab?: ServerTab;
    reason?: string;
}

/** Full state sync from server */
export interface TabStateSyncMessage {
    type: 'tab_state_sync';
    tabs: ServerTab[];
}

/** Incremental state update from server */
export interface TabStateUpdateMessage {
    type: 'tab_state_update';
    changes: TabChange[];
}

/** Response to create_tab request */
export interface CreateTabResponse {
    type: 'create_tab_response';
    request_id: string;
    success: boolean;
    tab?: ServerTab;
    error?: string;
}

/** Response to close_tab request */
export interface CloseTabResponse {
    type: 'close_tab_response';
    request_id: string;
    success: boolean;
    error?: string;
}

/** Authentication messages */
export interface AuthRequiredMessage {
    type: 'auth_required';
}

export interface AuthSuccessMessage {
    type: 'auth_success';
}

export interface AuthFailedMessage {
    type: 'auth_failed';
    attempts_remaining: number;
    error?: string;
}

export interface AuthMessage {
    type: 'auth';
    password: string;
}

export type ManagementMessage =
    | TabStateSyncMessage
    | TabStateUpdateMessage
    | CreateTabResponse
    | CloseTabResponse
    | PongMessage
    | AuthRequiredMessage
    | AuthSuccessMessage
    | AuthFailedMessage;
