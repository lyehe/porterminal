"""Tests for copy-mode rendering in the startup screen (the privacy invariant)."""

from porterminal.cli import display

# A distinctive, short token that won't wrap; if the URL leaked, it would appear.
_URL = "https://abcxyz123.example.com"
_TOKEN = "abcxyz123"


def _render(**kwargs) -> str:
    with display.console.capture() as cap:
        display.display_startup_screen(_URL, **kwargs)
    return cap.get()


class TestCopyModeRendering:
    """In copy mode the plaintext URL must never be printed."""

    def test_copy_mode_hides_url_and_shows_hint(self):
        """copy_mode hides the URL and shows the 'press c to copy' hint."""
        out = _render(copy_mode=True)
        assert _TOKEN not in out
        assert "copy URL" in out

    def test_without_copy_mode_shows_url(self):
        """Default (background / non-interactive) still prints the URL."""
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
