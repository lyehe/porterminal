/**
 * Input Handler - Processes button and key input
 * Single Responsibility: Input event handling and dispatch
 */

import type { EventBus } from '@/core/events';
import type { KeyMapper } from './KeyMapper';
import type { ModifierManager } from './ModifierManager';

export interface InputHandler {
    /** Handle a key button press */
    handleKeyButton(key: string): void;

    /** Send raw input data */
    sendInput(data: string): void;
}

/**
 * Create an input handler instance
 */
export function createInputHandler(
    eventBus: EventBus,
    keyMapper: KeyMapper,
    modifierManager: ModifierManager,
    callbacks: {
        sendInput: (data: string) => void;
        focusTerminal: () => void;
    }
): InputHandler {
    return {
        handleKeyButton(key: string): void {
            const sequence = keyMapper.getSequence(key, modifierManager.state);
            if (sequence) {
                callbacks.sendInput(sequence);
                callbacks.focusTerminal();
            }

            // Consume sticky modifiers after key press
            modifierManager.consumeSticky();
        },

        sendInput(data: string): void {
            callbacks.sendInput(data);
            eventBus.emit('input:send', { data });
        },
    };
}
