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
