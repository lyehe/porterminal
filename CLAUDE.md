# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Porterminal is a web-based terminal accessible from mobile devices via Cloudflare Quick Tunnel. It provides a touch-friendly interface with virtual buttons for special keys and modifiers.

## Quick Reference

```bash
# Backend
uv sync                  # Install dependencies
uv run ptn               # Run server
uv run pytest            # Run tests
uv run ruff check .      # Lint
uv run ruff format .     # Format
uv build                 # Build package

# Frontend (in frontend/)
npm install              # Install deps
npm run dev              # Dev server with HMR
npm run build            # Build to porterminal/static/
```

**Release:** `git tag v0.1.x -m "Release" && git push origin v0.1.x`

## Architecture

Hexagonal architecture with clean layer separation:

- `porterminal/domain/` - Core business logic, ports (interfaces), no external deps
- `porterminal/application/` - Use cases (TerminalService, SessionService)
- `porterminal/infrastructure/` - Adapters (WebSocket, config, cloudflared)
- `porterminal/pty/` - Platform PTY (windows.py, unix.py)
- `frontend/` - TypeScript/Vite app → builds to `porterminal/static/`

## Key Constraints

- Cross-platform: Windows (pywinpty), Linux/macOS (pty module)
- Requires `cloudflared` CLI for tunnel functionality (auto-installed if missing)
- Sessions persist as long as PTY is alive (no timeout)
- Frontend must be rebuilt (`npm run build`) for changes to appear in packaged app
