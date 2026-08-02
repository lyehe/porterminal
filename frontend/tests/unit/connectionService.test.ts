import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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


function createService() {
    return createConnectionService(createEventBus(), {
        maxReconnectAttempts: 2,
        reconnectDelayMs: 10,
        heartbeatMs: 30_000,
    }, {
        onSessionInfo: vi.fn(),
        onDisconnect: vi.fn(),
        onReconnectFailed: vi.fn(),
    });
}


function binary(text: string): ArrayBuffer {
    const encoded = new TextEncoder().encode(text);
    const buffer = new window.ArrayBuffer(encoded.byteLength);
    new window.Uint8Array(buffer).set(encoded);
    return buffer;
}


function receiveBinary(socket: FakeWebSocket, text: string): void {
    socket.onmessage?.({ data: binary(text) } as MessageEvent<ArrayBuffer>);
}


describe('connection service', () => {
    beforeEach(() => {
        installFakeWebSocket();
    });

    afterEach(() => {
        vi.clearAllTimers();
        vi.useRealTimers();
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

    it('reconnects normal closures with buffer replay disabled', () => {
        vi.useFakeTimers();
        const service = createService();
        const tab = createTab();

        service.connect(tab);
        const first = FakeWebSocket.instances[0]!;
        first.open();
        first.closeFromServer(1006, 'network lost');

        expect(service.getState(tab.id)).toBe('disconnected');
        expect(FakeWebSocket.instances).toHaveLength(1);
        vi.advanceTimersByTime(10);

        expect(FakeWebSocket.instances).toHaveLength(2);
        expect(FakeWebSocket.instances[1]!.url).toContain('skip_buffer=1');
        service.disconnect(tab);
    });

    it('cancels a pending reconnect when tab state is cleaned up', () => {
        vi.useFakeTimers();
        const service = createService();
        const tab = createTab();

        service.connect(tab);
        FakeWebSocket.instances[0]!.open();
        FakeWebSocket.instances[0]!.closeFromServer(1006, 'network lost');
        service.cleanupTabState(tab.id);
        vi.advanceTimersByTime(100);

        expect(FakeWebSocket.instances).toHaveLength(1);
    });

    it('trims buffered output received before the connection opens', () => {
        const service = createService();
        const tab = createTab();
        const write = vi.mocked(tab.term.write);
        const firstChunk = 'a'.repeat(600_000);
        const secondChunk = 'b'.repeat(600_000);

        service.connect(tab);
        const socket = FakeWebSocket.instances[0]!;
        receiveBinary(socket, firstChunk);
        receiveBinary(socket, secondChunk);
        socket.open();

        expect(write).toHaveBeenCalledTimes(1);
        expect(write).toHaveBeenCalledWith(secondChunk, expect.any(Function));
    });

    it('confirms pause once and performs emergency recovery when rendering stalls', () => {
        vi.useFakeTimers();
        const service = createService();
        const tab = createTab();
        tab.term.write = vi.fn();

        service.connect(tab);
        const socket = FakeWebSocket.instances[0]!;
        socket.open();
        vi.advanceTimersByTime(32);
        receiveBinary(socket, 'x'.repeat(100_001));
        vi.advanceTimersToNextFrame();

        const pause = JSON.stringify({ type: 'pause' });
        const ack = JSON.stringify({ type: 'ack' });
        expect(socket.sent.filter((item) => item === pause)).toHaveLength(1);

        socket.message({ type: 'pause_ack' });
        vi.advanceTimersByTime(500);
        expect(socket.sent.filter((item) => item === pause)).toHaveLength(1);

        vi.advanceTimersByTime(4_500);
        expect(socket.sent.filter((item) => item === ack)).toHaveLength(1);
        service.disconnect(tab);
    });

    it('ignores render callbacks left behind by an older connection generation', () => {
        const service = createService();
        const tab = createTab();
        let rendered: (() => void) | undefined;
        tab.term.write = vi.fn((_data: string, callback?: () => void) => {
            rendered = callback;
        });

        service.connect(tab);
        const first = FakeWebSocket.instances[0]!;
        first.open();
        receiveBinary(first, 'x'.repeat(100_001));
        service.connect(tab);
        rendered?.();

        expect(first.sent).not.toContain(JSON.stringify({ type: 'ack' }));
        service.disconnect(tab);
    });
});
