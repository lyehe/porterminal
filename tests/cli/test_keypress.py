"""Tests for the cross-platform key listener."""

from threading import Event

from porterminal.cli import keypress
from porterminal.cli.keypress import _dispatch, start_key_listener


class _FakeStdin:
    """Minimal stdin stub exposing only isatty()."""

    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class _FakeThread:
    """Records whether start() was called instead of spawning a real thread."""

    def __init__(self, log: list):
        self._log = log

    def start(self) -> None:
        self._log.append("started")


class TestDispatch:
    """Tests for key-to-handler dispatch."""

    def test_calls_matching_handler(self):
        """The handler mapped to the pressed key is invoked."""
        called = []
        _dispatch("c", {"c": lambda: called.append(True)})
        assert called == [True]

    def test_is_case_insensitive(self):
        """Uppercase input matches a lowercase handler key."""
        called = []
        _dispatch("C", {"c": lambda: called.append(True)})
        assert called == [True]

    def test_ignores_unmapped_key(self):
        """A key with no handler does nothing."""
        called = []
        _dispatch("x", {"c": lambda: called.append(True)})
        assert called == []

    def test_swallows_handler_exceptions(self):
        """A raising handler must not propagate out of the listener loop."""

        def boom():
            raise RuntimeError("boom")

        # Should not raise.
        _dispatch("c", {"c": boom})


class TestStartKeyListener:
    """Tests for listener startup guards."""

    def test_noop_when_not_a_tty(self, monkeypatch):
        """No thread is spawned and None is returned when stdin is not a TTY."""
        monkeypatch.setattr(keypress.sys, "stdin", _FakeStdin(tty=False))
        started: list = []
        monkeypatch.setattr(keypress, "Thread", lambda *a, **k: _FakeThread(started))

        result = start_key_listener(Event(), {"c": lambda: None})

        assert started == []
        assert result is None

    def test_starts_thread_when_tty(self, monkeypatch):
        """A daemon thread is spawned and returned when stdin is a terminal."""
        monkeypatch.setattr(keypress.sys, "stdin", _FakeStdin(tty=True))
        started: list = []
        monkeypatch.setattr(keypress, "Thread", lambda *a, **k: _FakeThread(started))

        result = start_key_listener(Event(), {"c": lambda: None})

        assert started == ["started"]
        assert result is not None
