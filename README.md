<p align="center">
  <a href="https://github.com/lyehe/porterminal">
    <img src="assets/banner.jpg" alt="Porterminal - Vibe Code From Anywhere" width="600">
  </a>
</p>

<p align="center">
  <a href="https://pypi.org/project/ptn/">
    <img src="https://img.shields.io/pypi/v/ptn?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI">
  </a>
  <a href="https://pypi.org/project/ptn/">
    <img src="https://img.shields.io/pypi/pyversions/ptn?style=flat-square&logo=python&logoColor=white" alt="Python">
  </a>
  <a href="https://pypi.org/project/ptn/">
    <img src="https://img.shields.io/pypi/dm/ptn?style=flat-square&label=Downloads" alt="Downloads">
  </a>
  <a href="https://github.com/lyehe/porterminal/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/lyehe/porterminal?style=flat-square" alt="License">
  </a>
</p>

Web terminal accessible from your phone via Cloudflare Quick Tunnel. Touch-friendly interface with virtual keys, multi-tab sessions, etc.

## Features

- **Touch-optimized** - Virtual keyboard, touch gestures
- **Multi-tab sessions** - Run multiple terminals simultaneously with persistent sessions
- **Instant access** - Cloudflare Quick Tunnel with QR code, no port forwarding needed
- **Cross-platform** - Windows (PowerShell, CMD, WSL), Linux/macOS (Bash, Zsh, Fish)

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
- [uv](https://docs.astral.sh/uv/) is prefered
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (auto-installed if missing)

## License

[AGPL-3.0](LICENSE)
