import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createManagementService } from '@/services/ManagementService';

import { FakeWebSocket, installFakeWebSocket } from './fakeWebSocket';


describe('management service', () => {
    beforeEach(installFakeWebSocket);

    it('waits for state sync and routes authentication events', async () => {
        const callbacks = {
            onStateSync: vi.fn(),
            onStateUpdate: vi.fn(),
            onDisconnect: vi.fn(),
            onConnect: vi.fn(),
            onAuthRequired: vi.fn(),
            onAuthFailed: vi.fn(),
            onAuthSuccess: vi.fn(),
        };
        const service = createManagementService(callbacks);
        let synchronized = false;
        const connected = service.connect().then(() => { synchronized = true; });
        const socket = FakeWebSocket.instances[0]!;

        socket.open();
        await Promise.resolve();
        expect(synchronized).toBe(false);
        expect(callbacks.onConnect).toHaveBeenCalledOnce();

        socket.message({ type: 'auth_required' });
        service.authenticate('secret');
        socket.message({ type: 'auth_failed', attempts_remaining: 2, error: 'bad password' });
        socket.message({ type: 'auth_success' });
        socket.message({ type: 'tab_state_sync', tabs: [] });
        await connected;

        expect(callbacks.onAuthRequired).toHaveBeenCalledOnce();
        expect(callbacks.onAuthFailed).toHaveBeenCalledWith(2, 'bad password');
        expect(callbacks.onAuthSuccess).toHaveBeenCalledOnce();
        expect(callbacks.onStateSync).toHaveBeenCalledWith([]);
        expect(socket.sent).toContain(JSON.stringify({ type: 'auth', password: 'secret' }));

        service.disconnect();
    });

    it('correlates tab requests with server responses', async () => {
        const service = createManagementService({
            onStateSync: vi.fn(),
            onStateUpdate: vi.fn(),
            onDisconnect: vi.fn(),
        });
        const connected = service.connect();
        const socket = FakeWebSocket.instances[0]!;
        socket.open();
        socket.message({ type: 'tab_state_sync', tabs: [] });
        await connected;

        const created = service.createTab('pwsh');
        const request = JSON.parse(socket.sent.at(-1) as string) as {
            request_id: string;
            shell_id: string;
        };
        socket.message({
            type: 'create_tab_response',
            request_id: request.request_id,
            success: true,
            tab: {
                id: 'tab-1',
                session_id: 'session-1',
                shell_id: request.shell_id,
                name: 'PowerShell',
                created_at: 'now',
                last_accessed: 'now',
            },
        });

        await expect(created).resolves.toMatchObject({ id: 'tab-1', shell_id: 'pwsh' });
        service.disconnect();
    });
});
