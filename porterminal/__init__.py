"""Porterminal package metadata and public entry point."""

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0-dev"  # Fallback before first build


def main() -> int:
    """Run the command-line application without loading it during package import."""
    from .cli.main import main as cli_main

    return cli_main()


__all__ = ["__version__", "main"]
