"""Characterization tests for the public package and module entry points."""

import subprocess
import sys

import pytest

import porterminal
from porterminal.cli.args import _extract_internal_url_file, parse_args


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
    assert "--_url-file" not in result.stdout


def test_internal_background_option_is_accepted_but_hidden() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from porterminal.cli.args import parse_args; "
                "sys.argv = ['ptn', '--_url-file=C:/Temp/ready.json', '--no-tunnel']; "
                "args = parse_args(); "
                "print(args.url_file); print(args.no_tunnel)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["C:/Temp/ready.json", "True"]


def test_internal_background_option_after_sentinel_is_a_public_positional(
    monkeypatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ptn", "--", "--_url-file=literal"])

    args = parse_args()

    assert args.path == "--_url-file=literal"
    assert args.url_file is None


@pytest.mark.parametrize("path", ["--version", "-V"])
def test_version_like_path_after_sentinel_is_a_public_positional(
    path: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ptn", "--", path])

    args = parse_args()

    assert args.path == path


def test_internal_option_extraction_preserves_sentinel_and_every_following_value() -> None:
    arguments = ["--verbose", "--", "--_url-file=literal", "--no-tunnel"]

    public_arguments, url_file = _extract_internal_url_file(arguments)

    assert public_arguments == arguments
    assert url_file is None


@pytest.mark.parametrize("malformed", ["--_url-file", "--_url-file="])
def test_internal_background_option_requires_nonempty_equals_form(malformed: str) -> None:
    with pytest.raises(SystemExit, match=r"--_url-file requires"):
        _extract_internal_url_file([malformed, "--no-tunnel"])


def test_internal_background_option_does_not_consume_an_option_as_its_value() -> None:
    with pytest.raises(SystemExit, match=r"--_url-file requires .*--_url-file=PATH"):
        _extract_internal_url_file(["--_url-file", "--no-tunnel"])


def test_internal_background_option_rejects_duplicates() -> None:
    with pytest.raises(SystemExit, match=r"--_url-file may only be specified once"):
        _extract_internal_url_file(
            ["--_url-file=first.json", "--no-tunnel", "--_url-file=second.json"]
        )
