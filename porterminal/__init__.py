"""
Porterminal - Web-based terminal accessible via Cloudflare Tunnel.

This package provides:
- FastAPI server with WebSocket terminal endpoint
- PTY management with cross-platform support (Windows/Unix)
- Session management with reconnection support
- Configuration system with shell auto-detection
"""

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0-dev"  # Fallback before first build

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, Thread

from rich.console import Console

from porterminal.cli import display_startup_screen, parse_args
from porterminal.infrastructure import (
    CloudflaredInstaller,
    drain_process_output,
    find_available_port,
    is_port_available,
    start_cloudflared,
    start_server,
    wait_for_server,
)

console = Console()


def _run_in_background(args) -> int:
    """Spawn the server in background and return immediately."""
    import tempfile

    # Create temp file for URL communication
    url_file = Path(tempfile.gettempdir()) / f"porterminal-{os.getpid()}.url"

    # Build command without --background flag, with URL file
    cmd = [sys.executable, "-m", "porterminal", f"--_url-file={url_file}"]
    if args.path:
        cmd.append(args.path)
    if args.no_tunnel:
        cmd.append("--no-tunnel")
    if args.verbose:
        cmd.append("--verbose")

    # Start subprocess
    popen_kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        # Windows: CREATE_NO_WINDOW hides console window
        CREATE_NO_WINDOW = 0x08000000
        popen_kwargs["creationflags"] = CREATE_NO_WINDOW
    else:
        # Unix: start_new_session to detach from terminal
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except Exception as e:
        console.print(f"[red]Error starting process:[/red] {e}")
        return 1

    # Wait for URL file to be created (with timeout)
    timeout = 30
    start_time = time.time()

    with console.status("[cyan]Starting in background...[/cyan]", spinner="dots") as status:
        while time.time() - start_time < timeout:
            if url_file.exists():
                try:
                    content = url_file.read_text().strip()
                    if content:
                        status.stop()
                        url = content
                        is_tunnel = url.startswith("https://")
                        cwd = args.path or os.getcwd()

                        # Display full startup screen with QR code
                        display_startup_screen(url, is_tunnel=is_tunnel, cwd=cwd)

                        # Add background mode info
                        console.print(
                            f"[green]Running in background[/green] [dim](PID: {proc.pid})[/dim]"
                        )
                        stop_cmd = (
                            f"taskkill /T /PID {proc.pid} /F"
                            if sys.platform == "win32"
                            else f"kill {proc.pid}"
                        )
                        console.print(f"[dim]Stop with: {stop_cmd}[/dim]\n")

                        # Cleanup temp file
                        try:
                            url_file.unlink()
                        except OSError:
                            pass
                        return 0
                except OSError:
                    pass

            if proc.poll() is not None:
                status.stop()
                console.print(
                    f"[red]Error:[/red] Process exited unexpectedly (code: {proc.returncode})"
                )
                # Cleanup temp file
                try:
                    url_file.unlink()
                except OSError:
                    pass
                return 1

            time.sleep(0.2)

    console.print("[red]Error:[/red] Timeout waiting for server to start")
    # Kill the process tree (includes child shells)
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/PID", str(proc.pid), "/F"], capture_output=True)
    else:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    return 1


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Check for updates (notification only, never exec's)
    from porterminal.updater import check_and_notify

    check_and_notify()
    verbose = args.verbose

    # Load config to check require_password setting
    from porterminal.config import get_config

    config = get_config()

    # Handle password mode (CLI flag or config setting)
    if args.password or config.security.require_password:
        import getpass

        try:
            password = getpass.getpass("Enter password: ")
            if not password:
                console.print("[red]Error:[/red] Password cannot be empty")
                return 1

            import bcrypt

            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            os.environ["PORTERMINAL_PASSWORD_HASH"] = password_hash.decode()
            console.print("[green]Password protection enabled[/green]")
        except KeyboardInterrupt:
            console.print("\n[dim]Cancelled[/dim]")
            return 0

    # Handle background mode
    if args.background:
        return _run_in_background(args)

    # Set log level based on verbose flag
    if verbose:
        os.environ["PORTERMINAL_LOG_LEVEL"] = "DEBUG"

    # Validate and set working directory
    cwd_str = None
    if args.path:
        cwd = Path(args.path).resolve()
        if not cwd.exists():
            console.print(f"[red]Error:[/red] Path does not exist: {cwd}")
            return 1
        if not cwd.is_dir():
            console.print(f"[red]Error:[/red] Path is not a directory: {cwd}")
            return 1
        cwd_str = str(cwd)
        os.environ["PORTERMINAL_CWD"] = cwd_str

    bind_host = config.server.host
    preferred_port = config.server.port
    port = preferred_port
    # Use 127.0.0.1 for health checks (can't connect to 0.0.0.0)
    check_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host

    # Check cloudflared (skip if --no-tunnel)
    if not args.no_tunnel and not CloudflaredInstaller.is_installed():
        console.print("[yellow]cloudflared not found[/yellow]")
        if not CloudflaredInstaller.install():
            console.print()
            console.print("Install manually: [cyan]winget install cloudflare.cloudflared[/cyan]")
            return 1
        # Verify installation - if still not found, ask to restart shell
        if not CloudflaredInstaller.is_installed():
            console.print()
            console.print("[yellow]Please restart your terminal and run again.[/yellow]")
            return 0  # Exit gracefully, not an error

    # Show startup status
    with console.status("[cyan]Starting...[/cyan]", spinner="dots") as status:
        # Start or reuse server
        if wait_for_server(check_host, port, timeout=1):
            if verbose:
                console.print(f"[dim]Reusing server on {bind_host}:{port}[/dim]")
            server_process = None
        else:
            if not is_port_available(bind_host, port):
                port = find_available_port(bind_host, preferred_port)
                if verbose:
                    console.print(f"[dim]Using port {port}[/dim]")

            status.update("[cyan]Starting server...[/cyan]")
            server_process = start_server(bind_host, port, verbose=verbose)

            if not wait_for_server(check_host, port, timeout=30):
                console.print("[red]Error:[/red] Server failed to start")
                if server_process and server_process.poll() is None:
                    server_process.terminate()
                    try:
                        server_process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        server_process.kill()
                        server_process.wait()
                return 1

        tunnel_process = None
        tunnel_url = None

        if not args.no_tunnel:
            status.update("[cyan]Establishing tunnel...[/cyan]")
            tunnel_process, tunnel_url = start_cloudflared(port)

            if tunnel_url:
                # Wait for tunnel to stabilize before showing URL
                time.sleep(1)

            if not tunnel_url:
                console.print("[red]Error:[/red] Failed to establish tunnel")
                for proc in [server_process, tunnel_process]:
                    if proc and proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                return 1

    # Determine final URL
    display_cwd = cwd_str or os.getcwd()
    if args.no_tunnel:
        display_url = f"http://{check_host}:{port}"
    else:
        display_url = tunnel_url

    # If running as background child, write URL to file and skip display
    if args.url_file:
        try:
            Path(args.url_file).write_text(display_url)
        except OSError as e:
            console.print(f"[red]Error writing URL file:[/red] {e}")
    else:
        # Display final screen (only in foreground mode)
        display_startup_screen(display_url, is_tunnel=not args.no_tunnel, cwd=display_cwd)

    # Drain process output silently in background (only when not verbose)
    if server_process is not None and not verbose:
        Thread(target=drain_process_output, args=(server_process,), daemon=True).start()
    if tunnel_process is not None:
        Thread(target=drain_process_output, args=(tunnel_process,), daemon=True).start()

    # Use an event for responsive Ctrl+C handling on Windows
    shutdown_event = Event()

    def signal_handler(signum: int, frame: object) -> None:
        shutdown_event.set()

    old_handler = signal.signal(signal.SIGINT, signal_handler)
    try:
        while not shutdown_event.is_set():
            if server_process is not None and server_process.poll() is not None:
                code = server_process.returncode
                if code == 0 or code < 0:
                    console.print("\n[dim]Server stopped[/dim]")
                else:
                    console.print(f"\n[yellow]Server stopped (exit code {code})[/yellow]")
                break
            if tunnel_process is not None and tunnel_process.poll() is not None:
                code = tunnel_process.returncode
                if code == 0 or code < 0:
                    console.print("\n[dim]Tunnel closed[/dim]")
                else:
                    console.print(f"\n[yellow]Tunnel stopped (exit code {code})[/yellow]")
                break
            shutdown_event.wait(0.1)
    finally:
        signal.signal(signal.SIGINT, old_handler)

    if shutdown_event.is_set():
        console.print("\n[dim]Shutting down...[/dim]")

    # Cleanup - terminate gracefully, then kill if needed
    def cleanup_process(proc: subprocess.Popen | None, name: str) -> None:
        if proc is None or proc.poll() is not None:
            return

        if sys.platform == "win32":
            # Windows: use taskkill /T to kill entire process tree
            try:
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=10,
                )
                # Wait for process to actually terminate
                proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                # Last resort: try to kill just the main process
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        else:
            # Unix: terminate gracefully, then kill
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    # Ignore Ctrl+C during cleanup to prevent orphaned processes
    # Cleanup has timeouts so it won't hang forever
    old_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        cleanup_process(server_process, "server")
        cleanup_process(tunnel_process, "tunnel")
    finally:
        signal.signal(signal.SIGINT, old_handler)

    return 0


if __name__ == "__main__":
    sys.exit(main())
