/**
 * Shared type definitions for Porterminal
 */

import type { Terminal } from '@xterm/xterm';
import type { FitAddon } from '@xterm/addon-fit';

/** Tab state */
export interface Tab {
    id: number;
    shellId: string;
    term: Terminal;
    fitAddon: FitAddon;
    container: HTMLElement;
    ws: WebSocket | null;
    sessionId: string | null;
    heartbeatInterval: ReturnType<typeof setInterval> | null;
    reconnectAttempts: number;
}

/** Saved tab state for localStorage persistence */
export interface SavedTab {
    id: number;
    shellId: string;
    sessionId: string | null;
}

/** Saved state from localStorage */
export interface SavedState {
    tabs: SavedTab[];
    activeTabId: number | null;
    tabCounter: number;
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

/** App configuration from /api/config */
export interface AppConfig {
    shells: ShellConfig[];
    default_shell: string;
    buttons?: Array<{ label: string; send: string }>;
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

export type WebSocketMessage = SessionInfoMessage | PingMessage | PongMessage | ErrorMessage;
