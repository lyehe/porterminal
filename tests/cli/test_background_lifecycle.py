"""POSIX integration coverage for the detached CLI lifecycle."""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pytest


def _reserve_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    # PID 1 may not immediately reap an orphaned child in every Linux CI
    # container. A zombie has completed cleanup even though kill(pid, 0) succeeds.
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        return stat_path.read_text(encoding="utf-8").split()[2] != "Z"
    except (FileNotFoundError, IndexError, OSError):
        return True


def _process_group_is_running(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _descendant_pids(root_pid: int) -> set[int]:
    """Best-effort snapshot for safe exact-PID cleanup if detachment regresses."""
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,ppid="],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return set()

    children_by_parent: dict[int, set[int]] = {}
    for line in result.stdout.splitlines():
        try:
            child_pid, parent_pid = (int(value) for value in line.split())
        except (TypeError, ValueError):
            continue
        children_by_parent.setdefault(parent_pid, set()).add(child_pid)

    descendants: set[int] = set()
    pending = [root_pid]
    while pending:
        parent_pid = pending.pop()
        for child_pid in children_by_parent.get(parent_pid, set()):
            if child_pid not in descendants:
                descendants.add(child_pid)
                pending.append(child_pid)
    return descendants


def _register_owned_processes(
    process_ids: set[int],
    *,
    process_groups: set[int],
    exact_processes: set[int],
) -> None:
    """Record only verified private groups, with exact-PID fallback."""
    memberships: dict[int, int] = {}
    for process_id in process_ids:
        try:
            memberships[process_id] = os.getpgid(process_id)
        except ProcessLookupError:
            continue

    process_groups.update(
        process_id
        for process_id, process_group in memberships.items()
        if process_group == process_id
    )
    exact_processes.update(
        process_id
        for process_id, process_group in memberships.items()
        if process_group not in process_groups
    )


def _wait_until(predicate: Callable[[], bool], *, timeout: float = 12) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def _http_status(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal and process-group contract")
def test_sighup_before_handoff_stops_the_unadvertised_process_group(tmp_path):
    """A terminal disconnect cannot orphan a child before ownership handoff."""
    child_pid_file = tmp_path / "child.pid"
    helper = """
import subprocess
import sys
from pathlib import Path

from porterminal.cli import main as cli_main
from porterminal.cli.args import Args

child_pid_file = Path(sys.argv[1])

def spawn(_command):
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    child_pid_file.write_text(str(child.pid), encoding="utf-8")
    return child

cli_main._spawn_background_process = spawn
raise SystemExit(
    cli_main._run_in_background(Args(no_tunnel=True), "SighupAccessCode_123456")
)
"""
    environment = os.environ.copy()
    for variable in ("TMPDIR", "TMP", "TEMP"):
        environment[variable] = str(tmp_path)

    launcher = subprocess.Popen(
        [sys.executable, "-c", helper, str(child_pid_file)],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    child_pid: int | None = None
    try:
        assert _wait_until(child_pid_file.exists, timeout=10)
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        assert _process_is_running(child_pid)
        assert os.getpgid(child_pid) == child_pid

        os.kill(launcher.pid, signal.SIGHUP)
        output, _ = launcher.communicate(timeout=15)

        assert launcher.returncode == 130, output
        assert _wait_until(lambda: not _process_is_running(child_pid))
        assert _wait_until(lambda: not _process_group_is_running(child_pid))
        assert not list(tmp_path.glob("porterminal-*"))
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=5)
        if child_pid is not None:
            try:
                if os.getpgid(child_pid) == child_pid:
                    os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal and process-group contract")
def test_detached_start_and_advertised_sigterm_stop_the_process_tree(tmp_path):
    preferred_port = _reserve_loopback_port()
    reported_port = preferred_port
    config_path = tmp_path / "ptn.yaml"
    config_path.write_text(
        "\n".join(
            [
                "server:",
                "  host: 127.0.0.1",
                f"  port: {preferred_port}",
                "update:",
                "  notify_on_startup: false",
                "terminal:",
                "  default_shell: sh",
                "  shells:",
                "    - id: sh",
                "      name: sh",
                "      command: /bin/sh",
                "",
            ]
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PORTERMINAL_CONFIG_PATH"] = str(config_path)
    environment.pop("PORTERMINAL_ACCESS_CODE", None)
    environment["PYTHONUNBUFFERED"] = "1"
    # Rich otherwise assumes an 80-column pipe and ellipsizes the bearer URL.
    environment["COLUMNS"] = "240"

    launcher = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "porterminal",
            str(tmp_path),
            "--background",
            "--no-tunnel",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pid: int | None = None
    reported_process_group: int | None = None
    owned_process_groups: set[int] = set()
    exact_cleanup_pids: set[int] = set()
    try:
        try:
            output, _ = launcher.communicate(timeout=60)
        except subprocess.TimeoutExpired as error:
            # Snapshot children before killing the launcher; a detached child
            # is reparented immediately afterward and would become undiscoverable.
            _register_owned_processes(
                _descendant_pids(launcher.pid),
                process_groups=owned_process_groups,
                exact_processes=exact_cleanup_pids,
            )
            launcher.kill()
            output, _ = launcher.communicate(timeout=5)
            raise AssertionError(f"background launcher timed out:\n{output}") from error

        pid_match = re.search(r"PID:\s*(\d+)", output)
        if pid_match is not None:
            pid = int(pid_match.group(1))
            owned_processes = {pid, *_descendant_pids(pid)}
            try:
                reported_process_group = os.getpgid(pid)
            except ProcessLookupError:
                pass
            _register_owned_processes(
                owned_processes,
                process_groups=owned_process_groups,
                exact_processes=exact_cleanup_pids,
            )

        assert launcher.returncode == 0, output
        assert pid_match is not None, output
        url_match = re.search(
            r"http://127\.0\.0\.1:(\d+)/[A-Za-z0-9_-]{16,128}/",
            output,
        )
        assert url_match is not None, output
        protected_url = url_match.group(0)
        reported_port = int(url_match.group(1))

        status, body = _http_status(f"{protected_url}health")
        assert status == 200
        assert json.loads(body)["status"] == "healthy"
        assert _http_status(f"http://127.0.0.1:{reported_port}/health")[0] == 404
        assert pid is not None and _process_is_running(pid)
        assert reported_process_group == pid

        # This is the exact POSIX stop operation printed by the CLI.
        os.kill(pid, signal.SIGTERM)

        assert _wait_until(lambda: not _port_is_open(reported_port))
        assert _wait_until(lambda: not _process_is_running(pid))
        assert _wait_until(lambda: not _process_group_is_running(pid))
    finally:
        if launcher.poll() is None:
            _register_owned_processes(
                _descendant_pids(launcher.pid),
                process_groups=owned_process_groups,
                exact_processes=exact_cleanup_pids,
            )
            launcher.kill()
            launcher.wait(timeout=5)

        for process_group in owned_process_groups:
            try:
                os.killpg(process_group, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for cleanup_pid in exact_cleanup_pids:
            try:
                os.kill(cleanup_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        def cleanup_complete() -> bool:
            return (
                not _port_is_open(reported_port)
                and not any(
                    _process_group_is_running(process_group)
                    for process_group in owned_process_groups
                )
                and not any(_process_is_running(cleanup_pid) for cleanup_pid in exact_cleanup_pids)
            )

        if not _wait_until(cleanup_complete, timeout=3):
            for process_group in owned_process_groups:
                try:
                    os.killpg(process_group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for cleanup_pid in exact_cleanup_pids:
                try:
                    os.kill(cleanup_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            _wait_until(cleanup_complete, timeout=3)
