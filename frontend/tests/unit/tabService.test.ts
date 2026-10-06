import { afterEach, describe, expect, it, vi } from 'vitest';

import { createEventBus } from '@/core/events';
import { createTabService } from '@/services/TabService';
import type { ConnectionService } from '@/services/ConnectionService';
import type { ManagementService } from '@/services/ManagementService';
import type { ServerTab } from '@/types';

vi.mock('@xterm/xterm', () => ({
    Terminal: class {
        textarea = document.createElement('textarea');
        loadAddon() {}
        open(container: HTMLElement) { container.append(this.textarea); }
        onData() {}
        onSelectionChange() {}
        onResize() {}
        focus() { this.textarea.focus(); }
        dispose() {}
    },
}));
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }));
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }));
vi.mock('@xterm/addon-webgl', () => ({ WebglAddon: class { onContextLoss() {} } }));

function setup() {
    document.body.innerHTML = '<div id="tab-bar"><div id="shell-selector"></div></div><div id="terminal"></div>';
    const closeTab = vi.fn().mockResolvedValue(undefined);
    const connection = {
        connect: vi.fn(), disconnect: vi.fn(), cleanupTabState: vi.fn(),
    };
    const service = createTabService(createEventBus(), { closeTab } as unknown as ManagementService,
        connection as unknown as ConnectionService, { ctrl: 'off', alt: 'off', shift: 'off' }, {
        onInputSend: vi.fn(), onSelectionCopy: vi.fn(), scheduleResize: vi.fn(),
    });
    const tabs: ServerTab[] = ['first', 'second'].map(id => ({
        id, session_id: id, shell_id: 'bash', name: id,
        created_at: '', last_accessed: '', origin: 'human',
    }));
    service.applyStateSync(tabs);
    return { service, closeTab, connection };
}

afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
});

describe('accessible terminal tab controls', () => {
    it('offers separate labelled selection and close buttons', () => {
        setup();
        expect(document.querySelectorAll('button.tab-select')).toHaveLength(2);
        expect(document.querySelectorAll('button.tab-close')).toHaveLength(2);
        expect(document.querySelector('button button')).toBeNull();
        expect(document.querySelector('.tab-select')?.getAttribute('aria-label'))
            .toBe('Select terminal tab 1, bash');
        expect(document.querySelector('.tab-close')?.getAttribute('aria-label'))
            .toBe('Close terminal tab 1');
    });

    it('closes a tab on confirmed keyboard activation and restores focus', async () => {
        const { closeTab } = setup();
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const button = document.querySelector<HTMLButtonElement>('button.tab-close')!;
        button.focus();
        button.click(); // Native Enter/Space activation dispatches click.

        await vi.waitFor(() => expect(closeTab).toHaveBeenCalledWith('first'));
        await vi.waitFor(() => expect(document.querySelectorAll('.tab-select')).toHaveLength(1));
        expect(document.activeElement).toBe(document.querySelector('.tab-select'));
    });

    it('keeps the tab when keyboard confirmation is declined', () => {
        const { closeTab } = setup();
        vi.spyOn(window, 'confirm').mockReturnValue(false);
        document.querySelector<HTMLButtonElement>('button.tab-close')!.click();
        expect(closeTab).not.toHaveBeenCalled();
        expect(document.querySelectorAll('.tab-select')).toHaveLength(2);
    });

    it('retains deliberate pointer hold without requiring another confirmation', async () => {
        vi.useFakeTimers();
        const { closeTab } = setup();
        const confirm = vi.spyOn(window, 'confirm');
        const button = document.querySelector<HTMLButtonElement>('button.tab-close')!;
        button.dispatchEvent(new Event('pointerdown'));
        await vi.advanceTimersByTimeAsync(400);
        button.click();
        expect(closeTab).toHaveBeenCalledTimes(1);
        expect(confirm).not.toHaveBeenCalled();
    });

    it.each(['click', 'hold'])('restores the terminal and allows retry after a failed %s close', async activation => {
        vi.useFakeTimers();
        const { service, closeTab, connection } = setup();
        const tab = service.tabs[0];
        connection.connect.mockClear();
        const error = new Error('Close request rejected');
        closeTab.mockRejectedValueOnce(error);
        const logError = vi.spyOn(console, 'error').mockImplementation(() => {});
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const button = document.querySelector<HTMLButtonElement>('button.tab-close')!;

        if (activation === 'hold') {
            button.dispatchEvent(new Event('pointerdown'));
            await vi.advanceTimersByTimeAsync(400);
        } else {
            button.click();
            await vi.advanceTimersByTimeAsync(0);
        }

        expect(logError).toHaveBeenCalledWith(error);
        expect(connection.disconnect).toHaveBeenCalledWith(tab);
        expect(connection.connect).toHaveBeenCalledWith(tab);
        expect(document.querySelectorAll('.tab-select')).toHaveLength(2);
        expect(button.classList.contains('ready')).toBe(false);

        button.click();
        await vi.advanceTimersByTimeAsync(0);
        expect(closeTab).toHaveBeenCalledTimes(2);
        expect(document.querySelectorAll('.tab-select')).toHaveLength(1);
    });
});
