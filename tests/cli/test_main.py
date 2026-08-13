"""Characterization tests for CLI orchestration branches."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from porterminal.cli import args as cli_args
from porterminal.cli import main as cli_main
from porterminal.cli.args import Args

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


def test_background_child_persists_only_the_validated_base_url(tmp_path):
    ready_file = tmp_path / "ready.json"
    runtime = cli_main._Runtime(
        server_process=None,
        tunnel_process=None,
        base_url="http://127.0.0.1:8080",
        display_url=f"http://127.0.0.1:8080/{ACCESS_CODE}/",
        display_cwd=str(tmp_path),
    )

    assert cli_main._show_or_persist_url(
        runtime,
        Args(no_tunnel=True, url_file=str(ready_file)),
    )

    payload = json.loads(ready_file.read_text(encoding="utf-8"))
    assert payload == {"version": 1, "base_url": "http://127.0.0.1:8080"}
    assert ACCESS_CODE not in ready_file.read_text(encoding="utf-8")
    assert list(tmp_path.glob("*.tmp")) == []
    assert (
        cli_main._read_background_url(
            ready_file,
            access_code=ACCESS_CODE,
            no_tunnel=True,
        )
        == runtime.display_url
    )


def test_background_command_round_trips_an_option_shaped_path(tmp_path, monkeypatch):
    ready_file = tmp_path / "ready.json"
    command = cli_main._background_command(
        Args(path="--background", no_tunnel=True, verbose=True, background=True),
        ready_file,
    )

    assert command[3:] == [
        f"--_url-file={ready_file}",
        "--no-tunnel",
        "--verbose",
        "--",
        "--background",
    ]

    monkeypatch.setattr(cli_args.sys, "argv", ["ptn", *command[3:]])
    child_args = cli_args.parse_args()
    assert child_args.url_file == str(ready_file)
    assert child_args.path == "--background"
    assert child_args.no_tunnel is True
    assert child_args.verbose is True
    assert child_args.background is False


def test_background_child_reports_url_and_preserves_forwarded_options(tmp_path, monkeypatch):
    console = _Console()
    process = _Process()
    captured: dict = {}
    displayed: list[tuple[str, bool, str]] = []

    def popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        url_path = Path(
            next(arg.split("=", 1)[1] for arg in command if arg.startswith("--_url-file="))
        )
        cli_main._write_background_ready(url_path, "http://127.0.0.1:8080")
        captured["ready_payload"] = url_path.read_text(encoding="utf-8")
        return process

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main.subprocess, "Popen", popen)
    monkeypatch.setattr(
        cli_main,
        "_stop_background_process",
        lambda _process: pytest.fail("a successfully reported child must not be stopped"),
    )
    monkeypatch.setattr(
        cli_main,
        "display_startup_screen",
        lambda url, *, is_tunnel, cwd: displayed.append((url, is_tunnel, cwd)),
    )
    args = Args(path=str(tmp_path), no_tunnel=True, verbose=True, background=True)

    assert cli_main._run_in_background(args, ACCESS_CODE) == 0

    assert captured["command"][-4:] == ["--no-tunnel", "--verbose", "--", str(tmp_path)]
    assert displayed == [(f"http://127.0.0.1:8080/{ACCESS_CODE}/", False, str(tmp_path))]
    assert ACCESS_CODE not in captured["ready_payload"]
    assert not list(tmp_path.glob("porterminal-*"))
    assert any("PID: 4321" in line for line in console.lines)


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        '{"version":2,"base_url":"http://127.0.0.1:8080"}',
        '{"version":1,"base_url":"https://attacker.test"}',
        '{"version":1,"base_url":"http://user:pass@127.0.0.1:8080"}',
        '{"version":1,"base_url":"http://127.0.0.1:8080/extra"}',
        '{"version":1,"base_url":"http://127.0.0.1:8080?redirect=evil"}',
    ],
)
def test_background_parent_rejects_untrusted_ready_payload(
    payload,
    tmp_path,
    monkeypatch,
):
    console = _Console()
    process = _Process()

    def popen(command, **_kwargs):
        url_path = Path(
            next(arg.split("=", 1)[1] for arg in command if arg.startswith("--_url-file="))
        )
        url_path.write_text(payload, encoding="utf-8")
        return process

    def stop_background(stopped_process):
        assert stopped_process is process
        stopped_process.terminate()

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main.subprocess, "Popen", popen)
    monkeypatch.setattr(cli_main, "_stop_background_process", stop_background)

    assert cli_main._run_in_background(Args(no_tunnel=True), ACCESS_CODE) == 1
    assert process.terminated is True
    assert not list(tmp_path.glob("porterminal-*"))
    assert any("Background process reported" in line for line in console.lines)


def test_background_timeout_stops_child_and_removes_rendezvous(tmp_path, monkeypatch):
    console = _Console()
    process = _Process()
    ticks = iter([0.0, 31.0])

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(cli_main.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(cli_main, "_stop_background_process", lambda child: child.terminate())

    assert cli_main._run_in_background(Args(no_tunnel=True), ACCESS_CODE) == 1
    assert process.terminated is True
    assert not list(tmp_path.glob("porterminal-*"))
    assert any("Timeout waiting" in line for line in console.lines)


def test_background_child_exit_removes_rendezvous(tmp_path, monkeypatch):
    console = _Console()
    process = _Process(returncode=7)

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main.subprocess, "Popen", lambda *_args, **_kwargs: process)

    assert cli_main._run_in_background(Args(no_tunnel=True), ACCESS_CODE) == 1
    assert process.terminated is False
    assert process.killed is False
    assert not list(tmp_path.glob("porterminal-*"))
    assert any("Process exited unexpectedly (code: 7)" in line for line in console.lines)


def test_background_ready_then_exit_is_not_reported_as_success(tmp_path, monkeypatch):
    console = _Console()
    process = _Process()
    poll_results = iter([None, 7])
    stopped: list[_Process] = []

    def spawn(command):
        url_path = Path(
            next(arg.split("=", 1)[1] for arg in command if arg.startswith("--_url-file="))
        )
        cli_main._write_background_ready(url_path, "http://127.0.0.1:8080")
        return process

    def process_exit(_process):
        return next(poll_results)

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main, "_spawn_background_process", spawn)
    monkeypatch.setattr(cli_main, "_background_process_exit", process_exit)
    monkeypatch.setattr(cli_main, "_stop_background_process", stopped.append)
    monkeypatch.setattr(
        cli_main,
        "_report_background_started",
        lambda *_args: pytest.fail("an exited child must not be reported as ready"),
    )

    assert cli_main._run_in_background(Args(no_tunnel=True), ACCESS_CODE) == 1
    assert stopped == [process]
    assert not list(tmp_path.glob("porterminal-*"))
    assert any("Process exited unexpectedly (code: 7)" in line for line in console.lines)


def test_background_interrupt_after_ready_stops_child_before_removing_rendezvous(
    tmp_path,
    monkeypatch,
):
    console = _Console()
    process = _Process()
    stopped: list[tuple[_Process, bool]] = []

    def spawn(command):
        url_path = Path(
            next(arg.split("=", 1)[1] for arg in command if arg.startswith("--_url-file="))
        )
        cli_main._write_background_ready(url_path, "http://127.0.0.1:8080")
        return process

    def stop_background(child):
        stopped.append((child, any(tmp_path.glob("porterminal-*/ready.json"))))

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main, "_spawn_background_process", spawn)
    monkeypatch.setattr(cli_main, "_stop_background_process", stop_background)
    monkeypatch.setattr(
        cli_main,
        "_report_background_started",
        lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    assert cli_main._run_in_background(Args(no_tunnel=True), ACCESS_CODE) == 130
    assert stopped == [(process, True)]
    assert not list(tmp_path.glob("porterminal-*"))
    assert any("Cancelled" in line for line in console.lines)


def test_background_unexpected_report_failure_stops_unhanded_child(tmp_path, monkeypatch):
    console = _Console()
    process = _Process()
    stopped: list[_Process] = []

    def spawn(command):
        url_path = Path(
            next(arg.split("=", 1)[1] for arg in command if arg.startswith("--_url-file="))
        )
        cli_main._write_background_ready(url_path, "http://127.0.0.1:8080")
        return process

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main, "_spawn_background_process", spawn)
    monkeypatch.setattr(cli_main, "_stop_background_process", stopped.append)
    monkeypatch.setattr(
        cli_main,
        "_report_background_started",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("display failed")),
    )

    assert cli_main._run_in_background(Args(no_tunnel=True), ACCESS_CODE) == 1
    assert stopped == [process]
    assert not list(tmp_path.glob("porterminal-*"))
    assert any("display failed" in line for line in console.lines)


@pytest.mark.parametrize(
    "shutdown_signal",
    [cli_main.signal.SIGTERM, 1],
    ids=["sigterm", "sighup"],
)
def test_background_parent_signal_before_handoff_stops_child_and_restores_handlers(
    shutdown_signal,
    tmp_path,
    monkeypatch,
):
    console = _Console()
    process = _Process()
    monkeypatch.setattr(cli_main.signal, "SIGHUP", 1, raising=False)
    original_handlers = {
        cli_main.signal.SIGTERM: object(),
        cli_main.signal.SIGHUP: object(),
    }
    current_handlers = dict(original_handlers)
    stopped: list[_Process] = []

    def set_signal(signum, handler):
        previous = current_handlers[signum]
        current_handlers[signum] = handler
        return previous

    def read_url(*_args, **_kwargs):
        current_handlers[shutdown_signal](shutdown_signal, None)
        return None

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr(cli_main.sys, "platform", "linux")
    monkeypatch.setattr(cli_main.signal, "signal", set_signal)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main, "_spawn_background_process", lambda _command: process)
    monkeypatch.setattr(cli_main, "_read_background_url", read_url)
    monkeypatch.setattr(cli_main, "_stop_background_process", stopped.append)
    monkeypatch.setattr(cli_main.time, "sleep", lambda _seconds: None)

    assert cli_main._run_in_background(Args(no_tunnel=True), ACCESS_CODE) == 130
    assert stopped == [process]
    assert current_handlers == original_handlers
    assert not list(tmp_path.glob("porterminal-*"))


def test_windows_background_stop_falls_back_when_taskkill_fails(monkeypatch):
    process = _Process()
    captured: dict = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(cli_main.sys, "platform", "win32")
    monkeypatch.setattr(cli_main.subprocess, "run", run)

    cli_main._stop_background_process(process)

    assert captured == {
        "command": ["taskkill", "/T", "/PID", str(process.pid), "/F"],
        "kwargs": {"capture_output": True, "timeout": 10},
    }
    assert process.killed is True
    assert process.waits == [3]


def test_posix_background_stop_cleans_group_after_leader_exit(monkeypatch):
    process = _Process(returncode=7)
    group_signals: list[int] = []
    clock = 0.0
    group_running = True

    def kill_group(pid, sig):
        nonlocal group_running
        assert pid == process.pid
        group_signals.append(sig)
        if sig == cli_main.signal.SIGKILL:
            group_running = False
        elif sig == 0 and not group_running:
            raise ProcessLookupError

    def monotonic():
        nonlocal clock
        clock += 1
        return clock

    monkeypatch.setattr(cli_main.sys, "platform", "linux")
    monkeypatch.setattr(cli_main.os, "killpg", kill_group, raising=False)
    monkeypatch.setattr(cli_main.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(cli_main.time, "monotonic", monotonic)
    monkeypatch.setattr(cli_main.time, "sleep", lambda _seconds: None)

    cli_main._stop_background_process(process)

    assert group_signals == [
        cli_main.signal.SIGTERM,
        0,
        0,
        0,
        cli_main.signal.SIGKILL,
        0,
    ]
    assert process.waits == [0]
    assert process.terminated is False
    assert process.killed is False


def test_posix_background_stop_reaps_leader_during_term_grace_period(monkeypatch):
    process = _Process()
    group_signals: list[int] = []
    leader_reaped = False

    def poll():
        nonlocal leader_reaped
        leader_reaped = True
        process.returncode = -15
        return process.returncode

    def kill_group(pid, sig):
        assert pid == process.pid
        group_signals.append(sig)
        if sig == 0 and leader_reaped:
            raise ProcessLookupError

    process.poll = poll
    monkeypatch.setattr(cli_main.sys, "platform", "linux")
    monkeypatch.setattr(cli_main.os, "killpg", kill_group, raising=False)
    monkeypatch.setattr(cli_main.time, "monotonic", lambda: 0.0)

    cli_main._stop_background_process(process)

    assert group_signals == [cli_main.signal.SIGTERM, 0]
    assert process.waits == [0]
    assert process.killed is False


def test_background_parent_passes_the_generated_access_code(monkeypatch):
    _prepare_main(monkeypatch, Args(no_tunnel=True, background=True))
    captured: dict = {}

    def run_in_background(_args, access_code):
        captured["access_code"] = access_code
        captured["environment_code"] = cli_main.os.environ[cli_main.ACCESS_CODE_ENV]
        return 0

    monkeypatch.setattr(cli_main, "_run_in_background", run_in_background)

    assert cli_main.main() == 0
    assert captured == {
        "access_code": ACCESS_CODE,
        "environment_code": ACCESS_CODE,
    }


def test_background_child_fails_closed_without_an_inherited_access_code(monkeypatch):
    console = _prepare_main(
        monkeypatch,
        Args(no_tunnel=True, url_file="unused-ready.json"),
    )
    monkeypatch.setattr(
        cli_main,
        "generate_access_code",
        lambda: pytest.fail("a background child must not generate a replacement access code"),
    )

    assert cli_main.main() == 1
    assert cli_main.ACCESS_CODE_ENV not in cli_main.os.environ
    assert any("missing its access code" in line for line in console.lines)


def test_background_child_fails_closed_with_an_invalid_inherited_access_code(monkeypatch):
    console = _prepare_main(
        monkeypatch,
        Args(no_tunnel=True, url_file="unused-ready.json"),
    )
    monkeypatch.setenv(cli_main.ACCESS_CODE_ENV, "too-short")
    monkeypatch.setattr(
        cli_main,
        "generate_access_code",
        lambda: pytest.fail("a background child must not generate a replacement access code"),
    )

    assert cli_main.main() == 1
    assert cli_main.os.environ[cli_main.ACCESS_CODE_ENV] == "too-short"
    assert any("Invalid background child access code" in line for line in console.lines)


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


def test_foreground_validation_failure_cleans_the_runtime(tmp_path, monkeypatch):
    console = _Console()
    runtime = cli_main._Runtime(
        server_process=_Process(),
        tunnel_process=None,
        base_url="https://wrong-scheme.example",
        display_url=f"https://wrong-scheme.example/{ACCESS_CODE}/",
        display_cwd=str(tmp_path),
    )
    cleaned: list[cli_main._Runtime] = []

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr(cli_main, "_cleanup_runtime", cleaned.append)

    assert (
        cli_main._run_foreground(
            runtime,
            Args(no_tunnel=True, url_file=str(tmp_path / "ready.json")),
        )
        == 1
    )
    assert cleaned == [runtime]
    assert not (tmp_path / "ready.json").exists()
    assert any("invalid server URL" in line for line in console.lines)


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
    monkeypatch.setattr(cli_main, "_show_or_persist_url", lambda *_args: True)
    monkeypatch.setattr(cli_main, "_start_background_drainers", lambda *_args: None)
    monkeypatch.setattr(cli_main, "_start_interactive_listener", lambda *_args: None)
    monkeypatch.setattr(cli_main, "_run_foreground_loop", run_loop)
    monkeypatch.setattr(cli_main, "_cleanup_runtime", lambda _runtime: events.append("cleanup"))

    assert cli_main._run_foreground(runtime, Args(no_tunnel=True)) == 0
    assert events == ["loop", "cleanup"]
    assert current_handlers == original_handlers
