/**
 * Storage utilities for authentication
 */

import { appBaseUrl } from '@/config/paths';

const STORAGE_PREFIX = 'ptn_auth_';
const CURRENT_AUTH_KEY = `${STORAGE_PREFIX}current_v2`;

interface StoredCredential {
    version: 2;
    baseUrl: string;
    password: string;
}

/** Remove Porterminal password entries from this browser origin. */
function removeAuthKeys(keepKey?: string): void {
    try {
        const keysToRemove: string[] = [];
        for (let index = 0; index < localStorage.length; index++) {
            const key = localStorage.key(index);
            if (key?.startsWith(STORAGE_PREFIX) && key !== keepKey) {
                keysToRemove.push(key);
            }
        }

        for (const key of keysToRemove) {
            try {
                localStorage.removeItem(key);
            } catch {
                // Keep trying the remaining Porterminal auth keys.
            }
        }
    } catch {
        // localStorage may be unavailable in some contexts.
    }
}

export function getSavedPassword(): string | null {
    try {
        const value = localStorage.getItem(CURRENT_AUTH_KEY);
        if (value === null) return null;

        const credential: unknown = JSON.parse(value);
        if (
            typeof credential !== 'object'
            || credential === null
            || !('version' in credential)
            || credential.version !== 2
            || !('baseUrl' in credential)
            || credential.baseUrl !== appBaseUrl()
            || !('password' in credential)
            || typeof credential.password !== 'string'
        ) return null;

        return credential.password;
    } catch {
        return null;
    }
}

export function savePassword(password: string): void {
    try {
        const credential: StoredCredential = {
            version: 2,
            baseUrl: appBaseUrl(),
            password,
        };
        localStorage.setItem(CURRENT_AUTH_KEY, JSON.stringify(credential));
    } catch {
        // localStorage may be unavailable in some contexts
        return;
    }

    // A successfully saved launch supersedes older credentials on this origin.
    removeAuthKeys(CURRENT_AUTH_KEY);
}

export function clearPassword(): void {
    removeAuthKeys();
}

// ========== Compose Mode Storage ==========

const COMPOSE_MODE_KEY = 'ptn_compose_mode';

/**
 * Check if user has explicitly set a compose mode preference.
 * Returns true if user has toggled compose mode at least once.
 */
export function hasComposeModePreference(): boolean {
    try {
        return localStorage.getItem(COMPOSE_MODE_KEY) !== null;
    } catch {
        return false;
    }
}

/**
 * Get compose mode from localStorage.
 * Returns null if no preference has been set (use server default).
 */
export function getComposeMode(): boolean | null {
    try {
        const value = localStorage.getItem(COMPOSE_MODE_KEY);
        if (value === null) return null;
        return value === 'true';
    } catch {
        return null;
    }
}

export function setComposeMode(enabled: boolean): void {
    try {
        // Always store the explicit value so user preference takes precedence
        localStorage.setItem(COMPOSE_MODE_KEY, enabled ? 'true' : 'false');
    } catch {
        // Ignore errors
    }
}

// ========== Disabled Buttons Storage ==========

const DISABLED_BUTTONS_KEY = 'ptn_disabled_buttons';

/**
 * Get list of disabled button labels from localStorage.
 * These buttons will be hidden in the toolbar.
 */
export function getDisabledButtons(): string[] {
    try {
        const value = localStorage.getItem(DISABLED_BUTTONS_KEY);
        if (!value) return [];
        const parsed = JSON.parse(value);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

/**
 * Set the list of disabled button labels.
 */
export function setDisabledButtons(labels: string[]): void {
    try {
        localStorage.setItem(DISABLED_BUTTONS_KEY, JSON.stringify(labels));
    } catch {
        // Ignore errors
    }
}
