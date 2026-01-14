"""Auto-discover project scripts for config initialization."""

import json
import re
import tomllib
from pathlib import Path

import yaml

# Pattern for safe script names (alphanumeric, hyphens, underscores only)
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def _is_safe_name(name: str) -> bool:
    """Check if script name contains only safe characters."""
    return bool(_SAFE_NAME.match(name)) and len(name) <= 50


def discover_scripts(cwd: Path | None = None) -> list[dict]:
    """Discover project scripts in current directory.

    Returns list of button configs: [{"label": "build", "send": "npm run build\\r", "row": 2}]
    Only includes scripts explicitly defined in project files.
    """
    base = cwd or Path.cwd()
    buttons = []

    # Check each project type (only those with explicit scripts)
    # Order matters: first match wins for deduplication
    buttons.extend(_discover_npm_scripts(base))  # Also handles Bun
    buttons.extend(_discover_deno_tasks(base))
    buttons.extend(_discover_python_scripts(base))
    buttons.extend(_discover_makefile_targets(base))
    buttons.extend(_discover_just_recipes(base))
    buttons.extend(_discover_taskfile_tasks(base))

    # Dedupe by label, keep first occurrence
    unique: dict[str, dict] = {}
    for btn in buttons:
        unique.setdefault(btn["label"], btn)
    return list(unique.values())


def _discover_npm_scripts(base: Path) -> list[dict]:
    """Extract scripts from package.json.

    Uses 'bun run' if bun.lockb exists, otherwise 'npm run'.
    """
    pkg_file = base / "package.json"
    if not pkg_file.exists():
        return []

    try:
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})

        # Detect package manager: bun if bun.lockb exists
        runner = "bun run" if (base / "bun.lockb").exists() else "npm run"

        # Common useful scripts to include (if defined)
        priority = ["build", "dev", "start", "test", "lint", "format", "watch"]

        buttons = []
        for name in priority:
            if name in scripts:
                buttons.append({"label": name, "send": f"{runner} {name}\r", "row": 2})

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
            if _is_safe_name(name):
                buttons.append({"label": name, "send": f"{name}\r", "row": 2})

        # Check [tool.poetry.scripts]
        poetry_scripts = data.get("tool", {}).get("poetry", {}).get("scripts", {})
        for name in list(poetry_scripts.keys())[:4]:
            if _is_safe_name(name) and not any(b["label"] == name for b in buttons):
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


def _discover_deno_tasks(base: Path) -> list[dict]:
    """Extract tasks from deno.json or deno.jsonc."""
    # Try both deno.json and deno.jsonc
    for filename in ["deno.json", "deno.jsonc"]:
        deno_file = base / filename
        if deno_file.exists():
            break
    else:
        return []

    try:
        content = deno_file.read_text(encoding="utf-8")
        # Strip comments for deno.jsonc (same approach as Windows Terminal settings)
        if filename.endswith(".jsonc"):
            content = _strip_json_comments(content)
        data = json.loads(content)
        tasks = data.get("tasks", {})

        # Common useful tasks to include (if defined)
        priority = ["build", "dev", "start", "test", "lint", "format", "check"]

        buttons = []
        for name in priority:
            if name in tasks and _is_safe_name(name):
                buttons.append({"label": name, "send": f"deno task {name}\r", "row": 2})

        # Add remaining tasks not in priority list
        for name in tasks:
            if name not in priority and _is_safe_name(name) and len(buttons) < 6:
                buttons.append({"label": name, "send": f"deno task {name}\r", "row": 2})

        return buttons[:6]
    except Exception:
        return []


def _strip_json_comments(content: str) -> str:
    """Strip comments from JSON content (for .jsonc files)."""
    result = []
    i = 0
    in_string = False
    escape_next = False

    while i < len(content):
        char = content[i]

        if escape_next:
            result.append(char)
            escape_next = False
            i += 1
            continue

        if char == "\\" and in_string:
            result.append(char)
            escape_next = True
            i += 1
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            result.append(char)
            i += 1
            continue

        if not in_string:
            # Single-line comment
            if content[i : i + 2] == "//":
                while i < len(content) and content[i] != "\n":
                    i += 1
                continue
            # Multi-line comment
            if content[i : i + 2] == "/*":
                i += 2
                while i < len(content) - 1 and content[i : i + 2] != "*/":
                    i += 1
                i += 2
                continue

        result.append(char)
        i += 1

    return "".join(result)


def _discover_just_recipes(base: Path) -> list[dict]:
    """Extract recipes from justfile."""
    # Try both justfile and Justfile
    for filename in ["justfile", "Justfile", ".justfile"]:
        justfile = base / filename
        if justfile.exists():
            break
    else:
        return []

    try:
        content = justfile.read_text(encoding="utf-8")
        # Match recipe definitions: "recipe:" or "recipe arg:" at start of line
        # Exclude private recipes (starting with _) and recipes with @ prefix
        pattern = r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*(?:[^:]*)?:"
        recipes = re.findall(pattern, content, re.MULTILINE)

        # Priority order for common recipes
        priority = ["build", "test", "run", "dev", "check", "lint", "fmt", "clean"]
        priority_set = set(priority)
        recipe_set = set(recipes)

        # Priority recipes first, then remaining
        ordered = [r for r in priority if r in recipe_set]
        ordered.extend(r for r in recipes if r not in priority_set and _is_safe_name(r))

        return [{"label": name, "send": f"just {name}\r", "row": 2} for name in ordered[:6]]
    except Exception:
        return []


def _discover_taskfile_tasks(base: Path) -> list[dict]:
    """Extract tasks from Taskfile.yml."""
    # Try multiple filenames
    for filename in ["Taskfile.yml", "Taskfile.yaml", "taskfile.yml", "taskfile.yaml"]:
        taskfile = base / filename
        if taskfile.exists():
            break
    else:
        return []

    try:
        data = yaml.safe_load(taskfile.read_text(encoding="utf-8"))
        tasks = data.get("tasks", {})

        # Priority order for common tasks
        priority = ["build", "test", "run", "dev", "lint", "fmt", "clean", "default"]

        buttons = []
        for name in priority:
            if name in tasks and _is_safe_name(name):
                buttons.append({"label": name, "send": f"task {name}\r", "row": 2})

        # Add remaining tasks not in priority list
        for name in tasks:
            if name not in priority and _is_safe_name(name) and len(buttons) < 6:
                buttons.append({"label": name, "send": f"task {name}\r", "row": 2})

        return buttons[:6]
    except Exception:
        return []
