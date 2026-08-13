import { afterEach, describe, expect, it } from 'vitest';

import {
    appBasePath,
    appBaseUrl,
    appPath,
    appWebSocketUrl,
} from '@/config/paths';


const ACCESS_PATH = '/AccessCode_1234567890';

function setBasePath(content: string): void {
    const meta = document.createElement('meta');
    meta.name = 'porterminal-base-path';
    meta.content = content;
    document.head.appendChild(meta);
}

describe('runtime paths', () => {
    afterEach(() => {
        document.querySelector('meta[name="porterminal-base-path"]')?.remove();
        window.history.replaceState(null, '', '/');
    });

    it('keeps development URLs rooted at the host', () => {
        expect(appBasePath()).toBe('');
        expect(appPath('/api/config')).toBe('/api/config');
        expect(appBaseUrl()).toBe(window.location.origin);
    });

    it('prefixes HTTP, WebSocket, and share URLs with the advertised path', () => {
        setBasePath(`${ACCESS_PATH}/`);

        expect(appBasePath()).toBe(ACCESS_PATH);
        expect(appPath('/api/config')).toBe(`${ACCESS_PATH}/api/config`);
        expect(appWebSocketUrl('/ws?tab_id=one')).toBe(
            `ws://${window.location.host}${ACCESS_PATH}/ws?tab_id=one`,
        );
        expect(appBaseUrl()).toBe(`${window.location.origin}${ACCESS_PATH}`);
    });

    it('ignores malformed injected base paths', () => {
        setBasePath('//attacker.example/path');

        expect(appBasePath()).toBe('');
        expect(appPath('/health')).toBe('/health');
    });
});
