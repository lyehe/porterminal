"""ASGI application factory for uvicorn.

This module provides a factory function that uvicorn can use to create
the FastAPI application with proper dependency injection.

Usage:
    uvicorn porterminal.asgi:create_app_from_env --factory
"""

import os

from porterminal.composition import create_container


def create_app_from_env():
    """Create FastAPI app from environment variables.

    This is called by uvicorn when using the --factory flag.
    Environment variables:
        PORTERMINAL_CONFIG_PATH: Path to config file (overrides search)
        PORTERMINAL_CWD: Working directory for PTY sessions

    Config search order (when env var not set):
        1. ptn.yaml in cwd
        2. .ptn/ptn.yaml in cwd
        3. ~/.ptn/ptn.yaml
    """
    from porterminal.app import create_app

    cwd = os.environ.get("PORTERMINAL_CWD")

    # config_path=None uses find_config_file() to search standard locations
    container = create_container(config_path=None, cwd=cwd)

    # Create app with container
    # Note: The current app.py doesn't accept container yet,
    # so we just create the default app and store container in state
    app = create_app()

    # Store container in app state for handlers to access
    app.state.container = container

    return app
