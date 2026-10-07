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
            reset: vi.fn(),
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
        vi.unstubAllGlobals();
        vi.clearAllTimers();
        vi.useRealTimers();
    });

    it.each(['€', 'é', '😀'])('preserves %s split across binary output frames', (text) => {
        const service = createService();
        const tab = createTab();
        service.connect(tab);
        const socket = FakeWebSocket.instances[0]!;
        socket.open();
        const bytes = new TextEncoder().encode(text);
        for (const byte of bytes) {
            const chunk = new window.ArrayBuffer(1);
            new window.Uint8Array(chunk)[0] = byte;
            socket.onmessage?.({ data: chunk } as MessageEvent<ArrayBuffer>);
        }

        expect(vi.mocked(tab.term.write).mock.calls.map(([data]) => data).join('')).toBe(text);
        service.disconnect(tab);
    });

    it('keeps UTF-8 decoding independent between tabs', () => {
        const service = createService();
        const firstTab = createTab('first');
        const secondTab = { ...createTab('second'), id: 2 };
        service.connect(firstTab);
        service.connect(secondTab);
        const first = FakeWebSocket.instances[0]!;
        const second = FakeWebSocket.instances[1]!;
        first.open();
        second.open();
        const bytes = new TextEncoder().encode('€');
        const sendBytes = (socket: FakeWebSocket, data: Uint8Array) => {
            const buffer = new window.ArrayBuffer(data.length);
            new window.Uint8Array(buffer).set(data);
            socket.onmessage?.({ data: buffer } as MessageEvent<ArrayBuffer>);
        };
        sendBytes(first, bytes.slice(0, 1));
        receiveBinary(second, 'other tab');
        sendBytes(first, bytes.slice(1));

        expect(vi.mocked(firstTab.term.write).mock.calls.map(([data]) => data).join('')).toBe('€');
        expect(vi.mocked(secondTab.term.write).mock.calls.map(([data]) => data).join('')).toBe('other tab');
        service.disconnect(firstTab);
        service.disconnect(secondTab);
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

    it('reconnects with a fresh terminal and buffer replay enabled', () => {
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
        expect(FakeWebSocket.instances[1]!.url).not.toContain('skip_buffer=1');
        expect(tab.term.reset).toHaveBeenCalledTimes(2);
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

    it('preserves buffered output received before terminal layout completes', () => {
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
        expect(write).toHaveBeenCalledWith(firstChunk + secondChunk, expect.any(Function));
        service.disconnect(tab);
    });

    it('confirms pause once and replays instead of acknowledging stalled rendering', () => {
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
        const close = vi.spyOn(socket, 'close');
        expect(socket.sent.filter((item) => item === pause)).toHaveLength(1);

        socket.message({ type: 'pause_ack' });
        vi.advanceTimersByTime(500);
        expect(socket.sent.filter((item) => item === pause)).toHaveLength(1);

        vi.advanceTimersByTime(4_500);
        expect(socket.sent).not.toContain(ack);
        expect(close).toHaveBeenCalledWith(4008, expect.stringContaining('replay'));
        vi.advanceTimersByTime(10);
        expect(FakeWebSocket.instances[1]!.url).not.toContain('skip_buffer=1');
        service.disconnect(tab);
    });

    it('pauses and bounds background output even when animation frames never run', () => {
        vi.useFakeTimers();
        const service = createService();
        const tab = createTab();
        service.connect(tab);
        const socket = FakeWebSocket.instances[0]!;
        socket.open();
        vi.advanceTimersByTime(64);
        const frames: FrameRequestCallback[] = [];
        vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
            frames.push(callback);
            return frames.length;
        });
        const close = vi.spyOn(socket, 'close');
        for (let i = 0; i < 80; i++) receiveBinary(socket, 'x'.repeat(65_536));

        expect(socket.sent).toContain(JSON.stringify({ type: 'pause' }));
        expect(close).toHaveBeenCalledOnce();
        expect(close).toHaveBeenCalledWith(4008, expect.stringContaining('replay'));
        expect(tab.term.write).not.toHaveBeenCalled();
        frames.forEach((callback) => callback(0));
        expect(tab.term.write).not.toHaveBeenCalled();

        vi.unstubAllGlobals();
        vi.advanceTimersByTime(10);
        const reconnected = FakeWebSocket.instances[1]!;
        expect(reconnected.url).not.toContain('skip_buffer=1');
        reconnected.open();
        vi.advanceTimersByTime(64);
        receiveBinary(reconnected, 'replayed output');
        vi.advanceTimersToNextFrame();
        expect(tab.term.write).toHaveBeenCalledExactlyOnceWith('replayed output', expect.any(Function));
        service.disconnect(tab);
    });

    it('bounds output while the initial terminal layout is suspended', () => {
        vi.useFakeTimers();
        const service = createService();
        const tab = createTab();
        service.connect(tab);
        const socket = FakeWebSocket.instances[0]!;
        socket.open();
        const close = vi.spyOn(socket, 'close');
        receiveBinary(socket, 'x'.repeat(2_000_001));

        expect(close).toHaveBeenCalledWith(4008, expect.stringContaining('replay'));
        expect(tab.term.write).not.toHaveBeenCalled();
        service.disconnect(tab);
    });

    it.each([false, true])('replays pending output and ignores stale frames (skip requested: %s)', (skip) => {
        const service = createService();
        const tab = createTab();
        service.connect(tab);
        const first = FakeWebSocket.instances[0]!;
        first.open();
        const frames: FrameRequestCallback[] = [];
        vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
            frames.push(callback);
            return frames.length;
        });
        const flushFrame = () => frames.splice(0).forEach((callback) => callback(0));
        receiveBinary(first, 'old output');
        const staleFrame = frames.shift()!;
        service.connect(tab, skip);
        const second = FakeWebSocket.instances[1]!;
        expect(second.url).not.toContain('skip_buffer=1');
        expect(tab.term.reset).toHaveBeenCalledTimes(2);
        second.open();
        receiveBinary(second, 'new output');
        staleFrame(0);
        expect(tab.term.write).not.toHaveBeenCalled();
        flushFrame();
        flushFrame();
        flushFrame();
        expect(tab.term.write).toHaveBeenCalledExactlyOnceWith('new output', expect.any(Function));
        service.disconnect(tab);
    });

    it('requests replay when returning to a disconnected tab', () => {
        const service = createService();
        const tab = createTab();
        service.connect(tab);
        FakeWebSocket.instances[0]!.open();
        FakeWebSocket.instances[0]!.closeFromServer(1006, 'background disconnect');
        service.connect(tab, true);
        expect(FakeWebSocket.instances[1]!.url).not.toContain('skip_buffer=1');
        expect(tab.term.reset).toHaveBeenCalledTimes(2);
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
