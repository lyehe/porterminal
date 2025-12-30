<p align="center">
  <img src="assets/banner.png" alt="Porterminal - Vibe Code From Anywhere" width="600">
</p>

<p align="center">
  <a href="https://pypi.org/project/ptn/"><img src="https://img.shields.io/pypi/v/ptn" alt="PyPI"></a>
  <a href="https://pypi.org/project/ptn/"><img src="https://img.shields.io/pypi/pyversions/ptn" alt="Python"></a>
  <a href="https://github.com/lyehe/porterminal/blob/main/LICENSE"><img src="https://img.shields.io/github/license/lyehe/porterminal" alt="License"></a>
</p>

Web-based terminal accessible from your phone via Cloudflare Quick Tunnel. Touch-friendly interface with virtual keys, multi-tab sessions, and automatic reconnection.

## Features

- **Touch-optimized** - Virtual keyboard with Ctrl/Alt/Shift modifiers, swipe gestures, pinch-to-zoom
- **Multi-tab sessions** - Run multiple terminals simultaneously with persistent sessions
- **Instant access** - Cloudflare Quick Tunnel with QR code, no port forwarding needed
- **Cross-platform** - Windows (PowerShell, CMD, WSL), Linux/macOS (Bash, Zsh, Fish)
- **Secure** - Environment sanitization blocks API keys and secrets

## Quick Start

```bash
# Install
uv tool install ptn

# Run
ptn
```

Scan the QR code with your phone to connect.

**Alternative methods:**

```bash
# Run without installing
uvx ptn

# Or with pip
pip install ptn
```

## Usage

```
ptn [path] [options]

Options:
  --no-tunnel       Local network only (no Cloudflare tunnel)
  -v, --verbose     Show detailed logs
  -U, --update      Update to latest version
  -V, --version     Show version
```

## Configuration

Create `config.yaml` to customize:

```yaml
server:
  host: "127.0.0.1"
  port: 8000

terminal:
  cols: 120
  rows: 30
  default_shell: powershell  # cmd, wsl, bash, zsh

buttons:
  - label: "git"
    send: "git status\r"
```

## Security

> **Warning:** The URL is the only authentication. Anyone with the link can access your terminal.

- Environment variables sanitized (API keys, tokens, secrets blocked)
- Rate limiting on input
- Sessions isolated per user via Cloudflare Access

## Requirements

- Python 3.12+
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (auto-installed if missing)

## License

[AGPL-3.0](LICENSE)
