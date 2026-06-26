"""Tests for the cross-platform clipboard helper."""

import subprocess

from porterminal.cli import clipboard
from porterminal.cli.clipboard import copy_to_clipboard
from porterminal.cli.share import build_agent_share_text


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
        assert calls == [["pbcopy"]]

    def test_linux_tries_tools_in_order_until_success(self, monkeypatch):
        """Linux tries wl-copy, then xclip, then xsel, stopping at first success."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")
        attempted = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            if cmd[0] in ("wl-copy", "xclip"):
                raise FileNotFoundError(cmd[0])
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is True
        assert attempted == ["wl-copy", "xclip", "xsel"]

    def test_linux_returns_false_when_no_tool_available(self, monkeypatch):
        """Linux returns False when none of the clipboard tools exist."""
        monkeypatch.setattr(clipboard.sys, "platform", "linux")

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is False

    def test_returns_false_on_command_failure(self, monkeypatch):
        """A non-zero exit (CalledProcessError) is reported as failure, not raised."""
        monkeypatch.setattr(clipboard.sys, "platform", "darwin")

        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

        assert copy_to_clipboard("text") is False

    def test_returns_false_on_timeout(self, monkeypatch):
        """A timeout is reported as failure, not raised."""
        monkeypatch.setattr(clipboard.sys, "platform", "win32")

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
