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

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_get_user_shell_id_returns_fish(self, monkeypatch):
        """Test that $SHELL pointing to fish returns 'fish'."""
        import shutil

        fish_path = shutil.which("fish")
        if not fish_path:
            pytest.skip("fish not installed")

        monkeypatch.setenv("SHELL", fish_path)
        detector = ShellDetector()

        result = detector._get_user_shell_id()

        assert result == "fish"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_get_user_shell_id_returns_zsh(self, monkeypatch):
        """Test that $SHELL pointing to zsh returns 'zsh'."""
        import shutil

        zsh_path = shutil.which("zsh")
        if not zsh_path:
            pytest.skip("zsh not installed")

        monkeypatch.setenv("SHELL", zsh_path)
        detector = ShellDetector()

        result = detector._get_user_shell_id()

        assert result == "zsh"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_get_user_shell_id_returns_bash(self, monkeypatch):
        """Test that $SHELL pointing to bash returns 'bash'."""
        import shutil

        bash_path = shutil.which("bash")
        if not bash_path:
            pytest.skip("bash not installed")

        monkeypatch.setenv("SHELL", bash_path)
        detector = ShellDetector()

        result = detector._get_user_shell_id()

        assert result == "bash"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_get_user_shell_id_returns_none_for_nonexistent(self, monkeypatch):
        """Test that non-existent shell returns None."""
        monkeypatch.setenv("SHELL", "/usr/bin/nonexistent-shell-xyz")
        detector = ShellDetector()

        result = detector._get_user_shell_id()

        assert result is None

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_get_user_shell_id_returns_name_for_unknown_shell(self, monkeypatch, tmp_path):
        """Test that unknown but existing shell returns its name."""
        # Create a fake shell executable
        fake_shell = tmp_path / "nu"
        fake_shell.touch()
        fake_shell.chmod(0o755)

        monkeypatch.setenv("SHELL", str(fake_shell))
        detector = ShellDetector()

        result = detector._get_user_shell_id()

        assert result == "nu"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_create_shell_from_env_unknown_shell(self, monkeypatch, tmp_path):
        """Test that _create_shell_from_env works for unknown shells."""
        # Create a fake nushell executable
        fake_shell = tmp_path / "nu"
        fake_shell.touch()
        fake_shell.chmod(0o755)

        monkeypatch.setenv("SHELL", str(fake_shell))
        detector = ShellDetector()

        shell = detector._create_shell_from_env()

        assert shell is not None
        assert shell.id == "nu"
        assert shell.name == "Nu"  # Capitalized
        assert shell.command == str(fake_shell)
        assert shell.args == ()  # No special args for unknown shells

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_create_shell_from_env_known_shell(self, monkeypatch):
        """Test that _create_shell_from_env uses correct args for known shells."""
        import shutil

        bash_path = shutil.which("bash")
        if not bash_path:
            pytest.skip("bash not installed")

        monkeypatch.setenv("SHELL", bash_path)
        detector = ShellDetector()

        shell = detector._create_shell_from_env()

        assert shell is not None
        assert shell.id == "bash"
        assert shell.name == "Bash"
        assert shell.args == ("--login",)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_detect_shells_includes_unknown_user_shell(self, monkeypatch, tmp_path):
        """Test that detect_shells includes user's unknown $SHELL."""
        # Create a fake nushell executable
        fake_shell = tmp_path / "nu"
        fake_shell.touch()
        fake_shell.chmod(0o755)

        monkeypatch.setenv("SHELL", str(fake_shell))
        detector = ShellDetector()

        shells = detector.detect_shells()
        shell_ids = [s.id for s in shells]

        # User's shell should be included and first in the list
        assert "nu" in shell_ids
        assert shells[0].id == "nu"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_detect_shells_does_not_duplicate_known_shell(self, monkeypatch):
        """Test that detect_shells doesn't duplicate a known shell from $SHELL."""
        import shutil

        bash_path = shutil.which("bash")
        if not bash_path:
            pytest.skip("bash not installed")

        monkeypatch.setenv("SHELL", bash_path)
        detector = ShellDetector()

        shells = detector.detect_shells()
        bash_shells = [s for s in shells if s.id == "bash"]

        # Should only have one bash entry
        assert len(bash_shells) == 1

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_get_user_shell_id_returns_none_when_unset(self, monkeypatch):
        """Test that missing $SHELL returns None."""
        monkeypatch.delenv("SHELL", raising=False)
        detector = ShellDetector()

        result = detector._get_user_shell_id()

        assert result is None

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_macos_default_uses_user_shell(self, monkeypatch):
        """Test that macOS default respects $SHELL."""
        import shutil

        fish_path = shutil.which("fish")
        if not fish_path:
            pytest.skip("fish not installed")

        monkeypatch.setenv("SHELL", fish_path)
        detector = ShellDetector()

        result = detector._get_macos_default()

        assert result == "fish"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_linux_default_uses_user_shell(self, monkeypatch):
        """Test that Linux default respects $SHELL."""
        import shutil

        fish_path = shutil.which("fish")
        if not fish_path:
            pytest.skip("fish not installed")

        monkeypatch.setenv("SHELL", fish_path)
        detector = ShellDetector()

        result = detector._get_linux_default()

        assert result == "fish"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_fish_detected_when_installed(self):
        """Test that fish shell is detected when installed on system."""
        import shutil

        if not shutil.which("fish"):
            pytest.skip("fish not installed")

        detector = ShellDetector()
        shells = detector.detect_shells()
        shell_ids = [s.id for s in shells]

        assert "fish" in shell_ids

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_default_shell_respects_shell_env(self, monkeypatch):
        """Test that get_default_shell_id() respects $SHELL (PR #12)."""
        import shutil

        fish_path = shutil.which("fish")
        if not fish_path:
            pytest.skip("fish not installed")

        # Set $SHELL to fish (simulates user's login shell)
        monkeypatch.setenv("SHELL", fish_path)

        detector = ShellDetector()
        default_id = detector.get_default_shell_id()

        assert default_id == "fish"

    # Issue #13: Nushell support tests
    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_nushell_detected_via_shell_env(self, monkeypatch):
        """Test that Nushell is detected when set as $SHELL (Issue #13)."""
        import shutil

        nu_path = shutil.which("nu")
        if not nu_path:
            pytest.skip("nushell not installed")

        monkeypatch.setenv("SHELL", nu_path)
        detector = ShellDetector()

        # Should return "nu" as the shell ID
        result = detector._get_user_shell_id()
        assert result == "nu"

        # Should be added to detected shells
        shells = detector.detect_shells()
        shell_ids = [s.id for s in shells]
        assert "nu" in shell_ids

        # Should be the default shell
        default_id = detector.get_default_shell_id()
        assert default_id == "nu"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_nushell_shell_command_created_correctly(self, monkeypatch):
        """Test that Nushell ShellCommand has correct properties (Issue #13)."""
        import shutil

        nu_path = shutil.which("nu")
        if not nu_path:
            pytest.skip("nushell not installed")

        monkeypatch.setenv("SHELL", nu_path)
        detector = ShellDetector()

        shell = detector._create_shell_from_env()

        assert shell is not None
        assert shell.id == "nu"
        assert shell.name == "Nu"
        assert shell.command == nu_path
        assert shell.args == ()  # No special args for nushell
