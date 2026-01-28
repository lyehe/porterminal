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


def _mask_url(url: str) -> str:
    """Replace URL content with block characters, keeping protocol visible."""
    if "://" in url:
        protocol, rest = url.split("://", 1)
        return f"{protocol}://{'█' * len(rest)}"
    return "█" * len(url)


def _generate_spiral(size: int) -> str:
    """Generate a black/white square spiral pattern.

    Args:
        size: Size of the square (in characters width, half that in height).

    Returns:
        ASCII art spiral pattern using half-block characters.
    """
    grid_size = size
    grid = [[False] * grid_size for _ in range(grid_size)]

    # Draw spiral path with alternating colors every few steps
    x, y = 0, 0
    dx, dy = 1, 0  # Start moving right
    min_x, max_x = 0, grid_size - 1
    min_y, max_y = 0, grid_size - 1
    step = 0
    band_size = max(3, grid_size // 9)  # Alternate every N steps for visible bands

    while min_x <= max_x and min_y <= max_y:
        # Fill current cell - alternate based on position along spiral path
        grid[y][x] = (step // band_size) % 2 == 0
        step += 1

        # Move to next position
        next_x, next_y = x + dx, y + dy

        # Check if we need to turn
        if dx == 1 and next_x > max_x:  # Moving right, hit right edge
            min_y += 1
            dx, dy = 0, 1
        elif dy == 1 and next_y > max_y:  # Moving down, hit bottom edge
            max_x -= 1
            dx, dy = -1, 0
        elif dx == -1 and next_x < min_x:  # Moving left, hit left edge
            max_y -= 1
            dx, dy = 0, -1
        elif dy == -1 and next_y < min_y:  # Moving up, hit top edge
            min_x += 1
            dx, dy = 1, 0

        next_x, next_y = x + dx, y + dy
        if min_x <= next_x <= max_x and min_y <= next_y <= max_y:
            x, y = next_x, next_y
        else:
            break

    # Convert to half-block characters (2 rows per character)
    lines = []
    for row in range(0, grid_size, 2):
        line = ""
        for col in range(grid_size):
            top = grid[row][col] if row < grid_size else False
            bottom = grid[row + 1][col] if row + 1 < grid_size else False
            if top and bottom:
                line += "█"
            elif top and not bottom:
                line += "▀"
            elif not top and bottom:
                line += "▄"
            else:
                line += " "
        lines.append(line)

    return "\n".join(lines)


def get_spiral_placeholder(url: str) -> str:
    """Generate a spiral pattern matching the size of a QR code for the URL.

    Args:
        url: URL that would be encoded (used to determine QR size).

    Returns:
        ASCII art spiral pattern.
    """
    # Generate a real QR to get its dimensions
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Get the QR code dimensions
    buffer = io.StringIO()
    qr.print_ascii(out=buffer, invert=True)
    qr_lines = [line for line in buffer.getvalue().split("\n") if line]

    if not qr_lines:
        return _generate_spiral(21)  # Default size

    # Match the QR code width (it's typically square)
    width = len(qr_lines[0]) if qr_lines else 21

    # Generate spiral with matching dimensions
    return _generate_spiral(width)


def display_connected_screen(url: str, cwd: str | None = None) -> None:
    """Display screen after first connection (QR replaced with spiral, URL masked).

    Args:
        url: URL to display (will be masked with blocks).
        cwd: Current working directory to display.
    """
    console.clear()

    # Build spiral placeholder (same size as QR would be)
    spiral_text = get_spiral_placeholder(url)

    # Build logo and tagline with gradients
    logo_colored = _apply_gradient(
        LOGO.strip().split("\n"),
        ["bold bright_cyan", "bright_cyan", "cyan", "bright_blue", "blue"],
    )
    tagline_colored = _apply_gradient(
        TAGLINE.split("\n"),
        ["bright_magenta", "magenta"],
    )

    masked_url = _mask_url(url)

    # Left side content (same structure as startup screen)
    left_lines = [
        *logo_colored,
        f"[dim]v{__version__}[/dim]",
        "",
        *tagline_colored,
        "",
        "[green]●[/green] [bold green]CONNECTED[/bold green]",
        "",
        "",
        f"[dim]{masked_url}[/dim]",
    ]
    if cwd:
        left_lines.append(f"[dim]{cwd}[/dim]")
    left_lines.append("[dim]Ctrl+C to stop[/dim]")

    left_content = "\n".join(left_lines)

    # Create side-by-side layout (same as startup screen)
    table = Table.grid(padding=(0, 4))
    table.add_column(justify="left", vertical="middle")
    table.add_column(justify="left", vertical="middle")
    table.add_row(left_content, spiral_text)

    console.print()
    console.print(Align.center(table))
    console.print()


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
