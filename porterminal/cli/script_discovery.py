"""Auto-discover project scripts for config initialization."""

import json
import re
import tomllib
from pathlib import Path


def discover_scripts(cwd: Path | None = None) -> list[dict]:
    """Discover project scripts in current directory.

    Returns list of button configs: [{"label": "build", "send": "npm run build\\r", "row": 2}]
    Only includes scripts explicitly defined in project files.
    """
    base = cwd or Path.cwd()
    buttons = []

    # Check each project type (only those with explicit scripts)
    buttons.extend(_discover_npm_scripts(base))
    buttons.extend(_discover_python_scripts(base))
    buttons.extend(_discover_makefile_targets(base))

    # Dedupe by label, keep first occurrence
    unique: dict[str, dict] = {}
    for btn in buttons:
        unique.setdefault(btn["label"], btn)
    return list(unique.values())


def _discover_npm_scripts(base: Path) -> list[dict]:
    """Extract scripts from package.json."""
    pkg_file = base / "package.json"
    if not pkg_file.exists():
        return []

    try:
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})

        # Common useful scripts to include (if defined)
        priority = ["build", "dev", "start", "test", "lint", "format", "watch"]

        buttons = []
        for name in priority:
            if name in scripts:
                buttons.append({"label": name, "send": f"npm run {name}\r", "row": 2})

        return buttons[:6]  # Limit to 6 buttons
    except Exception:
        return []


def _discover_python_scripts(base: Path) -> list[dict]:
    """Extract scripts from pyproject.toml."""
    toml_file = base / "pyproject.toml"
    if not toml_file.exists():
        return []

    try:
        data = tomllib.loads(toml_file.read_text(encoding="utf-8"))
        buttons = []

        # Check [project.scripts] (PEP 621)
        project_scripts = data.get("project", {}).get("scripts", {})
        for name in list(project_scripts.keys())[:4]:
            buttons.append({"label": name, "send": f"{name}\r", "row": 2})

        # Check [tool.poetry.scripts]
        poetry_scripts = data.get("tool", {}).get("poetry", {}).get("scripts", {})
        for name in list(poetry_scripts.keys())[:4]:
            if not any(b["label"] == name for b in buttons):
                buttons.append({"label": name, "send": f"{name}\r", "row": 2})

        return buttons[:6]
    except Exception:
        return []


def _discover_makefile_targets(base: Path) -> list[dict]:
    """Extract targets from Makefile."""
    makefile = base / "Makefile"
    if not makefile.exists():
        return []

    try:
        content = makefile.read_text(encoding="utf-8")
        # Match target definitions: "target:" at start of line
        # Regex excludes targets starting with . (internal targets like .PHONY)
        pattern = r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:"
        targets = re.findall(pattern, content, re.MULTILINE)

        # Priority order for common targets (use set for O(1) lookup)
        priority = ["build", "test", "run", "clean", "install", "dev", "lint", "all"]
        priority_set = set(priority)
        target_set = set(targets)

        # Priority targets first, then remaining targets
        ordered = [t for t in priority if t in target_set]
        ordered.extend(t for t in targets if t not in priority_set)

        return [{"label": name, "send": f"make {name}\r", "row": 2} for name in ordered[:6]]
    except Exception:
        return []
