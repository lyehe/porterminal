"""Tests for script discovery module."""

from porterminal.cli.script_discovery import (
    _discover_makefile_targets,
    _discover_npm_scripts,
    _discover_python_scripts,
    discover_scripts,
)


class TestDiscoverNpmScripts:
    """Tests for npm script discovery."""

    def test_discovers_scripts_from_package_json(self, tmp_path):
        """Test that scripts are discovered from package.json."""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"scripts": {"build": "tsc", "test": "vitest"}}')

        result = _discover_npm_scripts(tmp_path)

        assert len(result) == 2
        assert result[0] == {"label": "build", "send": "npm run build\r", "row": 2}
        assert result[1] == {"label": "test", "send": "npm run test\r", "row": 2}

    def test_respects_priority_order(self, tmp_path):
        """Test that scripts are ordered by priority."""
        package_json = tmp_path / "package.json"
        package_json.write_text(
            '{"scripts": {"watch": "w", "build": "b", "test": "t", "dev": "d"}}'
        )

        result = _discover_npm_scripts(tmp_path)

        labels = [r["label"] for r in result]
        # Priority order: build, dev, start, test, lint, format, watch
        assert labels == ["build", "dev", "test", "watch"]

    def test_limits_to_six_buttons(self, tmp_path):
        """Test that at most 6 buttons are returned."""
        package_json = tmp_path / "package.json"
        package_json.write_text(
            '{"scripts": {"build": "1", "dev": "2", "start": "3", '
            '"test": "4", "lint": "5", "format": "6", "watch": "7"}}'
        )

        result = _discover_npm_scripts(tmp_path)

        assert len(result) == 6

    def test_returns_empty_if_no_package_json(self, tmp_path):
        """Test that empty list is returned if no package.json exists."""
        result = _discover_npm_scripts(tmp_path)

        assert result == []

    def test_returns_empty_if_no_scripts_section(self, tmp_path):
        """Test that empty list is returned if no scripts section."""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"name": "test"}')

        result = _discover_npm_scripts(tmp_path)

        assert result == []

    def test_handles_malformed_json(self, tmp_path):
        """Test that malformed JSON is handled gracefully."""
        package_json = tmp_path / "package.json"
        package_json.write_text("not valid json {")

        result = _discover_npm_scripts(tmp_path)

        assert result == []

    def test_only_includes_priority_scripts(self, tmp_path):
        """Test that only priority scripts are included."""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"scripts": {"custom-script": "echo 1", "my-task": "echo 2"}}')

        result = _discover_npm_scripts(tmp_path)

        # Neither script is in priority list
        assert result == []


class TestDiscoverPythonScripts:
    """Tests for Python script discovery."""

    def test_discovers_project_scripts(self, tmp_path):
        """Test discovery from [project.scripts]."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project.scripts]\nptn = "porterminal.cli:main"\nother = "pkg:run"')

        result = _discover_python_scripts(tmp_path)

        assert len(result) == 2
        assert result[0] == {"label": "ptn", "send": "ptn\r", "row": 2}
        assert result[1] == {"label": "other", "send": "other\r", "row": 2}

    def test_discovers_poetry_scripts(self, tmp_path):
        """Test discovery from [tool.poetry.scripts]."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.poetry.scripts]\nmycli = "mypackage:main"')

        result = _discover_python_scripts(tmp_path)

        assert len(result) == 1
        assert result[0] == {"label": "mycli", "send": "mycli\r", "row": 2}

    def test_dedupes_project_and_poetry_scripts(self, tmp_path):
        """Test that duplicate scripts are not added twice."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project.scripts]\nmycli = "pkg:main"\n\n'
            '[tool.poetry.scripts]\nmycli = "pkg:main"\nother = "pkg:other"'
        )

        result = _discover_python_scripts(tmp_path)

        labels = [r["label"] for r in result]
        assert labels.count("mycli") == 1
        assert "other" in labels

    def test_returns_empty_if_no_pyproject(self, tmp_path):
        """Test that empty list is returned if no pyproject.toml."""
        result = _discover_python_scripts(tmp_path)

        assert result == []

    def test_returns_empty_if_no_scripts_sections(self, tmp_path):
        """Test that empty list is returned if no scripts sections."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"')

        result = _discover_python_scripts(tmp_path)

        assert result == []

    def test_handles_malformed_toml(self, tmp_path):
        """Test that malformed TOML is handled gracefully."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("not valid toml [[[")

        result = _discover_python_scripts(tmp_path)

        assert result == []

    def test_limits_buttons_per_source(self, tmp_path):
        """Test that buttons are limited per source (4 each) and total (6)."""
        pyproject = tmp_path / "pyproject.toml"
        # 10 project scripts + 10 poetry scripts
        pyproject.write_text(
            "[project.scripts]\n"
            + "\n".join(f'p{i} = "pkg:f{i}"' for i in range(10))
            + "\n\n[tool.poetry.scripts]\n"
            + "\n".join(f't{i} = "pkg:g{i}"' for i in range(10))
        )

        result = _discover_python_scripts(tmp_path)

        # 4 from project + 4 from poetry = 8, capped at 6
        assert len(result) == 6
        labels = [r["label"] for r in result]
        # First 4 from project.scripts
        assert labels[:4] == ["p0", "p1", "p2", "p3"]
        # Then 2 from poetry.scripts (to reach cap of 6)
        assert labels[4:6] == ["t0", "t1"]

    def test_filters_unsafe_script_names(self, tmp_path):
        """Test that script names with unsafe characters are filtered out."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[project.scripts]\n"
            'safe-name = "pkg:safe"\n'
            '"test; rm -rf /" = "pkg:bad"\n'  # Injection attempt
            'also_safe = "pkg:ok"\n'
        )

        result = _discover_python_scripts(tmp_path)

        labels = [r["label"] for r in result]
        assert "safe-name" in labels
        assert "also_safe" in labels
        assert "test; rm -rf /" not in labels


class TestDiscoverMakefileTargets:
    """Tests for Makefile target discovery."""

    def test_discovers_makefile_targets(self, tmp_path):
        """Test that targets are discovered from Makefile."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("build:\n\techo build\n\ntest:\n\techo test\n")

        result = _discover_makefile_targets(tmp_path)

        assert len(result) == 2
        assert result[0] == {"label": "build", "send": "make build\r", "row": 2}
        assert result[1] == {"label": "test", "send": "make test\r", "row": 2}

    def test_respects_priority_order(self, tmp_path):
        """Test that targets are ordered by priority."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("clean:\n\trm\n\nbuild:\n\tgcc\n\ntest:\n\tpytest\n")

        result = _discover_makefile_targets(tmp_path)

        labels = [r["label"] for r in result]
        # Priority: build, test, run, clean, install, dev, lint, all
        assert labels == ["build", "test", "clean"]

    def test_excludes_phony_targets(self, tmp_path):
        """Test that .PHONY and other special targets are excluded."""
        makefile = tmp_path / "Makefile"
        makefile.write_text(".PHONY: build test\n\nbuild:\n\techo\n")

        result = _discover_makefile_targets(tmp_path)

        labels = [r["label"] for r in result]
        assert ".PHONY" not in labels
        assert "build" in labels

    def test_excludes_dot_prefixed_targets(self, tmp_path):
        """Test that targets starting with . are excluded."""
        makefile = tmp_path / "Makefile"
        makefile.write_text(".hidden:\n\techo\n\nbuild:\n\techo\n")

        result = _discover_makefile_targets(tmp_path)

        labels = [r["label"] for r in result]
        assert ".hidden" not in labels
        assert "build" in labels

    def test_handles_targets_with_dependencies(self, tmp_path):
        """Test targets with dependencies are discovered."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("build: src/main.c src/util.c\n\tgcc -o app $^\n")

        result = _discover_makefile_targets(tmp_path)

        assert len(result) == 1
        assert result[0]["label"] == "build"

    def test_returns_empty_if_no_makefile(self, tmp_path):
        """Test that empty list is returned if no Makefile."""
        result = _discover_makefile_targets(tmp_path)

        assert result == []

    def test_limits_to_six_buttons(self, tmp_path):
        """Test that at most 6 buttons are returned."""
        makefile = tmp_path / "Makefile"
        targets = "\n".join(f"target{i}:\n\techo {i}" for i in range(10))
        makefile.write_text(targets)

        result = _discover_makefile_targets(tmp_path)

        assert len(result) == 6

    def test_handles_targets_with_hyphens_and_underscores(self, tmp_path):
        """Test targets with hyphens and underscores."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("build-all:\n\techo\n\nrun_tests:\n\techo\n")

        result = _discover_makefile_targets(tmp_path)

        labels = [r["label"] for r in result]
        assert "build-all" in labels
        assert "run_tests" in labels


class TestDiscoverScripts:
    """Tests for main discover_scripts function."""

    def test_combines_all_sources(self, tmp_path):
        """Test that scripts from all sources are combined."""
        # Create package.json
        package_json = tmp_path / "package.json"
        package_json.write_text('{"scripts": {"build": "npm build"}}')

        # Create Makefile
        makefile = tmp_path / "Makefile"
        makefile.write_text("test:\n\tpytest\n")

        result = discover_scripts(tmp_path)

        labels = [r["label"] for r in result]
        assert "build" in labels
        assert "test" in labels

    def test_deduplicates_by_label(self, tmp_path):
        """Test that duplicate labels are deduplicated."""
        # Both have 'build'
        package_json = tmp_path / "package.json"
        package_json.write_text('{"scripts": {"build": "npm build"}}')

        makefile = tmp_path / "Makefile"
        makefile.write_text("build:\n\tmake build\n")

        result = discover_scripts(tmp_path)

        labels = [r["label"] for r in result]
        assert labels.count("build") == 1
        # npm is checked first, so npm version wins
        assert result[0]["send"] == "npm run build\r"

    def test_returns_empty_for_empty_directory(self, tmp_path):
        """Test that empty list is returned for empty directory."""
        result = discover_scripts(tmp_path)

        assert result == []

    def test_all_buttons_have_row_2(self, tmp_path):
        """Test that all discovered buttons have row 2."""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"scripts": {"build": "b", "test": "t"}}')

        result = discover_scripts(tmp_path)

        for btn in result:
            assert btn["row"] == 2

    def test_uses_cwd_if_not_provided(self, tmp_path, monkeypatch):
        """Test that cwd is used if path not provided."""
        monkeypatch.chdir(tmp_path)
        package_json = tmp_path / "package.json"
        package_json.write_text('{"scripts": {"dev": "vite"}}')

        result = discover_scripts()  # No path argument

        assert len(result) == 1
        assert result[0]["label"] == "dev"
