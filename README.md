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

Simple, quick and dirty web terminal accessible from your phone via Cloudflare Quick Tunnel. Vibe-coding-friendly interface with virtual keys, multi-tab sessions, etc.

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
```

**Examples:**

```bash
# Start in current directory with tunnel
ptn

# Start in a specific project folder
ptn ~/projects/myapp

# Local network only (no Cloudflare tunnel)
ptn --no-tunnel

# Run in background (returns immediately)
ptn -b

# Show detailed startup logs
ptn -v

# Update to latest version
ptn -U

# Check for updates without installing
ptn --check-update
```

**Options:**

| Option | Description |
|--------|-------------|
| `path` | Starting directory for the shell (default: current) |
| `--no-tunnel` | Local network only, no Cloudflare tunnel |
| `-b, --background` | Run in background and return immediately |
| `-v, --verbose` | Show detailed startup logs |
| `-U, --update` | Update to the latest version |
| `--check-update` | Check if a newer version is available |
| `-V, --version` | Show version |
| `-h, --help` | Show help message |

## Configuration

Create `config.yaml` in your working directory to customize:

```yaml
# Server settings
server:
  host: "127.0.0.1"
  port: 8000

# Terminal settings
terminal:
  cols: 120        # Default columns (40-500)
  rows: 30         # Default rows (10-200)
  default_shell: powershell  # Default shell ID

  # Custom shells (optional - auto-detected if not specified)
  shells:
    - id: powershell
      name: PowerShell
      command: powershell.exe
      args: ["-NoLogo"]
    - id: wsl
      name: WSL
      command: wsl.exe
      args: []

# Custom quick-action buttons
buttons:
  - label: "git"
    send: "git status\r"
  - label: "ls"
    send: "ls -la\r"
  - label: "clear"
    send: "clear\r"
  - label: "exit"
    send: "exit\r"
```

**Minimal config example:**

```yaml
terminal:
  default_shell: bash
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
