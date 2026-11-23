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
from tests.plugins.conftest import make_parser_module


class _DemoSettings(PluginSettings):
    group = "demo"
    model_config = SettingsConfigDict(env_prefix="FAB_DEMO__")
    jobs: int = 1


@pytest.mark.parametrize(
    ("environ", "dot_env", "expected"),
    [
        pytest.param("7", None, 7, id="environment"),
        pytest.param(None, "5", 5, id="project-dot-env"),
        pytest.param("7", "5", 7, id="environment-overrides-dot-env"),
    ],
)
def test_plugin_settings_read_from_context_sources(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    environ: str | None,
    dot_env: str | None,
    expected: int,
) -> None:
    """Plugin settings come from the same sources as FABulous's own settings."""
    if environ is not None:
        monkeypatch.setenv("FAB_DEMO__JOBS", environ)
    if dot_env is not None:
        with (project / ".FABulous" / ".env").open("a") as env_file:
            env_file.write(f"FAB_DEMO__JOBS={dot_env}\n")
    init_context(project)

    module = types.ModuleType("demo_settings_plugin")

    @hookspecs.hookimpl
    def fabulous_register_settings() -> type[PluginSettings]:
        return _DemoSettings

    module.fabulous_register_settings = fabulous_register_settings

    manager = PluginManager()
    manager.pm.register(module, name="demo_settings")
    manager.build_registries()

    assert _DemoSettings.from_context().jobs == expected


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


@pytest.mark.parametrize("skip_broken", [False, True])
def test_plugin_settings_outside_their_namespace_are_rejected(
    project: Path, skip_broken: bool
) -> None:
    """A prefix other than `FAB_<GROUP>__` would collide with FABulous's own keys."""
    init_context(project)

    class _Clashing(PluginSettings):
        group = "clash"
        model_config = SettingsConfigDict(env_prefix="FAB_")

    module = make_parser_module(".clash", "clashing")

    @hookspecs.hookimpl
    def fabulous_register_settings() -> type[PluginSettings]:
        return _Clashing

    module.fabulous_register_settings = fabulous_register_settings
    manager = PluginManager(skip_broken=skip_broken)
    manager.pm.register(module, name="clashing")
    manager.pm.register(make_parser_module(".healthy", "healthy"), name="healthy")

    if not skip_broken:
        with pytest.raises(PluginError, match="FAB_CLASH__"):
            manager.build_registries()
        return

    manager.build_registries()
    assert manager.pm.get_plugin("clashing") is None
    assert "clash" not in get_context().plugin_settings
    with pytest.raises(PluginError, match="No parser"):
        manager.make_parser(Path("fabric.clash"))
    assert callable(manager.make_parser(Path("fabric.healthy")))


def test_startup_failure_removes_registries_and_settings(project: Path) -> None:
    """A plugin skipped at startup cannot supply a parser or settings later."""
    init_context(project)
    module = make_parser_module(".demo", "demo")

    @hookspecs.hookimpl
    def fabulous_register_settings() -> type[PluginSettings]:
        return _DemoSettings

    @hookspecs.hookimpl
    def fabulous_startup() -> None:
        assert _DemoSettings.from_context().jobs == 1
        raise RuntimeError("broken startup")

    module.fabulous_register_settings = fabulous_register_settings
    module.fabulous_startup = fabulous_startup
    manager = PluginManager(skip_broken=True)
    manager.pm.register(module, name="demo")
    manager.build_registries()
    assert callable(manager.make_parser(Path("fabric.demo")))
    assert "demo" in get_context().plugin_settings

    manager.notify_startup()

    assert manager.pm.get_plugin("demo") is None
    assert "demo" not in get_context().plugin_settings
    with pytest.raises(PluginError, match="No parser"):
        manager.make_parser(Path("fabric.demo"))
