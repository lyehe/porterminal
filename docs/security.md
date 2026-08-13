# Security

Porterminal exposes a terminal over the network. This document covers its
per-launch access path and optional browser password.

## Per-Launch Access Path

Every `ptn` start generates a new 128-bit URL-safe access code and appends it to
the connection URL:

```text
https://<tunnel>.trycloudflare.com/<access-code>/
```

The outer server boundary requires that exact prefix for every browser page,
static asset, WebSocket, MCP request, REST call, discovery document, and health
check. Requests to the bare hostname or a wrong path receive 404; rejected
WebSockets close before reaching terminal code. The page also sends
`Referrer-Policy: no-referrer` to reduce accidental link leakage.

This prevents someone who only discovers or brute-forces the tunnel hostname
from reaching the terminal. It is not an account system: the complete URL is a
bearer credential. It appears in the QR code, browser history, copied share
text, and any place you paste it. Anyone with that complete URL can use the
terminal and agent APIs. Stop and restart Porterminal to rotate the code after
a suspected leak.

The MCP SDK's static localhost-only Host validation is disabled for the nested
MCP application because a Quick Tunnel hostname is dynamic and learned only
after the server starts. This does not bypass the application boundary: the
outer access-path middleware validates the 128-bit capability before any MCP
request is dispatched. The exact `/mcp` route is also forwarded internally to
the mounted MCP application, avoiding an external redirect whose scheme could
otherwise be derived from the local proxy connection.

## When to Use Password Protection

Use a password as an extra layer for browser connections if the complete URL
might be exposed. A password does not protect MCP or REST, so rotate the URL if
someone untrusted sees the QR code or complete link.

## Password Protection

Password protection authenticates the browser's management and terminal
WebSocket connections. Agent MCP and REST access intentionally continues to use
the complete generated URL as its credential; see
[Agent Access](agent-access.md#security--limits).

### Enabling Password Protection

**For current session only:**
```bash
ptn -p
```
You'll be prompted to enter a password. It is required for all connecting browser devices.

**Toggle the default requirement:**
```bash
ptn -tp
```

Use `ptn -sp` to save or clear a password hash in the configuration file.

**Via config file:**
```yaml
security:
  require_password: true
  max_auth_attempts: 5
```

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                        SERVER                                │
│  1. Startup: prompt for password                            │
│  2. Hash with bcrypt, store in memory                       │
│  3. On WebSocket connect: require auth message              │
│  4. Validate password against hash                          │
│  5. Allow/reject connection                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT                                │
│  1. Connect to WebSocket                                    │
│  2. Receive "auth_required" message                         │
│  3. Show password prompt (or use saved password)            │
│  4. Send password to server                                 │
│  5. On success: save to localStorage, proceed               │
│  6. On failure: show error, allow retry                     │
└─────────────────────────────────────────────────────────────┘
```

### Password Storage and Lifetime

`ptn -p` creates a disposable session password. `ptn -sp` deliberately saves a
bcrypt hash so password protection can start without prompting:

| Location | What's Stored | Lifetime |
|----------|---------------|----------|
| Server memory | bcrypt hash | Until server stops |
| Config file | bcrypt hash, when saved with `ptn -sp` | Until changed or cleared |
| Browser localStorage | Plaintext password plus its exact protected base URL | Until another launch is saved, storage is cleared, or auth fails |

**Key points:**
- `ptn -p` prompts for a new session password
- `ptn -sp` stores only a bcrypt hash, never the plaintext password
- A saved hash can be cleared by entering an empty password with `ptn -sp`
- Browser remembers one password for convenience alongside the complete
  origin-plus-launch-path URL. That URL must match exactly before the password
  is returned, so a password from one protected path is never read for another.
- Legacy hash-keyed credentials are not read because two different launch URLs
  could share a 32-bit hash.
- After successful authentication, saving the current password removes stale
  `ptn_auth_*` entries for older launch paths on that browser origin. Explicit
  clearing or an authentication failure removes all such entries. Other
  localStorage keys, including Porterminal UI preferences, are preserved.
- This single-current-credential policy prevents old plaintext passwords from
  accumulating after path rotation. Concurrent launches on the same origin may
  ask for their password again after another launch authenticates; existing
  authenticated WebSockets are unaffected. Different origins remain naturally
  isolated by browser storage.

### Retry Limits

Failed authentication attempts are tracked per WebSocket connection:

- Default: 5 attempts before disconnect
- Configurable via `security.max_auth_attempts`
- After max attempts, the server shuts down to stop further guesses

When this happens, the CLI prints a security warning. Someone able to reach the
password prompt already has the complete protected URL, so investigate how it
was exposed before restarting; the restart will also rotate the access code.

### WebSocket Protocol

**Server → Client:**
```json
{"type": "auth_required"}
{"type": "auth_success"}
{"type": "auth_failed", "attempts_remaining": 4, "error": "Invalid password"}
```

**Client → Server:**
```json
{"type": "auth", "password": "..."}
```

### Close Codes

| Code | Meaning |
|------|---------|
| 4001 | Authentication failed or required |

## Security Model

### With Password Protection

- Every route still requires the exact per-launch access path
- Browser WebSockets require the password before terminal access
- Password validated against bcrypt hash (server-side)
- Failed attempts are limited per connection, and exhaustion shuts down the server
- MCP and `/api/agent/*` retain the documented complete-URL-as-credential model

### Without Password Protection

- The random per-launch URL is the only credential
- The bare hostname and wrong paths expose no application routes
- Anyone with the complete link has full terminal access

### Administrative Shutdown Boundary

`POST /api/shutdown` accepts requests only when the server's direct TCP peer is
loopback. Porterminal disables Uvicorn's proxy-header rewriting for this check,
so forwarded headers such as `CF-Ray`, `CF-Access-Authenticated-User-Email`, and
`X-Forwarded-For` cannot turn a remote direct request into a local one.

The bundled Cloudflare Quick Tunnel connects to Porterminal through
`127.0.0.1`, so the existing browser shutdown control continues to work through
the tunnel. If you put Porterminal behind a different reverse proxy, run that
proxy on the same machine and connect it to Porterminal over loopback; a proxy
whose origin connection comes from a non-loopback address receives HTTP 403.

## Best Practices

1. **Keep the complete URL and QR private**
2. **Restart to rotate the access code** after a suspected leak
3. **Use a password** (`-p`) as an extra browser-only layer
4. **Stop the server** when not in use (`Ctrl+C`)
5. **Use `--no-tunnel`** for local network only
6. **Don't run as admin/root** - server warns if elevated
7. **Keep the origin private** when relying on Cloudflare Access identity headers

## Troubleshooting

**Connection fails?** Use the complete generated URL, including the access code.
Restart the server (`Ctrl+C`, then `ptn`) to get a fresh tunnel and access path.

## Cloudflare Access Integration

For team deployments, you can add an additional layer with [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/):

1. Cloudflare Access authenticates users at the edge
2. Only authenticated traffic reaches your server
3. User identity available via `cf-access-authenticated-user-email` header
4. Each user gets isolated sessions

This can be combined with password protection for defense in depth.

See [configuration.md](configuration.md#cloudflare-access-integration) for setup details.
