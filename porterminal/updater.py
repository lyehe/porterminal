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

PACKAGE_NAME = "ptn"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
CACHE_DIR = Path.home() / ".cache" / "porterminal"
CACHE_FILE = CACHE_DIR / "update_check.json"
CACHE_TTL = 86400  # 24 hours


def parse_version(version: str) -> tuple[int, ...]:
    """Parse version string into comparable tuple.

    Handles PEP 440 versions like "0.1.0", "1.0.0a1", "2.0.0.post1".

    Args:
        version: Version string.

    Returns:
        Tuple of integers for comparison (ignores pre/post/dev).
    """
    version = version.lstrip("v")
    # Extract just the release numbers (before any pre/post/dev markers)
    base = version.split("a")[0].split("b")[0].split("rc")[0]
    base = base.split(".dev")[0].split(".post")[0].split("+")[0]
    parts = []
    for p in base.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) if parts else (0,)


def get_latest_version() -> str | None:
    """Fetch the latest version from PyPI.

    Returns:
        Latest version string or None if fetch failed.
    """
    try:
        request = Request(PYPI_URL, headers={"User-Agent": f"{PACKAGE_NAME}/{__version__}"})
        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data["info"]["version"]
    except (URLError, json.JSONDecodeError, KeyError, TimeoutError):
        return None


def get_cached_version() -> str | None:
    """Get cached latest version if still valid.

    Returns:
        Cached version string or None if cache expired/missing.
    """
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
        if time.time() - data.get("timestamp", 0) < CACHE_TTL:
            return data.get("version")
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def cache_version(version: str) -> None:
    """Cache the latest version.

    Args:
        version: Version string to cache.
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(
                {
                    "version": version,
                    "timestamp": time.time(),
                }
            )
        )
    except OSError:
        pass  # Ignore cache write failures


def check_for_updates(use_cache: bool = True) -> tuple[bool, str | None]:
    """Check if a newer version is available.

    Args:
        use_cache: Whether to use cached version check.

    Returns:
        Tuple of (update_available, latest_version).
    """
    # Try cache first
    if use_cache:
        latest = get_cached_version()
        if latest:
            try:
                return parse_version(latest) > parse_version(__version__), latest
            except (ValueError, TypeError):
                pass

    # Fetch from PyPI
    latest = get_latest_version()
    if latest is None:
        return False, None

    # Cache the result
    cache_version(latest)

    try:
        return parse_version(latest) > parse_version(__version__), latest
    except (ValueError, TypeError):
        return False, latest


def detect_install_method() -> str:
    """Detect how porterminal was installed.

    Returns:
        One of: 'uv', 'pipx', 'pip'
    """
    executable = sys.executable
    file_path = str(Path(__file__).resolve())

    # Check for uv tool install
    uv_patterns = [
        "/.local/share/uv/tools/",
        "/uv/tools/",
        "\\uv\\tools\\",
    ]
    for pattern in uv_patterns:
        if pattern in executable or pattern in file_path:
            return "uv"

    # Check for pipx install
    pipx_patterns = [
        "/pipx/venvs/",
        "/.local/share/pipx/",
        "/.local/pipx/",
        "\\pipx\\venvs\\",
    ]
    for pattern in pipx_patterns:
        if pattern in executable or pattern in file_path:
            return "pipx"

    # Default to pip
    return "pip"


def get_upgrade_command() -> str:
    """Get the appropriate upgrade command for the installation method.

    Returns:
        Shell command string to upgrade porterminal.
    """
    method = detect_install_method()
    commands = {
        "uv": f"uv tool upgrade {PACKAGE_NAME}",
        "pipx": f"pipx upgrade {PACKAGE_NAME}",
        "pip": f"pip install --upgrade {PACKAGE_NAME}",
    }
    return commands.get(method, commands["pip"])


def update_package() -> bool:
    """Update porterminal to the latest version.

    Returns:
        True if update succeeded, False otherwise.
    """
    method = detect_install_method()

    # Check if update is available first
    has_update, latest = check_for_updates(use_cache=False)
    if not has_update:
        if latest:
            print(f"Already at latest version ({__version__})")
        else:
            print("Could not check for updates (network error)")
        return True

    print(f"Updating {PACKAGE_NAME} {__version__} → {latest}")

    try:
        if method == "uv":
            if not shutil.which("uv"):
                print("uv not found, falling back to pip")
                method = "pip"
            else:
                cmd = ["uv", "tool", "upgrade", PACKAGE_NAME]

        if method == "pipx":
            if not shutil.which("pipx"):
                print("pipx not found, falling back to pip")
                method = "pip"
            else:
                cmd = ["pipx", "upgrade", PACKAGE_NAME]

        if method == "pip":
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE_NAME]

        result = subprocess.run(cmd, timeout=120)

        if result.returncode == 0:
            print(f"Successfully updated to {latest}")
            print("Restart porterminal to use the new version")
            return True
        else:
            print(f"Update failed (exit code {result.returncode})")
            print(f"Try manually: {get_upgrade_command()}")
            return False

    except subprocess.TimeoutExpired:
        print("Update timed out")
        print(f"Try manually: {get_upgrade_command()}")
        return False
    except FileNotFoundError as e:
        print(f"Command not found: {e}")
        print(f"Try manually: {get_upgrade_command()}")
        return False


def print_update_notice(latest: str) -> None:
    """Print a styled update notice.

    Args:
        latest: Latest available version.
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console(stderr=True)
    upgrade_cmd = get_upgrade_command()

    console.print()
    console.print(
        Panel(
            f"[yellow]Update available:[/yellow] {__version__} → [green]{latest}[/green]\n"
            f"[dim]Run:[/dim] [cyan]{upgrade_cmd}[/cyan]",
            title="[bold]Porterminal[/bold]",
            border_style="yellow",
            padding=(0, 2),
        )
    )
