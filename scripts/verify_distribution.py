"""Verify a built distribution as a clean package consumer.

The project test environment is intentionally not reused: installing the wheel
into a temporary virtual environment catches missing package data and dependency
constraints that a locked editable install can hide.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def _run(*args: str | Path, cwd: Path | None = None) -> None:
    subprocess.run([str(arg) for arg in args], check=True, cwd=cwd)


def _venv_python(venv: Path) -> Path:
    windows_python = venv / "Scripts" / "python.exe"
    return windows_python if windows_python.exists() else venv / "bin" / "python"


def _venv_command(venv: Path, name: str) -> Path:
    windows_command = venv / "Scripts" / f"{name}.exe"
    return windows_command if windows_command.exists() else venv / "bin" / name


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _verify_server(python: Path, cwd: Path) -> None:
    """Boot the installed ASGI entry point and require a healthy response."""
    port = _available_port()
    environment = os.environ.copy()
    environment["PORTERMINAL_CONFIG_PATH"] = str(cwd / "missing-config.yaml")
    environment["PORTERMINAL_CWD"] = str(cwd)
    process = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "porterminal.asgi:create_app_from_env",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
            "--no-access-log",
        ],
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        health_url = f"http://127.0.0.1:{port}/health"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout is not None else ""
                raise RuntimeError(f"Installed server exited during startup:\n{output}")
            try:
                with urllib.request.urlopen(health_url, timeout=1) as response:
                    payload = json.load(response)
                if response.status == 200 and payload.get("status") == "healthy":
                    print(f"verified installed server at {health_url}")
                    return
            except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
                time.sleep(0.1)
        raise RuntimeError(f"Installed server did not become healthy at {health_url}")
    finally:
        process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


def verify_distribution(dist_dir: Path, python_version: str) -> None:
    wheels = sorted(dist_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected exactly one wheel in {dist_dir}, found {len(wheels)}")

    with tempfile.TemporaryDirectory(prefix="ptn-dist-check-") as temporary:
        venv = Path(temporary) / "venv"
        _run("uv", "venv", "--python", python_version, venv)
        python = _venv_python(venv)
        _run("uv", "pip", "install", "--refresh", "--python", python, wheels[0])

        smoke_test = """
from pathlib import Path
import re
import porterminal
from porterminal.app import create_app

package = Path(porterminal.__file__).parent
index_path = package / "static" / "index.html"
assert index_path.is_file(), "wheel is missing static/index.html"
references = re.findall(r'["\\\'](/static/[^"\\\']+)["\\\']', index_path.read_text(encoding="utf-8"))
missing_assets = [
    reference for reference in references
    if not (package / "static" / reference.removeprefix("/static/")).is_file()
]
assert not missing_assets, f"wheel is missing referenced static assets: {missing_assets}"
app = create_app()
documented_paths = set(app.openapi()["paths"])
mounted_paths = {getattr(route, "path", None) for route in app.routes}
assert "/mcp" in mounted_paths, f"wheel is missing /mcp mount: {mounted_paths}"
assert "/api/agent/run" in documented_paths, f"wheel is missing agent routes: {documented_paths}"
print(f"verified ptn {porterminal.__version__}")
"""
        isolated_cwd = Path(temporary)
        _run(python, "-c", smoke_test, cwd=isolated_cwd)
        _run(_venv_command(venv, "ptn"), "--help", cwd=isolated_cwd)
        _verify_server(python, isolated_cwd)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--python", default="3.12", dest="python_version")
    args = parser.parse_args()
    verify_distribution(args.dist_dir.resolve(), args.python_version)


if __name__ == "__main__":
    main()
