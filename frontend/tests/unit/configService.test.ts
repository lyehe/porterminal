import { afterEach, describe, expect, it, vi } from 'vitest';

import { createConfigService } from '@/services/ConfigService';


function response(status: number, payload: unknown): Response {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: vi.fn().mockResolvedValue(payload),
    } as unknown as Response;
}


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
});
