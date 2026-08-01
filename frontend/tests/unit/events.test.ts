import { describe, expect, it, vi } from 'vitest';

import { createEventBus } from '@/core/events';


describe('event bus', () => {
    it('subscribes, unsubscribes, and handles one-shot listeners', () => {
        const bus = createEventBus();
        const persistent = vi.fn();
        const once = vi.fn();
        const unsubscribe = bus.on('input:send', persistent);
        bus.once('input:send', once);

        bus.emit('input:send', { data: 'first' });
        bus.emit('input:send', { data: 'second' });
        unsubscribe();
        bus.emit('input:send', { data: 'third' });

        expect(persistent).toHaveBeenCalledTimes(2);
        expect(once).toHaveBeenCalledOnce();
        expect(once).toHaveBeenCalledWith({ data: 'first' });
    });

    it('isolates a failing listener from the rest of the bus', () => {
        const bus = createEventBus();
        const healthy = vi.fn();
        vi.spyOn(console, 'error').mockImplementation(() => undefined);
        bus.on('input:send', () => { throw new Error('listener failed'); });
        bus.on('input:send', healthy);

        bus.emit('input:send', { data: 'still delivered' });

        expect(healthy).toHaveBeenCalledWith({ data: 'still delivered' });
        expect(console.error).toHaveBeenCalledOnce();
    });
});
