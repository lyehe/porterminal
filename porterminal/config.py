"""Configuration discovery, validation, and persistence.

``ConfigStore`` is the single file-system boundary for configuration.  The
compatibility functions at the bottom intentionally delegate to it so CLI,
ASGI, and runtime settings all follow the same search and validation rules.
"""

import copy
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, Field, field_validator

from porterminal.domain import ShellCommand
from porterminal.domain.values import MAX_COLS, MAX_ROWS, MIN_COLS, MIN_ROWS

RawConfig = dict[str, Any]


class ShellDetectorPort(Protocol):
    """Small configuration-facing contract for platform shell detection."""

    def detect_shells(self) -> list[ShellCommand]: ...

    def get_default_shell_id(self) -> str: ...


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
    password_hash: str = ""  # Saved bcrypt password hash (use -sp to set)
    max_auth_attempts: int = Field(default=5, ge=1, le=100)


class UIConfig(BaseModel):
    """UI configuration."""

    compose_mode: bool = False  # Enable compose mode by default


class Config(BaseModel):
    """Application configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    buttons: list[ButtonConfig] = Field(default_factory=list)
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    ui: UIConfig = Field(default_factory=UIConfig)


class ConfigStore:
    """Locate, validate, and atomically persist Porterminal configuration."""

    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        cwd: Path | None = None,
        default_path: Path | None = None,
        shell_detector: ShellDetectorPort | None = None,
    ) -> None:
        self._explicit_path = Path(config_path).expanduser() if config_path is not None else None
        self._cwd = cwd or Path.cwd()
        self._default_path = default_path or Path.home() / ".ptn" / "ptn.yaml"
        self._shell_detector = shell_detector

    def resolve_path(self) -> Path | None:
        """Return the configured or first existing path in search order."""
        if self._explicit_path is not None:
            return self._explicit_path

        if env_path := os.environ.get("PORTERMINAL_CONFIG_PATH"):
            return Path(env_path).expanduser()

        candidates = [
            self._cwd / "ptn.yaml",
            self._cwd / ".ptn" / "ptn.yaml",
            Path.home() / ".ptn" / "ptn.yaml",
        ]
        return next((path for path in candidates if path.exists()), None)

    def path_for_write(self) -> Path:
        """Return an existing config path or the caller's explicit fallback."""
        return self.resolve_path() or self._default_path

    def read_raw(self) -> RawConfig:
        """Read YAML as a mapping without discarding unknown fields."""
        path = self.resolve_path()
        if path is None or not path.exists():
            return {}

        with path.open(encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration root must be a mapping: {path}")
        return data

    def load(self) -> Config:
        """Load a validated runtime configuration with usable shells."""
        return self._validate(self.read_raw())

    def save_raw(self, data: RawConfig) -> None:
        """Validate known fields and atomically save while preserving extras."""
        self._validate(data)
        path = self.path_for_write()
        path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                yaml.safe_dump(
                    data,
                    temporary,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def update(self, mutation: Callable[[RawConfig], None]) -> RawConfig:
        """Apply and persist a validated mutation, returning a defensive copy."""
        data = copy.deepcopy(self.read_raw())
        mutation(data)
        self.save_raw(data)
        return copy.deepcopy(data)

    def _detector(self) -> ShellDetectorPort:
        if self._shell_detector is None:
            from porterminal.infrastructure.config.shell_detector import ShellDetector

            self._shell_detector = ShellDetector()
        return self._shell_detector

    def _validate(self, raw: RawConfig) -> Config:
        """Validate a normalized copy; never add detected shells to persisted YAML."""
        data = copy.deepcopy(raw)
        terminal_data = data.setdefault("terminal", {})
        if not isinstance(terminal_data, dict):
            return Config.model_validate(data)

        shells_data = terminal_data.get("shells", [])
        valid_shells: list[RawConfig] = []
        if isinstance(shells_data, list):
            for shell in shells_data:
                if not isinstance(shell, dict):
                    continue
                command = shell.get("command", "")
                if isinstance(command, str) and (shutil.which(command) or Path(command).exists()):
                    valid_shells.append(shell)

        detector = self._detector()
        if not valid_shells:
            valid_shells = [
                {
                    "id": shell.id,
                    "name": shell.name,
                    "command": shell.command,
                    "args": list(shell.args),
                }
                for shell in detector.detect_shells()
            ]
        terminal_data["shells"] = valid_shells

        shell_ids = [
            shell.get("id") or str(shell.get("name", "")).lower() for shell in valid_shells
        ]
        default_shell = terminal_data.get("default_shell", "")
        if not default_shell or default_shell not in shell_ids:
            detected_default = detector.get_default_shell_id()
            terminal_data["default_shell"] = (
                detected_default
                if detected_default in shell_ids
                else (str(valid_shells[0].get("id", "")) if valid_shells else "")
            )

        return Config.model_validate(data)


def find_config_file(cwd: Path | None = None) -> Path | None:
    """Find config file in standard locations.

    Search order:
    1. PORTERMINAL_CONFIG_PATH env var (if set)
    2. ptn.yaml in cwd
    3. .ptn/ptn.yaml in cwd
    4. ~/.ptn/ptn.yaml (user home directory)
    """
    return ConfigStore(cwd=cwd).resolve_path()


def load_config(config_path: Path | str | None = None) -> Config:
    """Load configuration from YAML file."""
    return ConfigStore(config_path=config_path).load()


# Global config instance (loaded on import)
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
