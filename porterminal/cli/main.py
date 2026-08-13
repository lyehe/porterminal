"""Command-line runtime orchestration for Porterminal."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Thread
from types import FrameType
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from rich.console import Console

from porterminal.access_path import (
    ACCESS_CODE_ENV,
    access_path,
    build_access_url,
    generate_access_code,
    validate_access_code,
)
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
    url_visible: bool = True
    copy_feedback: str | None = None


@dataclass
class _BackgroundSignalState:
    """Original handlers and shutdown state during detached-process handoff."""

    old_handlers: dict[int, Any]
    shutdown_requested: Event


def _posix_termination_signals() -> list[int]:
    """Return catchable POSIX termination signals relevant to CLI ownership."""
    signals: list[int] = [signal.SIGTERM]
    sighup = getattr(signal, "SIGHUP", None)
    if sighup is not None:
        signals.append(sighup)
    return signals


def _background_command(args: Args, url_file: Path) -> list[str]:
    command = [sys.executable, "-m", "porterminal", f"--_url-file={url_file}"]
    if args.no_tunnel:
        command.append("--no-tunnel")
    if args.verbose:
        command.append("--verbose")
    if args.path:
        # The path is positional user data and may itself look like an option
        # (for example a directory named "--background"). Keep it after the
        # option delimiter so the child cannot reinterpret it as a CLI flag.
        command.extend(["--", args.path])
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


def _validated_background_base_url(value: str, *, no_tunnel: bool) -> str:
    """Validate the child-reported origin before adding the bearer path."""
    if not value or value != value.strip() or any(ord(character) < 32 for character in value):
        raise ValueError("Background process reported an invalid server URL")
    try:
        parsed = urlsplit(value)
        parsed.port  # Force validation of a malformed port.
    except ValueError as error:
        raise ValueError("Background process reported an invalid server URL") from error

    expected_scheme = "http" if no_tunnel else "https"
    if (
        parsed.scheme != expected_scheme
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Background process reported an invalid server URL")
    return value.rstrip("/")


def _write_background_ready(url_file: Path, base_url: str) -> None:
    """Atomically publish credential-free startup data to the parent process."""
    temporary_file = url_file.with_name(f".{url_file.name}.{os.getpid()}.tmp")
    payload = json.dumps(
        {"version": 1, "base_url": base_url},
        separators=(",", ":"),
    )
    try:
        with temporary_file.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{payload}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_file, url_file)
    finally:
        try:
            temporary_file.unlink()
        except FileNotFoundError:
            pass


def _read_background_url(
    url_file: Path,
    *,
    access_code: str,
    no_tunnel: bool,
) -> str | None:
    try:
        raw_payload = url_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as error:
        raise ValueError("Background process reported malformed startup data") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "base_url"}
        or type(payload["version"]) is not int
        or payload["version"] != 1
        or not isinstance(payload["base_url"], str)
    ):
        raise ValueError("Background process reported malformed startup data")

    base_url = _validated_background_base_url(payload["base_url"], no_tunnel=no_tunnel)
    return build_access_url(base_url, access_code)


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


def _stop_background_process(process: Process) -> None:
    if sys.platform == "win32":
        # On Windows we have no durable process-group handle. Never signal a
        # numeric PID after Popen has observed its child exit: it may be reused.
        if process.poll() is not None:
            return
        try:
            result = subprocess.run(
                ["taskkill", "/T", "/PID", str(process.pid), "/F"],
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None

        if result is not None and result.returncode == 0:
            try:
                process.wait(timeout=5)
                return
            except (OSError, subprocess.TimeoutExpired):
                pass

        # Popen retains a process handle even when taskkill itself fails. Use
        # that handle as a final best-effort fallback and reap the leader.
        if process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return

    # start_new_session=True makes the child's PID its dedicated PGID. The
    # leader may exit before uvicorn/cloudflared, so group liveness—not leader
    # liveness—governs cleanup.
    def group_is_running() -> bool:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        if process.poll() is None:
            process.terminate()

    deadline = time.monotonic() + 3
    while True:
        # Reap the group leader as soon as it exits. Otherwise its zombie can
        # make killpg(..., 0) report a live group for the entire grace period.
        process.poll()
        if not group_is_running():
            break
        if time.monotonic() >= deadline:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                if process.poll() is None:
                    process.kill()

            kill_deadline = time.monotonic() + 1
            while True:
                process.poll()
                if not group_is_running() or time.monotonic() >= kill_deadline:
                    break
                time.sleep(0.05)
            break
        time.sleep(0.05)

    if process.poll() is None:
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    else:
        # poll() normally reaps the leader. Fake/test Popen implementations and
        # alternate runtimes may still need a non-blocking wait.
        try:
            process.wait(timeout=0)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _background_process_exit(process: Process) -> int | None:
    """Return a stable child exit code, or None while it remains alive."""
    return process.poll()


def _install_background_parent_shutdown_handlers() -> _BackgroundSignalState | None:
    """Make POSIX pre-handoff termination unwind through ownership cleanup."""
    if sys.platform == "win32":
        return None

    shutdown_requested = Event()

    def signal_handler(_signum: int, _frame: FrameType | None) -> None:
        shutdown_requested.set()

    old_handlers: dict[int, Any] = {}
    try:
        for shutdown_signal in _posix_termination_signals():
            old_handlers[shutdown_signal] = signal.signal(shutdown_signal, signal_handler)
    except BaseException:
        for shutdown_signal in reversed(old_handlers):
            signal.signal(shutdown_signal, old_handlers[shutdown_signal])
        raise
    return _BackgroundSignalState(old_handlers, shutdown_requested)


def _restore_background_parent_shutdown_handlers(
    handler_state: _BackgroundSignalState | None,
) -> None:
    if handler_state is not None:
        for shutdown_signal in reversed(handler_state.old_handlers):
            signal.signal(shutdown_signal, handler_state.old_handlers[shutdown_signal])


def _background_parent_shutdown_requested(
    handler_state: _BackgroundSignalState | None,
) -> bool:
    return handler_state is not None and handler_state.shutdown_requested.is_set()


def _raise_if_background_parent_shutdown_requested(
    handler_state: _BackgroundSignalState | None,
) -> None:
    if _background_parent_shutdown_requested(handler_state):
        raise KeyboardInterrupt


def _run_in_background(args: Args, access_code: str) -> int:
    """Spawn the server in background and return immediately."""
    access_code = validate_access_code(access_code)
    shutdown_handler_state = _install_background_parent_shutdown_handlers()
    try:
        with tempfile.TemporaryDirectory(prefix="porterminal-") as rendezvous_directory:
            url_file = Path(rendezvous_directory) / "ready.json"
            process: Process | None = None
            handed_off = False
            try:
                process = _spawn_background_process(_background_command(args, url_file))
                deadline = time.monotonic() + 30
                with console.status(
                    "[cyan]Starting in background...[/cyan]", spinner="dots"
                ) as status:
                    while time.monotonic() < deadline:
                        _raise_if_background_parent_shutdown_requested(shutdown_handler_state)
                        exit_code = _background_process_exit(process)
                        if exit_code is not None:
                            status.stop()
                            console.print(
                                f"[red]Error:[/red] Process exited unexpectedly (code: {exit_code})"
                            )
                            return 1
                        try:
                            url = _read_background_url(
                                url_file,
                                access_code=access_code,
                                no_tunnel=args.no_tunnel,
                            )
                        except ValueError as error:
                            status.stop()
                            console.print(f"[red]Error:[/red] {error}")
                            return 1
                        if url is not None:
                            # Close the ready-then-exit race before reporting a
                            # PID that no longer owns a running child lifecycle.
                            exit_code = _background_process_exit(process)
                            if exit_code is not None:
                                status.stop()
                                console.print(
                                    "[red]Error:[/red] Process exited unexpectedly "
                                    f"(code: {exit_code})"
                                )
                                return 1
                            _raise_if_background_parent_shutdown_requested(shutdown_handler_state)
                            status.stop()
                            _report_background_started(args, process, url)
                            _raise_if_background_parent_shutdown_requested(shutdown_handler_state)
                            # Ownership changes only after the complete report succeeds. From
                            # this point on, the advertised child belongs to the caller.
                            handed_off = True
                            return 0
                        time.sleep(0.2)

                console.print("[red]Error:[/red] Timeout waiting for server to start")
                return 1
            finally:
                # Stop the process group before TemporaryDirectory removes the
                # rendezvous path, so a child cannot race a late readiness write.
                if process is not None and not handed_off:
                    _stop_background_process(process)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled[/dim]")
        return 130
    except Exception as error:
        console.print(f"[red]Error starting background process:[/red] {error}")
        return 1
    finally:
        _restore_background_parent_shutdown_handlers(shutdown_handler_state)


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
        copy_mode=sys.stdin.isatty() and not args.url_file and not args.no_tunnel,
        copy_status=status,
    )


def _show_or_persist_url(runtime: _Runtime, args: Args) -> bool:
    if not args.url_file:
        _redraw(runtime, args, True, None)
        return True

    try:
        base_url = _validated_background_base_url(runtime.base_url, no_tunnel=args.no_tunnel)
        _write_background_ready(Path(args.url_file), base_url)
    except ValueError as error:
        console.print(f"[red]Error:[/red] {error}")
        return False
    except OSError as error:
        console.print(f"[red]Error writing URL file:[/red] {error}")
        return False
    return True


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
    shutdown_signals = [signal.SIGINT]
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

    def signal_handler(_signum: int, _frame: FrameType | None) -> None:
        state.shutdown.set()

    shutdown_signals = [signal.SIGINT]
    if sys.platform != "win32":
        shutdown_signals.extend(_posix_termination_signals())
    try:
        # Install termination handlers before publishing background readiness.
        # Once a PID is advertised, `kill PID` must take the orderly cleanup path.
        for shutdown_signal in shutdown_signals:
            old_handlers[shutdown_signal] = signal.signal(shutdown_signal, signal_handler)

        if not _show_or_persist_url(runtime, args):
            return 1
        _start_background_drainers(runtime, args, state)
        listener = _start_interactive_listener(runtime, args, state)
        _run_foreground_loop(runtime, args, state, redraw)

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

    if args.url_file:
        inherited_access_code = os.environ.get(ACCESS_CODE_ENV)
        if inherited_access_code is None:
            console.print("[red]Error:[/red] Background child is missing its access code")
            return 1
        try:
            access_code = validate_access_code(inherited_access_code)
        except ValueError as error:
            console.print(f"[red]Error:[/red] Invalid background child access code: {error}")
            return 1
    else:
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
    if args.background:
        return _run_in_background(args, access_code)
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
