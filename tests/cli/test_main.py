"""Characterization tests for CLI orchestration branches."""

from types import SimpleNamespace

import pytest

from porterminal.cli import main as cli_main
from porterminal.cli.args import Args
from porterminal.cli.clipboard import CopyResult

ACCESS_CODE = "CliAccessCode_12345678"


class _Status:
    def __init__(self) -> None:
        self.updates: list[str] = []
        self.stopped = False

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def update(self, message: str) -> None:
        self.updates.append(message)

    def stop(self) -> None:
        self.stopped = True


class _Console:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.statuses: list[_Status] = []

    def print(self, *values, **_kwargs) -> None:
        self.lines.append(" ".join(str(value) for value in values))

    def status(self, *_args, **_kwargs) -> _Status:
        status = _Status()
        self.statuses.append(status)
        return status


class _Process:
    def __init__(self, returncode: int | None = None, pid: int = 4321) -> None:
        self.returncode = returncode
        self.pid = pid
        self.terminated = False
        self.killed = False
        self.waits: list[int | None] = []

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: int | None = None) -> int:
        self.waits.append(timeout)
        return self.returncode or 0


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        security=SimpleNamespace(require_password=False, password_hash=""),
        server=SimpleNamespace(host="127.0.0.1", port=8080),
    )


def _prepare_main(monkeypatch, args: Args) -> _Console:
    console = _Console()
    monkeypatch.delenv(cli_main.ACCESS_CODE_ENV, raising=False)
    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr(cli_main, "parse_args", lambda: args)
    monkeypatch.setattr("porterminal.updater.check_and_notify", lambda: None)
    monkeypatch.setattr("porterminal.config.get_config", _config)
    monkeypatch.setattr(cli_main, "generate_access_code", lambda: ACCESS_CODE)
    return console


def test_main_rejects_a_missing_working_directory(monkeypatch, tmp_path):
    missing = tmp_path / "missing"
    console = _prepare_main(monkeypatch, Args(path=str(missing), no_tunnel=True))

    assert cli_main.main() == 1
    assert any(f"Path does not exist: {missing}" in line for line in console.lines)


def test_main_uses_access_path_for_readiness_and_display_url(monkeypatch):
    _prepare_main(monkeypatch, Args(no_tunnel=True))
    process = _Process()
    captured: dict = {}

    def wait_for_server(*_args, **kwargs):
        captured["readiness_path"] = kwargs["access_path"]
        return True

    def run_foreground(runtime, _args):
        captured["display_url"] = runtime.display_url
        return 0

    monkeypatch.setattr(cli_main, "wait_for_server", wait_for_server)
    monkeypatch.setattr(cli_main, "is_port_available", lambda *_args: True)
    monkeypatch.setattr(cli_main, "start_server", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(cli_main, "_run_foreground", run_foreground)

    assert cli_main.main() == 0
    assert captured == {
        "readiness_path": f"/{ACCESS_CODE}",
        "display_url": f"http://127.0.0.1:8080/{ACCESS_CODE}/",
    }


def test_main_terminates_a_server_that_fails_its_health_check(monkeypatch):
    console = _prepare_main(monkeypatch, Args(no_tunnel=True))
    process = _Process()
    checks = iter([False, False])
    monkeypatch.setattr(cli_main, "wait_for_server", lambda *_args, **_kwargs: next(checks))
    monkeypatch.setattr(cli_main, "is_port_available", lambda *_args: True)
    monkeypatch.setattr(cli_main, "start_server", lambda *_args, **_kwargs: process)

    assert cli_main.main() == 1
    assert process.terminated is True
    assert process.waits == [3]
    assert any("Server failed to start" in line for line in console.lines)


def test_main_cleans_up_a_tunnel_process_when_url_discovery_fails(monkeypatch):
    console = _prepare_main(monkeypatch, Args())
    tunnel = _Process()
    monkeypatch.setattr(cli_main, "wait_for_server", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cli_main.CloudflaredInstaller, "is_installed", lambda: True)
    monkeypatch.setattr(cli_main, "start_cloudflared", lambda _port: (tunnel, None))

    assert cli_main.main() == 1
    assert tunnel.terminated is True
    assert tunnel.waits == [3]
    assert any("Failed to establish tunnel" in line for line in console.lines)


@pytest.mark.parametrize(
    "shutdown_signal",
    [cli_main.signal.SIGTERM, 1],
    ids=["sigterm", "sighup"],
)
def test_foreground_posix_signal_requests_cleanup_and_restores_handlers(
    shutdown_signal,
    monkeypatch,
):
    monkeypatch.setattr(cli_main.signal, "SIGHUP", 1, raising=False)
    runtime = cli_main._Runtime(
        server_process=_Process(),
        tunnel_process=None,
        base_url="http://127.0.0.1:8080",
        display_url=f"http://127.0.0.1:8080/{ACCESS_CODE}/",
        display_cwd=".",
    )
    original_handlers = {
        cli_main.signal.SIGINT: object(),
        cli_main.signal.SIGTERM: object(),
        cli_main.signal.SIGHUP: object(),
    }
    current_handlers = dict(original_handlers)
    events: list[str] = []

    def set_signal(signum, handler):
        previous = current_handlers[signum]
        current_handlers[signum] = handler
        return previous

    def run_loop(_runtime, _args, state, _redraw):
        events.append("loop")
        current_handlers[shutdown_signal](shutdown_signal, None)
        assert state.shutdown.is_set()

    monkeypatch.setattr(cli_main.sys, "platform", "linux")
    monkeypatch.setattr(cli_main.signal, "signal", set_signal)
    monkeypatch.setattr(cli_main, "_redraw", lambda *_args: None)
    monkeypatch.setattr(cli_main, "_start_background_drainers", lambda *_args: None)
    monkeypatch.setattr(cli_main, "_start_interactive_listener", lambda *_args: None)
    monkeypatch.setattr(cli_main, "_run_foreground_loop", run_loop)
    monkeypatch.setattr(cli_main, "_cleanup_runtime", lambda _runtime: events.append("cleanup"))

    assert cli_main._run_foreground(runtime, Args(no_tunnel=True)) == 0
    assert events == ["loop", "cleanup"]
    assert current_handlers == original_handlers


def _runtime(display_url: str = "https://example.trycloudflare.com/code/") -> cli_main._Runtime:
    return cli_main._Runtime(
        server_process=None,
        tunnel_process=None,
        base_url=display_url,
        display_url=display_url,
        display_cwd="/tmp",
    )


def test_copy_share_text_success_reports_copied(monkeypatch):
    monkeypatch.setattr(cli_main, "copy_to_clipboard", lambda _text: CopyResult.COPIED)
    state = cli_main._ForegroundState()

    cli_main._copy_share_text(_runtime(), state)

    assert state.copy_requested.is_set()
    assert state.copy_feedback == "[green]Copied agent instructions and URL[/green]"


def test_copy_url_via_terminal_shows_url_and_hint_because_osc52_is_unconfirmed(monkeypatch):
    """A terminal never acknowledges OSC 52, so the URL (and the install hint) stay visible."""
    monkeypatch.setattr(cli_main, "copy_to_clipboard", lambda _text: CopyResult.SENT_TO_TERMINAL)
    monkeypatch.setattr(
        cli_main, "clipboard_install_hint", lambda: "Install wl-clipboard to enable clipboard copy"
    )
    state = cli_main._ForegroundState()

    cli_main._copy_url(_runtime(), state)

    assert state.copy_requested.is_set()
    assert state.copy_feedback == (
        "[yellow]Sent to terminal clipboard (OSC 52)[/yellow]"
        "\n[dim]If paste is empty:[/dim] [cyan]https://example.trycloudflare.com/code/[/cyan]"
        "\n[dim]Install wl-clipboard to enable clipboard copy[/dim]"
    )


def test_copy_url_via_terminal_omits_hint_when_none(monkeypatch):
    monkeypatch.setattr(cli_main, "copy_to_clipboard", lambda _text: CopyResult.SENT_TO_TERMINAL)
    monkeypatch.setattr(cli_main, "clipboard_install_hint", lambda: None)
    state = cli_main._ForegroundState()

    cli_main._copy_url(_runtime(), state)

    assert state.copy_feedback == (
        "[yellow]Sent to terminal clipboard (OSC 52)[/yellow]"
        "\n[dim]If paste is empty:[/dim] [cyan]https://example.trycloudflare.com/code/[/cyan]"
    )


def test_copy_url_failure_shows_url_and_install_hint(monkeypatch):
    monkeypatch.setattr(cli_main, "copy_to_clipboard", lambda _text: CopyResult.UNAVAILABLE)
    monkeypatch.setattr(
        cli_main, "clipboard_install_hint", lambda: "Install wl-clipboard to enable clipboard copy"
    )
    state = cli_main._ForegroundState()

    cli_main._copy_url(_runtime(), state)

    assert state.copy_requested.is_set()
    assert state.copy_feedback == (
        "[yellow]Clipboard unavailable:[/yellow] [cyan]https://example.trycloudflare.com/code/[/cyan]"
        "\n[dim]Install wl-clipboard to enable clipboard copy[/dim]"
    )


def test_copy_share_text_failure_omits_hint_when_none(monkeypatch):
    monkeypatch.setattr(cli_main, "copy_to_clipboard", lambda _text: CopyResult.UNAVAILABLE)
    monkeypatch.setattr(cli_main, "clipboard_install_hint", lambda: None)
    state = cli_main._ForegroundState()

    cli_main._copy_share_text(_runtime(), state, mcp_only=True)

    assert state.copy_feedback == (
        "[yellow]Clipboard unavailable:[/yellow] "
        "[cyan]https://example.trycloudflare.com/code/mcp[/cyan]"
    )
