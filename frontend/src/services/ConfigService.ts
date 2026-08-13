/**
 * Config Service - Loads configuration from server
 * Single Responsibility: Only handles server config loading and updates
 */

import type { AppConfig, ButtonConfig } from '@/types';
import { appPath } from '@/config/paths';

export interface SettingsUpdate {
    compose_mode?: boolean;
    notify_on_startup?: boolean;
}

interface PersistedSettings {
    compose_mode: boolean;
    notify_on_startup: boolean;
    password_protected: boolean;
}

export interface SettingsUpdateResult {
    success: boolean;
    requires_restart: boolean;
    settings?: PersistedSettings;
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
    settings?: PersistedSettings;
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

interface ApiErrorPayload {
    error?: unknown;
    detail?: unknown;
}

interface PasswordResponse extends ApiErrorPayload {
    requires_restart: boolean;
    settings?: PersistedSettings;
    message?: string;
}

function apiError(payload: ApiErrorPayload, status: number): string {
    if (typeof payload.error === 'string' && payload.error) {
        return payload.error;
    }
    if (typeof payload.detail === 'string' && payload.detail) {
        return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
        const messages = payload.detail.flatMap((item: unknown) => {
            if (!item || typeof item !== 'object') return [];
            const detail = item as { loc?: unknown; msg?: unknown };
            if (typeof detail.msg !== 'string') return [];
            const location = Array.isArray(detail.loc)
                ? detail.loc.filter((part) => part !== 'body').join('.')
                : '';
            return [location ? `${location}: ${detail.msg}` : detail.msg];
        });
        if (messages.length > 0) return messages.join('; ');
    }
    return `Request failed (${status})`;
}

/** Helper for button API requests */
async function buttonRequest(url: string, options: RequestInit): Promise<ButtonResult> {
    try {
        const response = await fetch(url, options);
        const data = await response.json();
        if (!response.ok) {
            return { success: false, error: apiError(data as ApiErrorPayload, response.status) };
        }
        return { success: true, buttons: data.buttons };
    } catch (e) {
        return { success: false, error: e instanceof Error ? e.message : 'Unknown error' };
    }
}

async function passwordRequest(url: string, options: RequestInit): Promise<PasswordResult> {
    try {
        const response = await fetch(url, options);
        const data = await response.json() as PasswordResponse;
        if (!response.ok) {
            return {
                success: false,
                requires_restart: false,
                error: apiError(data, response.status),
            };
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
}

/**
 * Create a config service instance
 */
export function createConfigService(): ConfigService {
    return {
        async load(): Promise<AppConfig> {
            try {
                const response = await fetch(appPath('/api/config'));
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
                const response = await fetch(appPath('/api/settings'), {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(settings),
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({})) as ApiErrorPayload;
                    return {
                        success: false,
                        requires_restart: false,
                        error: apiError(errorData, response.status),
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
            return buttonRequest(appPath('/api/buttons'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, send, row: row ?? 1 }),
            });
        },

        async removeButton(label: string): Promise<ButtonResult> {
            return buttonRequest(appPath(`/api/buttons/${encodeURIComponent(label)}`), {
                method: 'DELETE',
            });
        },

        async getPasswordStatus(): Promise<PasswordStatus> {
            try {
                const response = await fetch(appPath('/api/password'));
                if (!response.ok) {
                    return { password_saved: false, require_password: false, currently_protected: false };
                }
                return await response.json();
            } catch {
                return { password_saved: false, require_password: false, currently_protected: false };
            }
        },

        async setPassword(password: string): Promise<PasswordResult> {
            return passwordRequest(appPath('/api/password'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password }),
            });
        },

        async clearPassword(): Promise<PasswordResult> {
            return passwordRequest(appPath('/api/password'), { method: 'DELETE' });
        },

        async setRequirePassword(require: boolean): Promise<PasswordResult> {
            return passwordRequest(appPath('/api/password/require'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ require }),
            });
        },
    };
}
