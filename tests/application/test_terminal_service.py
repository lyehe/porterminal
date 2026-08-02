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
    monkeypatch.setattr(terminal_module.time, "time", lambda: now[0])
    service._register_connection(session_id, connection)

    await service._handle_json_message(sample_session, {"type": "pause"}, connection)

    assert connection.messages == [{"type": "pause_ack"}]
    await service._send_to_connections([connection], b"held")
    assert connection.outputs == []

    now[0] += terminal_module.FLOW_PAUSE_TIMEOUT + 0.01
    await service._send_to_connections([connection], b"auto-resumed")
    assert connection.outputs == [b"auto-resumed"]

    await service._handle_json_message(sample_session, {"type": "pause"}, connection)
    await service._handle_json_message(sample_session, {"type": "ack"}, connection)
    await service._send_to_connections([connection], b"explicitly-resumed")
    assert connection.outputs == [b"auto-resumed", b"explicitly-resumed"]


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
async def test_last_disconnect_stops_shared_reader_and_cleans_session_state(
    sample_session,
    monkeypatch,
):
    service = TerminalService()
    first = RecordingConnection()
    second = RecordingConnection()
    entered = {first: asyncio.Event(), second: asyncio.Event()}
    release = {first: asyncio.Event(), second: asyncio.Event()}
    starts: list[str] = []
    stops: list[str] = []

    async def handle_input(_session, connection, _rate_limiter) -> None:
        entered[connection].set()
        await release[connection].wait()

    def start_reader(_session, session_id: str) -> None:
        starts.append(session_id)

    async def stop_reader(session_id: str) -> None:
        stops.append(session_id)

    monkeypatch.setattr(service, "_handle_input_loop", handle_input)
    monkeypatch.setattr(service, "_start_broadcast_read_loop", start_reader)
    monkeypatch.setattr(service, "_stop_broadcast_read_loop", stop_reader)

    first_task = asyncio.create_task(service.handle_session(sample_session, first))
    second_task = asyncio.create_task(service.handle_session(sample_session, second))
    await asyncio.gather(entered[first].wait(), entered[second].wait())

    session_id = str(sample_session.id)
    assert starts == [session_id]
    assert service._session_connections[session_id] == {first, second}

    release[first].set()
    await first_task
    assert service._session_connections[session_id] == {second}
    assert stops == []
    assert session_id in service._session_locks

    release[second].set()
    await second_task
    assert session_id not in service._session_connections
    assert session_id not in service._session_locks
    assert first not in service._flow_state
    assert second not in service._flow_state
    assert stops == [session_id]
