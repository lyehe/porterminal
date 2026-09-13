"""Characterization tests for the public package and module entry points."""

import subprocess
import sys

import pytest

import porterminal
from porterminal.cli.args import parse_args


@pytest.mark.parametrize("flag", ["--background", "-b", "--_url-file=ready.json"])
def test_removed_detached_options_are_rejected(monkeypatch, flag):
    monkeypatch.setattr(sys, "argv", ["ptn", flag])
    with pytest.raises(SystemExit) as error:
        parse_args()
    assert error.value.code != 0


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
        "--mcp-only",
        "--init-from",
        "--password",
        "--toggle-password",
        "--save-password",
        "--compose",
        "--keep-qr",
    ):
        assert option in result.stdout
    assert "--_url-file" not in result.stdout
    assert "--background" not in result.stdout


@pytest.mark.parametrize("path", ["--version", "-V"])
def test_version_like_path_after_sentinel_is_a_public_positional(
    path: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ptn", "--", path])

    args = parse_args()

    assert args.path == path
