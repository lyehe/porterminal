# Copilot Code Review Instructions

When reviewing code in this repository, please follow these guidelines:

## Project Context
- This is a web-based terminal (Porterminal) accessible via Cloudflare Quick Tunnel
- Cross-platform support required: Windows (pywinpty), Linux/macOS (pty module)
- Hexagonal architecture with clean layer separation

## Code Quality Checks
- Ensure no secrets or credentials are committed
- Check for proper error handling (specific exceptions, not bare `except`)
- Verify async/await patterns are used correctly
- Flag any blocking I/O in async contexts

## Security Focus
- Check for command injection vulnerabilities in terminal input handling
- Verify WebSocket message validation
- Ensure environment variable sanitization is applied
- Flag hardcoded paths or credentials

## Architecture Guidelines
- Domain layer (`porterminal/domain/`) should have no external dependencies
- Infrastructure concerns should not leak into domain/application layers
- New features should follow existing patterns in the codebase

## Python Standards
- Target Python 3.12+
- Use type hints for function signatures
- Follow ruff linting rules (E, F, I, UP)
- Max line length: 100 characters

## Frontend Standards
- TypeScript strict mode
- No `any` types without justification
- Prefer functional components and hooks patterns
