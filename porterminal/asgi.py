"""ASGI application factory for uvicorn.

This module provides a factory function that uvicorn can use to create
the FastAPI application with proper dependency injection.

Usage:
    uvicorn porterminal.asgi:create_app_from_env --factory
"""


def create_app_from_env():
    """Create FastAPI app from environment variables.

    This is called by uvicorn when using the --factory flag.
    Environment variables:
        PORTERMINAL_CONFIG_PATH: Path to config file (overrides search)
        PORTERMINAL_CWD: Working directory for PTY sessions
        PORTERMINAL_PASSWORD_HASH: Active password hash supplied by the CLI
        PORTERMINAL_COMPOSE_MODE: Optional compose-mode override

    Config search order (when env var not set):
        1. ptn.yaml in cwd
        2. .ptn/ptn.yaml in cwd
        3. ~/.ptn/ptn.yaml
    """
    from porterminal.app import create_app

    # The application lifespan performs environment-aware composition exactly
    # once. Tests and embedders can still inject a precomposed container through
    # porterminal.app.create_app(container).
    return create_app()
