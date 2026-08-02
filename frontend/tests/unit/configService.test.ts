import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    createConfigService,
    type ConfigService,
    type PasswordResult,
} from '@/services/ConfigService';


function response(status: number, payload: unknown): Response {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: vi.fn().mockResolvedValue(payload),
    } as unknown as Response;
}

const passwordRequests: Array<{
    name: string;
    invoke: (service: ConfigService) => Promise<PasswordResult>;
    url: string;
    options: RequestInit;
}> = [
    {
        name: 'sets a password',
        invoke: (service) => service.setPassword('secret'),
        url: '/api/password',
        options: {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: 'secret' }),
        },
    },
    {
        name: 'clears a password',
        invoke: (service) => service.clearPassword(),
        url: '/api/password',
        options: { method: 'DELETE' },
    },
    {
        name: 'changes the password requirement',
        invoke: (service) => service.setRequirePassword(false),
        url: '/api/password/require',
        options: {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ require: false }),
        },
    },
];


describe('config service', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('preserves boolean values in settings requests', async () => {
        const fetchMock = vi.fn().mockResolvedValue(response(200, {
            settings: {
                compose_mode: false,
                notify_on_startup: true,
                password_protected: false,
            },
            requires_restart: false,
        }));
        vi.stubGlobal('fetch', fetchMock);

        const result = await createConfigService().updateSettings({ compose_mode: false });

        expect(result.success).toBe(true);
        const options = fetchMock.mock.calls[0]![1] as RequestInit;
        expect(JSON.parse(options.body as string)).toEqual({ compose_mode: false });
    });

    it('turns structured 422 details into a readable field error', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(422, {
            detail: [{
                type: 'bool_type',
                loc: ['body', 'compose_mode'],
                msg: 'Input should be a valid boolean',
            }],
        })));

        const result = await createConfigService().updateSettings({ compose_mode: false });

        expect(result).toEqual({
            success: false,
            requires_restart: false,
            error: 'compose_mode: Input should be a valid boolean',
        });
    });

    it('uses the same structured validation errors for button requests', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(422, {
            detail: [{ loc: ['body', 'row'], msg: 'Input should be less than or equal to 10' }],
        })));

        const result = await createConfigService().addButton('Run', 'echo ok', 11);

        expect(result).toEqual({
            success: false,
            error: 'row: Input should be less than or equal to 10',
        });
    });

    it.each(passwordRequests)(
        '$name through the shared response contract',
        async ({ invoke, url, options }) => {
            const payload = {
                settings: {
                    compose_mode: false,
                    notify_on_startup: true,
                    password_protected: true,
                },
                requires_restart: true,
                message: 'Restart required',
            };
            const fetchMock = vi.fn().mockResolvedValue(response(200, payload));
            vi.stubGlobal('fetch', fetchMock);

            const result = await invoke(createConfigService());

            expect(fetchMock).toHaveBeenCalledWith(url, options);
            expect(result).toEqual({ success: true, ...payload });
        },
    );

    it('uses structured validation errors for password requests', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(422, {
            detail: [{ loc: ['body', 'password'], msg: 'String should have at least 1 character' }],
        })));

        const result = await createConfigService().setPassword('secret');

        expect(result).toEqual({
            success: false,
            requires_restart: false,
            error: 'password: String should have at least 1 character',
        });
    });
});
