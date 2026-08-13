/** Runtime URL helpers for an app mounted below a per-launch access path. */

const BASE_PATH_META = 'meta[name="porterminal-base-path"]';

function normalizeBasePath(value: string | null): string {
    if (!value || value === '/') return '';
    if (
        !value.startsWith('/')
        || value.startsWith('//')
        || value.includes('\\')
        || value.includes('?')
        || value.includes('#')
        || value.split('/').some((segment) => segment === '.' || segment === '..')
    ) return '';
    return value.replace(/\/+$/, '');
}

export function appBasePath(): string {
    const configured = document.querySelector<HTMLMetaElement>(BASE_PATH_META)?.content ?? null;
    if (configured !== null) return normalizeBasePath(configured);

    // Vite serves the development app at `/`; packaged pages inject the meta tag.
    return window.location.pathname === '/' ? '' : normalizeBasePath(window.location.pathname);
}

export function appPath(path: string): string {
    return `${appBasePath()}/${path.replace(/^\/+/, '')}`;
}

export function appWebSocketUrl(path: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}${appPath(path)}`;
}

export function appBaseUrl(): string {
    return `${window.location.origin}${appBasePath()}`;
}
