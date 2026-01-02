# Contributing to Porterminal

## Development Workflow

1. Create feature branch from `dev`:
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/your-feature
   ```

2. Make changes and test locally:
   ```bash
   uv run pytest
   uv run ruff check . && uv run ruff format .
   cd frontend && npm run build
   ```

3. Push and create PR to `master`:
   ```bash
   git push -u origin feature/your-feature
   # Open PR on GitHub: feature/your-feature -> master
   ```

4. After PR approval and merge, delete feature branch

## Release Process

1. Ensure `master` has all changes for release
2. Tag and push:
   ```bash
   git tag v0.x.x -m "Release v0.x.x"
   git push origin v0.x.x
   ```
3. CI automatically publishes to PyPI and creates GitHub Release

## Code Quality

Before submitting a PR, ensure:

- **Linting**: `uv run ruff check .`
- **Formatting**: `uv run ruff format .`
- **Tests**: `uv run pytest`
- **Frontend**: `cd frontend && npm run build`

## Branch Protection

The `master` branch requires:
- Pull request with at least 1 approval
- All CI checks to pass (lint, tests, frontend build)
- Branch to be up-to-date before merging
