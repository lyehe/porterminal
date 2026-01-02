"""Auto-update checker for ptn."""

import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

# Check once per day
CHECK_INTERVAL = 86400
CONFIG_DIR = Path.home() / ".ptn"
CONFIG_FILE = CONFIG_DIR / "ptn.yaml"
CACHE_FILE = CONFIG_DIR / "update_check.json"
PYPI_URL = "https://pypi.org/pypi/ptn/json"

DEFAULT_GLOBAL_CONFIG = """\
# ptn global configuration (~/.ptn/ptn.yaml)
# This file is auto-generated on first run.

# Auto-update: check for new versions and update automatically (uvx only)
auto_update: true
"""


def _get_auto_update_setting() -> bool:
    """Get auto_update setting from global config. Creates config if missing."""
    # Create config on first run
    if not CONFIG_FILE.exists():
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(DEFAULT_GLOBAL_CONFIG)
        except Exception:
            pass
        return True  # Default to enabled

    # Read config
    try:
        import yaml

        data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
        return data.get("auto_update", True)
    except Exception:
        return True  # Default to enabled on error


def _get_current_version() -> str:
    """Get currently installed version."""
    try:
        from porterminal._version import __version__

        return __version__
    except ImportError:
        return "0.0.0"


def _get_latest_version() -> str | None:
    """Fetch latest version from PyPI."""
    try:
        req = urllib.request.Request(PYPI_URL, headers={"User-Agent": "ptn"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return data["info"]["version"]
    except Exception:
        return None


def _should_check() -> bool:
    """Check if enough time has passed since last check."""
    if not CACHE_FILE.exists():
        return True
    try:
        data = json.loads(CACHE_FILE.read_text())
        return time.time() - data.get("last_check", 0) > CHECK_INTERVAL
    except Exception:
        return True


def _save_check_time() -> None:
    """Save current time as last check."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({"last_check": time.time()}))
    except Exception:
        pass


def _compare_versions(current: str, latest: str) -> bool:
    """Return True if latest > current."""
    try:
        from packaging.version import Version

        return Version(latest) > Version(current)
    except Exception:
        # Fallback: simple string comparison
        return latest != current and latest > current


def _is_uvx() -> bool:
    """Check if running via uvx."""
    # uvx sets this, or we can check if uvx is available
    return shutil.which("uvx") is not None


def check_and_update() -> None:
    """Check for updates and auto-update if available.

    Call this at the very beginning of main(), before any other setup.
    If an update is found and auto_update is enabled, this function will
    not return - it replaces the current process with an updated version.

    Auto-update can be disabled in ~/.ptn/ptn.yaml:
        auto_update: false
    """
    # Check if auto-update is enabled (also creates config on first run)
    auto_update_enabled = _get_auto_update_setting()

    if not _should_check():
        return

    current = _get_current_version()
    latest = _get_latest_version()
    _save_check_time()

    if not latest:
        return

    if not _compare_versions(current, latest):
        return

    # Update available
    if not _is_uvx() or not auto_update_enabled:
        # Not using uvx or auto-update disabled, just notify
        print(f"\n📦 Update available: ptn {current} → {latest}")
        print("   Run: uvx --refresh ptn\n" if _is_uvx() else "   Run: pip install -U ptn\n")
        return

    # Auto-update via uvx
    print(f"🔄 Updating ptn {current} → {latest}...")

    # Build new command
    args = ["uvx", "--refresh", "ptn"] + sys.argv[1:]

    if sys.platform == "win32":
        # Windows: can't use execvp, use subprocess and exit
        import subprocess

        result = subprocess.call(args)
        sys.exit(result)
    else:
        # Unix: replace current process
        os.execvp("uvx", args)
