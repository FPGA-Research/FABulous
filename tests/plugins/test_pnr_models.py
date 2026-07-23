"""Place-and-route model registry folding and backend selection."""

import types

import pytest

from fabulous.fabric_definition.define import PnRTool
from fabulous.fabulous_settings import get_context
from fabulous.plugins.manager import PluginManager
from fabulous.plugins.types import PluginError
from tests.plugins.conftest import make_pnr_model_module


def test_resolves_registered_pnr_model(
    fake_pnr_model_module: types.ModuleType,
) -> None:
    manager = PluginManager()
    manager.pm.register(fake_pnr_model_module, name="fake_pnr")
    manager.build_registries()
    provider = manager.make_pnr_model("fake")
    assert provider.tool == "fake"
    assert provider.generate(None, None) == {"fake.txt": "timed=False"}


def test_builtin_registers_nextpnr() -> None:
    manager = PluginManager.core_only()
    provider = manager.make_pnr_model(PnRTool.NEXTPNR)
    assert provider.supports_timing


def test_no_tool_uses_pnr_backend_setting(
    fake_pnr_model_module: types.ModuleType,
) -> None:
    get_context().pnr_backend = "fake"
    manager = PluginManager()
    manager.pm.register(fake_pnr_model_module, name="fake_pnr")
    manager.build_registries()
    assert manager.make_pnr_model().tool == "fake"


def test_explicit_tool_overrides_pnr_backend_setting(
    fake_pnr_model_module: types.ModuleType,
) -> None:
    get_context().pnr_backend = "fake"
    manager = PluginManager.core_only()
    manager.pm.register(fake_pnr_model_module, name="fake_pnr")
    manager.build_registries()
    assert manager.make_pnr_model(PnRTool.NEXTPNR).tool == PnRTool.NEXTPNR


def test_duplicate_tool_raises_naming_both() -> None:
    manager = PluginManager()
    manager.pm.register(make_pnr_model_module("dup", name="alpha"), name="alpha")
    manager.pm.register(make_pnr_model_module("dup", name="beta"), name="beta")
    with pytest.raises(PluginError) as exc:
        manager.build_registries()
    message = str(exc.value)
    assert "alpha" in message
    assert "beta" in message


def test_missing_tool_lists_available(
    fake_pnr_model_module: types.ModuleType,
) -> None:
    manager = PluginManager()
    manager.pm.register(fake_pnr_model_module, name="fake_pnr")
    manager.build_registries()
    with pytest.raises(PluginError) as exc:
        manager.make_pnr_model("nope")
    assert "fake" in str(exc.value)


def test_timing_request_on_untimed_backend_raises() -> None:
    """An untimed backend must reject a delay model, never ignore it."""
    manager = PluginManager()
    manager.pm.register(
        make_pnr_model_module("untimed", supports_timing=False), name="untimed_pnr"
    )
    manager.build_registries()

    assert manager.make_pnr_model("untimed").tool == "untimed"
    with pytest.raises(PluginError, match="does not support timing"):
        manager.make_pnr_model("untimed", timed=True)
