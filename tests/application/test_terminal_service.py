"""Characterization tests for terminal I/O coordination."""

import asyncio

import pytest

from porterminal.application.services import terminal_service as terminal_module
from porterminal.application.services.terminal_service import TerminalService


class RecordingConnection:
    """Small controllable ConnectionPort used by service-level tests."""

    def __init__(self) -> None:
        self.outputs: list[bytes] = []
        self.messages: list[dict] = []
        self.connected = True

    async def send_output(self, data: bytes) -> None:
        self.outputs.append(data)

    async def send_message(self, message: dict) -> None:
        self.messages.append(message)

    async def receive(self) -> dict | bytes:
        await asyncio.sleep(3600)
        return b""

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected


@pytest.mark.asyncio
async def test_pause_ack_resume_and_timeout_control_delivery(sample_session, monkeypatch):
    service = TerminalService()
    connection = RecordingConnection()
    session_id = str(sample_session.id)
    now = [100.0]
    monkeypatch.setattr(terminal_module, "monotonic", lambda: now[0])
    service._register_connection(session_id, connection)

    await service._handle_json_message(sample_session, {"type": "pause"}, connection)

    assert connection.messages == [{"type": "pause_ack"}]
    await service._send_to_connections([connection], b"held")
    assert connection.outputs == []

    now[0] += terminal_module.FLOW_PAUSE_TIMEOUT + 0.01
    await service._send_to_connections([connection], b"auto-resumed")
    assert b"".join(connection.outputs) == b"heldauto-resumed"

    await service._handle_json_message(sample_session, {"type": "pause"}, connection)
    await service._handle_json_message(sample_session, {"type": "ack"}, connection)
    await service._send_to_connections([connection], b"explicitly-resumed")
    assert b"".join(connection.outputs) == b"heldauto-resumedexplicitly-resumed"


@pytest.mark.asyncio
async def test_ack_flushes_paused_output_without_waiting_for_more_pty_data(sample_session):
    service = TerminalService()
    connection = RecordingConnection()
    service._register_connection(str(sample_session.id), connection)

    await service._handle_json_message(sample_session, {"type": "pause"}, connection)
    await service._send_to_connections([connection], b"first")
    await service._send_to_connections([connection], b"second")
    await service._handle_json_message(sample_session, {"type": "ack"}, connection)

    assert b"".join(connection.outputs) == b"firstsecond"


@pytest.mark.asyncio
async def test_reader_drains_output_without_connected_viewers(
    sample_session, fake_pty, monkeypatch
):
    service = TerminalService()

    def read(_size: int = 4096) -> bytes:
        fake_pty.kill()
        return b"background command finished"

    monkeypatch.setattr(fake_pty, "read", read)
    await service._read_pty_broadcast_loop(sample_session, str(sample_session.id))

    assert sample_session.get_buffered_output() == b"background command finished"


@pytest.mark.asyncio
async def test_cancelled_buffer_replay_unregisters_connection(sample_session):
    service = TerminalService()
    started = asyncio.Event()
    session_id = str(sample_session.id)
    sample_session.add_output(b"previous output")

    class WaitingReplay(RecordingConnection):
        async def send_output(self, data: bytes) -> None:
            started.set()
            await asyncio.Event().wait()

    connection = WaitingReplay()
    task = asyncio.create_task(service.handle_session(sample_session, connection))
    try:
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert connection not in service._session_connections.get(session_id, set())
        assert connection not in service._flow_state
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await service.stop_session(sample_session.id)


async def test_output_waiting_for_replay_is_dropped_when_connection_unregisters(sample_session):
    service = TerminalService()
    started = asyncio.Event()
    sample_session.add_output(b"previous output")

    class WaitingReplay(RecordingConnection):
        async def send_output(self, data: bytes) -> None:
            if data == b"previous output":
                started.set()
                await asyncio.Event().wait()
            await super().send_output(data)

    connection = WaitingReplay()
    replay = asyncio.create_task(service.handle_session(sample_session, connection))
    queued = None
    try:
        await asyncio.wait_for(started.wait(), 1)
        queued = asyncio.create_task(service._send_connection_output(connection, b"live output"))
        await asyncio.sleep(0)  # The live send waits for replay to release the connection lock.
        replay.cancel()
        with pytest.raises(asyncio.CancelledError):
            await replay
        await queued
        assert connection.outputs == []
    finally:
        replay.cancel()
        if queued:
            queued.cancel()
            await asyncio.gather(queued, return_exceptions=True)
        await asyncio.gather(replay, return_exceptions=True)
        await service.stop_session(sample_session.id)


@pytest.mark.asyncio
async def test_large_pty_reads_are_batched_before_broadcast(sample_session, fake_pty, monkeypatch):
    service = TerminalService()
    connection = RecordingConnection()
    session_id = str(sample_session.id)
    chunks = [b"a" * 100, b"b" * 200]

    def read(_size: int = 4096) -> bytes:
        data = chunks.pop(0)
        if not chunks:
            fake_pty.kill()
        return data

    monkeypatch.setattr(fake_pty, "read", read)
    service._register_connection(session_id, connection)

    await service._read_pty_broadcast_loop(sample_session, session_id)

    assert connection.outputs == [b"a" * 100 + b"b" * 200, b"\r\n[Shell exited]\r\n"]
    assert sample_session.get_buffered_output().endswith(b"a" * 100 + b"b" * 200)


@pytest.mark.asyncio
async def test_last_disconnect_keeps_reader_until_session_is_destroyed(
    sample_session,
    monkeypatch,
):
    service = TerminalService()
    first = RecordingConnection()
    second = RecordingConnection()
    entered = {first: asyncio.Event(), second: asyncio.Event()}
    release = {first: asyncio.Event(), second: asyncio.Event()}

    async def handle_input(_session, connection, _rate_limiter) -> None:
        entered[connection].set()
        await release[connection].wait()

    monkeypatch.setattr(service, "_handle_input_loop", handle_input)

    first_task = asyncio.create_task(service.handle_session(sample_session, first))
    second_task = asyncio.create_task(service.handle_session(sample_session, second))
    session_id = str(sample_session.id)
    try:
        async with asyncio.timeout(1):
            await asyncio.gather(entered[first].wait(), entered[second].wait())

        assert len(service._session_read_tasks) == 1
        reader = service._session_read_tasks[session_id]
        assert service._session_connections[session_id] == {first, second}

        release[first].set()
        await first_task
        assert service._session_connections[session_id] == {second}
        assert service._session_read_tasks[session_id] is reader
        assert session_id in service._session_locks

        release[second].set()
        await second_task
        assert session_id not in service._session_connections
        assert session_id in service._session_locks
        assert first not in service._flow_state
        assert second not in service._flow_state
        assert service._session_read_tasks[session_id] is reader
        assert not reader.done()

        sample_session.pty_handle.add_output(b"output while disconnected")
        async with asyncio.timeout(1):
            while b"output while disconnected" not in sample_session.get_buffered_output():
                await asyncio.sleep(0)
    finally:
        first_task.cancel()
        second_task.cancel()
        await asyncio.gather(first_task, second_task, return_exceptions=True)
        await service.stop_session(sample_session.id)

    assert reader.cancelled()
    assert session_id not in service._session_read_tasks
    assert session_id not in service._session_locks


async def test_paused_output_overflow_requests_replay_instead_of_silent_loss(
    sample_session, monkeypatch
):
    service = TerminalService()
    connection = RecordingConnection()
    monkeypatch.setattr(terminal_module, "FLOW_BUFFER_MAX_BYTES", 5)
    service._register_connection(str(sample_session.id), connection)
    await service._handle_json_message(sample_session, {"type": "pause"}, connection)

    await service._send_to_connections([connection], b"12345")
    assert connection.is_connected()
    await service._send_to_connections([connection], b"6")

    assert not connection.is_connected()
    assert service._flow_state[connection].pending_output == b""
