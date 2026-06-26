/**
 * Sharing helpers for Porterminal URLs.
 */

function cleanBaseUrl(url: string): string {
    return url.replace(/\/+$/, '');
}

export function buildAgentShareText(url: string): string {
    const base = cleanBaseUrl(url);
    return [
        'Use this Porterminal link to control the remote computer:',
        base,
        '',
        'Agent instructions:',
        `- First read ${base}/llms.txt for the exact API.`,
        `- Use MCP at ${base}/mcp if your runtime can connect remote MCP.`,
        `- If MCP is not already available, use REST at ${base}/api/agent/run; do not ask the user to configure MCP.`,
        `- If browsing manually, open ${base}/ and read the visible terminal screen.`,
        '- If the user included a task, start using the terminal. If not, ask one short question: "What should I run?"',
    ].join('\n');
}

export function currentBaseUrl(): string {
    return window.location.origin;
}
