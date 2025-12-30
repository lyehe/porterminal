/**
 * Event bus for decoupled communication between modules
 * Follows the Dependency Inversion principle - modules depend on events, not each other
 */

import type { Tab, SwipeDirection, ModifierMode } from '@/types';

/** Event payload types */
export interface EventMap {
    // Tab events
    'tab:created': { tab: Tab };
    'tab:switched': { tabId: number; tab: Tab };
    'tab:closed': { tabId: number };

    // Connection events
    'connection:open': { tabId: number };
    'connection:close': { tabId: number; code: number };
    'connection:message': { tabId: number; data: unknown };
    'connection:error': { tabId: number; error: string };

    // Input events
    'input:send': { data: string };
    'input:key': { key: string };

    // Modifier events
    'modifier:changed': { modifier: 'ctrl' | 'alt' | 'shift'; state: ModifierMode };

    // Selection events
    'selection:changed': { text: string };
    'selection:cleared': Record<string, never>;

    // Gesture events
    'gesture:swipe': { direction: SwipeDirection };
    'gesture:pinch': { scale: number };

    // UI events
    'ui:disconnect': Record<string, never>;
    'ui:reconnect': Record<string, never>;
}

type EventHandler<T> = (payload: T) => void;

/** Event bus interface */
export interface EventBus {
    /** Emit an event */
    emit<K extends keyof EventMap>(event: K, payload: EventMap[K]): void;

    /** Subscribe to an event, returns unsubscribe function */
    on<K extends keyof EventMap>(event: K, handler: EventHandler<EventMap[K]>): () => void;

    /** Unsubscribe from an event */
    off<K extends keyof EventMap>(event: K, handler: EventHandler<EventMap[K]>): void;

    /** Subscribe to an event once */
    once<K extends keyof EventMap>(event: K, handler: EventHandler<EventMap[K]>): () => void;
}

/**
 * Create a new event bus instance
 */
export function createEventBus(): EventBus {
    const handlers = new Map<keyof EventMap, Set<EventHandler<unknown>>>();

    return {
        emit<K extends keyof EventMap>(event: K, payload: EventMap[K]): void {
            const eventHandlers = handlers.get(event);
            if (eventHandlers) {
                for (const handler of eventHandlers) {
                    try {
                        handler(payload);
                    } catch (error) {
                        console.error(`Error in event handler for "${event}":`, error);
                    }
                }
            }
        },

        on<K extends keyof EventMap>(event: K, handler: EventHandler<EventMap[K]>): () => void {
            let eventHandlers = handlers.get(event);
            if (!eventHandlers) {
                eventHandlers = new Set();
                handlers.set(event, eventHandlers);
            }
            eventHandlers.add(handler as EventHandler<unknown>);

            // Return unsubscribe function
            return () => this.off(event, handler);
        },

        off<K extends keyof EventMap>(event: K, handler: EventHandler<EventMap[K]>): void {
            const eventHandlers = handlers.get(event);
            if (eventHandlers) {
                eventHandlers.delete(handler as EventHandler<unknown>);
            }
        },

        once<K extends keyof EventMap>(event: K, handler: EventHandler<EventMap[K]>): () => void {
            const wrapper = (payload: EventMap[K]) => {
                this.off(event, wrapper);
                handler(payload);
            };
            return this.on(event, wrapper);
        },
    };
}
