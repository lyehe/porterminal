/**
 * Storage utilities for authentication
 */

const STORAGE_PREFIX = 'ptn_auth_';

function getStorageKey(): string {
    // Simple hash of origin for uniqueness across different tunnel URLs
    const origin = window.location.origin;
    let hash = 0;
    for (let i = 0; i < origin.length; i++) {
        const char = origin.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32-bit integer
    }
    return `${STORAGE_PREFIX}${Math.abs(hash).toString(36)}`;
}

export function getSavedPassword(): string | null {
    try {
        return localStorage.getItem(getStorageKey());
    } catch {
        return null;
    }
}

export function savePassword(password: string): void {
    try {
        localStorage.setItem(getStorageKey(), password);
    } catch {
        // localStorage may be unavailable in some contexts
    }
}

export function clearPassword(): void {
    try {
        localStorage.removeItem(getStorageKey());
    } catch {
        // Ignore errors
    }
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
