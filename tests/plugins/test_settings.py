"""Plugin settings: defaults, nested env parsing, and project-env writes."""

import json
from pathlib import Path

import pytest

from fabulous.fabulous_settings import (
    PluginSettings,
    add_var_to_project_env,
    get_context,
    init_context,
)


def test_plugin_settings_defaults() -> None:
    settings = PluginSettings()
    assert settings.disabled == []
    assert settings.skip_broken is False
    assert settings.dir == Path("plugins")


def test_plugin_settings_nested_env(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAB_PLUGINS__DISABLED", json.dumps(["foo", "bar"]))
    monkeypatch.setenv("FAB_PLUGINS__SKIP_BROKEN", "true")
    init_context(project)
    plugins = get_context().plugins
    assert plugins.disabled == ["foo", "bar"]
    assert plugins.skip_broken is True


def test_add_var_to_project_env_writes_key(project: Path) -> None:
    init_context(project)
    add_var_to_project_env("FAB_PLUGINS__DISABLED", json.dumps(["x"]))
    env_file = project / ".FABulous" / ".env"
    assert env_file.exists()
    assert "FAB_PLUGINS__DISABLED" in env_file.read_text()
