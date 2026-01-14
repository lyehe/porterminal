"""Auto-discover project scripts for config initialization."""

import json
import re
import tomllib
from pathlib import Path

import yaml

# Pattern for safe script names (alphanumeric, hyphens, underscores only)
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")

# Maximum buttons to return from each discovery function
_MAX_BUTTONS = 6


def _is_safe_name(name: str) -> bool:
    """Check if script name contains only safe characters."""
    return bool(_SAFE_NAME.match(name)) and len(name) <= 50


def _find_file(base: Path, filenames: list[str]) -> Path | None:
    """Find the first existing file from a list of candidates."""
    for filename in filenames:
        path = base / filename
        if path.exists():
            return path
    return None


def _build_buttons(
    tasks: dict,
    priority: list[str],
    command_prefix: str,
    *,
    priority_only: bool = False,
) -> list[dict]:
    """Build button configs from tasks dict with priority ordering.

    Args:
        tasks: Dict of task names to their definitions
        priority: List of task names to prioritize
        command_prefix: Command prefix (e.g., "deno task", "task", "just")
        priority_only: If True, only include tasks from priority list
    """
    buttons = []
    priority_set = set(priority)

    # Add priority tasks first
    for name in priority:
        if name in tasks and _is_safe_name(name):
            buttons.append({"label": name, "send": f"{command_prefix} {name}\r", "row": 2})

    # Add remaining tasks (unless priority_only is set)
    if not priority_only:
        for name in tasks:
            if name not in priority_set and _is_safe_name(name) and len(buttons) < _MAX_BUTTONS:
                buttons.append({"label": name, "send": f"{command_prefix} {name}\r", "row": 2})

    return buttons[:_MAX_BUTTONS]


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
    Only includes scripts from the priority list (build, dev, start, etc.).
    """
    pkg_file = base / "package.json"
    if not pkg_file.exists():
        return []

    try:
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})

        # Detect package manager: bun if bun.lockb exists
        runner = "bun run" if (base / "bun.lockb").exists() else "npm run"
        priority = ["build", "dev", "start", "test", "lint", "format", "watch"]

        return _build_buttons(scripts, priority, runner, priority_only=True)
    except Exception:
        return []


def _discover_python_scripts(base: Path) -> list[dict]:
    """Extract scripts from pyproject.toml.

    Checks [project.scripts] (PEP 621) first, then [tool.poetry.scripts].
    Takes up to 4 from each source, deduplicates, and caps at 6 total.
    """
    toml_file = base / "pyproject.toml"
    if not toml_file.exists():
        return []

    try:
        data = tomllib.loads(toml_file.read_text(encoding="utf-8"))
        buttons = []

        # Check [project.scripts] (PEP 621) - take up to 4
        project_scripts = data.get("project", {}).get("scripts", {})
        for name in list(project_scripts.keys())[:4]:
            if _is_safe_name(name):
                buttons.append({"label": name, "send": f"{name}\r", "row": 2})

        # Check [tool.poetry.scripts] - take up to 4, skip duplicates
        existing_labels = {b["label"] for b in buttons}
        poetry_scripts = data.get("tool", {}).get("poetry", {}).get("scripts", {})
        for name in list(poetry_scripts.keys())[:4]:
            if _is_safe_name(name) and name not in existing_labels:
                buttons.append({"label": name, "send": f"{name}\r", "row": 2})

        return buttons[:_MAX_BUTTONS]
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

        # Convert list to dict for _build_buttons compatibility
        targets_dict = {t: True for t in targets}
        priority = ["build", "test", "run", "clean", "install", "dev", "lint", "all"]

        return _build_buttons(targets_dict, priority, "make")
    except Exception:
        return []


def _discover_deno_tasks(base: Path) -> list[dict]:
    """Extract tasks from deno.json or deno.jsonc."""
    deno_file = _find_file(base, ["deno.json", "deno.jsonc"])
    if not deno_file:
        return []

    try:
        content = deno_file.read_text(encoding="utf-8")
        if deno_file.suffix == ".jsonc":
            content = _strip_json_comments(content)

        tasks = json.loads(content).get("tasks", {})
        priority = ["build", "dev", "start", "test", "lint", "format", "check"]

        return _build_buttons(tasks, priority, "deno task")
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
    justfile = _find_file(base, ["justfile", "Justfile", ".justfile"])
    if not justfile:
        return []

    try:
        content = justfile.read_text(encoding="utf-8")
        # Match recipe definitions: "recipe:" or "recipe arg:" at start of line
        # Exclude private recipes (starting with _) and recipes with @ prefix
        pattern = r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*(?:[^:]*)?:"
        recipes = re.findall(pattern, content, re.MULTILINE)

        # Convert list to dict for _build_buttons compatibility
        recipes_dict = {r: True for r in recipes}
        priority = ["build", "test", "run", "dev", "check", "lint", "fmt", "clean"]

        return _build_buttons(recipes_dict, priority, "just")
    except Exception:
        return []


def _discover_taskfile_tasks(base: Path) -> list[dict]:
    """Extract tasks from Taskfile.yml."""
    taskfile = _find_file(base, ["Taskfile.yml", "Taskfile.yaml", "taskfile.yml", "taskfile.yaml"])
    if not taskfile:
        return []

    try:
        tasks = yaml.safe_load(taskfile.read_text(encoding="utf-8")).get("tasks", {})
        priority = ["build", "test", "run", "dev", "lint", "fmt", "clean", "default"]

        return _build_buttons(tasks, priority, "task")
    except Exception:
        return []
