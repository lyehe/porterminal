/**
 * Dependency Injection Container
 * Centralizes service creation and wiring
 */

import { createEventBus, type EventBus } from './events';

// Service imports (will be added as we create them)
// import { createStorageService, type StorageService } from '@/services/StorageService';
// import { createConfigService, type ConfigService } from '@/services/ConfigService';
// ...

/** Container interface - holds all services */
export interface Container {
    readonly eventBus: EventBus;
    // Services will be added here as we migrate:
    // readonly storageService: StorageService;
    // readonly configService: ConfigService;
    // readonly connectionService: ConnectionService;
    // readonly tabService: TabService;
    // readonly modifierManager: ModifierManager;
    // readonly clipboardManager: ClipboardManager;
    // readonly gestureRecognizer: GestureRecognizer;
}

/** Container configuration options */
export interface ContainerOptions {
    /** Storage key for localStorage */
    storageKey?: string;
    /** Maximum reconnection attempts */
    maxReconnectAttempts?: number;
    /** Reconnection delay in ms */
    reconnectDelayMs?: number;
    /** Heartbeat interval in ms */
    heartbeatMs?: number;
}

const DEFAULT_OPTIONS: Required<ContainerOptions> = {
    storageKey: 'porterminal-tabs',
    maxReconnectAttempts: 5,
    reconnectDelayMs: 1000,
    heartbeatMs: 25000,
};

/**
 * Create the dependency injection container
 * This is the composition root - all services are wired here
 */
export function createContainer(options: ContainerOptions = {}): Container {
    // Config will be used as we add services
    const _config = { ...DEFAULT_OPTIONS, ...options };
    void _config; // Suppress unused warning during migration

    // Create core infrastructure
    const eventBus = createEventBus();

    // TODO: Create services as we migrate them
    // const storageService = createStorageService(config.storageKey);
    // const configService = createConfigService();
    // const connectionService = createConnectionService(eventBus, {
    //     maxReconnectAttempts: config.maxReconnectAttempts,
    //     reconnectDelayMs: config.reconnectDelayMs,
    //     heartbeatMs: config.heartbeatMs,
    // });
    // ...

    return {
        eventBus,
        // Services will be added here
    };
}

// Singleton container instance (will be initialized in main.ts)
let containerInstance: Container | null = null;

/** Get or create the container singleton */
export function getContainer(): Container {
    if (!containerInstance) {
        containerInstance = createContainer();
    }
    return containerInstance;
}

/** Initialize the container with options (call once at app startup) */
export function initContainer(options: ContainerOptions = {}): Container {
    containerInstance = createContainer(options);
    return containerInstance;
}
