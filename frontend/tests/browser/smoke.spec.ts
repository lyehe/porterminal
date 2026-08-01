import { expect, test } from '@playwright/test';


test.beforeEach(async ({ page }) => {
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/config') {
            await route.fulfill({
                json: {
                    shells: [{ id: 'test-shell', name: 'Test Shell' }],
                    default_shell: 'test-shell',
                    buttons: [{ label: 'status', send: 'status\r', row: 1 }],
                    compose_mode: false,
                    version: 'browser-test',
                    update_available: false,
                    latest_version: null,
                    upgrade_command: null,
                    password_protected: false,
                    notify_on_startup: false,
                },
            });
            return;
        }
        if (url.pathname === '/api/settings') {
            await route.fulfill({
                json: {
                    compose_mode: false,
                    notify_on_startup: false,
                    password_protected: false,
                },
            });
            return;
        }
        if (url.pathname === '/api/password') {
            await route.fulfill({
                json: {
                    password_saved: false,
                    require_password: false,
                    currently_protected: false,
                },
            });
            return;
        }
        await route.fulfill({ json: {} });
    });

    await page.addInitScript(() => {
        class BrowserTestWebSocket {
            static readonly CONNECTING = 0;
            static readonly OPEN = 1;
            static readonly CLOSING = 2;
            static readonly CLOSED = 3;

            readonly url: string;
            readyState = BrowserTestWebSocket.CONNECTING;
            binaryType: BinaryType = 'blob';
            onopen: ((event: Event) => void) | null = null;
            onmessage: ((event: MessageEvent) => void) | null = null;
            onclose: ((event: CloseEvent) => void) | null = null;
            onerror: ((event: Event) => void) | null = null;

            constructor(url: string | URL) {
                this.url = String(url);
                window.setTimeout(() => {
                    this.readyState = BrowserTestWebSocket.OPEN;
                    this.onopen?.(new Event('open'));
                    if (this.url.includes('/ws/management')) {
                        this.deliver({ type: 'tab_state_sync', tabs: [] });
                    } else {
                        this.deliver({
                            type: 'session_info',
                            session_id: 'session-browser-test',
                            tab_id: 'tab-browser-test',
                            cols: 80,
                            rows: 24,
                        });
                    }
                });
            }

            send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
                if (typeof data !== 'string') return;
                const message = JSON.parse(data) as { type?: string; request_id?: string };
                if (message.type === 'create_tab') {
                    window.setTimeout(() => this.deliver({
                        type: 'create_tab_response',
                        request_id: message.request_id,
                        success: true,
                        tab: {
                            id: 'tab-browser-test',
                            session_id: 'session-browser-test',
                            shell_id: 'test-shell',
                            name: 'Test Shell',
                            created_at: new Date().toISOString(),
                            last_accessed: new Date().toISOString(),
                            origin: 'human',
                        },
                    }));
                } else if (message.type === 'ping') {
                    window.setTimeout(() => this.deliver({ type: 'pong' }));
                }
            }

            close(code = 1000, reason = ''): void {
                this.readyState = BrowserTestWebSocket.CLOSED;
                this.onclose?.(new CloseEvent('close', { code, reason }));
            }

            private deliver(message: object): void {
                this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(message) }));
            }
        }

        Object.defineProperty(window, 'WebSocket', {
            configurable: true,
            value: BrowserTestWebSocket,
        });
    });
});


test('boots the terminal UI and exposes essential controls', async ({ page }) => {
    await page.goto('/');

    await expect(page).toHaveTitle('Porterminal Remote Computer');
    await expect(page.getByText('Porterminal remote computer. AI agents')).toBeAttached();
    await expect(page.locator('.tab-btn:not(.tab-add)')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'status' })).toBeVisible();

    await page.getByRole('button', { name: 'Open help' }).click();
    await expect(page.locator('#help-overlay')).not.toHaveClass(/hidden/);
    await page.getByRole('button', { name: 'Close' }).first().click();

    await page.getByRole('button', { name: 'Open settings' }).click();
    await expect(page.locator('#settings-overlay')).not.toHaveClass(/hidden/);
    await expect(page.locator('label[for="settings-compose"]')).toBeVisible();
});
