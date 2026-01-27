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

    check_update: Annotated[bool, tyro.conf.arg(aliases=["-c"])] = False
    """Check if a newer version is available."""

    background: Annotated[bool, tyro.conf.arg(aliases=["-b"])] = False
    """Run in background and return immediately."""

    init: Annotated[
        str | None,
        tyro.conf.arg(aliases=["-i"], metavar="URL_OR_PATH"),
    ] = None
    """Create .ptn/ptn.yaml config. Use "" for auto-discovery or provide URL/path."""

    password: Annotated[bool, tyro.conf.arg(aliases=["-p"])] = False
    """Prompt for password to protect terminal access."""

    toggle_password: Annotated[
        str | None,
        tyro.conf.arg(aliases=["-tp"], metavar="on|off"),
    ] = None
    """Set password requirement (on/off) or 'toggle'."""

    save_password: Annotated[bool, tyro.conf.arg(aliases=["-sp"])] = False
    """Save or clear password in config."""

    compose: Annotated[bool, tyro.conf.arg(aliases=["-C"])] = False
    """Enable compose mode by default."""

    # Internal argument for background mode communication (hidden from help)
    url_file: Annotated[
        str | None,
        tyro.conf.arg(name="_url-file"),
        tyro.conf.Suppress,
    ] = None


def parse_args() -> Args:
    """Parse command line arguments.

    Returns:
        Parsed Args dataclass with all CLI options.
    """
    # Check for --version flag manually (tyro doesn't have built-in version action)
    if "--version" in sys.argv or "-V" in sys.argv:
        console.print(f"[cyan]ptn[/cyan] [bold]{__version__}[/bold]")
        sys.exit(0)

    args = tyro.cli(
        Args,
        prog="ptn",
        description="Porterminal - Web terminal via Cloudflare Tunnel",
    )

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

    if args.init is not None:
        _init_config(args.init if args.init else None)
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
                console.print(f"[dim]Downloading config from[/dim] [cyan]{source}[/cyan]...")
                with urlopen(source, timeout=10) as response:
                    content = response.read().decode("utf-8")
                config_file.write_text(content)
                console.print(f"[green]✓[/green] Created: [cyan]{config_file}[/cyan]")
            except (URLError, OSError, TimeoutError) as e:
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
                config_file.write_text(content)
                console.print(
                    f"[green]✓[/green] Created: [cyan]{config_file}[/cyan] "
                    f"[dim](from {source_path})[/dim]"
                )
            except OSError as e:
                console.print(f"[red]Error:[/red] Failed to read config: {e}")
                return
        return

    # No source - use auto-discovery
    if config_file.exists():
        console.print(f"[yellow]Config already exists:[/yellow] [cyan]{config_file}[/cyan]")
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

    console.print(f"[green]✓[/green] Created: [cyan]{config_file}[/cyan]")
    if discovered:
        labels = ", ".join(f"[bold]{b['label']}[/bold]" for b in discovered)
        console.print(f"[dim]Discovered {len(discovered)} project script(s):[/dim] {labels}")


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
        console.print(
            f"[red]Error:[/red] Invalid value '[bold]{value}[/bold]'. "
            "Use [cyan]on[/cyan]/[cyan]off[/cyan]/[cyan]toggle[/cyan]"
        )
        return

    config_path, data = _get_or_create_config()

    if "security" not in data:
        data["security"] = {}

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
