import { fileURLToPath, URL } from 'node:url';

import { defineConfig } from 'vitest/config';


export default defineConfig({
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url)),
        },
    },
    test: {
        environment: 'jsdom',
        setupFiles: ['./tests/setup.ts'],
        include: ['tests/unit/**/*.test.ts'],
        restoreMocks: true,
        coverage: {
            provider: 'v8',
            reporter: ['text', 'json-summary', 'lcov'],
            reportsDirectory: 'coverage',
            include: ['src/**/*.ts'],
        },
    },
});
