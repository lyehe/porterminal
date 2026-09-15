"""Tests for the cross-platform clipboard helper."""

import base64
import subprocess
import sys
import textwrap

from porterminal.cli import clipboard
from porterminal.cli.clipboard import CopyResult, clipboard_install_hint, copy_to_clipboard
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

        assert copy_to_clipboard("https://example.com") is CopyResult.COPIED
        assert calls == [(["clip"], "https://example.com")]

    def test_macos_uses_pbcopy(self, monkeypatch):
        """macOS pipes the text into `pbcopy`."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is CopyResult.COPIED
        assert calls == [["/usr/bin/pbcopy"]]

    def test_macos_retries_transient_pbcopy_failure(self, monkeypatch):
        """macOS retries a failed pbcopy run before reporting the clipboard as unavailable."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        monkeypatch.setattr(clipboard, "_MACOS_RETRY_DELAYS_SECONDS", (0,))
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
        monkeypatch.setattr(clipboard.time, "sleep", lambda _delay: None)

        assert copy_to_clipboard("text") is CopyResult.COPIED
        assert calls == [["/usr/bin/pbcopy"], ["/usr/bin/pbcopy"]]

    def test_macos_does_not_retry_when_pbcopy_hangs(self, monkeypatch):
        """A hang is not transient; retrying would only multiply the freeze."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))
        calls = []
        sleeps = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 3))

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
        monkeypatch.setattr(clipboard.time, "sleep", sleeps.append)

        assert copy_to_clipboard("text") is CopyResult.UNAVAILABLE
        assert calls == [["/usr/bin/pbcopy"]]
        assert sleeps == []

    def test_macos_does_not_retry_when_pbcopy_is_missing(self, monkeypatch):
        """A missing binary is not a transient failure; retrying only delays the answer."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))
        attempted = []
        sleeps = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd)
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
        monkeypatch.setattr(clipboard.time, "sleep", sleeps.append)

        assert copy_to_clipboard("text") is CopyResult.UNAVAILABLE
        assert attempted == [["/usr/bin/pbcopy"]]
        assert sleeps == []

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

        assert copy_to_clipboard("text") is CopyResult.COPIED
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

        assert copy_to_clipboard("text") is CopyResult.COPIED
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

        assert copy_to_clipboard("text") is CopyResult.COPIED
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

        assert copy_to_clipboard("text") is CopyResult.COPIED
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

        assert copy_to_clipboard("text") is CopyResult.COPIED
        assert attempted == ["wl-copy", "xclip", "xsel", "wl-copy"]

    def test_linux_does_not_retry_when_no_tool_is_installed(self, monkeypatch):
        """A missing binary is not a transient failure; retrying only delays the answer."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        attempted = []
        sleeps = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
        monkeypatch.setattr(clipboard.time, "sleep", sleeps.append)

        assert copy_to_clipboard("text") is CopyResult.UNAVAILABLE
        assert attempted == ["wl-copy", "xclip", "xsel"]
        assert sleeps == []

    def test_linux_stops_at_the_first_hung_tool(self, monkeypatch):
        """A hung tool means a broken session: bail out instead of trying and retrying."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        attempted = []
        sleeps = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            if cmd[0] == "wl-copy":
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 3))
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
        monkeypatch.setattr(clipboard.time, "sleep", sleeps.append)

        assert copy_to_clipboard("text") is CopyResult.UNAVAILABLE
        assert attempted == ["wl-copy"]
        assert sleeps == []

    def test_returns_unavailable_when_text_cannot_be_encoded(self, monkeypatch):
        """An encoding error must become feedback, not an exception the key thread swallows."""
        monkeypatch.setattr(clipboard.sys, "platform", "win32")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))

        def fake_run(cmd, **kwargs):
            raise UnicodeEncodeError("charmap", "☃", 0, 1, "character maps to <undefined>")

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("☃") is CopyResult.UNAVAILABLE

    def test_terminal_clipboard_fallback_writes_osc52(self, monkeypatch):
        """OSC52 is used as an interactive-terminal fallback, reported as unconfirmed."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard, "_LINUX_RETRY_DELAYS_SECONDS", ())
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("PORTERMINAL_DISABLE_OSC52_CLIPBOARD", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        fake_stdout = _FakeStdout()
        monkeypatch.setattr(clipboard.sys, "stdout", fake_stdout)

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("hello") is CopyResult.SENT_TO_TERMINAL
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

        assert copy_to_clipboard("hello") is CopyResult.UNAVAILABLE
        assert fake_stdout.writes == []

    def test_pipe_to_returns_when_tool_daemonizes_holding_stdio(self, tmp_path):
        """wl-copy and xclip fork a daemon that inherits stdout/stderr and keeps
        them open until the clipboard is replaced. _pipe_to must not wait for
        that daemon, or every call hits the timeout and reports failure. The
        daemon holds the pipe longer than the timeout, so the old
        capture_output code times out here while DEVNULL returns at once."""
        tool = tmp_path / "fake_wl_copy.py"
        tool.write_text(
            textwrap.dedent(
                """
                import subprocess, sys

                sys.stdin.read()
                subprocess.Popen(
                    [sys.executable, "-I", "-c", "import time; time.sleep(10)"],
                    stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr,
                )
                """
            ),
            encoding="utf-8",
        )

        assert clipboard._pipe_to([sys.executable, "-I", str(tool)], "text", timeout=3) is True

    def test_terminal_clipboard_fallback_skipped_in_vte_terminals(self, monkeypatch):
        """VTE-based terminals (GNOME Terminal, Tilix, ...) ignore OSC52, so claiming
        success there would hide the URL behind a false "Copied" message."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard, "_LINUX_RETRY_DELAYS_SECONDS", ())
        monkeypatch.setenv("VTE_VERSION", "7600")
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

        assert copy_to_clipboard("hello") is CopyResult.UNAVAILABLE
        assert fake_stdout.writes == []

    def test_returns_unavailable_on_command_failure(self, monkeypatch):
        """A non-zero exit (CalledProcessError) is reported as UNAVAILABLE, not raised."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))

        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is CopyResult.UNAVAILABLE

    def test_returns_unavailable_on_timeout(self, monkeypatch):
        """A timeout is reported as UNAVAILABLE, not raised."""
        monkeypatch.setattr(clipboard.sys, "platform", "win32")
        monkeypatch.setattr(clipboard.sys, "stdout", _FakeStdout(tty=False))

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 3)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is CopyResult.UNAVAILABLE


class TestClipboardInstallHint:
    """Tests for the install hint shown when Linux has no clipboard tool."""

    @staticmethod
    def _linux_desktop(monkeypatch, *, session: str) -> None:
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        if session == "wayland":
            monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        elif session == "x11":
            monkeypatch.setenv("DISPLAY", ":0")

    def test_wayland_without_tools_suggests_wl_clipboard(self, monkeypatch):
        """Stock Ubuntu (Wayland, no tools) is told to install wl-clipboard."""
        self._linux_desktop(monkeypatch, session="wayland")
        monkeypatch.setattr(clipboard.shutil, "which", lambda _name: None)

        assert clipboard_install_hint() == "Install wl-clipboard to enable clipboard copy"

    def test_x11_without_tools_suggests_xclip(self, monkeypatch):
        """An X11 session without tools is told to install xclip or xsel."""
        self._linux_desktop(monkeypatch, session="x11")
        monkeypatch.setattr(clipboard.shutil, "which", lambda _name: None)

        assert clipboard_install_hint() == "Install xclip or xsel to enable clipboard copy"

    def test_no_hint_when_a_tool_is_installed(self, monkeypatch):
        """If a tool exists, the failure is not an install problem."""
        self._linux_desktop(monkeypatch, session="wayland")
        monkeypatch.setattr(
            clipboard.shutil, "which", lambda name: "/usr/bin/xsel" if name == "xsel" else None
        )

        assert clipboard_install_hint() is None

    def test_no_hint_without_a_display(self, monkeypatch):
        """Headless/SSH sessions have no display, so no clipboard tool could help."""
        self._linux_desktop(monkeypatch, session="none")
        monkeypatch.setattr(clipboard.shutil, "which", lambda _name: None)

        assert clipboard_install_hint() is None

    def test_no_hint_on_platforms_with_builtin_tools(self, monkeypatch):
        """Windows, macOS and WSL always ship a clipboard command."""
        monkeypatch.setattr(clipboard.shutil, "which", lambda _name: None)

        monkeypatch.setattr(clipboard.sys, "platform", "win32")
        assert clipboard_install_hint() is None
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")
        assert clipboard_install_hint() is None
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        monkeypatch.setattr(clipboard, "_is_wsl", lambda: True)
        assert clipboard_install_hint() is None


class TestCopyResult:
    """Truthiness must mean "confirmed", so a bool check can never lie."""

    def test_only_a_confirmed_copy_is_truthy(self):
        assert bool(CopyResult.COPIED) is True
        assert bool(CopyResult.SENT_TO_TERMINAL) is False
        assert bool(CopyResult.UNAVAILABLE) is False


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
