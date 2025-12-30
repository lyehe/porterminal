/**
 * Config Service - Loads configuration from server
 * Single Responsibility: Only handles server config loading
 */

import type { AppConfig, ShellConfig } from '@/types';

export interface ConfigService {
    /** Load configuration from server */
    load(): Promise<AppConfig>;

    /** Get available shells (after load) */
    getShells(): ShellConfig[];

    /** Get default shell ID (after load) */
    getDefaultShell(): string;

    /** Check if config has been loaded */
    isLoaded(): boolean;
}

/**
 * Create a config service instance
 */
export function createConfigService(): ConfigService {
    let config: AppConfig | null = null;

    return {
        async load(): Promise<AppConfig> {
            try {
                const response = await fetch('/api/config');
                if (!response.ok) {
                    throw new Error(`Config fetch failed: ${response.status}`);
                }
                config = await response.json() as AppConfig;
                return config;
            } catch (e) {
                console.error('Failed to load config:', e);
                // Return sensible defaults
                config = {
                    shells: [{ id: 'default', name: 'Shell' }],
                    default_shell: 'default',
                };
                return config;
            }
        },

        getShells(): ShellConfig[] {
            return config?.shells ?? [];
        },

        getDefaultShell(): string {
            return config?.default_shell ?? 'default';
        },

        isLoaded(): boolean {
            return config !== null;
        },
    };
}
