"""Typed plugin settings: publication to the context and lookup."""

import types
from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict

from fabulous.custom_exception import PluginError
from fabulous.fabulous_settings import (
    PluginSettings,
    get_context,
    init_context,
)
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import PluginManager


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

    PluginManager().build_registries()
    assert "demo" not in get_context().plugin_settings
