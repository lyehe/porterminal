"""Tests for the shared configuration persistence boundary."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from porterminal.cli.args import _set_password_requirement
from porterminal.config import ConfigStore
from porterminal.domain import ShellCommand
from porterminal.infrastructure.config import ConfigService


class StubShellDetector:
    def detect_shells(self) -> list[ShellCommand]:
        return [
            ShellCommand(
                id="python",
                name="Python",
                command=sys.executable,
                args=(),
            )
        ]

    def get_default_shell_id(self) -> str:
        return "python"


def make_store(path: Path) -> ConfigStore:
    return ConfigStore(
        config_path=path,
        default_path=path,
        shell_detector=StubShellDetector(),
    )


def test_config_search_order_and_environment_override(tmp_path, monkeypatch):
    direct = tmp_path / "ptn.yaml"
    nested = tmp_path / ".ptn" / "ptn.yaml"
    nested.parent.mkdir()
    nested.write_text("ui: {}\n", encoding="utf-8")
    direct.write_text("ui: {}\n", encoding="utf-8")

    monkeypatch.delenv("PORTERMINAL_CONFIG_PATH", raising=False)
    store = ConfigStore(cwd=tmp_path, default_path=tmp_path / "fallback.yaml")
    assert store.resolve_path() == direct

    override = tmp_path / "not-created-yet.yaml"
    monkeypatch.setenv("PORTERMINAL_CONFIG_PATH", str(override))
    assert store.resolve_path() == override


def test_invalid_config_is_rejected_without_overwrite(tmp_path):
    path = tmp_path / "ptn.yaml"
    original = "server:\n  port: 0\n"
    path.write_text(original, encoding="utf-8")
    store = make_store(path)

    with pytest.raises(ValidationError):
        store.load()
    with pytest.raises(ValidationError):
        store.save_raw(store.read_raw())

    assert path.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_runtime_updates_preserve_unknown_fields(tmp_path):
    path = tmp_path / "ptn.yaml"
    store = make_store(path)
    store.save_raw(
        {
            "extension": {"owner": "user", "options": [1, 2, 3]},
            "ui": {"compose_mode": False},
            "buttons": [{"label": "one", "send": "1", "row": 1}],
        }
    )
    service = ConfigService(store)

    settings, requires_restart = await service.update_settings(
        {"compose_mode": True, "notify_on_startup": False}
    )
    buttons = await service.add_button("two", "2", row=2)

    raw = store.read_raw()
    assert raw["extension"] == {"owner": "user", "options": [1, 2, 3]}
    assert raw["ui"]["compose_mode"] is True
    assert raw["update"]["notify_on_startup"] is False
    assert [button["label"] for button in buttons] == ["one", "two"]
    assert settings["compose_mode"] is True
    assert requires_restart is False
    assert not list(tmp_path.glob("*.tmp"))


def test_cli_mutation_uses_shared_store(tmp_path, monkeypatch):
    path = tmp_path / "ptn.yaml"
    path.write_text("custom:\n  preserved: true\n", encoding="utf-8")
    monkeypatch.setenv("PORTERMINAL_CONFIG_PATH", str(path))

    _set_password_requirement(True)

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["custom"] == {"preserved": True}
    assert raw["security"]["require_password"] is True
