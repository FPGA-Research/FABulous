"""Plugin settings: framework config, env parsing, and typed plugin settings."""

import types
from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict

from fabulous.fabulous_settings import (
    PluginSettings,
    add_var_to_project_env,
    get_context,
    init_context,
)
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import PluginManager
from fabulous.plugins.types import PluginError


def test_plugin_settings_defaults(project: Path) -> None:
    init_context(project)
    settings = get_context()
    assert settings.skip_broken_plugins is False
    assert settings.plugin_dir == Path("plugins")


def test_plugin_settings_env(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAB_SKIP_BROKEN_PLUGINS", "true")
    init_context(project)
    assert get_context().skip_broken_plugins is True


def test_add_var_to_project_env_writes_key(project: Path) -> None:
    init_context(project)
    add_var_to_project_env("FAB_SKIP_BROKEN_PLUGINS", "true")
    env_file = project / ".FABulous" / ".env"
    assert env_file.exists()
    assert "FAB_SKIP_BROKEN_PLUGINS" in env_file.read_text()


class _DemoSettings(PluginSettings):
    group = "demo"
    model_config = SettingsConfigDict(env_prefix="FAB_DEMO__")
    jobs: int = 1


def test_plugin_settings_from_context_reads_singleton(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAB_DEMO__JOBS", "7")
    init_context(project)

    module = types.ModuleType("demo_settings_plugin")

    @hookspecs.hookimpl
    def fabulous_register_settings() -> type[PluginSettings]:
        return _DemoSettings

    module.fabulous_register_settings = fabulous_register_settings

    manager = PluginManager()
    manager.pm.register(module, name="demo_settings")
    manager.build_registries()

    assert get_context().plugin_settings["demo"].jobs == 7
    assert _DemoSettings.from_context().jobs == 7


def test_plugin_settings_from_context_unregistered_raises(project: Path) -> None:
    init_context(project)

    class _Missing(PluginSettings):
        group = "missing"

    with pytest.raises(PluginError):
        _Missing.from_context()


def test_build_registries_replaces_prior_plugin_settings(project: Path) -> None:
    init_context(project)

    first = types.ModuleType("first_settings_plugin")

    @hookspecs.hookimpl
    def fabulous_register_settings() -> type[PluginSettings]:
        return _DemoSettings

    first.fabulous_register_settings = fabulous_register_settings
    mgr_a = PluginManager()
    mgr_a.pm.register(first, name="first")
    mgr_a.build_registries()
    assert "demo" in get_context().plugin_settings

    # A second manager that contributes no settings becomes the authority and
    # clears the prior manager's published settings, so none can leak through.
    PluginManager().build_registries()
    assert "demo" not in get_context().plugin_settings
