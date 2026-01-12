"""Display utilities for the startup screen."""

import io
import random
import sys

import qrcode
from rich.align import Align
from rich.console import Console
from rich.table import Table

from porterminal import __version__

# Force UTF-8 for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

console = Console(force_terminal=True)

LOGO = r"""
██████  ██████  ██████  ██████  ██████  ██████  ██   ██  ██  ██   ██   ████   ██
██  ██  ██  ██  ██  ██    ██    ██      ██  ██  ███ ███  ██  ███  ██  ██  ██  ██
██████  ██  ██  ██████    ██    ████    ██████  ██ █ ██  ██  ██ █ ██  ██████  ██
██      ██  ██  ██  ██    ██    ██      ██  ██  ██   ██  ██  ██  ███  ██  ██  ██
██      ██████  ██  ██    ██    ██████  ██  ██  ██   ██  ██  ██   ██  ██  ██  ██████
"""

TAGLINE = r"""
█ █ █ █▄▄ █▀▀   █▀▀ █▀█ █▀▄ █▀▀   █▀▀ █▀█ █▀█ █▀▄▀█   ▄▀█ █▄ █ █▄█ █ █ █ █▀▀ █▀█ █▀▀
▀▄▀ █ █▄█ ██▄   █▄▄ █▄█ █▄▀ ██▄   █▀  █▀▄ █▄█ █ ▀ █   █▀█ █ ▀█  █  ▀▄▀▄▀ ██▄ █▀▄ ██▄
""".strip()

CAUTION_DEFAULT = "CAUTION: DO NOT VIBE CODE WHILE DRIVING"

CAUTION_EASTER_EGGS = [
    "VIBE CODING ON THE TOILET IS FINE THO",
    "DEPLOYING TO PROD FROM BED IS A LIFESTYLE",
    "TOUCHING GRASS WHILE TOUCHING CODE",
    "MOM SAID IT'S MY TURN ON THE SERVER",
    "IT WORKS ON MY PHONE",
    "404: WORK-LIFE BALANCE NOT FOUND",
    "git commit -m 'fixed from toilet'",
    "*HACKER VOICE* I'M IN (the bathroom)",
    "THEY SAID REMOTE WORK. I DELIVERED.",
    "TECHNICALLY THIS IS A STANDING DESK",
    "SUDO MAKE ME A SANDWICH (I'M IN LINE)",
    "MY OTHER TERMINAL IS A YACHT",
    "REAL PROGRAMMERS CODE IN TRAFFIC JAMS",
    "MERGE CONFLICTS RESOLVED AT 30,000 FT",
    "PUSHED TO MAIN FROM THE CHECKOUT LINE",
]


def get_caution() -> str:
    """Get caution message with 1% chance of easter egg."""
    if random.random() < 0.01:
        return random.choice(CAUTION_EASTER_EGGS)
    return CAUTION_DEFAULT


def _apply_gradient(lines: list[str], colors: list[str]) -> list[str]:
    """Apply color gradient to text lines."""
    return [
        f"[{colors[min(i, len(colors) - 1)]}]{line}[/{colors[min(i, len(colors) - 1)]}]"
        for i, line in enumerate(lines)
    ]


def get_qr_code(url: str) -> str:
    """Generate QR code as ASCII string.

    Args:
        url: URL to encode in the QR code.

    Returns:
        ASCII art representation of the QR code.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)

    buffer = io.StringIO()
    qr.print_ascii(out=buffer, invert=True)
    # Remove only truly empty lines (not whitespace-only lines which are part of QR)
    lines = [line for line in buffer.getvalue().split("\n") if line]
    # Strip trailing empty lines
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def display_startup_screen(
    url: str,
    is_tunnel: bool = True,
    cwd: str | None = None,
) -> None:
    """Display the final startup screen with QR code.

    Args:
        url: Primary URL to display and encode in QR.
        is_tunnel: Whether tunnel mode is active.
        cwd: Current working directory to display.
    """
    console.clear()

    # Build QR code
    try:
        qr_text = get_qr_code(url)
    except Exception:
        qr_text = "[QR code unavailable]"

    # Status indicator
    if is_tunnel:
        status = "[green]●[/green] TUNNEL ACTIVE - SCAN THE QR CODE TO ACCESS YOUR TERMINAL"
    else:
        status = "[yellow]●[/yellow] LOCAL MODE"

    # Build logo and tagline with gradients
    logo_colored = _apply_gradient(
        LOGO.strip().split("\n"),
        ["bold bright_cyan", "bright_cyan", "cyan", "bright_blue", "blue"],
    )
    tagline_colored = _apply_gradient(
        TAGLINE.split("\n"),
        ["bright_magenta", "magenta"],
    )

    # Left side content
    left_lines = [
        *logo_colored,
        f"[dim]v{__version__}[/dim]",
        "",
        *tagline_colored,
        "",
        f"[bold yellow]{get_caution()}[/bold yellow]",
        "[bright_red]Use -p for password protection if your screen is exposed[/bright_red]",
        status,
        f"[bold cyan]{url}[/bold cyan]",
    ]
    if cwd:
        left_lines.append(f"[dim]{cwd}[/dim]")
    left_lines.append("[dim]Ctrl+C to stop[/dim]")

    left_content = "\n".join(left_lines)

    # Create side-by-side layout (logo left, QR right)
    table = Table.grid(padding=(0, 4))
    table.add_column(justify="left", vertical="middle")
    table.add_column(justify="left", vertical="middle")
    table.add_row(left_content, qr_text)

    console.print()
    console.print(Align.center(table))
    console.print()
