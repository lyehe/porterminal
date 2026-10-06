# Porterminal Documentation

**Give your agent any computer.**

Porterminal gives an AI agent a real terminal on a Windows, macOS, or Linux
computer. Run `uvx ptn`, share the generated connection instructions, and
open the same URL in a browser to watch or type into the agent's session.

## Start here

1. Run `uvx ptn` on the computer you want the agent to use.
2. Press **`c`** to copy the URL and agent instructions, and share them with a task.
3. Scan the QR code or open the complete URL, then select the agent's **🤖 tab**.

The agent connects through MCP or REST, and the browser joins the same
terminal. Both can send input, so coordinate typing. You can also use
Porterminal as a phone terminal without an agent.

The complete URL and QR code grant shell access to the computer. Treat them as
credentials. The optional password protects browser connections; agent APIs
use the URL as their credential. Read [security](security.md).

## Guides

| Guide | What it covers |
|-------|----------------|
| [Installation](installation.md) | Package managers, requirements, and running from source |
| [Agent access](agent-access.md) | MCP, REST, browser fallback, and session lifetimes |
| [Demo](demo.md) | A repeatable agent task and recording plan |
| [Terminal controls](frontend_features.md) | Mobile input, gestures, compose mode, and tabs |
| [Configuration](configuration.md) | Shells, toolbar buttons, and server settings |
| [Security](security.md) | Access URLs, passwords, and deployment boundaries |
| [Architecture](architecture.md) | Services, protocols, and terminal I/O |
| [Development](development.md) | Local checks and release process |
| [Changelog](CHANGELOG.md) | Version history |

## Requirements

- Python 3.12+
- `cloudflared` for remote access (Porterminal attempts to install it if missing)
- An agent with remote MCP support or HTTP tools; humans connect through a browser
