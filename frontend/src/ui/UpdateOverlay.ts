/**
 * Update Overlay - Version notification UI
 * Single Responsibility: Show version info on startup (update available or up to date)
 */

export interface UpdateInfo {
    currentVersion: string;
    latestVersion: string | null;
    upgradeCommand: string | null;
    updateAvailable: boolean;
}

export interface UpdateOverlay {
    /** Show the overlay with version info */
    show(info: UpdateInfo): void;
    /** Hide the overlay */
    hide(): void;
    /** Setup event handlers */
    setup(): void;
}

/**
 * Create an update overlay controller
 */
export function createUpdateOverlay(): UpdateOverlay {
    const overlay = document.getElementById('update-overlay');
    const content = document.getElementById('update-content');
    const iconEl = document.getElementById('update-icon');
    const titleEl = document.getElementById('update-title');
    const currentEl = document.getElementById('update-current');
    const arrowEl = document.getElementById('update-arrow');
    const latestEl = document.getElementById('update-latest');
    const instructionsEl = document.getElementById('update-instructions');
    const commandEl = document.getElementById('update-command');
    const copyBtn = document.getElementById('update-copy');

    let currentCommand = '';

    async function copyCommand(e: Event): Promise<void> {
        e.stopPropagation(); // Don't close overlay when clicking copy
        if (!currentCommand || !copyBtn) return;

        try {
            await navigator.clipboard.writeText(currentCommand);
            copyBtn.textContent = 'Copied!';
            copyBtn.classList.add('copied');
            setTimeout(() => {
                copyBtn.textContent = 'Copy';
                copyBtn.classList.remove('copied');
            }, 2000);
        } catch {
            // Fallback: select the text
            if (commandEl) {
                const range = document.createRange();
                range.selectNodeContents(commandEl);
                const selection = window.getSelection();
                selection?.removeAllRanges();
                selection?.addRange(range);
            }
        }
    }

    return {
        show(info: UpdateInfo): void {
            if (!info.updateAvailable) {
                this.hide();
                return;
            }

            if (info.updateAvailable) {
                // Update available state
                overlay?.classList.remove('up-to-date');
                if (iconEl) iconEl.textContent = '↑';
                if (titleEl) titleEl.textContent = 'Update Available';
                if (currentEl) currentEl.textContent = info.currentVersion;
                if (arrowEl) arrowEl.style.display = '';
                if (latestEl) {
                    latestEl.textContent = info.latestVersion || '';
                    latestEl.style.display = '';
                }
                if (instructionsEl) instructionsEl.style.display = '';
                if (commandEl) commandEl.textContent = info.upgradeCommand || '';
                currentCommand = info.upgradeCommand || '';
            }
            overlay?.classList.remove('hidden');
        },

        hide(): void {
            overlay?.classList.add('hidden');
        },

        setup(): void {
            // Click anywhere on overlay/content to close. The copy button has
            // its own handler and keeps the notice open long enough to confirm.
            overlay?.addEventListener('click', () => {
                overlay?.classList.add('hidden');
            });

            content?.addEventListener('click', (e) => {
                if (e.target === copyBtn) {
                    return;
                }
                overlay?.classList.add('hidden');
            });

            // Copy button
            copyBtn?.addEventListener('click', copyCommand);
        },
    };
}
