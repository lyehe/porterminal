"""Config service for runtime settings persistence."""

import asyncio
import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _find_config_file() -> Path | None:
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

    base = Path.cwd()

    # Search order: cwd first, then home
    candidates = [
        base / "ptn.yaml",
        base / ".ptn" / "ptn.yaml",
        Path.home() / ".ptn" / "ptn.yaml",
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


class ConfigService:
    """Service for reading and updating persistent config settings.

    Handles file locking for safe concurrent access and provides
    async methods for settings management.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    def _get_config_path(self) -> Path:
        """Get or create config file path.

        If no config file exists, creates one at ~/.ptn/ptn.yaml
        """
        path = _find_config_file()
        if path is not None:
            return path

        # Create default config location
        default_path = Path.home() / ".ptn" / "ptn.yaml"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        if not default_path.exists():
            default_path.write_text("# Porterminal configuration\n", encoding="utf-8")
        return default_path

    def _load_config(self, path: Path) -> dict:
        """Load config from file."""
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Failed to load config from %s: %s", path, e)
            return {}

    def _save_config(self, path: Path, data: dict) -> None:
        """Save config to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)

    def _extract_settings(self, data: dict) -> dict:
        """Extract settings dict from raw config data."""
        return {
            "compose_mode": data.get("ui", {}).get("compose_mode", False),
            "notify_on_startup": data.get("update", {}).get("notify_on_startup", True),
            "password_protected": bool(data.get("security", {}).get("password_hash")),
        }

    async def get_settings(self) -> dict:
        """Get current settings from config file.

        Returns a dict with:
        - compose_mode: bool (from ui.compose_mode)
        - notify_on_startup: bool (from update.notify_on_startup)
        - password_protected: bool (from security.password_hash being set)
        """
        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)
            return self._extract_settings(data)

    async def update_settings(self, updates: dict) -> tuple[dict, bool]:
        """Update settings in config file.

        Args:
            updates: Dict with keys to update. Supported keys:
                - compose_mode: bool
                - notify_on_startup: bool

        Returns:
            Tuple of (new_settings, requires_restart) where:
            - new_settings: The updated settings dict
            - requires_restart: Always False (no settings currently require restart)

        Note: password_protected cannot be updated via this method.
        Use `ptn -tp` CLI command to change password.
        """
        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)

            # Update UI settings
            if "compose_mode" in updates:
                data.setdefault("ui", {})["compose_mode"] = bool(updates["compose_mode"])

            # Update notification settings
            if "notify_on_startup" in updates:
                data.setdefault("update", {})["notify_on_startup"] = bool(
                    updates["notify_on_startup"]
                )

            self._save_config(path, data)
            logger.info("Config updated: %s", updates)

            return self._extract_settings(data), False

    async def get_buttons(self) -> list[dict]:
        """Get current button configuration."""
        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)
            return data.get("buttons", [])

    async def add_button(self, label: str, send: str, row: int = 1) -> list[dict]:
        """Add a new button. Returns updated buttons list.

        Raises ValueError if label empty, duplicate, or invalid row.
        """
        if not label or not label.strip():
            raise ValueError("Label cannot be empty")
        label = label.strip()
        if not (1 <= row <= 10):
            raise ValueError("Row must be between 1 and 10")

        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)
            buttons = data.get("buttons", [])

            # Check duplicate (case-insensitive)
            if any(b.get("label", "").lower() == label.lower() for b in buttons):
                raise ValueError(f"Button '{label}' already exists")

            buttons.append({"label": label, "send": send, "row": row})
            data["buttons"] = buttons
            self._save_config(path, data)
            logger.info("Button added: %s", label)
            return buttons

    async def remove_button(self, label: str) -> list[dict]:
        """Remove a button by label. Returns updated buttons list.

        Raises ValueError if not found.
        """
        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)
            buttons = data.get("buttons", [])

            new_buttons = [b for b in buttons if b.get("label", "").lower() != label.lower()]
            if len(new_buttons) == len(buttons):
                raise ValueError(f"Button '{label}' not found")

            data["buttons"] = new_buttons
            self._save_config(path, data)
            logger.info("Button removed: %s", label)
            return new_buttons

    async def set_password(self, password: str) -> dict:
        """Set or change the password.

        Args:
            password: The new password to set.

        Returns:
            Updated settings dict.

        Note: Server restart required for password to take effect.
        """
        import bcrypt

        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)

            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            data.setdefault("security", {})["password_hash"] = password_hash
            data["security"]["require_password"] = True

            self._save_config(path, data)
            logger.info("Password set in config")
            return self._extract_settings(data)

    async def clear_password(self) -> dict:
        """Clear the password and disable password requirement.

        Returns:
            Updated settings dict.

        Note: Server restart required for change to take effect.
        """
        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)

            data.setdefault("security", {})["password_hash"] = ""
            data["security"]["require_password"] = False

            self._save_config(path, data)
            logger.info("Password cleared from config")
            return self._extract_settings(data)

    async def set_require_password(self, require: bool) -> dict:
        """Set whether password is required at startup.

        Args:
            require: True to require password, False to disable.

        Returns:
            Updated settings dict.

        Note: If require=True but no password is saved, user will be
        prompted at startup. Server restart required for change to take effect.
        """
        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)

            data.setdefault("security", {})["require_password"] = require

            self._save_config(path, data)
            logger.info("Password requirement set to: %s", require)
            return self._extract_settings(data)

    async def get_password_status(self) -> dict:
        """Get detailed password status.

        Returns:
            Dict with:
            - password_saved: bool - Whether a password hash is saved in config
            - require_password: bool - Whether password is required at startup
            - currently_protected: bool - Whether current session has password protection
        """
        async with self._lock:
            path = self._get_config_path()
            data = self._load_config(path)

            security = data.get("security", {})
            return {
                "password_saved": bool(security.get("password_hash")),
                "require_password": security.get("require_password", False),
            }
