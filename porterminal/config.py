"""Configuration loading and validation using Pydantic."""

import shutil
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


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


def detect_available_shells() -> list[ShellConfig]:
    """Auto-detect available shells based on the platform."""
    shells = []

    if sys.platform == "win32":
        # Windows shells
        candidates = [
            ("PowerShell", "powershell", "powershell.exe", ["-NoLogo"]),
            ("PowerShell 7", "pwsh", "pwsh.exe", ["-NoLogo"]),
            ("CMD", "cmd", "cmd.exe", []),
            ("WSL", "wsl", "wsl.exe", []),
            ("Git Bash", "gitbash", r"C:\Program Files\Git\bin\bash.exe", ["--login"]),
        ]
    else:
        # Unix-like shells (Linux, macOS)
        candidates = [
            ("Bash", "bash", "bash", ["--login"]),
            ("Zsh", "zsh", "zsh", ["--login"]),
            ("Fish", "fish", "fish", []),
            ("Sh", "sh", "sh", []),
        ]

    for name, shell_id, command, args in candidates:
        # Check if shell exists
        shell_path = shutil.which(command)
        if shell_path or Path(command).exists():
            shells.append(
                ShellConfig(
                    name=name,
                    id=shell_id,
                    command=shell_path or command,
                    args=args,
                )
            )

    return shells


def get_default_shell_id() -> str:
    """Get the default shell ID for the current platform."""
    if sys.platform == "win32":
        # Prefer PowerShell 7, then PowerShell, then CMD
        if shutil.which("pwsh"):
            return "pwsh"
        if shutil.which("powershell"):
            return "powershell"
        return "cmd"
    elif sys.platform == "darwin":
        # macOS defaults to zsh
        if shutil.which("zsh"):
            return "zsh"
        return "bash"
    else:
        # Linux - prefer bash
        if shutil.which("bash"):
            return "bash"
        if shutil.which("zsh"):
            return "zsh"
        return "sh"


class TerminalConfig(BaseModel):
    """Terminal configuration."""

    default_shell: str = ""
    cols: int = Field(default=120, ge=40, le=500)
    rows: int = Field(default=30, ge=10, le=200)
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
    send: str


class CloudflareConfig(BaseModel):
    """Cloudflare Access configuration."""

    team_domain: str = ""
    access_aud: str = ""


class Config(BaseModel):
    """Application configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    buttons: list[ButtonConfig] = Field(default_factory=list)
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)


def load_config(config_path: Path | str = "config.yaml") -> Config:
    """Load configuration from YAML file."""
    config_path = Path(config_path)

    if not config_path.exists():
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

    # If no valid shells from config, auto-detect
    if not valid_shells:
        detected = detect_available_shells()
        terminal_data["shells"] = [s.model_dump() for s in detected]
    else:
        terminal_data["shells"] = valid_shells

    # Auto-detect default shell if not specified or invalid
    default_shell = terminal_data.get("default_shell", "")
    shell_ids = [s.get("id") or s.get("name", "").lower() for s in terminal_data.get("shells", [])]
    if not default_shell or default_shell not in shell_ids:
        terminal_data["default_shell"] = get_default_shell_id()
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
