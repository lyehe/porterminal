import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createEventBus } from '@/core/events';
import { createModifierManager } from '@/input/ModifierManager';


describe('modifier manager', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(1_000);
    });

    afterEach(() => vi.useRealTimers());

    it('moves through sticky, locked, and off states', () => {
        const bus = createEventBus();
        const changes = vi.fn();
        bus.on('modifier:changed', changes);
        const manager = createModifierManager(bus);

        manager.handleTap('ctrl');
        expect(manager.getState('ctrl')).toBe('sticky');

        vi.setSystemTime(1_100);
        manager.handleTap('ctrl');
        expect(manager.getState('ctrl')).toBe('locked');

        vi.setSystemTime(1_500);
        manager.handleTap('ctrl');
        expect(manager.getState('ctrl')).toBe('off');
        expect(changes).toHaveBeenCalledTimes(3);
    });

    it('consumes sticky modifiers without clearing locked modifiers', () => {
        const manager = createModifierManager(createEventBus());
        manager.handleTap('ctrl');
        manager.handleTap('alt');
        vi.setSystemTime(1_100);
        manager.handleTap('alt');

        manager.consumeSticky();

        expect(manager.getState('ctrl')).toBe('off');
        expect(manager.getState('alt')).toBe('locked');
    });
});
