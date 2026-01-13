"""Tests for PTY environment variable handling."""

import os
import sys

import pytest

from porterminal.pty.env import SAFE_ENV_VARS, build_safe_environment


class TestSafeEnvVars:
    """Tests for SAFE_ENV_VARS allowlist."""

    def test_includes_basic_path_vars(self):
        """Test that basic path variables are in allowlist."""
        assert "PATH" in SAFE_ENV_VARS
        assert "HOME" in SAFE_ENV_VARS
        assert "TEMP" in SAFE_ENV_VARS

    def test_includes_terminal_vars(self):
        """Test that terminal variables are in allowlist."""
        assert "TERM" in SAFE_ENV_VARS
        assert "LANG" in SAFE_ENV_VARS
        assert "LC_ALL" in SAFE_ENV_VARS
        assert "LC_CTYPE" in SAFE_ENV_VARS

    def test_includes_user_identity_vars(self):
        """Test that user identity variables are in allowlist (Issue #13)."""
        assert "USER" in SAFE_ENV_VARS
        assert "LOGNAME" in SAFE_ENV_VARS
        assert "SHELL" in SAFE_ENV_VARS

    def test_includes_xdg_vars(self):
        """Test that XDG directories are in allowlist (needed by Nushell/Fish)."""
        assert "XDG_CONFIG_HOME" in SAFE_ENV_VARS
        assert "XDG_DATA_HOME" in SAFE_ENV_VARS
        assert "XDG_CACHE_HOME" in SAFE_ENV_VARS
        assert "XDG_RUNTIME_DIR" in SAFE_ENV_VARS


class TestBuildSafeEnvironment:
    """Tests for build_safe_environment function."""

    def test_sets_term_to_xterm_256color(self):
        """Test that TERM is always set to xterm-256color."""
        env = build_safe_environment()
        assert env["TERM"] == "xterm-256color"

    def test_sets_term_session_type(self):
        """Test that TERM_SESSION_TYPE is set for audit trail."""
        env = build_safe_environment()
        assert env["TERM_SESSION_TYPE"] == "remote-web"

    def test_includes_path(self):
        """Test that PATH is included if present."""
        env = build_safe_environment()
        if "PATH" in os.environ:
            assert "PATH" in env

    def test_excludes_unlisted_vars(self, monkeypatch):
        """Test that unlisted variables are excluded."""
        monkeypatch.setenv("MY_CUSTOM_VAR", "secret")
        env = build_safe_environment()
        assert "MY_CUSTOM_VAR" not in env

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_includes_shell_var(self, monkeypatch):
        """Test that SHELL variable is passed through (Issue #13)."""
        monkeypatch.setenv("SHELL", "/usr/bin/nu")
        env = build_safe_environment()
        assert env.get("SHELL") == "/usr/bin/nu"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_includes_user_var(self, monkeypatch):
        """Test that USER variable is passed through."""
        monkeypatch.setenv("USER", "testuser")
        env = build_safe_environment()
        assert env.get("USER") == "testuser"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_includes_xdg_config_home(self, monkeypatch):
        """Test that XDG_CONFIG_HOME is passed through (needed by Nushell)."""
        monkeypatch.setenv("XDG_CONFIG_HOME", "/home/user/.config")
        env = build_safe_environment()
        assert env.get("XDG_CONFIG_HOME") == "/home/user/.config"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_includes_xdg_data_home(self, monkeypatch):
        """Test that XDG_DATA_HOME is passed through (needed by Nushell)."""
        monkeypatch.setenv("XDG_DATA_HOME", "/home/user/.local/share")
        env = build_safe_environment()
        assert env.get("XDG_DATA_HOME") == "/home/user/.local/share"


class TestNushellEnvironment:
    """Tests specifically for Nushell compatibility (Issue #13)."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_nushell_required_vars_in_allowlist(self):
        """Test that all variables Nushell needs are in the allowlist."""
        # Nushell needs these for proper operation
        nushell_required = {
            "HOME",  # Home directory
            "USER",  # Current user
            "SHELL",  # Shell path
            "PATH",  # Executable path
            "TERM",  # Terminal type
            "XDG_CONFIG_HOME",  # Config directory (~/.config/nushell)
            "XDG_DATA_HOME",  # Data directory (history, etc.)
        }
        for var in nushell_required:
            assert var in SAFE_ENV_VARS, f"{var} missing from SAFE_ENV_VARS"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_nushell_env_complete(self, monkeypatch):
        """Test that a complete Nushell environment can be built."""
        # Simulate a typical Unix environment with Nushell
        monkeypatch.setenv("HOME", "/home/testuser")
        monkeypatch.setenv("USER", "testuser")
        monkeypatch.setenv("SHELL", "/usr/bin/nu")
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        monkeypatch.setenv("XDG_CONFIG_HOME", "/home/testuser/.config")
        monkeypatch.setenv("XDG_DATA_HOME", "/home/testuser/.local/share")

        env = build_safe_environment()

        # All critical vars should be present
        assert env["HOME"] == "/home/testuser"
        assert env["USER"] == "testuser"
        assert env["SHELL"] == "/usr/bin/nu"
        assert env["PATH"] == "/usr/bin:/bin"
        assert env["XDG_CONFIG_HOME"] == "/home/testuser/.config"
        assert env["XDG_DATA_HOME"] == "/home/testuser/.local/share"
        assert env["TERM"] == "xterm-256color"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_nushell_can_spawn(self):
        """Test that Nushell can be spawned with the safe environment."""
        import shutil

        nu_path = shutil.which("nu")
        if not nu_path:
            pytest.skip("nushell not installed")

        # Just verify the environment building doesn't crash
        # Actual PTY spawning is tested elsewhere
        env = build_safe_environment()
        assert "TERM" in env
        assert "PATH" in env
