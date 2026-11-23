"""FABulous_API resolves parsers via the manager and fires the lifecycle hook."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.custom_exception import PluginError
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabulous_api import FABulous_API
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import PluginManager


def test_loadfabric_unknown_suffix_raises(tmp_path: Path) -> None:
    manager = PluginManager.core_only()
    api = FABulous_API(VerilogCodeGenerator(), plugin_manager=manager)
    bad = tmp_path / "fabric.unknown"
    bad.write_text("")
    with pytest.raises(PluginError):
        api.loadFabric(bad)


def test_loadfabric_fires_after_fabric_loaded(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    manager = PluginManager.core_only()

    seen: list[FABulous_API] = []

    class _Spy:
        @hookspecs.hookimpl
        def fabulous_after_fabric_loaded(self, api: FABulous_API) -> None:
            seen.append(api)

    manager.pm.register(_Spy(), name="spy")

    api = FABulous_API(VerilogCodeGenerator(), plugin_manager=manager)
    fabric_file = tmp_path / "fabric.csv"
    mocker.patch.object(manager, "make_parser", return_value=lambda _path: "FABRIC")
    mocker.patch("fabulous.fabulous_api.GeometryGenerator", return_value=object())
    api.loadFabric(fabric_file)
    assert seen == [api]
    assert api.fabric == "FABRIC"
