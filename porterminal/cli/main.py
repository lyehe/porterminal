"""Command-line runtime orchestration for Porterminal."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Thread
from types import FrameType
from typing import TYPE_CHECKING, Any

from rich.console import Console

from porterminal.cli import (
    build_agent_share_text,
    copy_to_clipboard,
    display_startup_screen,
    parse_args,
    start_key_listener,
)
from porterminal.cli.args import Args
from porterminal.infrastructure import (
    CloudflaredInstaller,
    drain_process_output,
    find_available_port,
    is_port_available,
    start_cloudflared,
    start_server,
    wait_for_server,
)

if TYPE_CHECKING:
    from porterminal.config import Config

Process = subprocess.Popen[Any]
Redraw = Callable[[bool, str | None], None]

console = Console()


class _CliAbort(Exception):
    """Stop CLI startup after a helper has reported the reason."""

    def __init__(self, exit_code: int = 1) -> None:
        super().__init__(exit_code)
        self.exit_code = exit_code


@dataclass
class _Runtime:
    """Processes and display values owned by a foreground CLI invocation."""

    server_process: Process | None
    tunnel_process: Process | None
    display_url: str
    display_cwd: str


@dataclass
class _ForegroundState:
    """Mutable event state shared with listener and output-drainer threads."""

    shutdown: Event = field(default_factory=Event)
    connected: Event = field(default_factory=Event)
    visibility_changed: Event = field(default_factory=Event)
    copy_requested: Event = field(default_factory=Event)
    url_visible: bool = True
    copy_feedback: str | None = None


def _background_command(args: Args, url_file: Path) -> list[str]:
    command = [sys.executable, "-m", "porterminal", f"--_url-file={url_file}"]
    if args.path:
        command.append(args.path)
    if args.no_tunnel:
        command.append("--no-tunnel")
    if args.verbose:
        command.append("--verbose")
    return command


def _spawn_background_process(command: list[str]) -> Process:
    if sys.platform == "win32":
        # CREATE_NO_WINDOW hides the detached child's console window.
        return subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _remove_url_file(url_file: Path) -> None:
    try:
        url_file.unlink()
    except OSError:
        pass


def _read_background_url(url_file: Path) -> str | None:
    if not url_file.exists():
        return None
    try:
        return url_file.read_text().strip() or None
    except OSError:
        return None


def _report_background_started(args: Args, process: Process, url: str) -> None:
    display_startup_screen(
        url,
        is_tunnel=url.startswith("https://"),
        cwd=args.path or os.getcwd(),
    )
    console.print(f"[green]Running in background[/green] [dim](PID: {process.pid})[/dim]")
    stop_command = (
        f"taskkill /T /PID {process.pid} /F" if sys.platform == "win32" else f"kill {process.pid}"
    )
    console.print(f"[dim]Stop with: {stop_command}[/dim]\n")


def _stop_timed_out_background_process(process: Process) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/PID", str(process.pid), "/F"],
            capture_output=True,
        )
        return

    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_in_background(args: Args) -> int:
    """Spawn the server in background and return immediately."""
    import tempfile

    url_file = Path(tempfile.gettempdir()) / f"porterminal-{os.getpid()}.url"
    try:
        process = _spawn_background_process(_background_command(args, url_file))
    except Exception as error:
        console.print(f"[red]Error starting process:[/red] {error}")
        return 1

    deadline = time.time() + 30
    with console.status("[cyan]Starting in background...[/cyan]", spinner="dots") as status:
        while time.time() < deadline:
            if url := _read_background_url(url_file):
                status.stop()
                _report_background_started(args, process, url)
                _remove_url_file(url_file)
                return 0

            if process.poll() is not None:
                status.stop()
                console.print(
                    f"[red]Error:[/red] Process exited unexpectedly (code: {process.returncode})"
                )
                _remove_url_file(url_file)
                return 1

            time.sleep(0.2)

    console.print("[red]Error:[/red] Timeout waiting for server to start")
    _stop_timed_out_background_process(process)
    return 1


def _configure_password(args: Args, config: Config) -> int | None:
    """Apply the saved or interactively supplied password environment override."""
    if not (args.password or config.security.require_password):
        return None

    if not args.password and config.security.password_hash:
        os.environ["PORTERMINAL_PASSWORD_HASH"] = config.security.password_hash
        console.print("[green]Password protection enabled (saved)[/green]")
        return None

    import getpass

    import bcrypt

    try:
        password = getpass.getpass("Enter password: ")
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled[/dim]")
        return 0

    if not password:
        console.print("[red]Error:[/red] Password cannot be empty")
        return 1

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    os.environ["PORTERMINAL_PASSWORD_HASH"] = password_hash.decode()
    console.print("[green]Password protection enabled[/green]")
    return None


def _resolve_working_directory(path: str | None) -> str | None:
    if not path:
        return None

    working_directory = Path(path).resolve()
    if not working_directory.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {working_directory}")
        raise _CliAbort()
    if not working_directory.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {working_directory}")
        raise _CliAbort()

    value = str(working_directory)
    os.environ["PORTERMINAL_CWD"] = value
    return value


def _ensure_cloudflared(no_tunnel: bool) -> None:
    if no_tunnel or CloudflaredInstaller.is_installed():
        return

    console.print("[yellow]cloudflared not found[/yellow]")
    if not CloudflaredInstaller.install():
        console.print()
        console.print("Install manually: [cyan]winget install cloudflare.cloudflared[/cyan]")
        raise _CliAbort()
    if not CloudflaredInstaller.is_installed():
        console.print()
        console.print("[yellow]Please restart your terminal and run again.[/yellow]")
        raise _CliAbort(0)


def _terminate_startup_process(process: Process | None) -> None:
    """Stop a process created during an incomplete startup attempt."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _start_or_reuse_server(
    bind_host: str,
    check_host: str,
    preferred_port: int,
    *,
    verbose: bool,
    password_enabled: bool,
    on_start: Callable[[], None],
) -> tuple[Process | None, int]:
    if not password_enabled and wait_for_server(check_host, preferred_port, timeout=1):
        if verbose:
            console.print(f"[dim]Reusing server on {bind_host}:{preferred_port}[/dim]")
        return None, preferred_port

    port = preferred_port
    if not is_port_available(bind_host, port):
        port = find_available_port(bind_host, preferred_port)
        if verbose:
            console.print(f"[dim]Using port {port}[/dim]")

    on_start()
    server_process = start_server(bind_host, port, verbose=verbose)
    if wait_for_server(check_host, port, timeout=30):
        return server_process, port

    console.print("[red]Error:[/red] Server failed to start")
    _terminate_startup_process(server_process)
    raise _CliAbort()


def _start_runtime(args: Args, config: Config, working_directory: str | None) -> _Runtime:
    bind_host = config.server.host
    check_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    password_enabled = os.environ.get("PORTERMINAL_PASSWORD_HASH") is not None

    with console.status("[cyan]Starting...[/cyan]", spinner="dots") as status:
        server_process, port = _start_or_reuse_server(
            bind_host,
            check_host,
            config.server.port,
            verbose=args.verbose,
            password_enabled=password_enabled,
            on_start=lambda: status.update("[cyan]Starting server...[/cyan]"),
        )
        if args.no_tunnel:
            return _Runtime(
                server_process=server_process,
                tunnel_process=None,
                display_url=f"http://{check_host}:{port}",
                display_cwd=working_directory or os.getcwd(),
            )

        status.update("[cyan]Establishing tunnel...[/cyan]")
        tunnel_process, tunnel_url = start_cloudflared(port)
        if tunnel_url:
            time.sleep(1)
            return _Runtime(
                server_process=server_process,
                tunnel_process=tunnel_process,
                display_url=tunnel_url,
                display_cwd=working_directory or os.getcwd(),
            )

        console.print("[red]Error:[/red] Failed to establish tunnel")
        _terminate_startup_process(server_process)
        _terminate_startup_process(tunnel_process)
        raise _CliAbort()


def _redraw(runtime: _Runtime, args: Args, show_url: bool, status: str | None) -> None:
    display_startup_screen(
        runtime.display_url,
        is_tunnel=not args.no_tunnel,
        cwd=runtime.display_cwd,
        show_url=show_url,
        copy_mode=sys.stdin.isatty() and not args.url_file and not args.no_tunnel,
        copy_status=status,
    )


def _show_or_persist_url(runtime: _Runtime, args: Args) -> None:
    if not args.url_file:
        _redraw(runtime, args, True, None)
        return

    try:
        Path(args.url_file).write_text(runtime.display_url)
    except OSError as error:
        console.print(f"[red]Error writing URL file:[/red] {error}")


def _copy_share_text(runtime: _Runtime, state: _ForegroundState) -> None:
    if copy_to_clipboard(build_agent_share_text(runtime.display_url)):
        state.copy_feedback = "[green]Copied agent instructions and URL[/green]"
    else:
        state.copy_feedback = (
            f"[yellow]Clipboard unavailable:[/yellow] [cyan]{runtime.display_url}[/cyan]"
        )
    state.copy_requested.set()


def _copy_url(runtime: _Runtime, state: _ForegroundState) -> None:
    if copy_to_clipboard(runtime.display_url):
        state.copy_feedback = "[green]URL copied to clipboard[/green]"
    else:
        state.copy_feedback = (
            f"[yellow]Clipboard unavailable:[/yellow] [cyan]{runtime.display_url}[/cyan]"
        )
    state.copy_requested.set()


def _start_background_drainers(
    runtime: _Runtime,
    args: Args,
    state: _ForegroundState,
) -> None:
    def on_visibility(visible: bool) -> None:
        state.url_visible = visible
        state.visibility_changed.set()

    if runtime.server_process is not None and not args.verbose:
        Thread(
            target=drain_process_output,
            args=(runtime.server_process,),
            kwargs={"on_connected": state.connected.set, "on_url_visibility": on_visibility},
            daemon=True,
        ).start()
    if runtime.tunnel_process is not None:
        Thread(
            target=drain_process_output,
            args=(runtime.tunnel_process,),
            daemon=True,
        ).start()


def _start_interactive_listener(
    runtime: _Runtime,
    args: Args,
    state: _ForegroundState,
) -> Thread | None:
    interactive = sys.stdin.isatty() and not args.url_file and not args.no_tunnel
    if not interactive:
        return None
    return start_key_listener(
        state.shutdown,
        {
            "c": lambda: _copy_share_text(runtime, state),
            "u": lambda: _copy_url(runtime, state),
        },
    )


def _report_process_exit(
    process: Process | None,
    *,
    normal_message: str,
    failure_label: str,
) -> bool:
    if process is None or process.poll() is None:
        return False

    code = process.returncode
    if code == 0 or (code is not None and code < 0):
        console.print(f"\n[dim]{normal_message}[/dim]")
    else:
        console.print(f"\n[yellow]{failure_label} stopped (exit code {code})[/yellow]")
    return True


def _handle_display_events(
    args: Args,
    state: _ForegroundState,
    redraw: Redraw,
    *,
    qr_hidden: bool,
    current_show_url: bool,
) -> tuple[bool, bool]:
    if state.visibility_changed.is_set():
        state.visibility_changed.clear()
        current_show_url = state.url_visible
        redraw(current_show_url, None)
        qr_hidden = not state.url_visible
        if state.url_visible:
            state.connected.clear()
        return qr_hidden, current_show_url

    if not qr_hidden and state.connected.is_set():
        redraw(False, None)
        return True, False

    if state.copy_requested.is_set():
        state.copy_requested.clear()
        redraw(current_show_url, state.copy_feedback)

    return qr_hidden, current_show_url


def _run_foreground_loop(
    runtime: _Runtime,
    args: Args,
    state: _ForegroundState,
    redraw: Redraw,
) -> None:
    qr_hidden = args.url_file is not None or args.keep_qr
    current_show_url = True
    while not state.shutdown.is_set():
        if _report_process_exit(
            runtime.server_process,
            normal_message="Server stopped",
            failure_label="Server",
        ):
            break
        if _report_process_exit(
            runtime.tunnel_process,
            normal_message="Tunnel closed",
            failure_label="Tunnel",
        ):
            break
        qr_hidden, current_show_url = _handle_display_events(
            args,
            state,
            redraw,
            qr_hidden=qr_hidden,
            current_show_url=current_show_url,
        )
        state.shutdown.wait(0.1)


def _cleanup_process(process: Process | None) -> None:
    if process is None or process.poll() is not None:
        return

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                timeout=10,
            )
            process.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return

    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _cleanup_runtime(runtime: _Runtime) -> None:
    old_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        _cleanup_process(runtime.server_process)
        _cleanup_process(runtime.tunnel_process)
    finally:
        signal.signal(signal.SIGINT, old_handler)


def _run_foreground(runtime: _Runtime, args: Args) -> int:
    _show_or_persist_url(runtime, args)
    state = _ForegroundState()
    _start_background_drainers(runtime, args, state)
    listener = _start_interactive_listener(runtime, args, state)

    def redraw(show_url: bool = True, status: str | None = None) -> None:
        _redraw(runtime, args, show_url, status)

    def signal_handler(_signum: int, _frame: FrameType | None) -> None:
        state.shutdown.set()

    old_handler = signal.signal(signal.SIGINT, signal_handler)
    try:
        _run_foreground_loop(runtime, args, state, redraw)
    finally:
        signal.signal(signal.SIGINT, old_handler)

    if state.shutdown.is_set():
        console.print("\n[dim]Shutting down...[/dim]")

    state.shutdown.set()
    if listener is not None:
        listener.join(timeout=1)
    _cleanup_runtime(runtime)
    return 0


def main() -> int:
    """Run the Porterminal command-line application."""
    args = parse_args()

    from porterminal.config import get_config
    from porterminal.updater import check_and_notify

    check_and_notify()
    config = get_config()

    if (password_exit := _configure_password(args, config)) is not None:
        return password_exit
    if args.compose:
        os.environ["PORTERMINAL_COMPOSE_MODE"] = "true"
    if args.background:
        return _run_in_background(args)
    if args.verbose:
        os.environ["PORTERMINAL_LOG_LEVEL"] = "DEBUG"

    try:
        working_directory = _resolve_working_directory(args.path)
        _ensure_cloudflared(args.no_tunnel)
        runtime = _start_runtime(args, config, working_directory)
    except _CliAbort as abort:
        return abort.exit_code
    return _run_foreground(runtime, args)


if __name__ == "__main__":
    sys.exit(main())
