/** Synchronize the hidden accessible terminal screen with the active tab. */

import type { EventBus } from '@/core/events';
import type { TabService } from '@/services/TabService';
import type { TerminalScreenMirror } from '@/ui/TerminalScreenMirror';


export function wireTerminalScreenMirror(
    eventBus: EventBus,
    tabService: TabService,
    terminalScreenMirror: TerminalScreenMirror,
): void {
    const renderDisposables = new Map<number, { dispose: () => void }>();

    eventBus.on('tab:created', ({ tab }) => {
        renderDisposables.set(tab.id, tab.term.onRender(() => {
            if (tab.id === tabService.activeTabId) terminalScreenMirror.update(tab.term);
        }));
        if (tab.id === tabService.activeTabId || tabService.activeTabId === null) {
            terminalScreenMirror.update(tab.term);
        }
    });

    eventBus.on('tab:switched', ({ tab }) => terminalScreenMirror.update(tab.term));
    eventBus.on('tab:closed', ({ tabId }) => {
        renderDisposables.get(tabId)?.dispose();
        renderDisposables.delete(tabId);
        terminalScreenMirror.update(tabService.activeTab?.term ?? null);
    });
}
