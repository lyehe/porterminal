// @vitest-environment-options {"url":"http://127.0.0.1:8080/"}

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
    clearPassword,
    getSavedPassword,
    savePassword,
} from '@/utils/storage';


const BASE_PATH_META = 'meta[name="porterminal-base-path"]';
const FIRST_PATH = '/FirstAccessCode_1234567890';
const SECOND_PATH = '/SecondAccessCode_123456789';
const COLLIDING_PATH_ONE = '/24JVXSHqC7R3OStoExPipJ';
const COLLIDING_PATH_TWO = '/zh49cwWdAhYEUKeimFw4pM';

function setBasePath(path: string): void {
    let meta = document.querySelector<HTMLMetaElement>(BASE_PATH_META);
    if (!meta) {
        meta = document.createElement('meta');
        meta.name = 'porterminal-base-path';
        document.head.appendChild(meta);
    }
    meta.content = path;
}

function authKeys(): string[] {
    return Object.keys(localStorage).filter((key) => key.startsWith('ptn_auth_'));
}

function legacyAuthKey(baseUrl: string): string {
    let hash = 0;
    for (let index = 0; index < baseUrl.length; index++) {
        hash = ((hash << 5) - hash) + baseUrl.charCodeAt(index);
        hash &= hash;
    }
    return `ptn_auth_${Math.abs(hash).toString(36)}`;
}

describe('password storage', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    afterEach(() => {
        localStorage.clear();
        vi.restoreAllMocks();
    });

    it('isolates a saved password by protected base URL', () => {
        setBasePath(FIRST_PATH);
        savePassword('first password');

        setBasePath(SECOND_PATH);
        expect(getSavedPassword()).toBeNull();

        setBasePath(FIRST_PATH);
        expect(getSavedPassword()).toBe('first password');
    });

    it('isolates the concrete base URLs that collided under legacy hashing', () => {
        const firstUrl = `${window.location.origin}${COLLIDING_PATH_ONE}`;
        const secondUrl = `${window.location.origin}${COLLIDING_PATH_TWO}`;
        expect(legacyAuthKey(firstUrl)).toBe('ptn_auth_rmgzy4');
        expect(legacyAuthKey(secondUrl)).toBe('ptn_auth_rmgzy4');

        localStorage.setItem('ptn_auth_rmgzy4', 'unsafe legacy password');
        setBasePath(COLLIDING_PATH_ONE);
        expect(getSavedPassword()).toBeNull();

        savePassword('first password');
        expect(authKeys()).toHaveLength(1);

        setBasePath(COLLIDING_PATH_TWO);
        expect(getSavedPassword()).toBeNull();

        setBasePath(COLLIDING_PATH_ONE);
        expect(getSavedPassword()).toBe('first password');
    });

    it('retires stale path credentials after saving the current password', () => {
        setBasePath(FIRST_PATH);
        savePassword('first password');
        localStorage.setItem('unrelated', 'keep me');

        setBasePath(SECOND_PATH);
        savePassword('second password');

        expect(authKeys()).toHaveLength(1);
        expect(getSavedPassword()).toBe('second password');
        expect(localStorage.getItem('unrelated')).toBe('keep me');

        setBasePath(FIRST_PATH);
        expect(getSavedPassword()).toBeNull();
    });

    it('keeps the previous path credential when saving the current path fails', () => {
        setBasePath(FIRST_PATH);
        savePassword('first password');
        localStorage.setItem('unrelated', 'keep me');

        setBasePath(SECOND_PATH);
        const setItem = vi.spyOn(Storage.prototype, 'setItem')
            .mockImplementation(() => { throw new Error('blocked'); });
        expect(() => savePassword('second password')).not.toThrow();
        setItem.mockRestore();

        expect(authKeys()).toHaveLength(1);
        expect(getSavedPassword()).toBeNull();
        expect(localStorage.getItem('unrelated')).toBe('keep me');

        setBasePath(FIRST_PATH);
        expect(getSavedPassword()).toBe('first password');
    });

    it('explicit clear removes every Porterminal auth key and nothing else', () => {
        setBasePath(FIRST_PATH);
        savePassword('current password');
        localStorage.setItem('ptn_auth_stale-one', 'old password');
        localStorage.setItem('ptn_auth_stale-two', 'older password');
        localStorage.setItem('ptn_compose_mode', 'true');
        localStorage.setItem('site_preference', 'preserve');

        setBasePath(SECOND_PATH);
        clearPassword();

        expect(authKeys()).toEqual([]);
        expect(localStorage.getItem('ptn_compose_mode')).toBe('true');
        expect(localStorage.getItem('site_preference')).toBe('preserve');
    });

    it('does not surface localStorage access failures', () => {
        const getItem = vi.spyOn(Storage.prototype, 'getItem')
            .mockImplementation(() => { throw new Error('blocked'); });
        expect(getSavedPassword()).toBeNull();
        getItem.mockRestore();

        localStorage.setItem('ptn_auth_stale', 'old password');
        const removeItem = vi.spyOn(Storage.prototype, 'removeItem')
            .mockImplementation(() => { throw new Error('blocked'); });
        expect(() => clearPassword()).not.toThrow();
        expect(localStorage.getItem('ptn_auth_stale')).toBe('old password');
        removeItem.mockRestore();
    });
});
