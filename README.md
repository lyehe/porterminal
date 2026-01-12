<p align="center">
  <a href="https://github.com/lyehe/porterminal">
    <img src="assets/banner.jpg" alt="Porterminal - Vibe Code From Anywhere" width="600">
  </a>
</p>

<p align="center">
  <a href="https://pypi.org/project/ptn/"><img src="https://img.shields.io/pypi/v/ptn?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/ptn/"><img src="https://img.shields.io/pypi/pyversions/ptn?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://pypi.org/project/ptn/"><img src="https://img.shields.io/pypi/dm/ptn?style=flat-square&label=Downloads" alt="Downloads"></a>
  <a href="https://github.com/lyehe/porterminal/blob/master/LICENSE"><img src="https://img.shields.io/github/license/lyehe/porterminal?style=flat-square" alt="License"></a>
  <a href="https://github.com/lyehe/porterminal/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/lyehe/porterminal/ci.yml?branch=master&style=flat-square&logo=github&label=CI" alt="CI"></a>
</p>



<p align="center">
  <b>1.</b> <code>uvx ptn</code><br>
  <b>2.</b> Scan the QR<br>
  <b>3.</b> Access your terminal from your phone<br>
</p>

<p align="center">
  <img src="assets/demo.gif" alt="Porterminal demo" width="320">
</p>

## Why

I wanted to vibe code from bed.

**ngrok** requires registration and the free tier sucks. **Cloudflare Quick Tunnel** works great but is hard to use directly on the phone. **Termius** requires complicated setup: port forwarding, firewall rules, key management... Tried **Claude Code web**, but it can't access my local hardware and environment. Also tried **Happy**, but it's too bulky and updates lag behind.

So I built something simpler: **run a command, scan a QR, start typing.**

## Features

- **One command, instant access** - No SSH, no port forwarding, no config files. Cloudflare tunnel + QR code.
- **Actually usable on mobile** - Touch-optimized with momentum scrolling, pinch-to-zoom, swipe gestures, and modifier keys (Ctrl, Alt).
- **Full terminal apps** - vim, htop, less, tmux all work correctly with proper alt-screen buffer handling.
- **Persistent multi-tab sessions** - Sessions survive disconnects. Close the browser, switch networks, reconnect from another device—your shell and running processes are still there. Multiple devices can view the same session simultaneously.
- **Cross-platform** - Windows (PowerShell, CMD, WSL), Linux/macOS (Bash, Zsh, Fish, Nushell, and any shell via `$SHELL`). Auto-detects your shells.

## Install

| Method | Install | Update |
|--------|---------|--------|
| **uvx** (no install) | `uvx ptn` | `uvx --refresh ptn` |
| **uv tool** | `uv tool install ptn` | `uv tool upgrade ptn` |
| **pipx** | `pipx install ptn` | `pipx upgrade ptn` |
| **pip** | `pip install ptn` | `pip install -U ptn` |

**One-line install (uv + ptn):**

| OS | Command |
|----|---------|
| **Windows** | `powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/lyehe/porterminal/master/install.ps1 \| iex"` |
| **macOS/Linux** | `curl -LsSf https://raw.githubusercontent.com/lyehe/porterminal/master/install.sh \| sh` |

Requires Python 3.12+ and [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (auto-installed if missing).

## Usage

```bash
ptn                    # Start in current directory
ptn ~/projects/myapp   # Start in specific folder
```

| Flag | Description |
|------|-------------|
| `-n, --no-tunnel` | Local network only (no Cloudflare tunnel) |
| `-b, --background` | Run in background and return immediately |
| `-p, --password` | Prompt for password to protect this session |
| `-dp, --default-password` | Toggle password requirement in config (on/off) |
| `-v, --verbose` | Show detailed startup logs |
| `-i, --init` | Create `.ptn/ptn.yaml` config with auto-discovered project scripts |
| `-u, --update` | Update to the latest version |
| `-c, --check-update` | Check if a newer version is available |
| `-V, --version` | Show version |

## Mobile Gestures

| Gesture | Action |
|---------|--------|
| **Tap** | Focus terminal, clear selection |
| **Long-press** | Start text selection |
| **Double-tap** | Select word |
| **Swipe left/right** | Arrow keys (← →) |
| **Scroll** | Momentum scrolling with physics |
| **Pinch** | Zoom text (10-24px) |

**Modifier keys** (Ctrl, Alt, Shift): Tap once for sticky (one keystroke), double-tap for lock.

## Configuration

Run `ptn --init` to create a starter config. It auto-discovers project scripts from `package.json`, `pyproject.toml`, or `Makefile` and adds them as buttons:

```bash
ptn -i
# Created: .ptn/ptn.yaml
# Discovered 3 project script(s): build, dev, test
```

Or create `ptn.yaml` manually:

```yaml
# Terminal settings
terminal:
  default_shell: nu              # Default shell ID
  shells:                        # Custom shell definitions
    - id: nu
      name: Nushell
      command: nu
      args: []

# Custom buttons (appear in toolbar)
# row: 1 = default row, 2+ = additional rows
buttons:
  - label: "claude"
    send:
      - "claude"
      - 100        # delay in ms
      - "\r"
  - label: "build"
    send: "npm run build\r"
    row: 2         # second button row

# Update checker settings
update:
  notify_on_startup: true   # Show update notification
  check_interval: 86400     # Seconds between checks (default: 24h)

# Security settings
security:
  require_password: true    # Always prompt for password at startup
  max_auth_attempts: 5      # Max failed attempts before disconnect
```

Config is searched in order: `$PORTERMINAL_CONFIG_PATH`, `./ptn.yaml`, `./.ptn/ptn.yaml`, `~/.ptn/ptn.yaml`.

## Security

Use password if your screen can be exposed to others:
```bash
ptn -p                 # Prompt for password this session
ptn -dp                # Enable password by default (toggle)
```

Password is per-session (never saved to disk). See [docs/security.md](docs/security.md) for details.

## Troubleshooting

**Connection fails?** Cloudflare tunnel sometimes blocks connections. Restart the server (`Ctrl+C`, then `ptn`) to get a fresh tunnel URL.

**Shell not detected?** Set your `$SHELL` environment variable or configure shells in `ptn.yaml`.

## Contributing

Issues and PRs welcome.

```bash
git clone https://github.com/lyehe/porterminal
cd porterminal
uv sync
uv run ptn
```

## License

[AGPL-3.0](LICENSE)
