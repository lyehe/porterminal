"""YAML configuration loader."""

from pathlib import Path
from typing import Any

import yaml


class YAMLConfigLoader:
    """Load configuration from YAML files."""

    def __init__(self, config_path: Path | str = "config.yaml") -> None:
        self._config_path = Path(config_path)

    def load(self) -> dict[str, Any]:
        """Load raw configuration data from YAML.

        Returns:
            Configuration dictionary, empty dict if file not found.
        """
        if not self._config_path.exists():
            return {}

        with open(self._config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def reload(self) -> dict[str, Any]:
        """Reload configuration from file."""
        return self.load()

    @property
    def path(self) -> Path:
        """Get configuration file path."""
        return self._config_path
