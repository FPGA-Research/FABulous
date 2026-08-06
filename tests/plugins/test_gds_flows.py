"""GDS-flow registry folding and flow resolution."""

import types

import pytest
from librelane.flows.classic import Classic

from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileMacroFlow,
    FABulousTileVerilogMacroFlow,
    FABulousTileVHDLMacroFlow,
)
from fabulous.plugins.manager import PluginManager
from fabulous.plugins.types import PluginError
from tests.plugins.conftest import make_flow_class, make_gds_flow_module


class MyTileFlow(FABulousTileVerilogMacroFlow):
    """Stand-in for a tile flow contributed by a plugin.

    The class name is the key it registers under, so it is also what a
    `gds_config.yaml` would name.
    """


def test_builtin_registers_every_shipped_flow() -> None:
    manager = PluginManager.core_only()
    assert set(manager.gds_flow_names()) == {
        "FABulousTileVerilogMacroFlow",
        "FABulousTileVHDLMacroFlow",
        "FABulousFabricMacroFlow",
        "FABulousFabricVHDLMacroFlow",
        "FABulousFabricOptimisationFlow",
    }


def test_resolves_registered_flow() -> None:
    manager = PluginManager()
    manager.pm.register(make_gds_flow_module(MyTileFlow), name="fake_gds")
    manager.build_registries()
    assert manager.make_gds_flow("MyTileFlow", FABulousTileMacroFlow) is MyTileFlow


def test_builtin_flow_resolves_by_class_name() -> None:
    manager = PluginManager.core_only()
    resolved = manager.make_gds_flow("FABulousTileVHDLMacroFlow", FABulousTileMacroFlow)
    assert resolved is FABulousTileVHDLMacroFlow


def test_unregistered_flow_raises_listing_available() -> None:
    manager = PluginManager.core_only()
    with pytest.raises(PluginError) as exc:
        manager.make_gds_flow("NoSuchFlow", FABulousTileMacroFlow)
    message = str(exc.value)
    assert "NoSuchFlow" in message
    assert "FABulousTileVerilogMacroFlow" in message


def test_flow_outside_required_base_raises() -> None:
    """A flow FABulous cannot construct is rejected before the run starts."""
    manager = PluginManager()
    unrelated = make_flow_class("UnrelatedFlow", Classic)
    manager.pm.register(make_gds_flow_module(unrelated), name="fake_gds")
    manager.build_registries()
    with pytest.raises(PluginError, match="does not derive from"):
        manager.make_gds_flow("UnrelatedFlow", FABulousTileMacroFlow)


def test_tile_flow_rejected_for_the_fabric_call_site() -> None:
    """The base check is per call site, not merely 'is a FABulous flow'."""
    manager = PluginManager.core_only()
    with pytest.raises(PluginError, match="does not derive from"):
        manager.make_gds_flow("FABulousTileVerilogMacroFlow", FABulousFabricMacroFlow)


def test_duplicate_flow_name_raises_naming_both() -> None:
    manager = PluginManager()
    alpha = make_flow_class("DupFlow", module="plugin_alpha")
    beta = make_flow_class("DupFlow", module="plugin_beta")
    manager.pm.register(make_gds_flow_module(alpha), name="alpha")
    manager.pm.register(make_gds_flow_module(beta), name="beta")
    with pytest.raises(PluginError) as exc:
        manager.build_registries()
    message = str(exc.value)
    # Both providers agree on the flow name, so the module is what tells the
    # two apart in the message.
    assert "plugin_alpha.DupFlow" in message
    assert "plugin_beta.DupFlow" in message


def test_plugin_conflicting_with_a_builtin_flow_raises() -> None:
    """A plugin cannot silently shadow a shipped flow name."""
    manager = PluginManager.core_only()
    shadow = make_flow_class("FABulousTileVerilogMacroFlow", module="plugin_shadow")
    manager.pm.register(make_gds_flow_module(shadow), name="shadow")
    with pytest.raises(PluginError, match="FABulousTileVerilogMacroFlow"):
        manager.build_registries()


def test_info_lists_registered_flows(
    fake_parser_module: types.ModuleType,
) -> None:
    manager = PluginManager()
    manager.pm.register(make_gds_flow_module(MyTileFlow), name="fake_gds")
    manager.pm.register(fake_parser_module, name="fake_parser")
    manager.build_registries()
    assert "gds flows: MyTileFlow" in manager.get_plugin_info_str("fake_gds")
    assert "gds flows: (none)" in manager.get_plugin_info_str("fake_parser")
