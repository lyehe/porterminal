"""Update functionality for Porterminal."""

import json
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from porterminal import __version__

# Constants
PACKAGE_NAME = "ptn"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
CACHE_DIR = Path.home() / ".ptn"
CACHE_FILE = CACHE_DIR / "update_check.json"


def _detect_install_method() -> str:
    """Detect how ptn was installed: uvx, uv, pipx, or pip."""
    # Normalize paths to forward slashes for consistent matching
    executable = sys.executable.replace("\\", "/")
    file_path = str(Path(__file__).resolve()).replace("\\", "/")
    paths = executable + file_path

    # Check patterns in order of specificity
    if "/uv/cache/" in paths or "/.cache/uv/" in paths:
        return "uvx"
    if "/uv/tools/" in paths or "/uv/" in paths:
        return "uv"
    if "/pipx/venvs/" in paths:
        return "pipx"
    if "/site-packages/" in file_path:
        return "pip"
    return "uvx"


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse version string to comparable tuple."""
    v = v.lstrip("v").split("+")[0].split(".dev")[0]
    return tuple(int(p) for p in v.split(".")[:3] if p.isdigit())


def _is_newer(latest: str, current: str) -> bool:
    """Return True if latest > current."""
    try:
        from packaging.version import Version

        return Version(latest) > Version(current)
    except Exception:
        # Fallback: tuple comparison (handles 0.9 vs 0.10 correctly)
        try:
            return _parse_version(latest) > _parse_version(current)
        except ValueError:
            return False


def _get_check_interval() -> int:
    """Get check interval from config."""
    try:
        from porterminal.config import get_config

        return get_config().update.check_interval
    except Exception:
        return 86400  # Default 24h


def _should_check() -> bool:
    """Check if enough time passed since last check."""
    if not CACHE_FILE.exists():
        return True
    try:
        data = json.loads(CACHE_FILE.read_text())
        return time.time() - data.get("timestamp", 0) > _get_check_interval()
    except (OSError, json.JSONDecodeError, KeyError):
        return True


def _save_cache(version: str) -> None:
    """Save check result to cache."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({"version": version, "timestamp": time.time()}))
    except OSError:
        pass


def get_latest_version(use_cache: bool = True) -> str | None:
    """Fetch latest version from PyPI.

    Args:
        use_cache: Use cached result if valid.

    Returns:
        Latest version string or None if fetch failed.
    """
    # Try cache first
    if use_cache and CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text())
            if time.time() - data.get("timestamp", 0) < _get_check_interval():
                return data.get("version")
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    # Fetch from PyPI
    try:
        request = Request(PYPI_URL, headers={"User-Agent": f"{PACKAGE_NAME}/{__version__}"})
        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode())
            version = data["info"]["version"]
            _save_cache(version)
            return version
    except (URLError, json.JSONDecodeError, KeyError, TimeoutError, OSError):
        return None


def check_for_updates(use_cache: bool = True) -> tuple[bool, str | None]:
    """Check if a newer version is available.

    Args:
        use_cache: Use cached version check.

    Returns:
        Tuple of (update_available, latest_version).
    """
    latest = get_latest_version(use_cache=use_cache)
    if latest is None:
        return False, None
    return _is_newer(latest, __version__), latest


def get_upgrade_command() -> str:
    """Get appropriate upgrade command for the installation method."""
    method = _detect_install_method()
    commands = {
        "uvx": f"uvx --refresh {PACKAGE_NAME}",
        "uv": f"uv tool upgrade {PACKAGE_NAME}",
        "pipx": f"pipx upgrade {PACKAGE_NAME}",
        "pip": f"pip install -U {PACKAGE_NAME}",
    }
    return commands[method]


def check_and_notify() -> None:
    """Check for updates and print notification if available.

    Call at startup. Non-blocking, respects config settings, never exec's.
    """
    # Check if notifications are enabled
    try:
        from porterminal.config import get_config

        if not get_config().update.notify_on_startup:
            return
    except Exception:
        pass  # Default to enabled if config fails

    if not _should_check():
        return

    has_update, latest = check_for_updates(use_cache=False)
    if has_update and latest:
        from rich.console import Console

        console = Console()
        console.print(
            f"[yellow]Update available:[/yellow] {__version__} → [green]{latest}[/green]  "
            f"[dim]Run:[/dim] [cyan]{get_upgrade_command()}[/cyan]"
        )
