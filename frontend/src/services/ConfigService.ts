/**
 * Config Service - Loads configuration from server
 * Single Responsibility: Only handles server config loading and updates
 */

import type { AppConfig, ButtonConfig } from '@/types';

export interface SettingsUpdate {
    compose_mode?: boolean;
    notify_on_startup?: boolean;
}

export interface SettingsUpdateResult {
    success: boolean;
    requires_restart: boolean;
    settings?: {
        compose_mode: boolean;
        notify_on_startup: boolean;
        password_protected: boolean;
    };
    error?: string;
}

export interface ButtonResult {
    success: boolean;
    buttons?: ButtonConfig[];
    error?: string;
}

export interface PasswordStatus {
    password_saved: boolean;
    require_password: boolean;
    currently_protected: boolean;
}

export interface PasswordResult {
    success: boolean;
    requires_restart: boolean;
    settings?: {
        compose_mode: boolean;
        notify_on_startup: boolean;
        password_protected: boolean;
    };
    message?: string;
    error?: string;
}

export interface ConfigService {
    /** Load configuration from server */
    load(): Promise<AppConfig>;
    /** Update settings on server */
    updateSettings(settings: SettingsUpdate): Promise<SettingsUpdateResult>;
    /** Add a new button */
    addButton(label: string, send: string, row?: number): Promise<ButtonResult>;
    /** Remove a button by label */
    removeButton(label: string): Promise<ButtonResult>;
    /** Get password status */
    getPasswordStatus(): Promise<PasswordStatus>;
    /** Set or change password */
    setPassword(password: string): Promise<PasswordResult>;
    /** Clear password and disable requirement */
    clearPassword(): Promise<PasswordResult>;
    /** Set whether password is required at startup */
    setRequirePassword(require: boolean): Promise<PasswordResult>;
}

/** Helper for button API requests */
async function buttonRequest(url: string, options: RequestInit): Promise<ButtonResult> {
    try {
        const response = await fetch(url, options);
        const data = await response.json();
        if (!response.ok) {
            return { success: false, error: data.error };
        }
        return { success: true, buttons: data.buttons };
    } catch (e) {
        return { success: false, error: e instanceof Error ? e.message : 'Unknown error' };
    }
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

        async updateSettings(settings: SettingsUpdate): Promise<SettingsUpdateResult> {
            try {
                const response = await fetch('/api/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(settings),
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    return {
                        success: false,
                        requires_restart: false,
                        error: errorData.error || `Failed: ${response.status}`,
                    };
                }

                const data = await response.json();
                return {
                    success: true,
                    requires_restart: data.requires_restart || false,
                    settings: data.settings,
                };
            } catch (e) {
                console.error('Failed to update settings:', e);
                return {
                    success: false,
                    requires_restart: false,
                    error: e instanceof Error ? e.message : 'Unknown error',
                };
            }
        },

        async addButton(label: string, send: string, row?: number): Promise<ButtonResult> {
            return buttonRequest('/api/buttons', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, send, row: row ?? 1 }),
            });
        },

        async removeButton(label: string): Promise<ButtonResult> {
            return buttonRequest(`/api/buttons/${encodeURIComponent(label)}`, {
                method: 'DELETE',
            });
        },

        async getPasswordStatus(): Promise<PasswordStatus> {
            try {
                const response = await fetch('/api/password');
                if (!response.ok) {
                    return { password_saved: false, require_password: false, currently_protected: false };
                }
                return await response.json();
            } catch {
                return { password_saved: false, require_password: false, currently_protected: false };
            }
        },

        async setPassword(password: string): Promise<PasswordResult> {
            try {
                const response = await fetch('/api/password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password }),
                });
                const data = await response.json();
                if (!response.ok) {
                    return { success: false, requires_restart: false, error: data.error };
                }
                return {
                    success: true,
                    requires_restart: data.requires_restart,
                    settings: data.settings,
                    message: data.message,
                };
            } catch (e) {
                return {
                    success: false,
                    requires_restart: false,
                    error: e instanceof Error ? e.message : 'Unknown error',
                };
            }
        },

        async clearPassword(): Promise<PasswordResult> {
            try {
                const response = await fetch('/api/password', { method: 'DELETE' });
                const data = await response.json();
                if (!response.ok) {
                    return { success: false, requires_restart: false, error: data.error };
                }
                return {
                    success: true,
                    requires_restart: data.requires_restart,
                    settings: data.settings,
                    message: data.message,
                };
            } catch (e) {
                return {
                    success: false,
                    requires_restart: false,
                    error: e instanceof Error ? e.message : 'Unknown error',
                };
            }
        },

        async setRequirePassword(require: boolean): Promise<PasswordResult> {
            try {
                const response = await fetch('/api/password/require', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ require }),
                });
                const data = await response.json();
                if (!response.ok) {
                    return { success: false, requires_restart: false, error: data.error };
                }
                return {
                    success: true,
                    requires_restart: data.requires_restart,
                    settings: data.settings,
                    message: data.message,
                };
            } catch (e) {
                return {
                    success: false,
                    requires_restart: false,
                    error: e instanceof Error ? e.message : 'Unknown error',
                };
            }
        },
    };
}
