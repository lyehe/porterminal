"""Command line argument parsing using tyro."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import tyro
import tyro.extras
from rich.console import Console

from porterminal import __version__

console = Console()
_URL_FILE_OPTION = "--_url-file"

# Set accent color for help text
tyro.extras.set_accent_color("cyan")


@dataclass
class Args:
    """Porterminal - Web terminal via Cloudflare Tunnel."""

    path: Annotated[
        str | None,
        tyro.conf.Positional,
        tyro.conf.arg(metavar="PATH"),
    ] = None
    """Starting directory for the shell."""

    no_tunnel: Annotated[bool, tyro.conf.arg(aliases=["-n"])] = False
    """Start server only, without Cloudflare tunnel."""

    verbose: Annotated[bool, tyro.conf.arg(aliases=["-v"])] = False
    """Show detailed startup logs."""

    check_update: Annotated[bool, tyro.conf.arg(aliases=["-u"])] = False
    """Check if a newer version is available."""

    background: Annotated[bool, tyro.conf.arg(aliases=["-b"])] = False
    """Run in background and return immediately."""

    init: Annotated[bool, tyro.conf.arg(aliases=["-i"])] = False
    """Create .ptn/ptn.yaml config with auto-discovered scripts."""

    init_from: Annotated[
        str | None,
        tyro.conf.arg(aliases=["-if"], metavar="URL_OR_PATH"),
    ] = None
    """Create .ptn/ptn.yaml from a URL or local file path."""

    password: Annotated[bool, tyro.conf.arg(aliases=["-p"])] = False
    """Prompt for password to protect terminal access."""

    toggle_password: Annotated[bool, tyro.conf.arg(aliases=["-tp"])] = False
    """Toggle password requirement on/off."""

    save_password: Annotated[bool, tyro.conf.arg(aliases=["-sp"])] = False
    """Save or clear password in config."""

    compose: Annotated[bool, tyro.conf.arg(aliases=["-c"])] = False
    """Enable compose mode by default."""

    keep_qr: Annotated[bool, tyro.conf.arg(aliases=["-k"])] = False
    """Keep QR code visible after first connection."""

    # Populated by parse_args() from a separately parsed internal-only option.
    url_file: Annotated[str | None, tyro.conf.Suppress] = None


def _extract_internal_url_file(arguments: list[str]) -> tuple[list[str], str | None]:
    """Remove the hidden background handoff option before public parsing."""
    public_arguments: list[str] = []
    url_file: str | None = None
    for index, argument in enumerate(arguments):
        if argument == "--":
            # Everything after the end-of-options marker belongs to the public
            # parser, even if a positional value resembles our internal option.
            public_arguments.extend(arguments[index:])
            break

        if argument.startswith(f"{_URL_FILE_OPTION}="):
            if url_file is not None:
                raise SystemExit(f"{_URL_FILE_OPTION} may only be specified once")
            url_file = argument.split("=", 1)[1]
            if not url_file:
                raise SystemExit(f"{_URL_FILE_OPTION} requires a path")
        elif argument == _URL_FILE_OPTION:
            raise SystemExit(f"{_URL_FILE_OPTION} requires the {_URL_FILE_OPTION}=PATH form")
        else:
            public_arguments.append(argument)
    return public_arguments, url_file


def parse_args() -> Args:
    """Parse command line arguments.

    Returns:
        Parsed Args dataclass with all CLI options.
    """
    arguments = sys.argv[1:]
    end_of_options = arguments.index("--") if "--" in arguments else len(arguments)

    # Check for the version flag manually (tyro doesn't have a built-in version
    # action), while respecting the standard end-of-options marker.
    if any(argument in {"--version", "-V"} for argument in arguments[:end_of_options]):
        console.print(f"[cyan]ptn[/cyan] [bold]{__version__}[/bold]")
        sys.exit(0)

    public_arguments, url_file = _extract_internal_url_file(arguments)
    args = tyro.cli(
        Args,
        prog="ptn",
        description="Porterminal - Web terminal via Cloudflare Tunnel",
        args=public_arguments,
    )
    args.url_file = url_file

    # Handle check-update early (before main app starts)
    if args.check_update:
        from porterminal.updater import check_for_updates, get_upgrade_command

        has_update, latest = check_for_updates(use_cache=False)
        if has_update:
            console.print(
                f"[yellow]Update available:[/yellow] {__version__} → [green]{latest}[/green]"
            )
            console.print(f"[dim]Run:[/dim] [cyan]{get_upgrade_command()}[/cyan]")
        else:
            console.print(
                f"[green]✓[/green] Already at latest version [bold]({__version__})[/bold]"
            )
        sys.exit(0)

    if args.init or args.init_from is not None:
        _init_config(args.init_from)
        # Continue to launch ptn after creating config

    if args.toggle_password:
        _set_password_requirement(None)  # None means toggle
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
    from porterminal.config import ConfigStore

    cwd = Path.cwd()
    config_dir = cwd / ".ptn"
    config_file = config_dir / "ptn.yaml"
    store = ConfigStore(config_path=config_file, cwd=cwd, default_path=config_file)

    # If source is provided, fetch/copy it
    if source:
        config_dir.mkdir(exist_ok=True)

        if source.startswith(("http://", "https://")):
            # Download from URL
            try:
                console.print(f"[dim]Downloading config from[/dim] [cyan]{source}[/cyan]...")
                with urlopen(source, timeout=10) as response:
                    content = response.read().decode("utf-8")
                data = yaml.safe_load(content) or {}
                if not isinstance(data, dict):
                    raise ValueError("Configuration root must be a mapping")
                store.save_raw(data)
                console.print(f"[green]✓[/green] Created: [cyan]{config_file}[/cyan]")
            except (URLError, OSError, TimeoutError, ValueError, yaml.YAMLError) as e:
                console.print(f"[red]Error:[/red] Failed to download config: {e}")
                return
        else:
            # Copy from local file
            source_path = Path(source).expanduser().resolve()
            if not source_path.exists():
                console.print(f"[red]Error:[/red] File not found: [cyan]{source_path}[/cyan]")
                return
            try:
                content = source_path.read_text(encoding="utf-8")
                data = yaml.safe_load(content) or {}
                if not isinstance(data, dict):
                    raise ValueError("Configuration root must be a mapping")
                store.save_raw(data)
                console.print(
                    f"[green]✓[/green] Created: [cyan]{config_file}[/cyan] "
                    f"[dim](from {source_path})[/dim]"
                )
            except (OSError, ValueError, yaml.YAMLError) as e:
                console.print(f"[red]Error:[/red] Failed to read config: {e}")
                return
        return

    # No source - use auto-discovery
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

    store.save_raw(config)

    console.print(f"[green]✓[/green] Created: [cyan]{config_file}[/cyan]")
    if discovered:
        labels = ", ".join(f"[bold]{b['label']}[/bold]" for b in discovered)
        console.print(f"[dim]Discovered {len(discovered)} project script(s):[/dim] {labels}")


def _get_or_create_config() -> tuple[Path, dict]:
    """Get config path and data, creating directory if needed.

    Returns:
        Tuple of (config_path, config_data).
    """
    from porterminal.config import ConfigStore

    cwd = Path.cwd()
    store = ConfigStore(cwd=cwd, default_path=cwd / ".ptn" / "ptn.yaml")
    return store.path_for_write(), store.read_raw()


def _save_config(config_path: Path, data: dict) -> None:
    """Save config data to file."""
    from porterminal.config import ConfigStore

    ConfigStore(config_path=config_path).save_raw(data)


def _set_password_requirement(value: bool | None) -> None:
    """Set or toggle security.require_password in config file.

    Args:
        value: True to enable, False to disable, None to toggle.
    """
    config_path, data = _get_or_create_config()

    if "security" not in data:
        data["security"] = {}

    new_value = value
    if new_value is None:
        new_value = not data["security"].get("require_password", False)

    data["security"]["require_password"] = new_value
    _save_config(config_path, data)

    if new_value:
        console.print("[green]✓[/green] Password requirement [green]enabled[/green]")
    else:
        console.print("[yellow]✓[/yellow] Password requirement [yellow]disabled[/yellow]")
    console.print(f"[dim]Config:[/dim] [cyan]{config_path}[/cyan]")


def _save_password_to_config() -> None:
    """Save or clear password hash in config file."""
    import getpass

    config_path, data = _get_or_create_config()

    if "security" not in data:
        data["security"] = {}

    has_password = data["security"].get("password_hash", "")

    try:
        if has_password:
            console.print("[yellow]Password is currently set.[/yellow]")
            console.print("[dim]Enter new password or press Enter to clear:[/dim]")
        password = getpass.getpass("Password: ")

        if not password:
            data["security"]["password_hash"] = ""
            data["security"]["require_password"] = False
            _save_config(config_path, data)
            console.print("[yellow]✓[/yellow] Password [yellow]cleared[/yellow]")
            console.print(f"[dim]Config:[/dim] [cyan]{config_path}[/cyan]")
            return

        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            console.print("[red]Error:[/red] Passwords do not match")
            return
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled[/dim]")
        return

    import bcrypt

    data["security"]["password_hash"] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    data["security"]["require_password"] = True
    _save_config(config_path, data)

    console.print("[green]✓[/green] Password [green]saved[/green]")
    console.print(f"[dim]Config:[/dim] [cyan]{config_path}[/cyan]")
