# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Porterminal is a web-based terminal accessible from mobile devices via Cloudflare Quick Tunnel. It provides a touch-friendly interface with virtual buttons for special keys and modifiers.

## Quick Reference

```bash
# Backend
uv sync                         # Install dependencies
uv run ptn                      # Run server (opens tunnel + QR code)
uv run ptn --no-tunnel          # Run without cloudflare tunnel
uv run pytest                   # Run all tests
uv run pytest tests/domain/     # Run domain tests only
uv run pytest -k "test_name"    # Run specific test
uv run ruff check .             # Lint
uv run ruff format .            # Format

# Frontend (in frontend/)
npm install                     # Install deps
npm run dev                     # Dev server with HMR (port 5173)
npm run build                   # TypeScript check + build to porterminal/static/
npm run watch                   # Build with watch mode
```

**CLI options:**
```bash
ptn                    # Start server with tunnel
ptn ~/projects/myapp   # Start in specific folder
ptn --no-tunnel        # Local network only
ptn -b                 # Run in background
ptn -p                 # Enable password for this session
ptn -dp                # Toggle default password requirement
ptn -v                 # Verbose startup logs
ptn --init             # Create .ptn/ptn.yaml config
ptn -U                 # Update to latest version
```

**Config:** Search order: `$PORTERMINAL_CONFIG_PATH` → `./ptn.yaml` → `./.ptn/ptn.yaml` → `~/.ptn/ptn.yaml`

**Release:** `git tag v0.x.x -m "Release" && git push origin v0.x.x` (triggers CI publish)

**Important:** After frontend changes, run `npm run build` in `frontend/` - the backend serves from `porterminal/static/`.

**Git:** Main branch is `master`. PRs should target `master`.

## Architecture

Hexagonal architecture with clean layer separation. See `docs/architecture.md` for full details.

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

### Frontend Patterns

Factory + DI architecture with event-driven communication. See `docs/frontend_features.md` for full details on gestures, modifiers, buffering, iOS workarounds, and UI patterns.

**Key patterns to know:**
- Three-state modifiers: `off` → `sticky` (single tap) → `locked` (double tap)
- Watermark-based flow control with early buffer (1MB) for connection handshake
- Touch/click deduplication via `touchUsed` flag
- Multi-frame connection handshake: fit → layout → flush → show

## Code Standards

**Python:**
- Target Python 3.12+, use type hints
- Follow ruff rules (E, F, I, UP), max line length 100
- No blocking I/O in async contexts
- Domain layer must have zero external dependencies

**TypeScript:**
- Strict mode, no `any` types without justification
- Follow existing factory + DI patterns

## Key Constraints

- Cross-platform: Windows (pywinpty), Linux/macOS (pty module)
- Requires `cloudflared` CLI for tunnel functionality (auto-installed if missing)
- Sessions persist as long as PTY is alive (no timeout)
- Frontend must be rebuilt (`npm run build`) for changes to appear in packaged app
- Version is derived from git tags via hatch-vcs (no hardcoded version strings)

## Testing

Tests use pytest-asyncio with `asyncio_mode = "auto"`. Shared fixtures in `tests/conftest.py`:
- `FakePTY`, `FakeClock` - Mock implementations for unit tests
- `MockConnection` - Mock WebSocket connection
- `fake_pty_factory` - Factory for creating fake PTYs with dependency injection
- Domain fixtures: `session_id`, `user_id`, `default_dimensions`, `sample_session`, `sample_tab`
- Repository fixtures: `session_repository`, `tab_repository`, `connection_registry`

## Security Considerations

When modifying terminal input handling or WebSocket code:
- Validate all WebSocket message fields before processing
- Environment sanitization blocks sensitive patterns (`*_KEY`, `*_SECRET`, `*_TOKEN`, `AWS_*`, etc.)
- Check for command injection vulnerabilities in any shell-related code
