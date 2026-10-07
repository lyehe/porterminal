"""Password authentication must leave the terminal event loop responsive."""

import asyncio
import threading
from unittest.mock import Mock

import pytest

from porterminal.infrastructure import auth


class AuthConnection:
    def __init__(self, messages: list[dict | bytes]) -> None:
        self.incoming = messages.copy()
        self.messages: list[dict] = []

    async def receive(self) -> dict | bytes:
        if self.incoming:
            return self.incoming.pop(0)
        await asyncio.Event().wait()
        return b""

    async def send_message(self, message: dict) -> None:
        self.messages.append(message)

    async def send_output(self, data: bytes) -> None:
        pass

    async def close(self, code: int = 1000, reason: str = "") -> None:
        pass

    def is_connected(self) -> bool:
        return True


@pytest.mark.parametrize("authenticate", [auth.authenticate_connection, auth.validate_auth_message])
async def test_password_check_does_not_block_other_event_loop_work(monkeypatch, authenticate):
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    worker_threads = []

    def slow_check(password: bytes, password_hash: bytes) -> bool:
        assert (password, password_hash) == (b"correct", b"hash")
        worker_threads.append(threading.get_ident())
        loop.call_soon_threadsafe(started.set)
        if not release.wait(5):
            raise TimeoutError("The event loop could not release the password worker")
        return True

    monkeypatch.setattr(auth.bcrypt, "checkpw", slow_check)
    connection = AuthConnection([{"type": "auth", "password": "correct"}])
    task = asyncio.create_task(authenticate(connection, b"hash"))
    try:
        await asyncio.wait_for(started.wait(), 2)
        assert not task.done()
        assert len(worker_threads) == 1
        assert worker_threads[0] != threading.get_ident()
    finally:
        release.set()
        result = await task
    assert result is True


async def test_failed_attempts_keep_the_existing_retry_and_shutdown_policy(monkeypatch):
    monkeypatch.setattr(auth.bcrypt, "checkpw", lambda password, _: password == b"correct")
    shutdown = Mock()
    monkeypatch.setattr(auth, "_shutdown_server", shutdown)
    connection = AuthConnection(
        [{"type": "auth", "password": "wrong"}, {"type": "auth", "password": "correct"}]
    )
    assert await auth.authenticate_connection(connection, b"hash", max_attempts=2)
    assert connection.messages == [
        {"type": "auth_required"},
        {"type": "auth_failed", "attempts_remaining": 1, "error": "Invalid password"},
        {"type": "auth_success"},
    ]
    shutdown.assert_not_called()

    connection = AuthConnection([{"type": "auth", "password": "wrong"}])
    assert not await auth.authenticate_connection(connection, b"hash", max_attempts=1)
    shutdown.assert_called_once_with()


async def test_single_auth_rejects_non_auth_messages_without_checking_password(monkeypatch):
    check = Mock()
    monkeypatch.setattr(auth.bcrypt, "checkpw", check)
    assert not await auth.validate_auth_message(AuthConnection([b"terminal input"]), b"hash")
    check.assert_not_called()
