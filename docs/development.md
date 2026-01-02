# Development Guide

## Setup

```bash
git clone https://github.com/lyehe/porterminal
cd porterminal
uv sync
uv run ptn
```

## Frontend Development

The frontend is a TypeScript/Vite application in `frontend/`:

```bash
cd frontend
npm install
npm run dev    # Development server
npm run build  # Build to porterminal/static/
```

## Project Structure

```
porterminal/
├── domain/           # Core business logic (no dependencies)
│   ├── entities/     # Session, OutputBuffer
│   ├── values/       # Value objects
│   ├── services/     # RateLimiter, EnvironmentSanitizer
│   └── ports/        # Interfaces
├── application/      # Use cases
│   └── services/     # TerminalService, SessionService
├── infrastructure/   # External adapters
│   ├── web/          # WebSocket handling
│   ├── repositories/ # Session storage
│   └── config/       # YAML loading, shell detection
├── pty/              # Platform-specific PTY
│   ├── windows.py    # pywinpty backend
│   └── unix.py       # pty module backend
└── static/           # Built frontend assets

frontend/
├── src/
│   ├── services/     # ConnectionService, TabService
│   ├── input/        # KeyMapper, InputHandler
│   ├── gestures/     # Touch handling
│   └── ui/           # UI components
└── index.html
```

## Release Process

Versioning uses `hatch-vcs` - version is derived from git tags (single source of truth).

### Creating a Release

```bash
git tag v0.1.9 -m "Release v0.1.9"
git push origin v0.1.9
```

That's it. No manual steps required.

### Automation Chain

1. **Tag push** triggers `.github/workflows/release.yml`
2. **GitHub Release** is auto-created with generated release notes
3. **Release event** triggers `.github/workflows/publish.yml`
4. **PyPI publish** via trusted publishing (OIDC) - no tokens needed

### Workflows

| Workflow | Trigger | Action |
|----------|---------|--------|
| `ci.yml` | Push to master, PRs | Build & test on all platforms |
| `release.yml` | Tag push (`v*`) | Create GitHub Release |
| `publish.yml` | Release published | Build & publish to PyPI |

## Manual Build & Publish

For local testing or manual release:

```bash
uv build              # Creates dist/
uv publish            # Publishes to PyPI (requires credentials)
```
