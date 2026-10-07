"""Tests for the optional Windows PTY dependency boundary."""

import pytest

from porterminal.pty import windows


def test_windows_backend_reports_a_missing_pywinpty(monkeypatch) -> None:
    monkeypatch.setattr(windows, "WinPtyProcess", None)

    with pytest.raises(RuntimeError, match="pywinpty is not installed"):
        windows.WindowsPTYBackend()


class RecordingProcess:
    def __init__(self) -> None:
        self.writes: list[str] = []

    @classmethod
    def spawn(cls, *args, **kwargs):
        return cls()

    def write(self, text: str) -> None:
        self.writes.append(text)

    def isalive(self) -> bool:
        return False


@pytest.mark.parametrize("text", ["\u00e9", "\u20ac", "\U0001f642"])
def test_windows_input_preserves_utf8_at_every_byte_boundary(monkeypatch, text):
    monkeypatch.setattr(windows, "WinPtyProcess", RecordingProcess)
    encoded = text.encode()
    for boundary in range(1, len(encoded)):
        backend = windows.WindowsPTYBackend()
        backend.spawn(["fake"], {}, None, 24, 80)
        backend.write(encoded[:boundary])
        backend.write(encoded[boundary:])
        assert "".join(backend._pty.writes) == text


async def test_agent_input_chunking_keeps_unicode_on_windows(monkeypatch):
    from porterminal.infrastructure.web.agent_connection import AgentSessionConnection

    monkeypatch.setattr(windows, "WinPtyProcess", RecordingProcess)
    backend = windows.WindowsPTYBackend()
    backend.spawn(["fake"], {}, None, 24, 80)
    connection = AgentSessionConnection(80, 24)
    text = "x" * 4095 + "\U0001f642"
    await connection.push_input(text.encode())
    backend.write(await connection.receive())
    backend.write(await connection.receive())
    assert "".join(backend._pty.writes) == text


def test_windows_decoder_does_not_carry_input_into_a_new_process(monkeypatch):
    monkeypatch.setattr(windows, "WinPtyProcess", RecordingProcess)
    backend = windows.WindowsPTYBackend()
    backend.spawn(["fake"], {}, None, 24, 80)
    backend.write(b"\xf0\x9f")
    backend.close()
    backend.spawn(["fake"], {}, None, 24, 80)
    backend.write(b"new session")
    assert backend._pty.writes == ["new session"]
