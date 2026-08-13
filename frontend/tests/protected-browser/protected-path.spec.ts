import { expect, test } from '@playwright/test';

import {
    ACCESS_CODE,
    ORIGIN,
    PREFIX,
    PROTECTED_BASE_URL,
} from './environment';


test('the packaged server rejects requests outside the credential path', async ({ request }) => {
    const rejected = await Promise.all([
        request.get(`${ORIGIN}/`),
        request.get(`${ORIGIN}/health`),
        request.get(`${ORIGIN}/api/config`),
        request.get(`${ORIGIN}/WrongBrowserCode_123456/health`),
    ]);

    expect(rejected.map(response => response.status())).toEqual([404, 404, 404, 404]);
    for (const response of rejected) {
        expect(response.headers()['cache-control']).toBe('no-store');
        expect(response.headers()['referrer-policy']).toBe('no-referrer');
    }

    const redirect = await request.get(`${ORIGIN}/${ACCESS_CODE}`, { maxRedirects: 0 });
    expect(redirect.status()).toBe(307);
    expect(redirect.headers().location).toBe(`${PREFIX}/`);
});


test('the built browser client keeps HTTP, WebSocket, and share URLs protected', async ({ page }) => {
    const requestUrls: string[] = [];
    const websocketUrls: string[] = [];
    page.on('request', request => {
        if (request.url().startsWith(ORIGIN)) requestUrls.push(request.url());
    });
    page.on('websocket', websocket => websocketUrls.push(websocket.url()));

    const response = await page.goto(`${PROTECTED_BASE_URL}/`);
    expect(response?.status()).toBe(200);
    expect(response?.headers()['referrer-policy']).toBe('no-referrer');
    expect(response?.headers()['x-content-type-options']).toBe('nosniff');
    await expect(page).toHaveTitle('Porterminal Remote Computer');
    const basePathMeta = page.locator('meta[name="porterminal-base-path"]');
    await expect(basePathMeta).toHaveCount(1);
    await expect(basePathMeta).toHaveAttribute('content', PREFIX);
    await expect(page.locator('.tab-btn:not(.tab-add)')).toHaveCount(1, { timeout: 15_000 });

    await expect.poll(() => requestUrls.map(url => new URL(url).pathname)).toContain(
        `${PREFIX}/api/config`,
    );
    expect(requestUrls.map(url => new URL(url).pathname)).toEqual(
        expect.arrayContaining([
            `${PREFIX}/`,
            `${PREFIX}/api/config`,
        ]),
    );
    expect(
        requestUrls.some(url => new URL(url).pathname.startsWith(`${PREFIX}/static/`)),
    ).toBe(true);
    expect(
        requestUrls
            .map(url => new URL(url).pathname)
            .every(path => path === PREFIX || path.startsWith(`${PREFIX}/`)),
    ).toBe(true);

    await expect.poll(() => websocketUrls.map(url => new URL(url).pathname)).toContain(
        `${PREFIX}/ws/management`,
    );
    await expect.poll(() => websocketUrls.map(url => new URL(url).pathname)).toContain(
        `${PREFIX}/ws`,
    );
    expect(
        websocketUrls.every(url => new URL(url).pathname.startsWith(`${PREFIX}/ws`)),
    ).toBe(true);

    await page.getByRole('button', { name: 'Copy agent share link' }).click();
    await expect.poll(
        () => page.evaluate(() => navigator.clipboard.readText()),
    ).toContain(PROTECTED_BASE_URL);

    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toContain(`${PROTECTED_BASE_URL}/mcp`);
    expect(clipboardText).toContain(`${PROTECTED_BASE_URL}/api/agent/run`);
    expect(clipboardText).toContain(`${PROTECTED_BASE_URL}/llms.txt`);
});
