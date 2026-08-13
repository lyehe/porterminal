export const ACCESS_CODE = 'BrowserAccessCode_123456';

const configuredPort = Number(process.env.PORTERMINAL_PROTECTED_TEST_PORT ?? '8765');
if (!Number.isInteger(configuredPort) || configuredPort < 1 || configuredPort > 65_535) {
    throw new Error('PORTERMINAL_PROTECTED_TEST_PORT must be an integer from 1 to 65535');
}

export const PORT = configuredPort;
export const ORIGIN = `http://127.0.0.1:${PORT}`;
export const PREFIX = `/${ACCESS_CODE}`;
export const PROTECTED_BASE_URL = `${ORIGIN}${PREFIX}`;
