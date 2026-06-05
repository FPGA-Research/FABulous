"""FABulous_API resolves parsers via the manager and fires the lifecycle hook."""

import types
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabulous_api import FABulous_API
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import FABulousPluginManager
from fabulous.plugins.types import PluginError


def _core_manager() -> FABulousPluginManager:
    from fabulous.fabric_generator.code_generator import plugin as codegen_plugin
    from fabulous.fabric_generator.parser import plugin as parser_plugin

    manager = FABulousPluginManager()
    manager.pm.register(codegen_plugin, name="codegen")
    manager.pm.register(parser_plugin, name="parser")
    manager.build_registries()
    return manager


def test_loadfabric_unknown_suffix_raises(tmp_path: Path) -> None:
    manager = _core_manager()
    api = FABulous_API(VerilogCodeGenerator(), plugin_manager=manager)
    bad = tmp_path / "fabric.unknown"
    bad.write_text("")
    with pytest.raises(PluginError):
        api.loadFabric(bad)


def test_loadfabric_fires_after_fabric_loaded(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    manager = _core_manager()

    spy_module = types.ModuleType("spy_lifecycle")
    seen: list[object] = []

    @hookspecs.hookimpl
    def fabulous_after_fabric_loaded(api: object) -> None:
        seen.append(api)

    spy_module.fabulous_after_fabric_loaded = fabulous_after_fabric_loaded
    manager.pm.register(spy_module, name="spy")

    api = FABulous_API(VerilogCodeGenerator(), plugin_manager=manager)
    fabric_file = tmp_path / "fabric.csv"
    mocker.patch.object(manager, "get_parser", return_value=lambda _path: "FABRIC")
    mocker.patch("fabulous.fabulous_api.GeometryGenerator", return_value=object())
    api.loadFabric(fabric_file)
    assert seen == [api]
    assert api.fabric == "FABRIC"
