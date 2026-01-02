/**
 * Config Service - Loads configuration from server
 * Single Responsibility: Only handles server config loading
 */

import type { AppConfig } from '@/types';

export interface ConfigService {
    /** Load configuration from server */
    load(): Promise<AppConfig>;
}

/**
 * Create a config service instance
 */
export function createConfigService(): ConfigService {
    return {
        async load(): Promise<AppConfig> {
            try {
                const response = await fetch('/api/config');
                if (!response.ok) {
                    throw new Error(`Config fetch failed: ${response.status}`);
                }
                return await response.json() as AppConfig;
            } catch (e) {
                console.error('Failed to load config:', e);
                // Return sensible defaults
                return {
                    shells: [{ id: 'default', name: 'Shell' }],
                    default_shell: 'default',
                };
            }
        },
    };
}
