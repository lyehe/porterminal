export class FakeWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    static instances: FakeWebSocket[] = [];

    readonly url: string;
    readyState = FakeWebSocket.CONNECTING;
    binaryType: BinaryType = 'blob';
    sent: Array<string | ArrayBufferLike | Blob | ArrayBufferView> = [];
    onopen: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onclose: ((event: CloseEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;

    constructor(url: string | URL) {
        this.url = String(url);
        FakeWebSocket.instances.push(this);
    }

    static reset(): void {
        FakeWebSocket.instances = [];
    }

    open(): void {
        this.readyState = FakeWebSocket.OPEN;
        this.onopen?.(new Event('open'));
    }

    message(data: unknown): void {
        const payload = typeof data === 'string' || data instanceof ArrayBuffer
            ? data
            : JSON.stringify(data);
        this.onmessage?.(new MessageEvent('message', { data: payload }));
    }

    close(code = 1000, reason = ''): void {
        this.closeFromServer(code, reason);
    }

    closeFromServer(code = 1000, reason = ''): void {
        this.readyState = FakeWebSocket.CLOSED;
        this.onclose?.(new CloseEvent('close', { code, reason }));
    }

    fail(): void {
        this.onerror?.(new Event('error'));
    }

    send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
        this.sent.push(data);
    }
}


export function installFakeWebSocket(): void {
    FakeWebSocket.reset();
    Object.defineProperty(globalThis, 'WebSocket', {
        configurable: true,
        value: FakeWebSocket,
    });
}
