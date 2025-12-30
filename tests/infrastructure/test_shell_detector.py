"""Tests for ShellDetector."""

import sys

import pytest

from porterminal.infrastructure.config import ShellDetector


class TestShellDetector:
    """Tests for ShellDetector."""

    def test_detect_shells_returns_list(self):
        """Test that detect_shells returns a list."""
        detector = ShellDetector()

        shells = detector.detect_shells()

        assert isinstance(shells, list)
        # Should find at least one shell on any system
        assert len(shells) >= 1

    def test_detected_shells_have_required_fields(self):
        """Test that detected shells have required fields."""
        detector = ShellDetector()

        shells = detector.detect_shells()

        for shell in shells:
            assert shell.id
            assert shell.name
            assert shell.command
            assert isinstance(shell.args, tuple)

    def test_get_default_shell_id(self):
        """Test that get_default_shell_id returns a string."""
        detector = ShellDetector()

        default_id = detector.get_default_shell_id()

        assert isinstance(default_id, str)
        assert len(default_id) > 0

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_windows_shells_detected(self):
        """Test that Windows shells are detected on Windows."""
        detector = ShellDetector()

        shells = detector.detect_shells()
        shell_ids = [s.id for s in shells]

        # Should have at least cmd or powershell
        assert "cmd" in shell_ids or "powershell" in shell_ids or "pwsh" in shell_ids

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_unix_shells_detected(self):
        """Test that Unix shells are detected on Unix."""
        detector = ShellDetector()

        shells = detector.detect_shells()
        shell_ids = [s.id for s in shells]

        # Should have at least bash or sh
        assert "bash" in shell_ids or "sh" in shell_ids

    def test_to_command_list(self):
        """Test that shells can produce command lists."""
        detector = ShellDetector()

        shells = detector.detect_shells()

        for shell in shells:
            cmd_list = shell.to_command_list()
            assert isinstance(cmd_list, list)
            assert len(cmd_list) >= 1
            assert cmd_list[0] == shell.command
