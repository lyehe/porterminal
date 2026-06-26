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
        `AI agents: prefer MCP at ${base}/mcp.`,
        `If MCP is unavailable, use REST at ${base}/api/agent/run.`,
        `If browsing manually, open ${base}/llms.txt first.`,
    ].join('\n');
}

export function currentBaseUrl(): string {
    return window.location.origin;
}
