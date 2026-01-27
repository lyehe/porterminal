"""Configuration infrastructure - loading and detection."""

from .config_service import ConfigService
from .shell_detector import ShellDetector

__all__ = [
    "ConfigService",
    "ShellDetector",
]
