"""
PTY management with cross-platform support.

This package provides:
- PTYBackend Protocol for platform-specific implementations
- SecurePTYManager for secure PTY management with env sanitization
- Platform-specific backends (Windows, Unix)
"""

import sys

from .env import BLOCKED_ENV_VARS, SAFE_ENV_VARS, build_safe_environment
from .manager import SecurePTYManager
from .protocol import PTYBackend

__all__ = [
    # Protocol
    "PTYBackend",
    # Manager
    "SecurePTYManager",
    # Backends
    "create_backend",
    # Environment
    "SAFE_ENV_VARS",
    "BLOCKED_ENV_VARS",
    "build_safe_environment",
]


def create_backend() -> PTYBackend:
    """Create platform-appropriate PTY backend.

    Returns:
        PTYBackend instance for the current platform.

    Raises:
        RuntimeError: If no suitable backend is available.
    """
    if sys.platform == "win32":
        from .windows import WindowsPTYBackend

        return WindowsPTYBackend()
    else:
        from .unix import UnixPTYBackend

        return UnixPTYBackend()
