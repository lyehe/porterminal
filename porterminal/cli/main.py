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

from porterminal.access_path import (
    ACCESS_CODE_ENV,
    access_path,
    build_access_url,
    generate_access_code,
)
from porterminal.cli import (
    CopyResult,
    build_agent_share_text,
    clipboard_install_hint,
    copy_to_clipboard,
    display_prompt_screen,
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
    base_url: str
    display_url: str
    display_cwd: str


@dataclass
class _ForegroundState:
    """Mutable event state shared with listener and output-drainer threads."""

    shutdown: Event = field(default_factory=Event)
    connected: Event = field(default_factory=Event)
    visibility_changed: Event = field(default_factory=Event)
    copy_requested: Event = field(default_factory=Event)
    prompt_toggled: Event = field(default_factory=Event)
    url_visible: bool = True
    copy_feedback: str | None = None
    prompt_visible: bool = False


def _posix_termination_signals() -> list[int]:
    """Return catchable POSIX termination signals relevant to CLI ownership."""
    signals: list[int] = [signal.SIGTERM]
    sighup = getattr(signal, "SIGHUP", None)
    if sighup is not None:
        signals.append(sighup)
    return signals


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


def _start_server_process(
    bind_host: str,
    check_host: str,
    preferred_port: int,
    *,
    verbose: bool,
    access_code: str,
    on_start: Callable[[], None],
) -> tuple[Process, int]:
    port = preferred_port
    if not is_port_available(bind_host, port):
        port = find_available_port(bind_host, preferred_port)
        if verbose:
            console.print(f"[dim]Using port {port}[/dim]")

    on_start()
    server_process = start_server(bind_host, port, verbose=verbose)
    if wait_for_server(
        check_host,
        port,
        timeout=30,
        access_path=access_path(access_code),
    ):
        return server_process, port

    console.print("[red]Error:[/red] Server failed to start")
    _terminate_startup_process(server_process)
    raise _CliAbort()


def _start_runtime(
    args: Args,
    config: Config,
    working_directory: str | None,
    access_code: str,
) -> _Runtime:
    bind_host = config.server.host
    check_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host

    with console.status("[cyan]Starting...[/cyan]", spinner="dots") as status:
        server_process, port = _start_server_process(
            bind_host,
            check_host,
            config.server.port,
            verbose=args.verbose,
            access_code=access_code,
            on_start=lambda: status.update("[cyan]Starting server...[/cyan]"),
        )
        if args.no_tunnel:
            base_url = f"http://{check_host}:{port}"
            return _Runtime(
                server_process=server_process,
                tunnel_process=None,
                base_url=base_url,
                display_url=build_access_url(base_url, access_code),
                display_cwd=working_directory or os.getcwd(),
            )

        status.update("[cyan]Establishing tunnel...[/cyan]")
        tunnel_process, tunnel_url = start_cloudflared(port)
        if tunnel_url:
            time.sleep(1)
            return _Runtime(
                server_process=server_process,
                tunnel_process=tunnel_process,
                base_url=tunnel_url,
                display_url=build_access_url(tunnel_url, access_code),
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
        copy_mode=sys.stdin.isatty() and (args.mcp_only or not args.no_tunnel),
        copy_status=status,
        mcp_only=args.mcp_only,
    )


def _with_install_hint(feedback: str) -> str:
    """Append the install hint as a dim trailing line when one applies."""
    hint = clipboard_install_hint()
    if hint:
        feedback += f"\n[dim]{hint}[/dim]"
    return feedback


def _copy_feedback(result: CopyResult, url: str, *, copied_message: str) -> str:
    """Only a confirmed copy hides the URL; OSC52 is unverifiable, so keep it visible."""
    if result is CopyResult.COPIED:
        return f"[green]{copied_message}[/green]"
    if result is CopyResult.SENT_TO_TERMINAL:
        return _with_install_hint(
            "[yellow]Sent to terminal clipboard (OSC 52)[/yellow]"
            f"\n[dim]If paste is empty:[/dim] [cyan]{url}[/cyan]"
        )
    return _with_install_hint(f"[yellow]Clipboard unavailable:[/yellow] [cyan]{url}[/cyan]")


def _copy_share_text(runtime: _Runtime, state: _ForegroundState, *, mcp_only: bool = False) -> None:
    url = f"{runtime.display_url.rstrip('/')}/mcp" if mcp_only else runtime.display_url
    try:
        result = copy_to_clipboard(build_agent_share_text(runtime.display_url, mcp_only=mcp_only))
    except Exception:  # the URL must reach the screen no matter what failed
        result = CopyResult.UNAVAILABLE
    state.copy_feedback = _copy_feedback(
        result, url, copied_message="Copied agent instructions and URL"
    )
    state.copy_requested.set()


def _copy_url(runtime: _Runtime, state: _ForegroundState, *, mcp_only: bool = False) -> None:
    url = f"{runtime.display_url.rstrip('/')}/mcp" if mcp_only else runtime.display_url
    try:
        result = copy_to_clipboard(url)
    except Exception:  # the URL must reach the screen no matter what failed
        result = CopyResult.UNAVAILABLE
    state.copy_feedback = _copy_feedback(result, url, copied_message="URL copied to clipboard")
    state.copy_requested.set()


def _show_prompt(state: _ForegroundState) -> None:
    """'s': replace the startup screen with the agent prompt as selectable text."""
    state.prompt_visible = True
    state.prompt_toggled.set()


def _hide_prompt(state: _ForegroundState) -> None:
    """'q': restore the startup screen. A no-op unless the prompt is showing."""
    if not state.prompt_visible:
        return
    state.prompt_visible = False
    state.prompt_toggled.set()


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
    interactive = sys.stdin.isatty() and (args.mcp_only or not args.no_tunnel)
    if not interactive:
        return None
    return start_key_listener(
        state.shutdown,
        {
            "c": lambda: _copy_share_text(runtime, state, mcp_only=args.mcp_only),
            "u": lambda: _copy_url(runtime, state, mcp_only=args.mcp_only),
            "s": lambda: _show_prompt(state),
            "q": lambda: _hide_prompt(state),
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
    show_prompt: Callable[[], None],
    *,
    qr_hidden: bool,
    current_show_url: bool,
) -> tuple[bool, bool]:
    # Every startup-screen repaint replaces the prompt view, so it is no longer
    # showing afterwards regardless of which event triggered the repaint.
    if state.visibility_changed.is_set():
        state.visibility_changed.clear()
        state.prompt_visible = False
        current_show_url = state.url_visible
        redraw(current_show_url, None)
        qr_hidden = not state.url_visible
        if state.url_visible:
            state.connected.clear()
        return qr_hidden, current_show_url

    if not qr_hidden and state.connected.is_set():
        state.prompt_visible = False
        redraw(False, None)
        return True, False

    if state.copy_requested.is_set():
        state.copy_requested.clear()
        state.prompt_visible = False
        redraw(current_show_url, state.copy_feedback)
        return qr_hidden, current_show_url

    if state.prompt_toggled.is_set():
        state.prompt_toggled.clear()
        if state.prompt_visible:
            show_prompt()
        else:
            redraw(current_show_url, None)

    return qr_hidden, current_show_url


def _run_foreground_loop(
    runtime: _Runtime,
    args: Args,
    state: _ForegroundState,
    redraw: Redraw,
    show_prompt: Callable[[], None],
) -> None:
    qr_hidden = args.keep_qr or args.mcp_only
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
            show_prompt,
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
    shutdown_signals: list[int] = [signal.SIGINT]
    if sys.platform != "win32":
        shutdown_signals.extend(_posix_termination_signals())
    old_handlers: dict[int, Any] = {}
    try:
        for shutdown_signal in shutdown_signals:
            old_handlers[shutdown_signal] = signal.signal(shutdown_signal, signal.SIG_IGN)
        try:
            _cleanup_process(runtime.server_process)
        finally:
            _cleanup_process(runtime.tunnel_process)
    finally:
        for shutdown_signal in reversed(shutdown_signals):
            if shutdown_signal in old_handlers:
                signal.signal(shutdown_signal, old_handlers[shutdown_signal])


def _run_foreground(runtime: _Runtime, args: Args) -> int:
    state = _ForegroundState()
    listener: Thread | None = None
    old_handlers: dict[int, Any] = {}

    def redraw(show_url: bool = True, status: str | None = None) -> None:
        _redraw(runtime, args, show_url, status)

    def show_prompt() -> None:
        display_prompt_screen(build_agent_share_text(runtime.display_url, mcp_only=args.mcp_only))

    def signal_handler(_signum: int, _frame: FrameType | None) -> None:
        state.shutdown.set()

    shutdown_signals: list[int] = [signal.SIGINT]
    if sys.platform != "win32":
        shutdown_signals.extend(_posix_termination_signals())
    try:
        # Install termination handlers before displaying the connection controls.
        for shutdown_signal in shutdown_signals:
            old_handlers[shutdown_signal] = signal.signal(shutdown_signal, signal_handler)

        _redraw(runtime, args, True, None)
        _start_background_drainers(runtime, args, state)
        listener = _start_interactive_listener(runtime, args, state)
        _run_foreground_loop(runtime, args, state, redraw, show_prompt)

        if state.shutdown.is_set():
            console.print("\n[dim]Shutting down...[/dim]")
        return 0
    finally:
        state.shutdown.set()
        try:
            if listener is not None:
                listener.join(timeout=1)
        finally:
            try:
                _cleanup_runtime(runtime)
            finally:
                for shutdown_signal in reversed(shutdown_signals):
                    if shutdown_signal in old_handlers:
                        signal.signal(shutdown_signal, old_handlers[shutdown_signal])


def main() -> int:
    """Run the Porterminal command-line application."""
    args = parse_args()
    os.environ["PORTERMINAL_MCP_ONLY"] = "true" if args.mcp_only else "false"

    access_code = generate_access_code()
    os.environ[ACCESS_CODE_ENV] = access_code

    from porterminal.config import get_config
    from porterminal.updater import check_and_notify

    check_and_notify()
    config = get_config()

    if (password_exit := _configure_password(args, config)) is not None:
        return password_exit
    if args.compose:
        os.environ["PORTERMINAL_COMPOSE_MODE"] = "true"
    if args.verbose:
        os.environ["PORTERMINAL_LOG_LEVEL"] = "DEBUG"

    try:
        working_directory = _resolve_working_directory(args.path)
        _ensure_cloudflared(args.no_tunnel)
        runtime = _start_runtime(args, config, working_directory, access_code)
    except _CliAbort as abort:
        return abort.exit_code
    return _run_foreground(runtime, args)


if __name__ == "__main__":
    sys.exit(main())
