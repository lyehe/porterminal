import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createEventBus } from '@/core/events';
import { createConnectionService } from '@/services/ConnectionService';
import type { Tab } from '@/types';

import { FakeWebSocket, installFakeWebSocket } from './fakeWebSocket';


function createTab(tabId: string | null = 'server-tab'): Tab {
    const container = document.createElement('div');
    container.style.opacity = '0';
    return {
        id: 1,
        tabId,
        shellId: 'pwsh',
        term: {
            cols: 80,
            rows: 24,
            write: vi.fn((_data: string, callback?: () => void) => callback?.()),
            scrollToBottom: vi.fn(),
            onRender: vi.fn(() => ({ dispose: vi.fn() })),
            resize: vi.fn(),
        } as unknown as Tab['term'],
        fitAddon: { fit: vi.fn() } as unknown as Tab['fitAddon'],
        container,
        ws: null,
        sessionId: null,
        heartbeatInterval: null,
        reconnectAttempts: 0,
        origin: 'human',
    };
}


describe('connection service', () => {
    beforeEach(() => {
        installFakeWebSocket();
    });

    it('authenticates, synchronizes session state, and sends terminal input', () => {
        const bus = createEventBus();
        const opened = vi.fn();
        bus.on('connection:open', opened);
        const callbacks = {
            onSessionInfo: vi.fn(),
            onDisconnect: vi.fn(),
            onReconnectFailed: vi.fn(),
        };
        const service = createConnectionService(bus, {
            maxReconnectAttempts: 2,
            reconnectDelayMs: 10,
            heartbeatMs: 30_000,
        }, callbacks);
        const tab = createTab();
        service.setAuthPassword('secret');

        service.connect(tab);
        const socket = FakeWebSocket.instances[0]!;
        socket.open();
        socket.message({
            type: 'session_info',
            session_id: 'session-1',
            tab_id: 'server-tab',
            cols: 100,
            rows: 30,
        });
        service.sendInput(tab, 'hello');

        expect(service.isConnected(tab)).toBe(true);
        expect(opened).toHaveBeenCalledWith({ tabId: 1 });
        expect(callbacks.onSessionInfo).toHaveBeenCalledWith(
            tab,
            'session-1',
            'server-tab',
        );
        expect(socket.sent[0]).toBe(JSON.stringify({ type: 'auth', password: 'secret' }));
        expect(new TextDecoder().decode(socket.sent.at(-1) as Uint8Array)).toBe('hello');

        service.disconnect(tab);
    });

    it('does not reconnect stale tabs', () => {
        const bus = createEventBus();
        const stale = vi.fn();
        bus.on('tab:stale', stale);
        const service = createConnectionService(bus, {
            maxReconnectAttempts: 2,
            reconnectDelayMs: 10,
            heartbeatMs: 30_000,
        }, {
            onSessionInfo: vi.fn(),
            onDisconnect: vi.fn(),
            onReconnectFailed: vi.fn(),
        });
        const tab = createTab();

        service.connect(tab);
        FakeWebSocket.instances[0]!.closeFromServer(4004, 'Tab not found');
        expect(stale).toHaveBeenCalledWith({ tabId: 1, serverId: 'server-tab', code: 4004 });
        expect(FakeWebSocket.instances).toHaveLength(1);
    });
});
