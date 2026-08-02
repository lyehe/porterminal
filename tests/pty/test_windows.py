"""Tests for the optional Windows PTY dependency boundary."""

import pytest

from porterminal.pty import windows


def test_windows_backend_reports_a_missing_pywinpty(monkeypatch) -> None:
    monkeypatch.setattr(windows, "WinPtyProcess", None)

    with pytest.raises(RuntimeError, match="pywinpty is not installed"):
        windows.WindowsPTYBackend()
