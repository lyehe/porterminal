"""Environment variable sanitization for PTY processes."""

import os

# Environment variables to allowlist (safe to pass to shell)
SAFE_ENV_VARS: frozenset[str] = frozenset(
    {
        # System paths
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "COMSPEC",
        # User directories
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "APPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "COMMONPROGRAMFILES",
        # System info
        "COMPUTERNAME",
        "USERNAME",
        "USERDOMAIN",
        "OS",
        "PROCESSOR_ARCHITECTURE",
        "NUMBER_OF_PROCESSORS",
        # Terminal
        "TERM",
        # Locale settings for proper text rendering
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
    }
)

# Environment variables to explicitly block (secrets)
BLOCKED_ENV_VARS: frozenset[str] = frozenset(
    {
        # AWS
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        # Azure
        "AZURE_CLIENT_SECRET",
        "AZURE_CLIENT_ID",
        # Git/GitHub/GitLab
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        # Package managers
        "NPM_TOKEN",
        # AI APIs
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        # Payment
        "STRIPE_SECRET_KEY",
        # Database
        "DATABASE_URL",
        "DB_PASSWORD",
        # Generic secrets
        "SECRET_KEY",
        "API_KEY",
        "API_SECRET",
        "PRIVATE_KEY",
    }
)


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
