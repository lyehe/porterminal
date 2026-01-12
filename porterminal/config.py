"""Configuration loading and validation using Pydantic."""

import os
import shutil
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from porterminal.domain.values import MAX_COLS, MAX_ROWS, MIN_COLS, MIN_ROWS
from porterminal.infrastructure.config import ShellDetector


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class ShellConfig(BaseModel):
    """Shell configuration."""

    name: str
    id: str
    command: str
    args: list[str] = Field(default_factory=list)

    @field_validator("command")
    @classmethod
    def validate_command_exists(cls, v: str) -> str:
        """Validate shell executable exists."""
        # Check if it's a full path
        path = Path(v)
        if path.exists():
            return v
        # Check if it's in PATH
        if shutil.which(v):
            return v
        raise ValueError(f"Shell executable not found: {v}")


class TerminalConfig(BaseModel):
    """Terminal configuration."""

    default_shell: str = ""
    cols: int = Field(default=120, ge=MIN_COLS, le=MAX_COLS)
    rows: int = Field(default=30, ge=MIN_ROWS, le=MAX_ROWS)
    shells: list[ShellConfig] = Field(default_factory=list)

    def get_shell(self, shell_id: str) -> ShellConfig | None:
        """Get shell config by ID."""
        for shell in self.shells:
            if shell.id == shell_id:
                return shell
        return None


class ButtonConfig(BaseModel):
    """Custom button configuration."""

    label: str
    send: str | list[str | int] = ""  # string or list of strings/ints (ints = wait ms)
    row: int = Field(default=1, ge=1, le=10)  # toolbar row (1-10)


class CloudflareConfig(BaseModel):
    """Cloudflare Access configuration."""

    team_domain: str = ""
    access_aud: str = ""


class UpdateConfig(BaseModel):
    """Update checker configuration."""

    notify_on_startup: bool = True  # Show "update available" on startup
    check_interval: int = Field(default=86400, ge=0)  # Seconds between checks (0 = always)


class SecurityConfig(BaseModel):
    """Security configuration."""

    require_password: bool = False  # Prompt for password at startup
    max_auth_attempts: int = Field(default=5, ge=1, le=100)


class Config(BaseModel):
    """Application configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    buttons: list[ButtonConfig] = Field(default_factory=list)
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)


def find_config_file(cwd: Path | None = None) -> Path | None:
    """Find config file in standard locations.

    Search order:
    1. PORTERMINAL_CONFIG_PATH env var (if set)
    2. ptn.yaml in cwd
    3. .ptn/ptn.yaml in cwd
    4. ~/.ptn/ptn.yaml (user home directory)
    """
    # Check env var first
    if env_path := os.environ.get("PORTERMINAL_CONFIG_PATH"):
        return Path(env_path)

    base = cwd or Path.cwd()

    # Search order: cwd first, then home
    candidates = [
        base / "ptn.yaml",
        base / ".ptn" / "ptn.yaml",
        Path.home() / ".ptn" / "ptn.yaml",
    ]

    for path in candidates:
        if path.exists():
            return path

    return None  # No config found, use defaults


def load_config(config_path: Path | str | None = None) -> Config:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = find_config_file()

    detector = ShellDetector()

    if config_path is None or not Path(config_path).exists():
        data = {}
    else:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Auto-detect shells if not specified or empty
    terminal_data = data.get("terminal", {})
    shells_data = terminal_data.get("shells", [])

    # Filter out shells that don't exist on this system
    valid_shells = []
    for shell in shells_data:
        try:
            # Validate the shell exists
            cmd = shell.get("command", "")
            if shutil.which(cmd) or Path(cmd).exists():
                valid_shells.append(shell)
        except Exception:
            pass

    # If no valid shells from config, auto-detect using ShellDetector
    if not valid_shells:
        detected = detector.detect_shells()
        terminal_data["shells"] = [
            {"id": s.id, "name": s.name, "command": s.command, "args": list(s.args)}
            for s in detected
        ]
    else:
        terminal_data["shells"] = valid_shells

    # Auto-detect default shell if not specified or invalid
    default_shell = terminal_data.get("default_shell", "")
    shell_ids = [s.get("id") or s.get("name", "").lower() for s in terminal_data.get("shells", [])]
    if not default_shell or default_shell not in shell_ids:
        terminal_data["default_shell"] = detector.get_default_shell_id()
        # Make sure the default shell is in the list
        if terminal_data["default_shell"] not in shell_ids and terminal_data.get("shells"):
            terminal_data["default_shell"] = terminal_data["shells"][0].get("id", "")

    data["terminal"] = terminal_data

    return Config.model_validate(data)


# Global config instance (loaded on import)
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
