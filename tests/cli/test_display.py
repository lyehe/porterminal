"""Tests for copy-mode rendering in the startup screen (the privacy invariant)."""

from rich.text import Text

from porterminal.cli import display

# A distinctive, short token that won't wrap; if the URL leaked, it would appear.
_URL = "https://abcxyz123.example.com"
_TOKEN = "abcxyz123"


def _render(**kwargs) -> str:
    with display.console.capture() as cap:
        display.display_startup_screen(_URL, **kwargs)
    return cap.get()


def _plain(ansi: str) -> str:
    return Text.from_ansi(ansi).plain


class TestCopyModeRendering:
    """In copy mode the plaintext URL must never be printed."""

    def test_copy_mode_hides_url_and_shows_hint(self):
        """copy_mode hides the URL and shows the agent-share hotkey hint."""
        out = _render(copy_mode=True)
        assert _TOKEN not in out
        assert display.COPY_AGENT_HINT in out
        assert display.COPY_URL_HINT in out

    def test_without_copy_mode_shows_url(self):
        """Non-interactive mode still prints the URL."""
        out = _render(copy_mode=False)
        assert _TOKEN in out

    def test_copy_status_replaces_hint_and_still_hides_url(self):
        """A copy_status line replaces the hint without revealing the URL."""
        out = _render(copy_mode=True, copy_status="COPIED-OK")
        assert "COPIED-OK" in out
        assert _TOKEN not in out

    def test_copy_mode_hides_url_even_when_qr_is_hidden(self):
        """Hiding the QR (post-connect) must not fall back to printing the URL."""
        out = _render(copy_mode=True, show_url=False)
        assert _TOKEN not in out


class TestPromptScreen:
    """'s' shows the agent prompt as plain selectable text; 'q' hint closes it."""

    def test_copy_mode_shows_the_prompt_hint(self):
        out = _plain(_render(copy_mode=True))
        assert display.SHOW_PROMPT_HINT in out
        assert "Press 's'" in display.SHOW_PROMPT_HINT

    def test_mcp_only_copy_mode_shows_the_prompt_hint(self):
        out = _plain(_render(copy_mode=True, mcp_only=True))
        assert "Press 's': show agent prompt" in out

    def test_prompt_screen_prints_text_verbatim_with_close_hint(self):
        text = "Use this link: https://abcxyz123.example.com/code/\n- [step] one\n- step two"
        with display.console.capture() as cap:
            display.display_prompt_screen(text)
        out = _plain(cap.get())
        assert "https://abcxyz123.example.com/code/" in out
        assert "- [step] one" in out  # square brackets must not be eaten as Rich markup
        assert "- step two" in out
        assert "Press 'q' to close" in out
