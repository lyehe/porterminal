"""Environment sanitization rules value object."""

from dataclasses import dataclass, field

# These are the business rules for environment sanitization
# Extracted from pty/env.py - pure data, no I/O

DEFAULT_SAFE_VARS: frozenset[str] = frozenset(
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
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "COMMONPROGRAMFILES",
        # System info
        "COMPUTERNAME",
        "USERNAME",
        "USER",
        "LOGNAME",
        "USERDOMAIN",
        "OS",
        "PROCESSOR_ARCHITECTURE",
        "NUMBER_OF_PROCESSORS",
        # Terminal
        "TERM",
        "COLORTERM",
        "TERM_PROGRAM",
        # Locale
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        # Shell-specific
        "SHELL",
        "SHLVL",
        "PWD",
        "OLDPWD",
        # Editor
        "EDITOR",
        "VISUAL",
        # Display (for X11 forwarding if needed)
        "DISPLAY",
        # SSH (non-sensitive)
        "SSH_TTY",
        "SSH_CONNECTION",
        # XDG directories
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_RUNTIME_DIR",
        # Python
        "PYTHONPATH",
        "VIRTUAL_ENV",
        # Node
        "NODE_PATH",
        # Go
        "GOPATH",
        # Rust
        "CARGO_HOME",
        "RUSTUP_HOME",
    }
)

DEFAULT_BLOCKED_VARS: frozenset[str] = frozenset(
    {
        # AWS
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        # Azure
        "AZURE_CLIENT_SECRET",
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        # GCP
        "GOOGLE_APPLICATION_CREDENTIALS",
        "CLOUDSDK_AUTH_ACCESS_TOKEN",
        # Git/GitHub/GitLab
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        "GIT_ASKPASS",
        "GIT_CREDENTIALS",
        # Package managers
        "NPM_TOKEN",
        "PYPI_TOKEN",
        "RUBYGEMS_API_KEY",
        # AI APIs
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "COHERE_API_KEY",
        # Payment
        "STRIPE_SECRET_KEY",
        "STRIPE_API_KEY",
        # Database
        "DATABASE_URL",
        "DB_PASSWORD",
        "MYSQL_PASSWORD",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "MONGODB_URI",
        # Generic secrets
        "SECRET_KEY",
        "API_KEY",
        "API_SECRET",
        "PRIVATE_KEY",
        "ACCESS_TOKEN",
        "REFRESH_TOKEN",
        "AUTH_TOKEN",
        "JWT_SECRET",
        "ENCRYPTION_KEY",
        # SSH keys (if exposed via env)
        "SSH_PRIVATE_KEY",
        "SSH_KEY",
        # Misc services
        "SLACK_TOKEN",
        "DISCORD_TOKEN",
        "TELEGRAM_TOKEN",
        "TWILIO_AUTH_TOKEN",
        "SENDGRID_API_KEY",
        "MAILGUN_API_KEY",
    }
)


@dataclass(frozen=True)
class EnvironmentRules:
    """Rules for environment variable sanitization."""

    allowed_vars: frozenset[str] = field(default_factory=lambda: DEFAULT_SAFE_VARS)
    blocked_vars: frozenset[str] = field(default_factory=lambda: DEFAULT_BLOCKED_VARS)
    forced_vars: tuple[tuple[str, str], ...] = (
        ("TERM", "xterm-256color"),
        ("TERM_SESSION_TYPE", "remote-web"),
    )

    def __post_init__(self) -> None:
        # Ensure blocked vars are not in allowed vars
        overlap = self.allowed_vars & self.blocked_vars
        if overlap:
            raise ValueError(f"Vars cannot be both allowed and blocked: {overlap}")

    def get_forced_vars_dict(self) -> dict[str, str]:
        """Get forced variables as a dictionary."""
        return dict(self.forced_vars)
