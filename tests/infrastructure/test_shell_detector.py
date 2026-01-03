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

    def test_slugify(self):
        """Test that slugify converts names to valid IDs."""
        detector = ShellDetector()

        assert detector._slugify("PowerShell") == "powershell"
        assert (
            detector._slugify("Developer PowerShell for VS 2022")
            == "developer-powershell-for-vs-2022"
        )
        assert detector._slugify("Git Bash") == "git-bash"
        assert detector._slugify("  Spaces  ") == "spaces"
        assert detector._slugify("CMD!@#$%") == "cmd"

    def test_parse_commandline_simple(self):
        """Test parsing simple commandlines."""
        detector = ShellDetector()

        cmd, args = detector._parse_commandline("cmd.exe")
        assert cmd == "cmd.exe"
        assert args == []

        cmd, args = detector._parse_commandline("pwsh.exe -NoLogo")
        assert cmd == "pwsh.exe"
        assert args == ["-NoLogo"]

    def test_parse_commandline_with_quotes(self):
        """Test parsing commandlines with quoted arguments."""
        detector = ShellDetector()

        cmd, args = detector._parse_commandline('cmd.exe /k "vcvars64.bat"')
        assert cmd == "cmd.exe"
        assert "/k" in args

    def test_parse_commandline_wsl(self):
        """Test parsing WSL commandlines."""
        detector = ShellDetector()

        cmd, args = detector._parse_commandline("wsl.exe -d Ubuntu")
        assert cmd == "wsl.exe"
        assert args == ["-d", "Ubuntu"]

    def test_merge_candidates_deduplicates(self):
        """Test that merge_candidates removes duplicates."""
        detector = ShellDetector()

        primary = [("PowerShell", "ps", "powershell.exe", [])]
        secondary = [
            ("PS", "powershell", "powershell.exe", ["-NoLogo"]),
            ("CMD", "cmd", "cmd.exe", []),
        ]

        result = detector._merge_candidates(primary, secondary)

        # Should have PowerShell from primary and CMD from secondary
        assert len(result) == 2
        assert result[0][0] == "PowerShell"  # Primary version kept
        assert result[1][0] == "CMD"

    def test_merge_candidates_empty_primary(self):
        """Test merge with empty primary list."""
        detector = ShellDetector()

        primary = []
        secondary = [("CMD", "cmd", "cmd.exe", [])]

        result = detector._merge_candidates(primary, secondary)

        assert len(result) == 1
        assert result[0][0] == "CMD"

    def test_strip_json_comments_preserves_urls(self):
        """Test that URLs with // are preserved."""
        detector = ShellDetector()

        content = '{"url": "https://example.com/path"}'
        result = detector._strip_json_comments(content)

        assert result == content

    def test_strip_json_comments_removes_line_comments(self):
        """Test that single-line comments are removed."""
        detector = ShellDetector()

        content = '{\n  "key": "value" // this is a comment\n}'
        result = detector._strip_json_comments(content)

        assert "//" not in result
        assert "this is a comment" not in result
        assert '"key": "value"' in result

    def test_strip_json_comments_removes_block_comments(self):
        """Test that block comments are removed."""
        detector = ShellDetector()

        content = '{\n  /* comment */\n  "key": "value"\n}'
        result = detector._strip_json_comments(content)

        assert "/*" not in result
        assert "*/" not in result
        assert "comment" not in result
        assert '"key": "value"' in result
