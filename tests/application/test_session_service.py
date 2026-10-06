"""Session lifecycle regressions."""

import asyncio
import threading

from porterminal.application.services.session_service import SessionService
from porterminal.application.services.terminal_service import TerminalService
from porterminal.composition import create_container
from porterminal.domain import TerminalDimensions, UserId


async def test_slow_pty_shutdown_does_not_block_other_sessions(
    sample_session, session_repository, fake_pty, monkeypatch
):
    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    responsive = []

    def close():
        entered.set()
        release.wait(timeout=0.5)
        closed.set()

    monkeypatch.setattr(fake_pty, "close", close)
    session_repository.add(sample_session)
    service = SessionService(session_repository, lambda *_args: fake_pty)

    async def other_session_heartbeat():
        while not entered.is_set():
            await asyncio.sleep(0)
        responsive.append(not closed.is_set())
        release.set()

    await asyncio.gather(service.destroy_session(sample_session.id), other_session_heartbeat())

    assert responsive == [True]
    assert closed.is_set()
    assert session_repository.count() == 0


async def test_session_drains_before_first_viewer_and_stops_before_pty_close(
    session_repository, fake_pty_factory, fake_pty, bash_shell, user_id, default_dimensions
):
    terminal = TerminalService()
    service = SessionService(
        session_repository,
        fake_pty_factory,
        on_session_created=terminal.start_session,
        on_session_closing=terminal.stop_session,
    )
    session = await service.create_session(user_id, bash_shell, default_dimensions)
    try:
        fake_pty.add_output(b"initial background output")
        async with asyncio.timeout(1):
            while session.get_buffered_output() != b"initial background output":
                await asyncio.sleep(0)
        assert not session.is_connected
    finally:
        await service.destroy_session(session.id)

    assert not fake_pty.is_alive()
    assert not terminal._session_read_tasks
    assert not terminal._session_locks


async def test_real_pty_command_finishes_without_a_viewer(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    container = create_container(config_path=config_path, cwd=str(tmp_path))
    shell = next(
        shell for shell in container.available_shells if shell.id == container.default_shell_id
    )
    session = await container.session_service.create_session(
        UserId.local_user(), shell, TerminalDimensions.default()
    )
    try:
        # Observe completion outside terminal rendering: ConPTY may insert
        # cursor moves or line wraps into an output marker.
        completed_path = tmp_path / "offline.done"
        command = (
            'python -c "import sys; from pathlib import Path; '
            "sys.stdout.write('x'*2000000); sys.stdout.flush(); "
            "Path('offline.done').write_text('done')\"\r"
        )
        session.pty_handle.write(command.encode("utf-8"))
        # pywinpty 2.0.15 drains this volume much more slowly than newer releases.
        # Keep enough output to exceed PTY buffers and verify reader progress.
        async with asyncio.timeout(90):
            while not completed_path.exists():
                await asyncio.sleep(0.01)
        assert completed_path.read_text() == "done"
        assert not session.is_connected
        assert session.get_buffered_output()
        assert session.output_buffer.size <= session.output_buffer.max_bytes
    finally:
        await container.session_service.destroy_session(session.id)
