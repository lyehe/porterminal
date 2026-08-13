import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig, devices } from '@playwright/test';

import {
    ACCESS_CODE,
    PORT,
    PROTECTED_BASE_URL,
} from './tests/protected-browser/environment';


const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');


export default defineConfig({
    testDir: './tests/protected-browser',
    fullyParallel: false,
    workers: 1,
    forbidOnly: Boolean(process.env.CI),
    retries: process.env.CI ? 1 : 0,
    reporter: process.env.CI ? 'github' : 'list',
    webServer: {
        command: [
            'uv run --frozen python -m uvicorn',
            'porterminal.asgi:create_app_from_env',
            '--factory',
            '--host 127.0.0.1',
            `--port ${PORT}`,
            '--log-level warning',
            '--no-access-log',
            '--no-proxy-headers',
        ].join(' '),
        cwd: repositoryRoot,
        env: {
            PORTERMINAL_ACCESS_CODE: ACCESS_CODE,
            PORTERMINAL_COMPOSE_MODE: 'false',
            PORTERMINAL_CONFIG_PATH: path.join(repositoryRoot, '.playwright-missing-config.yaml'),
            PORTERMINAL_CWD: repositoryRoot,
            PORTERMINAL_PASSWORD_HASH: '',
        },
        url: `${PROTECTED_BASE_URL}/health`,
        reuseExistingServer: false,
        timeout: 60_000,
    },
    use: {
        baseURL: `${PROTECTED_BASE_URL}/`,
        permissions: ['clipboard-read', 'clipboard-write'],
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
    },
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
});
