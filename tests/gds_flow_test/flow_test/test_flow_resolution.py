"""Tests for GDS flow resolution.

`PluginManager.resolve_gds_flow` turns the LibreLane `meta` block of a
project's `gds_config.yaml` files, plus any `--flow` override, into the flow
class FABulous instantiates. That is how a user points a run at their own flow
without changing the FABulous core.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from librelane.flows.classic import Classic
from librelane.flows.flow import FlowException
from librelane.flows.sequential import SequentialFlow

from fabulous.custom_exception import InvalidFlowDefinition
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileMacroFlow,
    FABulousTileVerilogMacroFlow,
    FABulousTileVHDLMacroFlow,
)
from fabulous.fabulous_api import FABulous_API
from fabulous.plugins.manager import PluginManager
from tests.plugins.conftest import make_flow_class, make_gds_flow_module


class MyTileFlow(FABulousTileVerilogMacroFlow):
    """Stand-in for a tile flow contributed by a plugin.

    A flow registers under its class name, so this is also the value a
    `gds_config.yaml` puts in `meta.flow`.
    """


class RecordingTileFlow(FABulousTileMacroFlow):
    """A tile flow that records its construction instead of running anything."""

    instantiated: list[tuple] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        RecordingTileFlow.instantiated.append((args, kwargs))

    def start(self, **_kwargs: object) -> MagicMock:
        """Return a stand-in result whose snapshot call is a no-op."""
        return MagicMock()


class RecordingFabricFlow(FABulousFabricMacroFlow):
    """A fabric flow that records its construction instead of running anything."""

    instantiated: list[tuple] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        RecordingFabricFlow.instantiated.append((args, kwargs))

    def start(self, **_kwargs: object) -> MagicMock:
        """Return a stand-in result whose snapshot call is a no-op."""
        return MagicMock()


@pytest.fixture
def manager() -> PluginManager:
    """A manager with the built-in flows plus the test flows registered."""
    manager = PluginManager.core_only()
    extra = [
        MyTileFlow,
        make_flow_class("UnrelatedFlow", Classic),
        RecordingTileFlow,
        RecordingFabricFlow,
    ]
    for flow_cls in extra:
        manager.pm.register(
            make_gds_flow_module(flow_cls), name=f"fake_{flow_cls.__name__}"
        )
    manager.build_registries()
    return manager


@pytest.fixture(autouse=True)
def clear_recordings() -> None:
    """Drop construction records left by an earlier test."""
    RecordingTileFlow.instantiated.clear()
    RecordingFabricFlow.instantiated.clear()


def write_config(path: Path, config: dict) -> Path:
    """Write a GDS config YAML and return its path."""
    path.write_text(yaml.safe_dump(config))
    return path


def step_ids(flow: type[SequentialFlow]) -> list[str]:
    """Return the step IDs of a sequential flow, in order."""
    return [step.id for step in flow.Steps]


class TestReadFlowMeta:
    """Reading the `meta` block off a config file."""

    def test_missing_meta_selects_nothing(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """A config without a `meta` block leaves the default in place."""
        config = write_config(tmp_path / "gds_config.yaml", {"CLOCK_PERIOD": 20.0})
        resolved = manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [config])
        assert resolved is FABulousTileVerilogMacroFlow

    def test_reads_flow_and_substitutions_together(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """Both fields of one `meta` block take effect."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {
                "meta": {
                    "version": 2,
                    "flow": "MyTileFlow",
                    "substituting_steps": {"OpenROAD.IRDropReport": None},
                }
            },
        )
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow,
            [config],
            required_base=FABulousTileMacroFlow,
        )
        assert issubclass(resolved, MyTileFlow)
        assert "OpenROAD.IRDropReport" not in step_ids(resolved)

    def test_invalid_meta_raises(self, manager: PluginManager, tmp_path: Path) -> None:
        """An unknown key in `meta` is reported against the file."""
        config = write_config(
            tmp_path / "gds_config.yaml", {"meta": {"not_a_meta_field": 1}}
        )
        with pytest.raises(InvalidFlowDefinition, match="invalid 'meta' object"):
            manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [config])


class TestResolveFlow:
    """Picking the flow class from a list of config sources."""

    def test_defaults_without_configs(self, manager: PluginManager) -> None:
        """No sources at all leaves the built-in flow in place."""
        assert (
            manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [])
            is FABulousTileVerilogMacroFlow
        )

    @pytest.mark.parametrize("sources", [[None], [Path("does/not/exist.yaml")]])
    def test_skips_absent_sources(
        self, manager: PluginManager, sources: list[Path | None]
    ) -> None:
        """Missing and unset sources are ignored rather than raising."""
        assert (
            manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, sources)
            is FABulousTileVerilogMacroFlow
        )

    def test_selects_a_plugin_flow(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """`meta.flow` replaces the built-in flow."""
        config = write_config(
            tmp_path / "gds_config.yaml", {"meta": {"flow": "MyTileFlow"}}
        )
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow,
            [config],
            required_base=FABulousTileMacroFlow,
        )
        assert resolved is MyTileFlow

    def test_later_source_wins(self, manager: PluginManager, tmp_path: Path) -> None:
        """A tile-level config overrides the shared base config."""
        base = write_config(
            tmp_path / "base.yaml", {"meta": {"flow": "FABulousTileVHDLMacroFlow"}}
        )
        override = write_config(
            tmp_path / "override.yaml", {"meta": {"flow": "MyTileFlow"}}
        )
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow,
            [base, override],
            required_base=FABulousTileMacroFlow,
        )
        assert resolved is MyTileFlow

    def test_earlier_source_applies_when_later_is_silent(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """An override that says nothing about the flow keeps the base choice."""
        base = write_config(
            tmp_path / "base.yaml", {"meta": {"flow": "FABulousTileVHDLMacroFlow"}}
        )
        override = write_config(tmp_path / "override.yaml", {"CLOCK_PERIOD": 20.0})
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow,
            [base, override],
            required_base=FABulousTileMacroFlow,
        )
        assert resolved is FABulousTileVHDLMacroFlow

    def test_unknown_flow_names_the_config(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """The error says which config asked for the missing flow."""
        config = write_config(
            tmp_path / "gds_config.yaml", {"meta": {"flow": "NoSuchFlow"}}
        )
        with pytest.raises(InvalidFlowDefinition) as exc:
            manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [config])
        message = str(exc.value)
        assert "gds_config.yaml" in message
        assert "NoSuchFlow" in message

    def test_flow_outside_required_base_raises(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """A flow FABulous cannot construct is rejected up front."""
        config = write_config(
            tmp_path / "gds_config.yaml", {"meta": {"flow": "UnrelatedFlow"}}
        )
        with pytest.raises(InvalidFlowDefinition, match="does not derive from"):
            manager.resolve_gds_flow(
                FABulousTileVerilogMacroFlow,
                [config],
                required_base=FABulousTileMacroFlow,
            )

    def test_step_list_flow_raises(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """A bare step list has no FABulous constructor and is rejected."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {"meta": {"flow": ["Verilator.Lint", "Yosys.Synthesis"]}},
        )
        with pytest.raises(InvalidFlowDefinition, match="must name a registered flow"):
            manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [config])

    def test_fabric_flow_is_resolved_too(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """The same reader drives the fabric-stitching call site."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {"meta": {"flow": "FABulousFabricVHDLMacroFlow"}},
        )
        resolved = manager.resolve_gds_flow(
            FABulousFabricMacroFlow,
            [config],
            required_base=FABulousFabricMacroFlow,
        )
        assert resolved.__name__ == "FABulousFabricVHDLMacroFlow"


class TestSubstitutingSteps:
    """Applying `meta.substituting_steps` to the resolved flow.

    `SequentialFlow` consumes `Substitutions` when the subclass is created and
    resets the attribute, so the effect is asserted on `Steps`.
    """

    def test_removes_a_step(self, manager: PluginManager, tmp_path: Path) -> None:
        """A `null` replacement drops the step from the flow."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {"meta": {"substituting_steps": {"OpenROAD.IRDropReport": None}}},
        )
        resolved = manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [config])
        assert issubclass(resolved, FABulousTileVerilogMacroFlow)
        assert "OpenROAD.IRDropReport" not in step_ids(resolved)

    def test_accepts_a_pair_list(self, manager: PluginManager, tmp_path: Path) -> None:
        """The list-of-pairs spelling is accepted as well as the mapping one."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {"meta": {"substituting_steps": [["OpenROAD.IRDropReport", None]]}},
        )
        resolved = manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [config])
        assert "OpenROAD.IRDropReport" not in step_ids(resolved)

    def test_merges_across_sources(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """Substitutions from every config are applied to one subclass."""
        base = write_config(
            tmp_path / "base.yaml",
            {"meta": {"substituting_steps": {"OpenROAD.IRDropReport": None}}},
        )
        override = write_config(
            tmp_path / "override.yaml",
            {"meta": {"substituting_steps": {"Netgen.LVS": None}}},
        )
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow, [base, override]
        )
        ids = step_ids(resolved)
        assert "OpenROAD.IRDropReport" not in ids
        assert "Netgen.LVS" not in ids

    def test_later_source_wins_on_a_shared_key(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """An override retargets a substitution the base config introduced."""
        base = write_config(
            tmp_path / "base.yaml",
            {"meta": {"substituting_steps": {"Netgen.LVS": "OpenROAD.IRDropReport"}}},
        )
        override = write_config(
            tmp_path / "override.yaml",
            {"meta": {"substituting_steps": {"Netgen.LVS": None}}},
        )
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow, [base, override]
        )
        ids = step_ids(resolved)
        assert "Netgen.LVS" not in ids
        # The base config's replacement must not have been applied as well.
        assert ids.count("OpenROAD.IRDropReport") == 1

    def test_applies_to_a_plugin_flow(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """Substitutions land on the plugin flow, not on the built-in default."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {
                "meta": {
                    "flow": "MyTileFlow",
                    "substituting_steps": {"OpenROAD.IRDropReport": None},
                }
            },
        )
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow,
            [config],
            required_base=FABulousTileMacroFlow,
        )
        assert issubclass(resolved, MyTileFlow)
        assert "OpenROAD.IRDropReport" not in step_ids(resolved)

    def test_default_flow_is_left_untouched(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """`Substitute` must subclass rather than mutate the shared flow."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {"meta": {"substituting_steps": {"OpenROAD.IRDropReport": None}}},
        )
        manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [config])
        assert "OpenROAD.IRDropReport" in step_ids(FABulousTileVerilogMacroFlow)

    def test_unknown_step_raises(self, manager: PluginManager, tmp_path: Path) -> None:
        """A substitution that matches no step is reported by LibreLane."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {"meta": {"substituting_steps": {"No.SuchStep": None}}},
        )
        with pytest.raises(FlowException, match="No.SuchStep"):
            manager.resolve_gds_flow(FABulousTileVerilogMacroFlow, [config])


class TestApiWiring:
    """The GDS entry points of `FABulous_API` run the flow the config selects."""

    def test_gen_tile_macro_uses_the_selected_flow(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """`genTileMacro` instantiates the flow named by the tile config."""
        config = write_config(
            tmp_path / "gds_config.yaml", {"meta": {"flow": "RecordingTileFlow"}}
        )
        api = FABulous_API(manager.make_writer(HDLType.VERILOG), manager)
        api.fabric = MagicMock()

        api.genTileMacro(
            tmp_path / "LUT4AB",
            tmp_path / "pins.yaml",
            tmp_path / "macro",
            "sky130A",
            tmp_path / "pdk",
            base_config_path=config,
        )

        assert len(RecordingTileFlow.instantiated) == 1

    def test_fabric_stitching_uses_the_selected_flow(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """`fabric_stitching` instantiates the flow named by the fabric config."""
        config = write_config(
            tmp_path / "gds_config.yaml", {"meta": {"flow": "RecordingFabricFlow"}}
        )
        api = FABulous_API(manager.make_writer(HDLType.VERILOG), manager)
        api.fabric = MagicMock()

        api.fabric_stitching(
            {},
            tmp_path / "fabric.v",
            tmp_path / "macro",
            "sky130A",
            tmp_path / "pdk",
            base_config_path=config,
        )

        assert len(RecordingFabricFlow.instantiated) == 1


class TestFlowOverride:
    """`--flow` selects a flow for one run, beating every config source."""

    def test_override_without_any_config(self, manager: PluginManager) -> None:
        """The override alone replaces the built-in default."""
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow,
            [],
            required_base=FABulousTileMacroFlow,
            flow_override="MyTileFlow",
        )
        assert resolved is MyTileFlow

    def test_override_beats_meta_flow(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """A config naming another flow does not win over the command line."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {"meta": {"flow": "FABulousTileVHDLMacroFlow"}},
        )
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow,
            [config],
            required_base=FABulousTileMacroFlow,
            flow_override="MyTileFlow",
        )
        assert resolved is MyTileFlow

    def test_override_still_takes_config_substitutions(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """Substitutions are config-level, so they apply to the override too."""
        config = write_config(
            tmp_path / "gds_config.yaml",
            {"meta": {"substituting_steps": {"OpenROAD.IRDropReport": None}}},
        )
        resolved = manager.resolve_gds_flow(
            FABulousTileVerilogMacroFlow,
            [config],
            required_base=FABulousTileMacroFlow,
            flow_override="MyTileFlow",
        )
        assert issubclass(resolved, MyTileFlow)
        assert "OpenROAD.IRDropReport" not in step_ids(resolved)

    def test_unknown_override_blames_the_flag(self, manager: PluginManager) -> None:
        """The error points at `--flow`, not at a config file."""
        with pytest.raises(InvalidFlowDefinition) as exc:
            manager.resolve_gds_flow(
                FABulousTileVerilogMacroFlow, [], flow_override="NoSuchFlow"
            )
        assert "--flow" in str(exc.value)

    def test_override_outside_required_base_raises(
        self, manager: PluginManager
    ) -> None:
        """The base check applies to the override as well."""
        with pytest.raises(InvalidFlowDefinition, match="does not derive from"):
            manager.resolve_gds_flow(
                FABulousTileVerilogMacroFlow,
                [],
                required_base=FABulousTileMacroFlow,
                flow_override="UnrelatedFlow",
            )

    def test_api_passes_the_override_through(
        self, manager: PluginManager, tmp_path: Path
    ) -> None:
        """`genTileMacro(flow=...)` reaches the resolver."""
        api = FABulous_API(manager.make_writer(HDLType.VERILOG), manager)
        api.fabric = MagicMock()

        api.genTileMacro(
            tmp_path / "LUT4AB",
            tmp_path / "pins.yaml",
            tmp_path / "macro",
            "sky130A",
            tmp_path / "pdk",
            flow="RecordingTileFlow",
        )

        assert len(RecordingTileFlow.instantiated) == 1
