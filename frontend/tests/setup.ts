import { afterEach } from 'vitest';


Object.defineProperty(globalThis, 'requestAnimationFrame', {
    configurable: true,
    writable: true,
    value: (callback: FrameRequestCallback): number => {
        callback(performance.now());
        return 1;
    },
});
Object.defineProperty(globalThis, 'cancelAnimationFrame', {
    configurable: true,
    writable: true,
    value: (): void => undefined,
});

afterEach(() => {
    document.body.replaceChildren();
});
