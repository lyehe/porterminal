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
        PORTERMINAL_CONFIG_PATH: Path to config file (default: config.yaml)
        PORTERMINAL_CWD: Working directory for PTY sessions
    """
    from porterminal.app import create_app

    config_path = os.environ.get("PORTERMINAL_CONFIG_PATH", "config.yaml")
    cwd = os.environ.get("PORTERMINAL_CWD")

    container = create_container(config_path=config_path, cwd=cwd)

    # Create app with container
    # Note: The current app.py doesn't accept container yet,
    # so we just create the default app and store container in state
    app = create_app()

    # Store container in app state for handlers to access
    app.state.container = container

    return app
