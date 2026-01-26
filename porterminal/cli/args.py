"""Command line argument parsing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from porterminal import __version__


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace with:
        - path: Starting directory for the shell (optional)
        - no_tunnel: Whether to skip Cloudflare tunnel
        - verbose: Whether to show detailed logs
        - update: Whether to update to latest version
        - check_update: Whether to check for updates
    """
    parser = argparse.ArgumentParser(
        description="Porterminal - Web terminal via Cloudflare Tunnel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Starting directory for the shell (default: current directory)",
    )
    parser.add_argument(
        "-n",
        "--no-tunnel",
        action="store_true",
        help="Start server only, without Cloudflare tunnel",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed startup logs",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="Update to the latest version",
    )
    parser.add_argument(
        "-c",
        "--check-update",
        action="store_true",
        help="Check if a newer version is available",
    )
    parser.add_argument(
        "-b",
        "--background",
        action="store_true",
        help="Run in background and return immediately",
    )
    parser.add_argument(
        "-i",
        "--init",
        nargs="?",
        const=True,
        default=False,
        metavar="URL_OR_PATH",
        help="Create .ptn/ptn.yaml config (optionally from URL or file path)",
    )
    parser.add_argument(
        "-p",
        "--password",
        action="store_true",
        help="Prompt for password to protect terminal access",
    )
    parser.add_argument(
        "-tp",
        "--toggle-password",
        nargs="?",
        const="toggle",
        default=None,
        metavar="on|off",
        help="Set password requirement (on/off/true/false) or toggle if no value",
    )
    parser.add_argument(
        "-sp",
        "--save-password",
        action="store_true",
        help="Save or clear password in config (enter empty to clear)",
    )
    parser.add_argument(
        "-C",
        "--compose",
        action="store_true",
        help="Enable compose mode by default (text input before sending)",
    )
    # Internal argument for background mode communication
    parser.add_argument(
        "--_url-file",
        dest="url_file",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    # Handle update commands early (before main app starts)
    if args.check_update:
        from porterminal.updater import check_for_updates, get_upgrade_command

        has_update, latest = check_for_updates(use_cache=False)
        if has_update:
            print(f"Update available: {__version__} → {latest}")
            print(f"Run: {get_upgrade_command()}")
        else:
            print(f"Already at latest version ({__version__})")
        sys.exit(0)

    if args.update:
        from porterminal.updater import update_package

        success = update_package()
        sys.exit(0 if success else 1)

    if args.init:
        _init_config(args.init if args.init is not True else None)
        # Continue to launch ptn after creating config

    if args.toggle_password is not None:
        _toggle_password_requirement(args.toggle_password)
        sys.exit(0)

    if args.save_password:
        _save_password_to_config()
        sys.exit(0)

    return args


def _init_config(source: str | None = None) -> None:
    """Create .ptn/ptn.yaml in current directory.

    Args:
        source: Optional URL or file path to use as config source.
                If None, auto-discovers scripts and creates default config.
    """
    from urllib.error import URLError
    from urllib.request import urlopen

    import yaml

    from porterminal.cli.script_discovery import discover_scripts

    cwd = Path.cwd()
    config_dir = cwd / ".ptn"
    config_file = config_dir / "ptn.yaml"

    # If source is provided, fetch/copy it
    if source:
        config_dir.mkdir(exist_ok=True)

        if source.startswith(("http://", "https://")):
            # Download from URL
            try:
                print(f"Downloading config from {source}...")
                with urlopen(source, timeout=10) as response:
                    content = response.read().decode("utf-8")
                config_file.write_text(content)
                print(f"Created: {config_file}")
            except (URLError, OSError, TimeoutError) as e:
                print(f"Error downloading config: {e}")
                return
        else:
            # Copy from local file
            source_path = Path(source).expanduser().resolve()
            if not source_path.exists():
                print(f"Error: File not found: {source_path}")
                return
            try:
                content = source_path.read_text(encoding="utf-8")
                config_file.write_text(content)
                print(f"Created: {config_file} (from {source_path})")
            except OSError as e:
                print(f"Error reading config: {e}")
                return
        return

    # No source - use auto-discovery
    if config_file.exists():
        print(f"Config already exists: {config_file}")
        return

    # Build config with default buttons (row 1: AI coding tools)
    config: dict = {
        "buttons": [
            {"label": "new", "send": ["/new", 100, "\r"]},
            {"label": "init", "send": ["/init", 100, "\r"]},
            {"label": "resume", "send": ["/resume", 100, "\r"]},
            {"label": "compact", "send": ["/compact", 100, "\r"]},
            {"label": "claude", "send": ["claude", 100, "\r"]},
            {"label": "codex", "send": ["codex", 100, "\r"]},
        ]
    }

    # Auto-discover project scripts and add to row 2
    discovered = discover_scripts(cwd)
    if discovered:
        config["buttons"].extend(discovered)

    config_dir.mkdir(exist_ok=True)

    # Write YAML with comment header
    header = "# ptn configuration file\n# Docs: https://github.com/lyehe/porterminal\n\n"
    yaml_content = yaml.safe_dump(config, default_flow_style=False, sort_keys=False)
    config_file.write_text(header + yaml_content)

    print(f"Created: {config_file}")
    if discovered:
        print(
            f"Discovered {len(discovered)} project script(s): {', '.join(b['label'] for b in discovered)}"
        )


def _get_or_create_config() -> tuple[Path, dict]:
    """Get config path and data, creating directory if needed.

    Returns:
        Tuple of (config_path, config_data).
    """
    import yaml

    from porterminal.config import find_config_file

    config_path = find_config_file()
    if config_path is None:
        config_dir = Path.cwd() / ".ptn"
        config_path = config_dir / "ptn.yaml"
        config_dir.mkdir(exist_ok=True)

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    return config_path, data


def _save_config(config_path: Path, data: dict) -> None:
    """Save config data to file."""
    import yaml

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def _toggle_password_requirement(value: str) -> None:
    """Set or toggle security.require_password in config file.

    Args:
        value: "on", "off", "true", "false", or "toggle"
    """
    value_lower = value.lower()
    if value_lower in ("on", "true", "1"):
        new_value = True
    elif value_lower in ("off", "false", "0"):
        new_value = False
    elif value_lower == "toggle":
        new_value = None
    else:
        print(f"Error: Invalid value '{value}'. Use on/off/true/false")
        return

    config_path, data = _get_or_create_config()

    if "security" not in data:
        data["security"] = {}

    if new_value is None:
        new_value = not data["security"].get("require_password", False)

    data["security"]["require_password"] = new_value
    _save_config(config_path, data)

    status = "enabled" if new_value else "disabled"
    print(f"Password requirement {status} in {config_path}")


def _save_password_to_config() -> None:
    """Save or clear password hash in config file."""
    import getpass

    config_path, data = _get_or_create_config()

    if "security" not in data:
        data["security"] = {}

    has_password = data["security"].get("password_hash", "")

    try:
        if has_password:
            print("Password is currently set.")
            print("Enter new password or press Enter to clear:")
        password = getpass.getpass("Password: ")

        if not password:
            data["security"]["password_hash"] = ""
            data["security"]["require_password"] = False
            _save_config(config_path, data)
            print(f"Password cleared in {config_path}")
            print("Password protection disabled (require_password: false)")
            return

        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: Passwords do not match")
            return
    except KeyboardInterrupt:
        print("\nCancelled")
        return

    import bcrypt

    data["security"]["password_hash"] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    data["security"]["require_password"] = True
    _save_config(config_path, data)

    print(f"Password saved to {config_path}")
    print("Password protection enabled (require_password: true)")
