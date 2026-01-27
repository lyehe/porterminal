/**
 * Settings Overlay - Settings panel UI
 * Provides toggles for compose mode, update notifications, and custom button visibility
 */

import type { AppConfig, ButtonConfig } from '@/types';
import type { ConfigService } from '@/services/ConfigService';
import { getComposeMode, setComposeMode, getDisabledButtons, setDisabledButtons } from '@/utils/storage';

export interface SettingsCallbacks {
    /** Called when compose mode toggle changes */
    onComposeModeChange: (enabled: boolean) => void;
    /** Called when a button visibility toggle changes */
    onButtonVisibilityChange: (label: string, visible: boolean) => void;
    /** Called when buttons are added or removed */
    onButtonsChanged?: (buttons: ButtonConfig[]) => void;
}

export interface SettingsOverlay {
    /** Show the settings overlay */
    show(config: AppConfig): void;
    /** Hide the overlay */
    hide(): void;
    /** Setup event handlers and wire callbacks */
    setup(configService: ConfigService, callbacks: SettingsCallbacks): void;
    /** Sync compose mode state (for external changes) */
    syncComposeMode(enabled: boolean): void;
}

/** Create a debounced function that delays invocation */
function debounce(fn: () => void, delay: number): () => void {
    let timeout: ReturnType<typeof setTimeout> | null = null;
    return () => {
        if (timeout) clearTimeout(timeout);
        timeout = setTimeout(fn, delay);
    };
}

/** Escape HTML special characters */
function escapeHtml(str: string): string {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** Show a toast notification */
function showToast(message: string, type: 'success' | 'error' = 'success'): void {
    // Remove any existing toast
    document.querySelector('.settings-toast')?.remove();

    const toast = document.createElement('div');
    toast.className = `settings-toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 2000);
}

/**
 * Create a settings overlay controller
 */
export function createSettingsOverlay(): SettingsOverlay {
    const overlay = document.getElementById('settings-overlay');
    const content = document.getElementById('settings-content');
    const closeBtn = document.getElementById('settings-close');
    const composeToggle = document.getElementById('settings-compose') as HTMLInputElement | null;
    const updatesToggle = document.getElementById('settings-updates') as HTMLInputElement | null;
    const passwordStatus = document.getElementById('settings-password-status');
    const buttonsSection = document.getElementById('settings-buttons-section');

    // Password elements
    const requirePasswordToggle = document.getElementById('settings-require-password') as HTMLInputElement | null;
    const setPasswordBtn = document.getElementById('settings-set-password') as HTMLButtonElement | null;
    const clearPasswordBtn = document.getElementById('settings-clear-password') as HTMLButtonElement | null;
    const passwordForm = document.getElementById('settings-password-form');
    const passwordInput = document.getElementById('settings-password-input') as HTMLInputElement | null;
    const passwordConfirm = document.getElementById('settings-password-confirm') as HTMLInputElement | null;
    const passwordSaveBtn = document.getElementById('settings-password-save') as HTMLButtonElement | null;
    const passwordCancelBtn = document.getElementById('settings-password-cancel') as HTMLButtonElement | null;
    const restartNotice = document.getElementById('settings-restart-notice');

    let callbacks: SettingsCallbacks | null = null;
    let configService: ConfigService | null = null;
    let focusTrap: (() => void) | null = null;
    let needsRestart = false;

    /** Save notification setting to server (debounced) */
    const saveNotificationSetting = debounce(async () => {
        if (!configService || !updatesToggle) return;
        const result = await configService.updateSettings({
            notify_on_startup: updatesToggle.checked,
        });
        showToast(result.success ? 'Saved' : (result.error || 'Failed to save'),
            result.success ? 'success' : 'error');
    }, 300);

    /** Update password UI state based on status */
    function updatePasswordUI(passwordSaved: boolean, requirePassword: boolean, currentlyProtected: boolean): void {
        // Update status text
        if (passwordStatus) {
            if (currentlyProtected) {
                passwordStatus.textContent = 'Active';
                passwordStatus.className = 'settings-desc password-on';
            } else if (requirePassword) {
                passwordStatus.textContent = 'On (restart needed)';
                passwordStatus.className = 'settings-desc password-on';
            } else {
                passwordStatus.textContent = 'Off';
                passwordStatus.className = 'settings-desc password-off';
            }
        }

        // Update toggle
        if (requirePasswordToggle) {
            requirePasswordToggle.checked = requirePassword;
        }

        // Update buttons
        if (setPasswordBtn) {
            setPasswordBtn.textContent = passwordSaved ? 'Change Password' : 'Set Password';
        }
        if (clearPasswordBtn) {
            clearPasswordBtn.classList.toggle('hidden', !passwordSaved);
        }

        // Show restart notice if needed
        if (restartNotice) {
            restartNotice.classList.toggle('hidden', !needsRestart);
        }
    }

    /** Fetch and update password status */
    async function refreshPasswordStatus(): Promise<void> {
        if (!configService) return;
        const status = await configService.getPasswordStatus();
        updatePasswordUI(status.password_saved, status.require_password, status.currently_protected);
    }

    /** Show/hide password form */
    function showPasswordForm(show: boolean): void {
        passwordForm?.classList.toggle('hidden', !show);
        if (show && passwordInput) {
            passwordInput.value = '';
            if (passwordConfirm) passwordConfirm.value = '';
            passwordInput.focus();
        }
    }

    /** Handle password save */
    async function handlePasswordSave(): Promise<void> {
        if (!configService || !passwordInput || !passwordConfirm) return;

        const password = passwordInput.value;
        const confirm = passwordConfirm.value;

        if (!password) {
            showToast('Password required', 'error');
            return;
        }
        if (password !== confirm) {
            showToast('Passwords do not match', 'error');
            passwordConfirm.focus();
            return;
        }

        const result = await configService.setPassword(password);
        if (result.success) {
            showToast('Password saved');
            needsRestart = true;
            showPasswordForm(false);
            await refreshPasswordStatus();
        } else {
            showToast(result.error || 'Failed to save', 'error');
        }
    }

    /** Handle password clear */
    async function handlePasswordClear(): Promise<void> {
        if (!configService) return;

        const result = await configService.clearPassword();
        if (result.success) {
            showToast('Password cleared');
            needsRestart = true;
            await refreshPasswordStatus();
        } else {
            showToast(result.error || 'Failed to clear', 'error');
        }
    }

    /** Handle require password toggle */
    async function handleRequirePasswordToggle(): Promise<void> {
        if (!configService || !requirePasswordToggle) return;

        const result = await configService.setRequirePassword(requirePasswordToggle.checked);
        if (result.success) {
            showToast(requirePasswordToggle.checked ? 'Password required' : 'Password optional');
            needsRestart = true;
            await refreshPasswordStatus();
        } else {
            // Revert toggle on failure
            requirePasswordToggle.checked = !requirePasswordToggle.checked;
            showToast(result.error || 'Failed to update', 'error');
        }
    }

    /** Setup focus trap for accessibility */
    function setupFocusTrap(): () => void {
        if (!content) return () => {};

        const focusableSelector = 'button, input, [tabindex]:not([tabindex="-1"])';
        const focusableElements = content.querySelectorAll<HTMLElement>(focusableSelector);
        const firstFocusable = focusableElements[0];
        const lastFocusable = focusableElements[focusableElements.length - 1];

        const handleKeydown = (e: KeyboardEvent) => {
            if (e.key === 'Tab') {
                if (e.shiftKey) {
                    if (document.activeElement === firstFocusable) {
                        e.preventDefault();
                        lastFocusable?.focus();
                    }
                } else {
                    if (document.activeElement === lastFocusable) {
                        e.preventDefault();
                        firstFocusable?.focus();
                    }
                }
            }
        };

        content.addEventListener('keydown', handleKeydown);
        return () => content.removeEventListener('keydown', handleKeydown);
    }

    /** Render button toggles */
    function renderButtonToggles(buttons: ButtonConfig[]): void {
        if (!buttonsSection) return;

        buttonsSection.innerHTML = '';

        // Section header with add button
        const header = document.createElement('div');
        header.className = 'settings-section-header';
        header.innerHTML = `
            <span class="settings-section-title">Quick Buttons</span>
            <button class="settings-add-btn" title="Add button">+</button>
        `;
        buttonsSection.appendChild(header);

        // Add form (hidden by default)
        const form = document.createElement('div');
        form.className = 'settings-add-form hidden';
        form.innerHTML = `
            <div class="settings-add-row">
                <input type="text" class="settings-add-input settings-add-label" placeholder="Label" maxlength="10" data-field="label">
                <input type="text" class="settings-add-input settings-add-command" placeholder="Command" data-field="command">
                <button class="settings-add-submit">\u21b5</button>
            </div>
            <div class="settings-add-help">Use \\r for Enter, \\x1b for Escape. Numbers add delay (ms).</div>
        `;
        buttonsSection.appendChild(form);

        const labelInput = form.querySelector('[data-field="label"]') as HTMLInputElement;
        const commandInput = form.querySelector('[data-field="command"]') as HTMLInputElement;
        const addBtn = header.querySelector('.settings-add-btn') as HTMLButtonElement;

        addBtn.addEventListener('click', () => {
            const isHidden = form.classList.toggle('hidden');
            if (!isHidden) labelInput.focus();
        });

        const handleSubmit = async (): Promise<void> => {
            const label = labelInput.value.trim();
            const command = commandInput.value;

            if (!label || !command) {
                showToast('Label and command required', 'error');
                return;
            }
            if (!configService) return;

            const result = await configService.addButton(label, command);
            if (result.success) {
                const updatedButtons = result.buttons ?? [];
                showToast('Added');
                labelInput.value = '';
                commandInput.value = '';
                form.classList.add('hidden');
                callbacks?.onButtonsChanged?.(updatedButtons);
                renderButtonToggles(updatedButtons);
            } else {
                showToast(result.error || 'Failed to add', 'error');
            }
        };

        form.querySelector('.settings-add-submit')?.addEventListener('click', handleSubmit);
        commandInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleSubmit();
            }
        });
        labelInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                commandInput.focus();
            }
        });

        if (!buttons.length) {
            const empty = document.createElement('div');
            empty.className = 'settings-desc';
            empty.style.padding = '8px 0';
            empty.textContent = 'No custom buttons configured';
            buttonsSection.appendChild(empty);
            return;
        }

        const disabledButtons = getDisabledButtons();

        for (const btn of buttons) {
            const sendStr = Array.isArray(btn.send) ? btn.send.join(', ') : String(btn.send);
            const truncatedSend = sendStr.length > 30 ? sendStr.slice(0, 30) + '...' : sendStr;
            const safeLabel = escapeHtml(btn.label);
            const safeSend = escapeHtml(sendStr);
            const safeTruncated = escapeHtml(truncatedSend);

            const item = document.createElement('div');
            item.className = 'settings-button-item';
            item.innerHTML = `
                <label class="settings-button-label" for="settings-btn-${safeLabel}">
                    <span class="settings-button-preview">${safeLabel}</span>
                    <span class="settings-button-name" title="${safeSend}">${safeTruncated}</span>
                </label>
                <button class="settings-delete-btn" title="Delete">\u00d7</button>
                <label class="toggle-switch">
                    <input type="checkbox" id="settings-btn-${safeLabel}" role="switch">
                    <span class="toggle-slider"></span>
                </label>
            `;

            const checkbox = item.querySelector('input') as HTMLInputElement;
            checkbox.checked = !disabledButtons.includes(btn.label);

            checkbox.addEventListener('change', () => {
                const current = getDisabledButtons();
                const newDisabled = checkbox.checked
                    ? current.filter(l => l !== btn.label)
                    : [...current, btn.label];
                setDisabledButtons(newDisabled);
                callbacks?.onButtonVisibilityChange(btn.label, checkbox.checked);
            });

            item.querySelector('.settings-delete-btn')?.addEventListener('click', async () => {
                if (!configService) return;
                const result = await configService.removeButton(btn.label);
                if (result.success) {
                    const updatedButtons = result.buttons ?? [];
                    showToast('Removed');
                    callbacks?.onButtonsChanged?.(updatedButtons);
                    renderButtonToggles(updatedButtons);
                } else {
                    showToast(result.error || 'Failed to remove', 'error');
                }
            });

            buttonsSection.appendChild(item);
        }
    }

    return {
        show(config: AppConfig): void {
            // Update compose mode toggle
            if (composeToggle) {
                const localPref = getComposeMode();
                composeToggle.checked = localPref !== null ? localPref : (config.compose_mode ?? false);
            }

            // Update notifications toggle
            if (updatesToggle) {
                updatesToggle.checked = config.notify_on_startup ?? true;
            }

            // Fetch and update password status
            refreshPasswordStatus();

            // Hide password form initially
            showPasswordForm(false);

            // Render button toggles
            renderButtonToggles(config.buttons || []);

            // Show overlay
            overlay?.classList.remove('hidden');

            // Setup focus trap
            focusTrap = setupFocusTrap();

            // Focus close button
            closeBtn?.focus();
        },

        hide(): void {
            overlay?.classList.add('hidden');
            focusTrap?.();
            focusTrap = null;
        },

        syncComposeMode(enabled: boolean): void {
            if (composeToggle) {
                composeToggle.checked = enabled;
            }
        },

        setup(service: ConfigService, cbs: SettingsCallbacks): void {
            configService = service;
            callbacks = cbs;

            // Close button
            closeBtn?.addEventListener('click', () => this.hide());

            // Click outside to close
            overlay?.addEventListener('click', (e) => {
                if (e.target === overlay) this.hide();
            });

            // Escape key to close
            const handleEscape = (e: KeyboardEvent) => {
                if (e.key === 'Escape' && !overlay?.classList.contains('hidden')) {
                    e.preventDefault();
                    this.hide();
                }
            };
            document.addEventListener('keydown', handleEscape);

            // Compose mode toggle
            composeToggle?.addEventListener('change', () => {
                const enabled = composeToggle.checked;
                setComposeMode(enabled);
                callbacks?.onComposeModeChange(enabled);
            });

            // Update notifications toggle
            updatesToggle?.addEventListener('change', saveNotificationSetting);

            // Password management
            requirePasswordToggle?.addEventListener('change', handleRequirePasswordToggle);
            setPasswordBtn?.addEventListener('click', () => showPasswordForm(true));
            clearPasswordBtn?.addEventListener('click', handlePasswordClear);
            passwordSaveBtn?.addEventListener('click', handlePasswordSave);
            passwordCancelBtn?.addEventListener('click', () => showPasswordForm(false));

            // Enter key to save password
            passwordConfirm?.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    handlePasswordSave();
                }
            });
            passwordInput?.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    passwordConfirm?.focus();
                }
            });
        },
    };
}
