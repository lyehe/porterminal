"""Characterization tests for the public package and module entry points."""

import subprocess
import sys

import porterminal


def test_package_root_exposes_version_and_main() -> None:
    assert isinstance(porterminal.__version__, str)
    assert porterminal.__version__
    assert callable(porterminal.main)
    assert porterminal.main.__module__ == "porterminal"


def test_package_import_keeps_cli_runtime_lazy() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import porterminal; print('porterminal.cli.main' in sys.modules)",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "False"


def test_package_main_delegates_to_cli_runtime(monkeypatch) -> None:
    from porterminal.cli import main as cli_main

    monkeypatch.setattr(cli_main, "main", lambda: 37)

    assert porterminal.main() == 37


def test_module_help_preserves_public_cli_options() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "porterminal", "--help"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )

    assert result.returncode == 0
    assert "Porterminal - Web terminal via Cloudflare Tunnel" in result.stdout
    for option in (
        "--no-tunnel",
        "--verbose",
        "--check-update",
        "--background",
        "--init-from",
        "--password",
        "--toggle-password",
        "--save-password",
        "--compose",
        "--keep-qr",
    ):
        assert option in result.stdout
