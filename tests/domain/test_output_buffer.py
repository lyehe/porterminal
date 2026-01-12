"""Tests for OutputBuffer entity."""

from porterminal.domain.entities.output_buffer import (
    ALT_SCREEN_ENTER,
    ALT_SCREEN_EXIT,
    CLEAR_SCREEN_SEQUENCE,
    OutputBuffer,
)


class TestOutputBufferBasic:
    """Basic OutputBuffer tests."""

    def test_empty_buffer(self):
        """Test newly created buffer is empty."""
        buf = OutputBuffer()
        assert buf.is_empty
        assert buf.size == 0
        assert buf.get_all() == b""

    def test_add_data(self):
        """Test adding data to buffer."""
        buf = OutputBuffer()
        buf.add(b"hello")
        assert not buf.is_empty
        assert buf.size == 5
        assert buf.get_all() == b"hello"

    def test_add_multiple(self):
        """Test adding multiple chunks."""
        buf = OutputBuffer()
        buf.add(b"hello ")
        buf.add(b"world")
        assert buf.get_all() == b"hello world"

    def test_clear(self):
        """Test clearing buffer."""
        buf = OutputBuffer()
        buf.add(b"hello")
        buf.clear()
        assert buf.is_empty
        assert buf.get_all() == b""

    def test_clear_screen_detection(self):
        """Test clear screen sequence clears buffer."""
        buf = OutputBuffer()
        buf.add(b"old content")
        buf.add(CLEAR_SCREEN_SEQUENCE + b"new content")
        assert buf.get_all() == b"new content"

    def test_size_limit(self):
        """Test buffer respects size limit."""
        buf = OutputBuffer(max_bytes=100)
        buf.add(b"x" * 50)
        buf.add(b"y" * 60)  # Total 110, should trim
        assert buf.size <= 100


class TestAltScreenEnterExit:
    """Tests for alt-screen enter/exit handling."""

    def test_enter_alt_screen_snapshots_buffer(self):
        """Test entering alt-screen preserves normal buffer."""
        buf = OutputBuffer()
        buf.add(b"$ ls\nfile1 file2\n")

        # Enter alt-screen (vim starts)
        buf.add(b"\x1b[?1049h")

        assert buf.in_alt_screen
        # Buffer should be empty (alt-screen content not buffered yet)
        assert buf.is_empty

    def test_exit_alt_screen_restores_buffer(self):
        """Test exiting alt-screen restores normal buffer."""
        buf = OutputBuffer()
        buf.add(b"$ ls\nfile1 file2\n")

        # Enter alt-screen
        buf.add(b"\x1b[?1049h")

        # Add some vim content (this goes to alt buffer)
        buf.add(b"vim content line 1\n")
        buf.add(b"vim content line 2\n")

        # Exit alt-screen
        buf.add(b"\x1b[?1049l")

        assert not buf.in_alt_screen
        # Normal buffer should be restored
        assert b"file1" in buf.get_all()
        assert b"vim content" not in buf.get_all()

    def test_all_enter_variants(self):
        """Test all alt-screen enter escape sequences work."""
        for pattern in ALT_SCREEN_ENTER:
            buf = OutputBuffer()
            buf.add(b"normal content")
            buf.add(pattern)
            assert buf.in_alt_screen, f"Failed for pattern {pattern!r}"
            assert buf.is_empty

    def test_all_exit_variants(self):
        """Test all alt-screen exit escape sequences work."""
        for enter, exit_pattern in zip(ALT_SCREEN_ENTER, ALT_SCREEN_EXIT):
            buf = OutputBuffer()
            buf.add(b"normal content")
            buf.add(enter)
            buf.add(b"alt content")
            buf.add(exit_pattern)
            assert not buf.in_alt_screen, f"Failed for pattern {exit_pattern!r}"
            assert b"normal content" in buf.get_all()

    def test_nested_alt_screen_ignored(self):
        """Test nested alt-screen enters are ignored."""
        buf = OutputBuffer()
        buf.add(b"normal content")
        buf.add(b"\x1b[?1049h")  # Enter
        buf.add(b"\x1b[?1049h")  # Nested enter (ignored)
        assert buf.in_alt_screen
        buf.add(b"\x1b[?1049l")  # Exit
        assert not buf.in_alt_screen
        assert b"normal content" in buf.get_all()

    def test_exit_without_enter_ignored(self):
        """Test exit without enter does nothing."""
        buf = OutputBuffer()
        buf.add(b"normal content")
        buf.add(b"\x1b[?1049l")  # Exit without enter
        assert not buf.in_alt_screen
        assert b"normal content" in buf.get_all()

    def test_clear_in_alt_screen_preserves_normal(self):
        """Test clear screen in alt-screen doesn't affect normal buffer."""
        buf = OutputBuffer()
        buf.add(b"normal shell history\n")
        buf.add(b"\x1b[?1049h")  # vim starts
        buf.add(CLEAR_SCREEN_SEQUENCE + b"vim clears screen")
        buf.add(b"\x1b[?1049l")  # vim exits

        # Normal history should be preserved
        assert b"normal shell history" in buf.get_all()


class TestAltScreenVariant47:
    """Tests for DEC mode 47 (original alt-screen)."""

    def test_mode_47_enter_exit(self):
        """Test ?47h and ?47l sequences."""
        buf = OutputBuffer()
        buf.add(b"normal")
        buf.add(b"\x1b[?47h")
        assert buf.in_alt_screen
        buf.add(b"alt")
        buf.add(b"\x1b[?47l")
        assert not buf.in_alt_screen
        assert b"normal" in buf.get_all()
        assert b"alt" not in buf.get_all()


class TestAltScreenVariant1047:
    """Tests for DEC mode 1047."""

    def test_mode_1047_enter_exit(self):
        """Test ?1047h and ?1047l sequences."""
        buf = OutputBuffer()
        buf.add(b"normal")
        buf.add(b"\x1b[?1047h")
        assert buf.in_alt_screen
        buf.add(b"alt")
        buf.add(b"\x1b[?1047l")
        assert not buf.in_alt_screen
        assert b"normal" in buf.get_all()
        assert b"alt" not in buf.get_all()


class TestAltScreenVariant1049:
    """Tests for DEC mode 1049 (most common - used by vim, htop)."""

    def test_mode_1049_enter_exit(self):
        """Test ?1049h and ?1049l sequences."""
        buf = OutputBuffer()
        buf.add(b"$ whoami\nuser\n")
        buf.add(b"\x1b[?1049h")
        assert buf.in_alt_screen
        buf.add(b"htop output...")
        buf.add(b"\x1b[?1049l")
        assert not buf.in_alt_screen
        assert b"whoami" in buf.get_all()
        assert b"htop" not in buf.get_all()

    def test_realistic_vim_session(self):
        """Test realistic vim enter/exit flow."""
        buf = OutputBuffer()

        # User types some commands
        buf.add(b"$ cd project\n")
        buf.add(b"$ vim file.txt\n")

        # vim enters alt-screen
        buf.add(b"\x1b[?1049h\x1b[22;0;0t")  # With additional setup escapes

        # vim shows file content
        buf.add(b"\x1b[H\x1b[2J")  # Clear screen
        buf.add(b"Hello world\n")
        buf.add(b"~\n~\n~\n")  # vim tildes

        # User quits vim
        buf.add(b"\x1b[?1049l\x1b[23;0;0t")  # Exit alt-screen

        # Normal buffer restored
        result = buf.get_all()
        assert b"cd project" in result
        assert b"vim file.txt" in result
        assert b"Hello world" not in result
        assert b"~" not in result
