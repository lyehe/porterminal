# Installation

## Quick Start

**Run without installing:**
```bash
uvx ptn
```

## Package Managers

| Method | Install | Update |
|--------|---------|--------|
| **uvx** (no install) | `uvx ptn` | `uvx --refresh ptn` |
| **uv tool** | `uv tool install ptn` | `uv tool upgrade ptn` |
| **pipx** | `pipx install ptn` | `pipx upgrade ptn` |
| **pip** | `pip install ptn` | `pip install -U ptn` |

## From Source

```bash
git clone https://github.com/porterminal/porterminal.git
cd porterminal
uv sync --frozen
uv run --frozen ptn
```

## Prerequisites

### Python
Python 3.12 or higher is required.

### cloudflared
The Cloudflare tunnel CLI is required for remote access. Porterminal will attempt to install it automatically on first run.

**Manual installation:**

```powershell
# Windows
winget install cloudflare.cloudflared
```

```bash
# macOS
brew install cloudflared
```

```bash
# Linux (Debian/Ubuntu)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

## Verify Installation

```bash
ptn --help
```

Expected output:
```
usage: ptn [path] [options]

Arguments:
  path              Starting directory for the shell

Options:
  --no-tunnel       Start server only, without Cloudflare tunnel
  --mcp-only        MCP control with local copy shortcuts, no QR or web terminal
  -v, --verbose     Show detailed startup logs
```

## Troubleshooting

**Connection fails:** use the complete generated URL, including its access
code. Restart Porterminal for a fresh tunnel and access path if needed.

**`uvx ptn` runs an older version:** an existing `uv tool` installation can
take precedence. Run `uv tool upgrade ptn`, or bypass installed tools with
`uvx --isolated ptn@latest`.

**Clipboard unavailable on Linux:** install `wl-clipboard` for Wayland or
`xclip`/`xsel` for X11. You can also press `s` to show selectable agent
instructions and the complete URL, then `q` to close them. Terminal clipboard
support varies; set `PORTERMINAL_DISABLE_OSC52_CLIPBOARD=1` to disable the
OSC 52 fallback if it causes problems in your terminal.
