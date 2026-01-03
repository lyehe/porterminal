"""Server and tunnel management utilities."""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

from rich.console import Console

console = Console()


def _is_icmp_warning(line: str) -> bool:
    """Check if line is a harmless ICMP/ping warning from cloudflared."""
    lower = line.lower()
    return "icmp" in lower or "ping_group" in lower or "ping group" in lower


def wait_for_server(host: str, port: int, timeout: int = 30) -> bool:
    """Wait for the server to be ready and verify it's Porterminal.

    Args:
        host: Server host address.
        port: Server port number.
        timeout: Maximum seconds to wait.

    Returns:
        True if server is ready, False otherwise.
    """
    start_time = time.time()
    url = f"http://{host}:{port}/health"

    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    # Verify it's actually Porterminal by checking response structure
                    try:
                        data = json.loads(response.read().decode("utf-8"))
                        if data.get("status") == "healthy" and "sessions" in data:
                            return True
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(0.5)

    return False


def start_server(host: str, port: int, *, verbose: bool = False) -> subprocess.Popen:
    """Start the uvicorn server.

    Args:
        host: Host address to bind.
        port: Port number to bind.
        verbose: If True, show server logs directly.

    Returns:
        Popen process object for the server.
    """
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "porterminal.app:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        "debug" if verbose else "warning",
        "--no-access-log",  # Disable access logging
    ]

    # On Windows, use CREATE_NEW_PROCESS_GROUP to prevent Ctrl+C from propagating
    # to the child process - we handle cleanup ourselves
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    if verbose:
        # Let output go directly to console
        process = subprocess.Popen(cmd, **kwargs)
    else:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            **kwargs,
        )

    return process


def start_cloudflared(port: int) -> tuple[subprocess.Popen, str | None]:
    """Start cloudflared tunnel and return the URL.

    Args:
        port: Local port to tunnel.

    Returns:
        Tuple of (process, url) where url may be None if tunnel failed.
    """
    cmd = [
        "cloudflared",
        "tunnel",
        "--no-autoupdate",
        "--protocol",
        "http2",  # Use HTTP/2 instead of QUIC (more reliable on Windows)
        "--config",
        os.devnull,  # Ignore any config files (cross-platform)
        "--origincert",
        os.devnull,  # Skip origin certificate (cross-platform)
        "--url",
        f"http://127.0.0.1:{port}",  # Use 127.0.0.1 explicitly
    ]

    # Clear cloudflared config to ensure clean quick tunnel
    env = os.environ.copy()
    env["TUNNEL_ORIGIN_CERT"] = ""
    env["NO_AUTOUPDATE"] = "true"
    # Point to a non-existent config to force quick tunnel mode
    env["TUNNEL_CONFIG"] = os.devnull

    # On Windows, use CREATE_NEW_PROCESS_GROUP to prevent Ctrl+C from propagating
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        **kwargs,
    )

    # Parse URL from cloudflared output (flexible pattern for different Cloudflare domains)
    url_pattern = re.compile(r"https://[a-z0-9-]+\.(trycloudflare\.com|cloudflare-tunnel\.com)")
    url = None

    # Read output until we find the URL
    for line in iter(process.stdout.readline, ""):
        if process.poll() is not None:
            break

        match = url_pattern.search(line)
        if match:
            url = match.group(0)
            break

        # Also check for errors (ignore ICMP/ping warnings - harmless)
        if "error" in line.lower() and not _is_icmp_warning(line):
            console.print(f"[red]Cloudflared error:[/red] {line.strip()}")

    return process, url


def drain_process_output(process: subprocess.Popen) -> None:
    """Drain process output silently (only print errors and security warnings).

    Args:
        process: Subprocess to drain output from.
    """
    try:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            # Always print security warnings and related messages
            if any(
                kw in line.lower()
                for kw in (
                    "security warning",
                    "authentication attempts",
                    "url may have been leaked",
                )
            ):
                console.print(f"[bold red]{line}[/bold red]")
            # Print errors, but ignore harmless ICMP/ping warnings
            elif "error" in line.lower() and not _is_icmp_warning(line):
                console.print(f"[red]{line}[/red]")
    except (OSError, ValueError):
        pass
