# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Porterminal is a web-based terminal accessible from mobile devices via Cloudflare Quick Tunnel. It provides a touch-friendly interface with virtual buttons for special keys and modifiers.

## Quick Reference

```bash
# Backend
uv sync                         # Install dependencies
uv run ptn                      # Run server
uv run ptn --no-tunnel          # Run without cloudflare tunnel
uv run pytest                   # Run all tests
uv run pytest tests/domain/     # Run domain tests only
uv run pytest -k "test_name"    # Run specific test
uv run ruff check .             # Lint
uv run ruff format .            # Format
uv build                        # Build package

# Frontend (in frontend/)
npm install                     # Install deps
npm run dev                     # Dev server with HMR (port 5173)
npm run build                   # Build to porterminal/static/
npm run watch                   # Build with watch mode
```

**Release:** `git tag v0.x.x -m "Release" && git push origin v0.x.x` (triggers CI publish)

## Architecture

Hexagonal architecture with clean layer separation:

- `porterminal/domain/` - Core business logic, ports (interfaces), no external deps
- `porterminal/application/` - Use cases (TerminalService, SessionService, TabService, ManagementService)
- `porterminal/infrastructure/` - Adapters (WebSocket, repositories, cloudflared)
- `porterminal/pty/` - Platform PTY implementations (windows.py, unix.py)
- `frontend/src/` - TypeScript/Vite app → builds to `porterminal/static/`

### Dual WebSocket Architecture

Two separate WebSocket connections:
- `/ws/management` - Control plane: tab create/close/rename, state sync, auth
- `/ws?tab_id=...&session_id=...` - Data plane: binary terminal I/O, resize

### Key Files

- `porterminal/composition.py` - Dependency injection wiring (composition root)
- `porterminal/container.py` - DI container with all services
- `porterminal/app.py` - FastAPI application factory
- `frontend/src/main.ts` - Frontend bootstrap and service wiring

## Key Constraints

- Cross-platform: Windows (pywinpty), Linux/macOS (pty module)
- Requires `cloudflared` CLI for tunnel functionality (auto-installed if missing)
- Sessions persist as long as PTY is alive (no timeout)
- Frontend must be rebuilt (`npm run build`) for changes to appear in packaged app
- Domain layer must have zero external dependencies
- Version is derived from git tags via hatch-vcs (no hardcoded version strings)

## Testing

Tests use pytest-asyncio with `asyncio_mode = "auto"`. Shared fixtures in `tests/conftest.py` include:
- `FakePTY`, `FakeClock` - Mock implementations for unit tests
- `MockConnection` - Mock WebSocket connection
- Domain fixtures: `session_id`, `user_id`, `default_dimensions`, etc.
