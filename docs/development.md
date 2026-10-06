# Development Guide

## Setup

```bash
git clone https://github.com/porterminal/porterminal
cd porterminal
uv sync --frozen
uv run --frozen ptn
```

Use `--frozen` for normal local setup and checks (`uv sync --frozen`,
`uv run --frozen pytest`, `uv run --frozen ruff check .`). The package version
is generated from Git tags by `hatch-vcs`, so bare `uv sync` or `uv run ...` may
rewrite only the editable project's version line in `uv.lock` when the current
commit changes.

## Frontend Development

The frontend is a TypeScript/Vite application in `frontend/`:

```bash
cd frontend
npm install
npm run dev    # Development server
npm run test:run       # Unit/service tests
npm run test:typecheck # Type-check test code
npm run test:browser   # Chromium smoke test
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

### PyPI Trusted Publisher

Configure the existing `ptn` project's publisher on its
[Publishing page](https://pypi.org/manage/project/ptn/settings/publishing/):

| GitHub setting | Value |
|----------------|-------|
| Owner | `porterminal` |
| Repository | `porterminal` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

After a repository transfer, add a publisher matching the new owner before
pushing a release tag, then remove the obsolete publisher. The PyPI package
remains `ptn`. Project links come from `[project.urls]` in `pyproject.toml` and
are published with the next release.

See [PyPI's Trusted Publisher setup](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

### Creating a Release

```bash
git tag vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Replace `X.Y.Z` with the release version. No manual version file needs editing.

### Automation Chain

1. **Tag push** triggers `.github/workflows/publish.yml`
2. The reusable verifier runs the backend matrix, Pyright, frontend tests,
   Chromium smoke test, packaged-asset check, and a fresh wheel installation
   that must boot successfully and answer its health check
3. The verified distributions publish to PyPI through trusted publishing (OIDC)
4. A GitHub Release is created with generated release notes after PyPI succeeds

### Workflows

| Workflow | Trigger | Action |
|----------|---------|--------|
| `verify.yml` | Called by other workflows | Reusable backend, frontend, and distribution verification |
| `ci.yml` | Push to master, PRs | Invoke the reusable verifier |
| `publish.yml` | Tag push (`v*`) | Verify, publish to PyPI, then create the GitHub Release |

## Manual Build Verification

For local testing or manual release:

```bash
uv build
python scripts/verify_distribution.py --python 3.12
```

Publishing is intentionally performed by the tagged workflow so it cannot
bypass the same checks used by CI.
