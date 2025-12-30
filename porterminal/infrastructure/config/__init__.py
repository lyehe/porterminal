"""Configuration infrastructure - loading and detection."""

from .shell_detector import ShellDetector
from .yaml_loader import YAMLConfigLoader

__all__ = [
    "YAMLConfigLoader",
    "ShellDetector",
]
