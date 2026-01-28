"""Display utilities for the startup screen."""

import io
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
████████  ██████████  ██      ██
██    ██      ██      ████    ██
████████      ██      ██  ██  ██
██            ██      ██    ████
"""

TAGLINE_PORTABLE = r"""
█▀█ █▀█ █▀█ ▀█▀ ▄▀█ █▄▄ █   █▀▀
█▀▀ █▄█ █▀▄  █  █▀█ █▄█ █▄▄ ██▄
""".strip()

TAGLINE_TERMINAL = r"""
▀█▀ █▀▀ █▀█ █▀▄▀█ █ █▄ █ ▄▀█ █
 █  ██▄ █▀▄ █ ▀ █ █ █ ▀█ █▀█ █▄▄
""".strip()


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


def _generate_spiral(width: int, height: int) -> str:
    """Generate a spiral pattern using half-block characters like QR code.

    Args:
        width: Width in characters (output width).
        height: Height in output lines.

    Returns:
        ASCII art spiral pattern using █▀▄ and space.
    """
    # Ensure even dimensions for symmetric spiral
    grid_width = width + (width % 2)
    grid_height = height * 2  # Each output line = 2 grid rows
    grid_height = grid_height + (grid_height % 2)

    grid = [[False] * grid_width for _ in range(grid_height)]

    # Draw spiral path with alternating colors
    x, y = 0, 0
    dx, dy = 1, 0
    min_x, max_x = 0, grid_width - 1
    min_y, max_y = 0, grid_height - 1
    step = 0
    band_size = max(2, (grid_width + grid_height) // 18)

    while min_x <= max_x and min_y <= max_y:
        grid[y][x] = (step // band_size) % 2 == 0
        step += 1

        next_x, next_y = x + dx, y + dy

        if dx == 1 and next_x > max_x:
            min_y += 1
            dx, dy = 0, 1
        elif dy == 1 and next_y > max_y:
            max_x -= 1
            dx, dy = -1, 0
        elif dx == -1 and next_x < min_x:
            max_y -= 1
            dx, dy = 0, -1
        elif dy == -1 and next_y < min_y:
            min_x += 1
            dx, dy = 1, 0

        next_x, next_y = x + dx, y + dy
        if min_x <= next_x <= max_x and min_y <= next_y <= max_y:
            x, y = next_x, next_y
        else:
            break

    # Convert to half-block characters (2 grid rows per output line)
    lines = []
    for row in range(0, grid_height, 2):
        line = ""
        for col in range(grid_width):
            top = grid[row][col]
            bottom = grid[row + 1][col] if row + 1 < grid_height else False
            if top and bottom:
                line += "█"
            elif top and not bottom:
                line += "▀"
            elif not top and bottom:
                line += "▄"
            else:
                line += " "
        # Trim to original width
        lines.append(line[:width])

    # Trim to original height
    return "\n".join(lines[:height])


def get_qr_placeholder(url: str) -> str:
    """Generate a spiral placeholder matching the QR code size.

    Args:
        url: URL that would be encoded (used to determine QR size).

    Returns:
        ASCII art spiral pattern using same characters as QR.
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

    # Get the QR code output dimensions
    buffer = io.StringIO()
    qr.print_ascii(out=buffer, invert=True)
    qr_lines = [line for line in buffer.getvalue().split("\n") if line]

    # Width and height match QR output exactly
    width = len(qr_lines[0]) if qr_lines else 28
    height = len(qr_lines) if qr_lines else 14

    return _generate_spiral(width, height)


def display_startup_screen(
    url: str,
    is_tunnel: bool = True,
    cwd: str | None = None,
    show_url: bool = True,
) -> None:
    """Display the startup screen with QR code or spiral placeholder.

    Args:
        url: Primary URL to display and encode in QR.
        is_tunnel: Whether tunnel mode is active.
        cwd: Current working directory to display.
        show_url: If True, show URL and QR. If False, mask URL and show spiral.
    """
    console.clear()

    # Build QR code or spiral placeholder
    if show_url:
        try:
            right_panel = get_qr_code(url)
        except Exception:
            right_panel = "[QR code unavailable]"
        display_url = f"[bold cyan]{url}[/bold cyan]"
    else:
        right_panel = get_qr_placeholder(url)
        display_url = "[dim]Show URL via Settings (top right)[/dim]"

    # Status indicator
    if is_tunnel:
        if show_url:
            status = "[green]●[/green] TUNNEL ACTIVE - SCAN QR TO CONNECT"
        else:
            status = "[green]●[/green] TUNNEL ACTIVE"
    else:
        status = "[yellow]●[/yellow] LOCAL MODE"

    # Build logo and tagline with gradients
    logo_colored = _apply_gradient(
        LOGO.strip().split("\n"),
        ["bold bright_cyan", "bright_cyan", "cyan", "bright_blue"],
    )
    portable_colored = _apply_gradient(
        TAGLINE_PORTABLE.split("\n"),
        ["bright_yellow", "yellow"],
    )
    terminal_colored = _apply_gradient(
        TAGLINE_TERMINAL.split("\n"),
        ["bright_magenta", "magenta"],
    )

    # Left side content
    left_lines = [
        *logo_colored,
        "",
        *portable_colored,
        "",
        *terminal_colored,
        f"[dim]v{__version__}[/dim]",
        "",
        status,
        display_url,
    ]
    if cwd:
        left_lines.append(f"[dim]{cwd}[/dim]")
    left_lines.append("[dim]Ctrl+C to stop[/dim]")

    left_content = "\n".join(left_lines)

    # Create side-by-side layout (logo left, QR/spiral right)
    table = Table.grid(padding=(0, 4))
    table.add_column(justify="left", vertical="top")
    table.add_column(justify="left", vertical="top")
    table.add_row(left_content, right_panel)

    console.print(Align.center(table))


# Alias for backwards compatibility
def display_connected_screen(url: str, cwd: str | None = None) -> None:
    """Display screen with URL hidden (calls display_startup_screen with show_url=False)."""
    display_startup_screen(url, is_tunnel=True, cwd=cwd, show_url=False)
