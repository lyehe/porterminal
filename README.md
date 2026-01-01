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

<p align="center">
  <strong>Access your terminal from your phone. No setup. Just scan.</strong>
</p>

```bash
uvx ptn
```

<p align="center">
  <em>Scan the QR code. Start typing. That's it.</em>
</p>

---

## Why I Built This

I wanted to continue vibe coding after bed. I tried ngrok, but it requires registration. I tried Cloudflare Tunnel, but it doesn't provide a usable terminal UI. I tried Termius, but it comes with apps, accounts, and too much setup. I just wanted something simpler: open a browser, get a terminal, start typing.

So I built Porterminal. A mobile-first web terminal with secure tunneling, no registration, no installation on your phone, and a touch-friendly UI optimized for vibe coding with whatever AI app you want.

## Features

- **One command, instant access** - No SSH, no port forwarding, no config files. Cloudflare tunnel + QR code.
- **Actually usable on mobile** - Virtual modifier keys (Ctrl, Alt, Tab, arrows), swipe gestures, copy/paste that works.
- **Multi-tab sessions** - Run builds in one tab, tail logs in another. Sessions persist across reconnects.
- **Cross-platform** - Windows (PowerShell, CMD, WSL), Linux/macOS (Bash, Zsh, Fish). Auto-detects your shells.

## Installation

| Method | Install | Update |
|--------|---------|--------|
| **uvx** (no install) | `uvx ptn` | `uvx --refresh ptn` |
| **uv tool** | `uv tool install ptn` | `uv tool upgrade ptn` |
| **pipx** | `pipx install ptn` | `pipx upgrade ptn` |
| **pip** | `pip install ptn` | `pip install -U ptn` |

Requires Python 3.12+ and [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (auto-installed if missing).

## Usage

```bash
ptn                    # Start in current directory
ptn ~/projects/myapp   # Start in specific folder
ptn --no-tunnel        # Local network only (no Cloudflare)
ptn -b                 # Run in background
```

<details>
<summary><strong>All options</strong></summary>

| Option | Description |
|--------|-------------|
| `path` | Starting directory (default: current) |
| `--no-tunnel` | Local network only |
| `-b, --background` | Run in background |
| `-v, --verbose` | Detailed logs |
| `-U, --update` | Update to latest |
| `--check-update` | Check for updates |
| `-V, --version` | Show version |

</details>

## Configuration

Create `config.yaml` in your working directory (optional):

```yaml
terminal:
  default_shell: bash
  cols: 120
  rows: 30

buttons:
  - label: "git"
    send: "git status\r"
  - label: "build"
    send: "npm run build\r"
```

<details>
<summary><strong>Full config options</strong></summary>

```yaml
server:
  host: "127.0.0.1"
  port: 8000

terminal:
  cols: 120
  rows: 30
  default_shell: powershell

  # Custom shells (auto-detected if not specified)
  shells:
    - id: powershell
      name: PowerShell
      command: powershell.exe
      args: ["-NoLogo"]
    - id: wsl
      name: WSL
      command: wsl.exe

buttons:
  - label: "git"
    send: "git status\r"
  - label: "ls"
    send: "ls -la\r"
```

</details>

## Security

> **Warning:** The URL is the only authentication. Anyone with the link has full terminal access.

**Best practices:**
- Don't share the URL
- Stop the server when not in use (`Ctrl+C`)
- Use `--no-tunnel` for local network only

**Built-in protections:**
- Environment variables sanitized (API keys, tokens stripped)
- Rate limiting on input
- Cloudflare Access integration for teams

## Contributing

Issues and PRs welcome. This project uses [uv](https://docs.astral.sh/uv/) for development:

```bash
git clone https://github.com/lyehe/porterminal
cd porterminal
uv sync
uv run ptn
```

## License

[AGPL-3.0](LICENSE)
