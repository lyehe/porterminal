"""Command line argument parsing."""

import argparse
import sys

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
        "-V",
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
        "-U",
        "--update",
        action="store_true",
        help="Update to the latest version",
    )
    parser.add_argument(
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

    return args
