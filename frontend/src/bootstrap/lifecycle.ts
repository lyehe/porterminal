/** Browser lifecycle and reconnection wiring. */

import type { ModifierManager } from '@/input/ModifierManager';
import type { ConnectionService } from '@/services/ConnectionService';
import type { ManagementService } from '@/services/ManagementService';
import type { TabService } from '@/services/TabService';
import type { DisconnectOverlay } from '@/ui/DisconnectOverlay';


export interface LifecycleDependencies {
    modifierManager: ModifierManager;
    managementService: ManagementService;
    connectionService: ConnectionService;
    tabService: TabService;
    disconnectOverlay: DisconnectOverlay;
}


export function setupLifecycleHandlers(dependencies: LifecycleDependencies): void {
    const {
        modifierManager,
        managementService,
        connectionService,
        tabService,
        disconnectOverlay,
    } = dependencies;

    document.addEventListener('visibilitychange', async () => {
        modifierManager.reset();
        if (document.visibilityState !== 'visible') return;

        try {
            if (!managementService.isConnected()) await managementService.connect();
            for (const tab of tabService.tabs) {
                if (!connectionService.isConnected(tab)) connectionService.connect(tab, true);
            }
        } catch (error) {
            console.error('Failed to reconnect:', error);
            disconnectOverlay.show();
        }
    });

    window.addEventListener('blur', () => modifierManager.reset());

    if (window.visualViewport) {
        const app = document.getElementById('app');
        const updateAppSize = () => {
            if (!app || !window.visualViewport) return;
            app.style.height = `${window.visualViewport.height}px`;
            app.style.transform = `translateY(${window.visualViewport.offsetTop}px)`;
        };
        window.visualViewport.addEventListener('resize', updateAppSize);
        window.visualViewport.addEventListener('scroll', updateAppSize);
    }
}
