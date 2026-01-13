"""Environment variable sanitization for PTY processes.

This module re-exports the environment rules from the domain layer
and provides the build_safe_environment() function for PTY spawning.
"""

import os

from porterminal.domain.values.environment_rules import (
    DEFAULT_BLOCKED_VARS as BLOCKED_ENV_VARS,
)
from porterminal.domain.values.environment_rules import (
    DEFAULT_SAFE_VARS as SAFE_ENV_VARS,
)

# Re-export for backward compatibility
__all__ = ["SAFE_ENV_VARS", "BLOCKED_ENV_VARS", "build_safe_environment"]


def build_safe_environment() -> dict[str, str]:
    """Build a sanitized environment for the PTY.

    Uses allowlist approach - only SAFE_ENV_VARS are copied,
    so BLOCKED_ENV_VARS can never be included.

    Returns:
        Dictionary of safe environment variables.
    """
    safe_env = {var: os.environ[var] for var in SAFE_ENV_VARS if var in os.environ}

    # Set custom variables for audit trail
    safe_env["TERM"] = "xterm-256color"
    safe_env["TERM_SESSION_TYPE"] = "remote-web"

    return safe_env
