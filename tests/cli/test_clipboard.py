"""Tests for the cross-platform clipboard helper."""

import base64
import subprocess

from porterminal.cli import clipboard
from porterminal.cli.clipboard import copy_to_clipboard
from porterminal.cli.share import build_agent_share_text


class _FakeStdout:
    def __init__(self, *, tty: bool = True) -> None:
        self.tty = tty
        self.writes: list[str] = []
        self.flushed = False

    def isatty(self) -> bool:
        return self.tty

    def write(self, text: str) -> None:
        self.writes.append(text)

    def flush(self) -> None:
        self.flushed = True


class TestCopyToClipboard:
    """Tests for copy_to_clipboard platform dispatch and graceful failure."""

    def test_windows_uses_clip(self, monkeypatch):
        """Windows pipes the text into `clip`."""
        monkeypatch.setattr(clipboard.sys, "platform", "win32")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs.get("input")))
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("https://example.com") is True
        assert calls == [(["clip"], "https://example.com")]

    def test_macos_uses_pbcopy(self, monkeypatch):
        """macOS pipes the text into `pbcopy`."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is True
        assert calls == [["/usr/bin/pbcopy"]]

    def test_macos_retries_transient_pbcopy_failure(self, monkeypatch):
        """macOS retries pbcopy before reporting the clipboard as unavailable."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        monkeypatch.setattr(clipboard, "_MACOS_RETRY_DELAYS_SECONDS", (0,))
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 3))
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
        monkeypatch.setattr(clipboard.time, "sleep", lambda _delay: None)

        assert copy_to_clipboard("text") is True
        assert calls == [["/usr/bin/pbcopy"], ["/usr/bin/pbcopy"]]

    def test_linux_tries_tools_in_order_until_success(self, monkeypatch):
        """Linux tries wl-copy, then xclip, then xsel, stopping at first success."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        monkeypatch.delenv("WSL_INTEROP", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        attempted = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            if cmd[0] in ("wl-copy", "xclip"):
                raise FileNotFoundError(cmd[0])
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is True
        assert attempted == ["wl-copy", "xclip", "xsel"]

    def test_linux_prefers_ubuntu_wayland_then_x11_fallbacks(self, monkeypatch):
        """Ubuntu Wayland tries wl-copy before X11 fallback tools."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        attempted = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            if cmd[0] == "wl-copy":
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is True
        assert attempted == ["wl-copy", "xclip"]

    def test_linux_prefers_ubuntu_x11_tools(self, monkeypatch):
        """Ubuntu X11 tries X clipboard tools before the Wayland fallback."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        attempted = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            if cmd[0] == "xclip":
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is True
        assert attempted == ["xclip", "xsel"]

    def test_linux_wsl_uses_windows_clipboard_first(self, monkeypatch):
        """Ubuntu on WSL can copy through the Windows clipboard bridge."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        attempted = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is True
        assert attempted == ["clip.exe"]

    def test_linux_retries_transient_clipboard_failure(self, monkeypatch):
        """Linux retries the full fallback list before reporting failure."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard, "_LINUX_RETRY_DELAYS_SECONDS", (0,))
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        attempted = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            if len(attempted) < 4:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
        monkeypatch.setattr(clipboard.time, "sleep", lambda _delay: None)

        assert copy_to_clipboard("text") is True
        assert attempted == ["wl-copy", "xclip", "xsel", "wl-copy"]

    def test_linux_returns_false_when_no_tool_available(self, monkeypatch):
        """Linux returns False when none of the clipboard tools exist."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard, "_LINUX_RETRY_DELAYS_SECONDS", ())
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is False

    def test_terminal_clipboard_fallback_writes_osc52(self, monkeypatch):
        """OSC52 is used as an interactive-terminal fallback."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard, "_LINUX_RETRY_DELAYS_SECONDS", ())
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("PORTERMINAL_DISABLE_OSC52_CLIPBOARD", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        fake_stdout = _FakeStdout()
        monkeypatch.setattr(clipboard.sys, "stdout", fake_stdout)

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("hello") is True
        encoded = base64.b64encode(b"hello").decode("ascii")
        assert fake_stdout.writes == [f"\x1b]52;c;{encoded}\a"]
        assert fake_stdout.flushed is True

    def test_terminal_clipboard_fallback_can_be_disabled(self, monkeypatch):
        """The OSC52 fallback can be disabled for terminals that dislike it."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard, "_LINUX_RETRY_DELAYS_SECONDS", ())
        monkeypatch.setenv("PORTERMINAL_DISABLE_OSC52_CLIPBOARD", "1")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        fake_stdout = _FakeStdout()
        monkeypatch.setattr(clipboard.sys, "stdout", fake_stdout)

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("hello") is False
        assert fake_stdout.writes == []

    def test_returns_false_on_command_failure(self, monkeypatch):
        """A non-zero exit (CalledProcessError) is reported as failure, not raised."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))

        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is False

    def test_returns_false_on_timeout(self, monkeypatch):
        """A timeout is reported as failure, not raised."""
        monkeypatch.setattr(clipboard.sys, "platform", "win32")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 3)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is False


class TestAgentShareText:
    """Tests for the agent-ready text copied by the `c` hotkey."""

    def test_includes_base_url_mcp_and_llms(self):
        url = "https://example.trycloudflare.com"
        text = build_agent_share_text(url)

        assert "Use this Porterminal link to control the remote computer:" in text
        assert url in text
        assert f"{url}/mcp" in text
        assert f"{url}/api/agent/run" in text
        assert f"{url}/llms.txt" in text
        assert "Agent instructions:" in text
        assert "do not ask the user to configure MCP" in text
        assert 'ask one short question: "What should I run?"' in text

    def test_trims_trailing_slash_before_endpoint_paths(self):
        text = build_agent_share_text("https://example.trycloudflare.com/")

        assert "https://example.trycloudflare.com/mcp" in text
        assert "https://example.trycloudflare.com/api/agent/run" in text
        assert "https://example.trycloudflare.com//mcp" not in text
