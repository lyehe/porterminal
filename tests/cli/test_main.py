"""Characterization tests for CLI orchestration branches."""

from pathlib import Path
from types import SimpleNamespace

from porterminal.cli import main as cli_main
from porterminal.cli.args import Args


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
    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr(cli_main, "parse_args", lambda: args)
    monkeypatch.setattr("porterminal.updater.check_and_notify", lambda: None)
    monkeypatch.setattr("porterminal.config.get_config", _config)
    return console


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
        url_path.write_text("http://127.0.0.1:8080", encoding="utf-8")
        return process

    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(cli_main.subprocess, "Popen", popen)
    monkeypatch.setattr(
        cli_main,
        "display_startup_screen",
        lambda url, *, is_tunnel, cwd: displayed.append((url, is_tunnel, cwd)),
    )
    args = Args(path=str(tmp_path), no_tunnel=True, verbose=True, background=True)

    assert cli_main._run_in_background(args) == 0

    assert captured["command"][-3:] == [str(tmp_path), "--no-tunnel", "--verbose"]
    assert displayed == [("http://127.0.0.1:8080", False, str(tmp_path))]
    assert not list(tmp_path.glob("*.url"))
    assert any("PID: 4321" in line for line in console.lines)


def test_main_rejects_a_missing_working_directory(monkeypatch, tmp_path):
    missing = tmp_path / "missing"
    console = _prepare_main(monkeypatch, Args(path=str(missing), no_tunnel=True))

    assert cli_main.main() == 1
    assert any(f"Path does not exist: {missing}" in line for line in console.lines)


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
