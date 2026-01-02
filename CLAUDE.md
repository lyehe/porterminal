# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Porterminal is a web-based terminal accessible from mobile devices via Cloudflare Quick Tunnel. It provides a touch-friendly interface with virtual buttons for special keys and modifiers.

## Quick Reference

```bash
uv sync          # Install dependencies
uv run ptn       # Run locally
uv build         # Build package
```

**Release:** `git tag v0.1.x -m "Release" && git push origin v0.1.x`

## Documentation

See [docs/](docs/) for detailed documentation:
- [Development Guide](docs/development.md) - Setup, structure, release process
- [Architecture](docs/architecture.md) - Technical design
- [Configuration](docs/configuration.md) - Settings and options

## Architecture Summary

Hexagonal architecture:
- `porterminal/domain/` - Core business logic (entities, value objects, ports)
- `porterminal/application/` - Use cases (TerminalService, SessionService)
- `porterminal/infrastructure/` - Adapters (WebSocket, config, cloudflared)
- `porterminal/pty/` - Platform PTY (windows.py, unix.py)
- `frontend/` - TypeScript/Vite app → builds to `porterminal/static/`

## Key Constraints

- Cross-platform: Windows (pywinpty), Linux/macOS (pty module)
- Requires `cloudflared` CLI for tunnel functionality (auto-installed if missing)
- Sessions persist as long as PTY is alive (no timeout)
