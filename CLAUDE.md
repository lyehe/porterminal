# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Porterminal is a web-based terminal accessible from mobile devices via Cloudflare Quick Tunnel. It provides a touch-friendly interface with virtual buttons for special keys and modifiers.

## Commands

**Install from PyPI:**
```bash
uv tool install ptn
# or
pip install ptn
```

**Run (after install):**
```bash
ptn
```

**Run without installing:**
```bash
uvx ptn
```

**Development:**
```bash
uv sync
uv run ptn
```

**Build for PyPI:**
```bash
uv build
uv publish
```

## Architecture

Hexagonal architecture with clear separation of concerns.

### Domain Layer (`porterminal/domain/`)
Core business logic with no external dependencies:
- `entities/` - Session, OutputBuffer
- `values/` - SessionId, UserId, TerminalDimensions, ShellCommand, RateLimitConfig
- `services/` - RateLimiter, EnvironmentSanitizer, SessionLimits
- `ports/` - PtyPort, SessionRepository (interfaces)

### Application Layer (`porterminal/application/`)
Use cases orchestrating domain logic:
- `services/terminal_service.py` - Terminal I/O, resize, heartbeat handling
- `services/session_service.py` - Session lifecycle management
- `ports/` - ConfigPort, ConnectionPort (interfaces)

### Infrastructure Layer (`porterminal/infrastructure/`)
External adapters and implementations:
- `web/websocket_adapter.py` - WebSocket message routing
- `repositories/in_memory_session.py` - Session storage implementation
- `config/yaml_loader.py` - Configuration loading
- `config/shell_detector.py` - Auto-detect available shells
- `cloudflared.py` - Cloudflare tunnel management
- `server.py` - Uvicorn server wrapper

### PTY Layer (`porterminal/pty/`)
- `windows.py` - Windows backend using pywinpty
- `unix.py` - Unix backend using pty module

### Entry Points
- `porterminal/__init__.py` - Main entry point
- `porterminal/app.py` - FastAPI app with WebSocket at `/ws`, serves static files
- `porterminal/cli/` - CLI argument parsing and display

### Frontend (`frontend/`)
TypeScript/Vite application built to `porterminal/static/`:
- `src/main.ts` - Application entry point
- `src/services/` - ConnectionService, TabService, ConfigService
- `src/input/` - KeyMapper, InputHandler, ModifierManager
- `src/gestures/` - GestureRecognizer, SwipeDetector, SelectionHandler
- `src/terminal/` - ResizeManager
- `src/ui/` - ConnectionStatus, CopyButton, DisconnectOverlay

### Data Flow
1. Client connects via WebSocket to `/ws?session_id=<id>&shell=<id>&skip_buffer=<bool>`
2. Server spawns PTY with sanitized environment
3. Binary data (terminal I/O) and JSON messages (resize, ping/pong, session_info) flow over WebSocket
4. Output batched: immediate flush for interactive data (<64 bytes), delayed for bulk output

### Configuration
`config.yaml` defines:
- Server host/port (default: 127.0.0.1:8000)
- Available shells (auto-detected, or manually configured)
- Custom buttons with send sequences
- Terminal dimensions (cols: 40-500, rows: 10-200)
- Cloudflare Access integration (team_domain, access_aud)

## Key Constraints
- Cross-platform: Windows (pywinpty), Linux/macOS (pty module)
- Requires `cloudflared` CLI for tunnel functionality (auto-installed if missing)
- Sessions persist as long as PTY is alive (no timeout)
