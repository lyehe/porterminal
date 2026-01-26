/**
 * Auth Overlay - Password prompt UI
 * Single Responsibility: Authentication modal visibility and interaction
 */

export interface AuthOverlay {
    /** Show the overlay */
    show(): void;
    /** Hide the overlay */
    hide(): void;
    /** Show error message */
    showError(message: string): void;
    /** Clear error message */
    clearError(): void;
    /** Clear password input */
    clearInput(): void;
    /** Setup event handlers */
    setup(onSubmit: (password: string) => void): void;
    /** Focus password input */
    focus(): void;
}

/**
 * Create an auth overlay controller
 */
export function createAuthOverlay(): AuthOverlay {
    const overlay = document.getElementById('auth-overlay');
    const errorElement = document.getElementById('auth-error');
    const authForm = document.getElementById('auth-form') as HTMLFormElement | null;
    const passwordInput = document.getElementById('auth-password') as HTMLInputElement | null;

    return {
        show(): void {
            overlay?.classList.remove('hidden');
            this.focus();
        },

        hide(): void {
            overlay?.classList.add('hidden');
            this.clearError();
            this.clearInput();
        },

        showError(message: string): void {
            if (errorElement) {
                errorElement.textContent = message;
                errorElement.classList.remove('hidden');
            }
        },

        clearError(): void {
            if (errorElement) {
                errorElement.textContent = '';
                errorElement.classList.add('hidden');
            }
        },

        clearInput(): void {
            if (passwordInput) {
                passwordInput.value = '';
            }
        },

        focus(): void {
            // Delay focus to ensure overlay is visible
            requestAnimationFrame(() => {
                passwordInput?.focus();
            });
        },

        setup(onSubmit: (password: string) => void): void {
            // Handle form submission (enables browser password saving)
            authForm?.addEventListener('submit', (e) => {
                e.preventDefault();
                const password = passwordInput?.value ?? '';
                if (password.trim()) {
                    onSubmit(password);
                }
            });
        },
    };
}
