"""Tests for updater module."""

from porterminal.updater import _detect_install_method, _is_newer


class TestIsNewer:
    """Tests for _is_newer version comparison function."""

    def test_newer_minor_version(self):
        """Test that higher minor version is detected as newer."""
        assert _is_newer("1.2.0", "1.1.0") is True

    def test_newer_major_version(self):
        """Test that higher major version is detected as newer."""
        assert _is_newer("2.0.0", "1.9.9") is True

    def test_newer_patch_version(self):
        """Test that higher patch version is detected as newer."""
        assert _is_newer("1.0.1", "1.0.0") is True

    def test_same_version_not_newer(self):
        """Test that same version is not newer."""
        assert _is_newer("1.0.0", "1.0.0") is False

    def test_older_version_not_newer(self):
        """Test that older version is not newer."""
        assert _is_newer("1.0.0", "1.1.0") is False
        assert _is_newer("0.9.0", "1.0.0") is False

    def test_0_9_vs_0_10_correct(self):
        """Test semantic version handling: 0.10 > 0.9."""
        # This is a common edge case where string comparison fails
        assert _is_newer("0.10.0", "0.9.0") is True
        assert _is_newer("0.9.0", "0.10.0") is False

    def test_version_with_v_prefix(self):
        """Test version comparison with 'v' prefix."""
        assert _is_newer("v2.0.0", "v1.0.0") is True
        assert _is_newer("v1.0.0", "v2.0.0") is False

    def test_version_with_dev_suffix(self):
        """Test version comparison with .dev suffix."""
        # Dev version should be stripped and compared numerically
        assert _is_newer("1.1.0", "1.0.0.dev1") is True

    def test_malformed_version_handling(self):
        """Test handling of malformed versions."""
        # Malformed latest version is not newer than valid current
        assert _is_newer("not-a-version", "1.0.0") is False
        # Valid latest is newer than malformed current (empty tuple)
        assert _is_newer("1.0.0", "not-a-version") is True
        # Empty versions: empty tuple comparison (equal)
        assert _is_newer("", "") is False

    def test_two_part_versions(self):
        """Test versions with only major.minor."""
        assert _is_newer("1.1", "1.0") is True
        assert _is_newer("2.0", "1.9") is True


class TestDetectInstallMethod:
    """Tests for _detect_install_method function."""

    def test_detect_uv_install(self, monkeypatch):
        """Test detection of uv tool installation."""
        monkeypatch.setattr("sys.executable", "/home/user/.local/share/uv/tools/ptn/bin/python")
        assert _detect_install_method() == "uv"

    def test_detect_uv_install_windows(self, monkeypatch):
        """Test detection of uv tool installation on Windows."""
        monkeypatch.setattr("sys.executable", "C:\\Users\\user\\uv\\tools\\ptn\\python.exe")
        assert _detect_install_method() == "uv"

    def test_detect_uv_cache(self, monkeypatch):
        """Test detection of uv tool run / uvx (uses cache path)."""
        monkeypatch.setattr("sys.executable", "/home/user/.cache/uv/ptn/bin/python")
        assert _detect_install_method() == "uv"

    def test_detect_pipx_install(self, monkeypatch):
        """Test detection of pipx installation."""
        monkeypatch.setattr("sys.executable", "/home/user/.local/pipx/venvs/ptn/bin/python")
        assert _detect_install_method() == "pipx"

    def test_detect_pipx_install_windows(self, monkeypatch):
        """Test detection of pipx installation on Windows."""
        monkeypatch.setattr("sys.executable", "C:\\Users\\user\\pipx\\venvs\\ptn\\python.exe")
        assert _detect_install_method() == "pipx"

    def test_detect_pip_fallback(self, monkeypatch):
        """Test fallback to pip for regular installations."""
        monkeypatch.setattr("sys.executable", "/usr/bin/python3")
        assert _detect_install_method() == "pip"
