"""Update functionality for Porterminal."""

import json
import shutil
import subprocess
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
    """Detect how ptn was installed: uv, pipx, or pip."""
    executable = sys.executable
    file_path = str(Path(__file__).resolve())

    uv_patterns = ["/uv/tools/", "\\uv\\tools\\"]
    if any(p in executable or p in file_path for p in uv_patterns):
        return "uv"

    pipx_patterns = ["/pipx/venvs/", "\\pipx\\venvs\\"]
    if any(p in executable or p in file_path for p in pipx_patterns):
        return "pipx"

    return "pip"


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
        "uv": f"uv tool upgrade {PACKAGE_NAME}",
        "pipx": f"pipx upgrade {PACKAGE_NAME}",
        "pip": f"pip install -U {PACKAGE_NAME}",
    }
    return commands.get(method, commands["pip"])


def update_package() -> bool:
    """Update ptn to the latest version.

    Returns:
        True if update succeeded, False otherwise.
    """
    has_update, latest = check_for_updates(use_cache=False)
    if not has_update:
        if latest:
            print(f"Already at latest version ({__version__})")
        else:
            print("Could not check for updates (network error)")
        return True

    print(f"Updating {PACKAGE_NAME} {__version__} -> {latest}")

    # Windows: can't upgrade while running (exe is locked)
    if sys.platform == "win32":
        print("On Windows, close ptn first then run from another terminal:")
        print(f"  {get_upgrade_command()}")
        return False

    method = _detect_install_method()

    # Build command
    if method == "uv" and shutil.which("uv"):
        cmd = ["uv", "tool", "upgrade", PACKAGE_NAME]
    elif method == "pipx" and shutil.which("pipx"):
        cmd = ["pipx", "upgrade", PACKAGE_NAME]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "-U", PACKAGE_NAME]

    try:
        result = subprocess.run(cmd, timeout=120)
        if result.returncode == 0:
            print(f"Updated to {latest}. Restart to use new version.")
            return True
        print(f"Update failed (exit code {result.returncode})")
        print(f"Try: {get_upgrade_command()}")
        return False
    except subprocess.TimeoutExpired:
        print("Update timed out")
        print(f"Try: {get_upgrade_command()}")
        return False
    except FileNotFoundError as e:
        print(f"Command not found: {e}")
        print(f"Try: {get_upgrade_command()}")
        return False


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
        print(f"Update available: {__version__} -> {latest}. Run: {get_upgrade_command()}")
