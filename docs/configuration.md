# Configuration

Porterminal searches for `ptn.yaml` in these locations (first found wins):

1. `ptn.yaml` in working directory
2. `.ptn/ptn.yaml` in working directory
3. `~/.ptn/ptn.yaml` (user home)

Override with `PORTERMINAL_CONFIG_PATH` environment variable.

## Default Configuration

```yaml
server:
  host: "127.0.0.1"
  port: 8000

terminal:
  cols: 120
  rows: 30

buttons: []

cloudflare:
  team_domain: ""
  access_aud: ""
```

## Server Settings

| Option | Default | Description |
|--------|---------|-------------|
| `host` | `127.0.0.1` | Bind address. Use `0.0.0.0` only with tunnel |
| `port` | `8000` | Server port |

```yaml
server:
  host: "127.0.0.1"
  port: 8000
```

## Terminal Settings

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| `cols` | `120` | 40-500 | Terminal width in columns |
| `rows` | `30` | 10-200 | Terminal height in rows |
| `default_shell` | auto | - | Override auto-detected shell |
| `shells` | auto | - | Custom shell definitions |

### Shell Auto-Detection

Porterminal automatically detects available shells:

- **Windows**: PowerShell, CMD, WSL (if installed)
- **Unix**: bash, zsh, sh

### Custom Shells

```yaml
terminal:
  default_shell: "custom"
  shells:
    - name: "Custom Shell"
      id: "custom"
      command: "/path/to/shell"
      args: ["-l"]
```

## Custom Buttons

Add custom buttons to the toolbar (appears in third row):

```yaml
buttons:
  # Simple command
  - label: "git"
    send: "git status\r"

  # With delay before Enter (numbers = wait ms)
  - label: "new"
    send:
      - "/new"
      - 10           # wait 10ms
      - "\r"         # Enter

  # Control characters
  - label: "clear"
    send: "\x0c"     # Ctrl+L
```

| Property | Description |
|----------|-------------|
| `label` | Button text (keep short for mobile) |
| `send` | String or list. Use `\r` for Enter, numbers for delays (ms) |

### Control Character Reference

| YAML Escape | Key | Description |
|-------------|-----|-------------|
| `\r` | Enter | Carriage return |
| `\n` | Newline | Line feed |
| `\x03` | Ctrl+C | Interrupt |
| `\x04` | Ctrl+D | EOF |
| `\x0c` | Ctrl+L | Clear screen |
| `\x1a` | Ctrl+Z | Suspend |
| `\x1b` | Escape | Escape key |

Note: YAML escape sequences require double quotes (`"...\r"`). Single quotes treat backslash literally.

## Cloudflare Access Integration

For team deployments, you can protect your terminal with [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/).

### How It Works

When Cloudflare Access authenticates a user, it adds a header to every request:
```
cf-access-authenticated-user-email: user@example.com
```

Porterminal reads this header to identify users. Each user gets isolated sessions (max 10 per user).

### Setup

1. **Create a Cloudflare Access Application**
   - Go to Zero Trust Dashboard → Access → Applications
   - Add a self-hosted application
   - Set the application domain to your tunnel URL
   - Configure an Access Policy (e.g., allow specific emails)

2. **No config needed in Porterminal**

   Cloudflare handles authentication at the proxy level. The `cloudflare:` section in config is reserved for future use (JWT validation).

### Security Model

| Layer | What It Does |
|-------|--------------|
| Cloudflare Access | Validates JWT, enforces policies, sets trusted headers |
| Cloudflare Tunnel | Routes only authenticated traffic to your app |
| Porterminal | Trusts `cf-access-authenticated-user-email` header for user isolation |

This is secure because:
- Clients cannot set the `cf-access-authenticated-user-email` header directly
- All traffic goes through Cloudflare tunnel (not exposed to internet)
- Cloudflare validates tokens before forwarding requests

### Without Cloudflare Access

When running locally or without Access, users are identified as `local-user` and share sessions.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PORTERMINAL_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `PORTERMINAL_CWD` | Override working directory |
| `PORTERMINAL_CONFIG_PATH` | Path to config file (overrides search) |
