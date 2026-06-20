"""Tests for graph-only switch-matrix pattern generation."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import fabulous.fabulous_settings as fabulous_settings
from fabulous.fabric_cad.fabxplore.modules.routing_patterns import (
    SwitchMatrixPattern,
    SwitchMatrixPatternOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.common import (
    RoutingTrackGroup,
    active_pairs,
    cardinal_routable_groups,
    routing_track_groups,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes import SwitchMatrixPatternPass
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core import FabGraph
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingConfigBits,
    RoutingPipKind,
    RoutingResourceKey,
    RoutingSwitchMatrix,
    RoutingTileBelModel,
    RoutingTileModel,
    RoutingTilePortModel,
)
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabulous_api import FABulous_API

if TYPE_CHECKING:
    from collections.abc import Iterable


def test_switch_matrix_pattern_adds_graph_only_pairs() -> None:
    """Add BEL input, output coverage, and routing pattern pairs in memory."""
    graph = _FakePnRBridge()

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=2,
            output_fanin=1,
            routing_pip_pattern="subset",
            routing_pip_fs=2,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.applied_pips > 0
    assert result.stats.generated_bel_input_pips == 4
    assert result.stats.generated_output_coverage_pips > 0
    assert result.stats.generated_routing_pips > 0
    assert ("A_I0", "NEND1") in graph.active_pairs
    assert any(row.startswith("NBEG") for row, _source in graph.active_pairs)
    assert not graph.write_methods_called


def test_switch_matrix_pattern_can_replace_existing_matrix() -> None:
    """Replace the current matrix instead of keeping old active pairs."""
    graph = _FakePnRBridge()
    graph.active_pairs.add(("A_I0", "A_O"))

    SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=1,
            output_fanin=1,
            include_bel_output_sources=False,
            include_constant_sources=False,
            routing_pip_pattern="none",
            replace_existing_matrix=True,
            track_progress=False,
        )
    ).run(graph)

    assert ("A_I0", "A_O") not in graph.active_pairs
    assert graph.set_switch_matrix_called
    assert graph.active_pairs
    assert all(source != "A_O" for _row, source in graph.active_pairs)


def test_switch_matrix_pattern_generates_optional_jump_hierarchy() -> None:
    """Build BEL input access through generated graph JUMP resources."""
    graph = _FakePnRBridge()

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=4,
            output_fanin=1,
            routing_pip_pattern="none",
            hierarchy_enabled=True,
            hierarchy_levels=[2],
            hierarchy_jump_prefix="J_LOCAL",
            hierarchy_replace_direct_input_pips=True,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.added_jump_wires > 0
    assert result.stats.generated_hierarchy_pips > 0
    assert graph.added_external_resources
    assert any(row.startswith("J_LOCAL") for row, _source in graph.active_pairs)
    assert ("A_I0", "NEND0") not in graph.active_pairs
    assert any(
        row == "A_I0" and source.startswith("J_LOCAL")
        for row, source in graph.active_pairs
    )


def test_switch_matrix_pattern_generates_two_level_jump_hierarchy() -> None:
    """Build a two-level hierarchy when fanin needs multiple reduction stages."""
    graph = _FakePnRBridge()

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=4,
            include_bel_output_sources=False,
            include_constant_sources=False,
            output_fanin=1,
            cover_unconnected_matrix_rows=False,
            routing_pip_pattern="none",
            hierarchy_enabled=True,
            hierarchy_levels=[2, 2],
            hierarchy_jump_prefix="J_TREE",
            hierarchy_replace_direct_input_pips=True,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.added_jump_wires == 6
    assert result.stats.generated_hierarchy_pips == 14
    assert ("J_TREE_D0_A_I0_L0_0_BEG0", "NEND0") in graph.active_pairs
    assert ("J_TREE_D0_A_I0_L0_0_BEG0", "NEND1") in graph.active_pairs
    assert ("J_TREE_D0_A_I0_L0_1_BEG0", "NEND2") in graph.active_pairs
    assert ("J_TREE_D0_A_I0_L0_1_BEG0", "NEND3") in graph.active_pairs
    assert (
        "J_TREE_D0_A_I0_L1_0_BEG0",
        "J_TREE_D0_A_I0_L0_0_END0",
    ) in graph.active_pairs
    assert (
        "J_TREE_D0_A_I0_L1_0_BEG0",
        "J_TREE_D0_A_I0_L0_1_END0",
    ) in graph.active_pairs
    assert ("A_I0", "J_TREE_D0_A_I0_L1_0_END0") in graph.active_pairs
    assert not any(
        row == "A_I0" and source in {"NEND0", "NEND1", "NEND2", "NEND3"}
        for row, source in graph.active_pairs
    )


def test_switch_matrix_pattern_stops_redundant_hierarchy_levels() -> None:
    """Do not create extra hierarchy stages after fanin reaches one source."""
    graph = _FakePnRBridge()

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=4,
            include_bel_output_sources=False,
            include_constant_sources=False,
            output_fanin=1,
            cover_unconnected_matrix_rows=False,
            routing_pip_pattern="none",
            hierarchy_enabled=True,
            hierarchy_levels=[4, 2],
            hierarchy_jump_prefix="J_STOP",
            hierarchy_replace_direct_input_pips=True,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.added_jump_wires == 2
    assert result.stats.generated_hierarchy_pips == 10
    assert ("A_I0", "J_STOP_D0_A_I0_L0_0_END0") in graph.active_pairs
    assert not any("_L1_" in row for row, _source in graph.active_pairs)
    assert not any("_L1_" in source for _row, source in graph.active_pairs)


def test_switch_matrix_pattern_hierarchy_keeps_uneven_chunks() -> None:
    """Keep all sources when a hierarchy level leaves a partial chunk."""
    graph = _FakePnRBridge()

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=5,
            include_bel_output_sources=False,
            include_constant_sources=False,
            output_fanin=1,
            cover_unconnected_matrix_rows=False,
            routing_pip_pattern="none",
            hierarchy_enabled=True,
            hierarchy_levels=[2, 2],
            hierarchy_jump_prefix="J_ODD",
            hierarchy_replace_direct_input_pips=True,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.added_jump_wires == 10
    assert result.stats.generated_hierarchy_pips == 20
    for source in ("NEND0", "NEND1", "NEND2", "NEND3", "EEND0"):
        assert any(
            row.startswith("J_ODD_D0_A_I0_L0_") and active_source == source
            for row, active_source in graph.active_pairs
        )
    assert {
        source
        for row, source in graph.active_pairs
        if row == "A_I0" and source.startswith("J_ODD_D0_A_I0_L1_")
    } == {
        "J_ODD_D0_A_I0_L1_0_END0",
        "J_ODD_D0_A_I0_L1_1_END0",
    }


@pytest.mark.parametrize(
    ("input_fanin", "hierarchy_levels"),
    [
        (2, [2, 2, 2]),
        (3, [2, 2]),
        (4, [3, 2]),
        (5, [3, 2]),
        (6, [3, 2]),
        (7, [3, 3]),
        (7, [4, 2]),
        (7, [5, 2]),
        (7, [7, 2]),
        (6, [2, 3, 2]),
    ],
)
def test_switch_matrix_pattern_hierarchy_accepts_varied_level_lists(
    input_fanin: int,
    hierarchy_levels: list[int],
) -> None:
    """Handle several hierarchy lists with fanin entries up to seven."""
    graph = _FakePnRBridge()
    prefix = (
        f"J_CASE_{input_fanin}_{'_'.join(str(level) for level in hierarchy_levels)}"
    )

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=input_fanin,
            include_bel_output_sources=False,
            include_constant_sources=False,
            output_fanin=1,
            cover_unconnected_matrix_rows=False,
            routing_pip_pattern="none",
            hierarchy_enabled=True,
            hierarchy_levels=hierarchy_levels,
            hierarchy_jump_prefix=prefix,
            hierarchy_replace_direct_input_pips=True,
            track_progress=False,
        )
    ).run(graph)

    added_per_bel, pips_per_bel, generated_levels = _expected_hierarchy_shape(
        input_fanin,
        hierarchy_levels,
    )
    assert result.stats.added_jump_wires == added_per_bel * 2
    assert result.stats.generated_hierarchy_pips == pips_per_bel * 2
    for source in _expected_source_prefix(0, input_fanin):
        assert any(
            row.startswith(f"{prefix}_D0_A_I0_L0_") and active_source == source
            for row, active_source in graph.active_pairs
        )
    assert any(
        row == "A_I0" and source.startswith(f"{prefix}_D0_A_I0_L")
        for row, source in graph.active_pairs
    )
    assert not any(
        f"_L{generated_levels}_" in row or f"_L{generated_levels}_" in source
        for row, source in graph.active_pairs
    )


def test_switch_matrix_pattern_demo_opt_hierarchy_writes_real_lut5f_rtl(
    tmp_path: Path,
) -> None:
    """Apply hierarchy to real demo_opt LUT5F and regenerate tile artifacts."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    output_project = tmp_path / "demo_opt_export"
    shutil.copytree(project_dir, output_project)
    graph = _load_demo_opt_graph(project_dir)
    tile_name = "LUT5F"
    prefix = "J_REAL"
    options = SwitchMatrixPatternOptions(
        tile_name=tile_name,
        input_fanin=4,
        include_bel_output_sources=False,
        include_constant_sources=False,
        output_fanin=1,
        cover_unconnected_matrix_rows=False,
        routing_pip_pattern="none",
        hierarchy_enabled=True,
        hierarchy_levels=[3, 2],
        hierarchy_jump_prefix=prefix,
        hierarchy_replace_direct_input_pips=True,
        track_progress=False,
    )

    result = SwitchMatrixPattern(options).run(graph)
    matrix_pairs = set(active_pairs(graph.switch_matrix(tile_name)))
    first_bel_input = next(
        wire
        for bel in graph.tile_model(tile_name).bels
        for wire in bel.inputs
        if wire in graph.matrix_sources(tile_name)
    )

    assert result.stats.added_jump_wires > 0
    assert result.stats.generated_hierarchy_pips > 0
    assert any(row.startswith(f"{prefix}_D0_") for row, _source in matrix_pairs)
    assert any("_L1_" in row for row, _source in matrix_pairs)
    assert any(
        row == first_bel_input and source.startswith(f"{prefix}_D0_")
        for row, source in matrix_pairs
    )
    assert not any("_L2_" in row or "_L2_" in source for row, source in matrix_pairs)

    graph.write_tile_sources(
        output_root=output_project,
        tile_types=(tile_name,),
        generate_rtl=True,
    )

    tile_dir = output_project / "Tile" / tile_name
    matrix_list = tile_dir / f"{tile_name}_switch_matrix.list"
    matrix_csv = tile_dir / f"{tile_name}_switch_matrix.csv"
    matrix_rtl = tile_dir / f"{tile_name}_switch_matrix.v"
    tile_rtl = tile_dir / f"{tile_name}.v"

    assert matrix_list.exists()
    assert matrix_csv.exists()
    assert matrix_rtl.exists()
    assert tile_rtl.exists()
    assert prefix in matrix_list.read_text(encoding="utf-8")
    assert prefix in matrix_csv.read_text(encoding="utf-8")
    assert prefix in matrix_rtl.read_text(encoding="utf-8")


def test_switch_matrix_pattern_full_enables_current_matrix_domain() -> None:
    """Enable every cell in the current switch-matrix row/column domain."""
    graph = _FakePnRBridge()
    graph.active_pairs = {
        ("A_I0", "NEND0"),
        ("A_I1", "NEND1"),
    }

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            routing_pip_pattern="full",
            replace_existing_matrix=True,
            track_progress=False,
        )
    ).run(graph)

    assert graph.set_switch_matrix_called
    assert graph.active_pairs == {
        ("A_I0", "NEND0"),
        ("A_I0", "NEND1"),
        ("A_I1", "NEND0"),
        ("A_I1", "NEND1"),
    }
    assert result.stats.generated_routing_pips == 4
    assert result.stats.active_pips_after == 4


def test_routing_track_groups_keep_port_metadata() -> None:
    """Expose source, destination, offset, and track-count metadata."""
    graph = _FakePnRBridge()

    groups = routing_track_groups(graph, "Toy")
    north = next(group for group in groups if group.direction is Direction.NORTH)
    east = next(group for group in groups if group.direction is Direction.EAST)

    assert north.source_name == "NBEG"
    assert north.destination_name == "NEND"
    assert north.x_offset == 0
    assert north.y_offset == -1
    assert north.wire_count == 4
    assert north.destination_rows == ["NBEG0", "NBEG1", "NBEG2", "NBEG3"]
    assert north.selectable_sources == ["NEND0", "NEND1", "NEND2", "NEND3"]
    assert east.source_name == "EBEG"
    assert east.destination_name == "EEND"
    assert east.x_offset == 1
    assert east.y_offset == 0
    assert east.wire_count == 4


def test_routing_track_groups_use_graph_external_resources() -> None:
    """Discover routing groups added directly to the active graph."""
    graph = _FakePnRBridge()
    graph.add_external_resource(
        "Toy",
        Direction.SOUTH,
        "SBEG",
        0,
        1,
        "SEND",
        2,
    )

    groups = routing_track_groups(graph, "Toy")
    south = next(group for group in groups if group.direction is Direction.SOUTH)

    assert south.source_name == "SBEG"
    assert south.destination_name == "SEND"
    assert south.destination_rows == ["SBEG0", "SBEG1"]
    assert south.selectable_sources == ["SEND0", "SEND1"]

    SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=1,
            output_fanin=1,
            routing_pip_pattern="wilton",
            routing_pip_fs=3,
            track_progress=False,
        )
    ).run(graph)

    assert any(row in {"SBEG0", "SBEG1"} for row, _source in graph.active_pairs)
    assert any(source in {"SEND0", "SEND1"} for _row, source in graph.active_pairs)


def test_lut_carry_rich_balances_output_egress_by_group() -> None:
    """Connect LUT outputs into every discovered cardinal routing group."""
    graph = _FakePnRBridge()
    _use_rich_lut_tile_model(graph)

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=1,
            output_fanin=1,
            routing_pip_pattern="lut_carry_rich",
            routing_pip_fs=2,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.generated_routing_pips > 0
    assert any(
        row.startswith("NBEG") and source == "A_O" for row, source in graph.active_pairs
    )
    assert any(
        row.startswith("EBEG") and source == "A_O" for row, source in graph.active_pairs
    )
    assert ("A_I0", "GND0") in graph.active_pairs
    assert ("A_I1", "VCC0") in graph.active_pairs
    assert ("A_I0", "A_O") in graph.active_pairs
    assert ("B_I0", "A_O") in graph.active_pairs
    assert ("B_Ci", "A_Co") in graph.active_pairs
    assert ("A_I0", "A_Co") in graph.active_pairs
    assert ("A_SR", "EBEG0") in graph.active_pairs


def test_lut_carry_rich_caps_final_active_pips() -> None:
    """Keep a normal eight-BEL rich pattern below the LUT5F starter budget."""
    graph = _FakePnRBridge()
    _use_rich_lut_tile_model(graph, bel_count=8)

    result = SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=8,
            output_fanin=5,
            routing_pip_pattern="lut_carry_rich",
            routing_pip_fs=4,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.active_pips_after <= 3000


def test_lut_carry_rich_aligns_adjacent_bel_pair_lanes() -> None:
    """Use matching sparse routing lanes for paired BEL egress and ingress."""
    graph = _FakePnRBridge()
    _use_rich_lut_tile_model(graph, bel_count=8)

    SwitchMatrixPattern(
        SwitchMatrixPatternOptions(
            tile_name="Toy",
            input_fanin=8,
            output_fanin=5,
            routing_pip_pattern="lut_carry_rich",
            routing_pip_fs=4,
            track_progress=False,
        )
    ).run(graph)

    assert ("NBEG2", "H_O1") in graph.active_pairs
    assert ("G_Ci", "NEND2") in graph.active_pairs
    assert ("EBEG3", "H_O1") in graph.active_pairs
    assert ("G_Ci", "EEND3") in graph.active_pairs


def test_switch_matrix_pattern_pass_wrapper_uses_pnr_bridge() -> None:
    """Run the PnR wrapper against the bridge-shaped graph object."""
    graph = _FakePnRBridge()
    switch_matrix_pass = SwitchMatrixPatternPass(
        tile_name="Toy",
        input_fanin=1,
        routing_pip_pattern="none",
        track_progress=False,
    )

    switch_matrix_pass.run_on(graph)

    assert switch_matrix_pass.result_data is not None
    assert "Switch Matrix Pattern Report" in switch_matrix_pass.report_summary
    assert graph.active_pairs


def test_route_through_patterns_ignore_jump_groups() -> None:
    """Keep local JUMP groups out of route-through pattern candidates."""
    groups = [
        RoutingTrackGroup(
            direction=Direction.NORTH,
            source_name="NBEG",
            x_offset=0,
            y_offset=-1,
            destination_name="NEND",
            wire_count=1,
            destination_rows=["NBEG0"],
            selectable_sources=["NEND0"],
        ),
        RoutingTrackGroup(
            direction=Direction.JUMP,
            source_name="JBEG",
            x_offset=0,
            y_offset=0,
            destination_name="JEND",
            wire_count=1,
            destination_rows=["JBEG0"],
            selectable_sources=["JEND0"],
        ),
    ]

    assert cardinal_routable_groups(groups) == [groups[0]]


class _FakePnRBridge:
    """Small bridge-shaped graph fake for routing-pattern tests."""

    def __init__(self) -> None:
        self.model = _tile_model()
        self.available_wires = set(_base_available_wires())
        self.external_resource_keys = [
            RoutingResourceKey(
                tile_type="Toy",
                kind=RoutingPipKind.EXTERNAL_WIRE,
                source_name=port.source_name,
                destination_name=port.destination_name,
                direction=port.direction,
                x_offset=port.x_offset,
                y_offset=port.y_offset,
                wire_count=port.wire_count,
                wire_class=abs(port.x_offset) + abs(port.y_offset),
            )
            for port in self.model.ports
        ]
        self.active_pairs: set[tuple[str, str]] = {("A_I0", "NEND0")}
        self.added_external_resources: list[tuple[str, str]] = []
        self.set_switch_matrix_called = False
        self.write_methods_called = False

    def tile_model(self, tile_name: str) -> RoutingTileModel:
        """Return the fake tile model."""
        assert tile_name == "Toy"
        return self.model

    def matrix_sources(self, tile_name: str) -> list[str]:
        """Return matrix-visible wires."""
        assert tile_name == "Toy"
        return sorted(self.available_wires)

    def external_resources(
        self,
        tile_name: str,
        *,
        active_only: bool = True,
    ) -> list[RoutingResourceKey]:
        """Return fake active external resources."""
        assert tile_name == "Toy"
        assert active_only
        return list(self.external_resource_keys)

    def switch_matrix(self, tile_name: str) -> RoutingSwitchMatrix:
        """Return active matrix pairs as a delay matrix."""
        assert tile_name == "Toy"
        rows = list(dict.fromkeys(row for row, _source in sorted(self.active_pairs)))
        columns = list(
            dict.fromkeys(source for _row, source in sorted(self.active_pairs))
        )
        row_index = {row: index for index, row in enumerate(rows)}
        column_index = {column: index for index, column in enumerate(columns)}
        matrix = [[0.0 for _column in columns] for _row in rows]
        for row, source in self.active_pairs:
            matrix[row_index[row]][column_index[source]] = 8.0
        return RoutingSwitchMatrix(
            tile_type=tile_name,
            columns=columns,
            rows=rows,
            matrix=matrix,
        )

    def set_switch_matrix(
        self,
        tile_name: str,
        columns: list[str],
        rows: list[str],
        matrix: list[list[float]],
    ) -> None:
        """Replace active matrix pairs."""
        assert tile_name == "Toy"
        self.set_switch_matrix_called = True
        self.active_pairs.clear()
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                assert row in self.available_wires
                assert column in self.available_wires
                if matrix[row_index][column_index] > 0:
                    self.active_pairs.add((row, column))

    def add_matrix_rows(
        self,
        tile_name: str,
        entries: Iterable[tuple[str, str, float]],
        *,
        overwrite: bool = False,
    ) -> None:
        """Add active matrix pairs."""
        assert tile_name == "Toy"
        if overwrite:
            self.active_pairs.clear()
        for row, source, _delay in entries:
            assert row in self.available_wires
            assert source in self.available_wires
            assert (row, source) not in self.active_pairs
            self.active_pairs.add((row, source))

    def delete_matrix_resource(
        self,
        tile_name: str,
        source_name: str,
        destination_name: str,
    ) -> None:
        """Delete one active matrix pair."""
        assert tile_name == "Toy"
        self.active_pairs.remove((source_name, destination_name))

    def add_external_resource(
        self,
        tile_name: str,
        direction: Direction,
        source_name: str,
        x_offset: int,
        y_offset: int,
        destination_name: str,
        wire_count: int,
        *,
        delay: float = 8.0,
    ) -> None:
        """Add a fake external resource."""
        assert tile_name == "Toy"
        assert delay == 8.0
        self.available_wires.update(
            f"{wire}{index}"
            for index in range(wire_count)
            for wire in (source_name, destination_name)
            if wire != "NULL"
        )
        self.external_resource_keys.append(
            RoutingResourceKey(
                tile_type=tile_name,
                kind=RoutingPipKind.EXTERNAL_WIRE,
                source_name=source_name,
                destination_name=destination_name,
                direction=direction,
                x_offset=x_offset,
                y_offset=y_offset,
                wire_count=wire_count,
                wire_class=abs(x_offset) + abs(y_offset),
            )
        )
        self.added_external_resources.append((source_name, destination_name))

    def get_config_bits(self, tile_name: str) -> RoutingConfigBits:
        """Return simple config-bit counts."""
        assert tile_name == "Toy"
        matrix_bits = len(self.active_pairs)
        return RoutingConfigBits(
            tile_type=tile_name,
            matrix_config_bits=matrix_bits,
            fixed_config_bits=0,
            total_config_bits=matrix_bits,
        )

    def write_tile_sources(self, *args: object, **kwargs: object) -> None:
        """Fail if the graph-only pass tries to write files."""
        _ = args, kwargs
        self.write_methods_called = True
        raise AssertionError("routing pattern pass must not write tile sources")

    def write_project(self, *args: object, **kwargs: object) -> None:
        """Fail if the graph-only pass tries to write a project."""
        _ = args, kwargs
        self.write_methods_called = True
        raise AssertionError("routing pattern pass must not write projects")

    def write_pips(self, *args: object, **kwargs: object) -> None:
        """Fail if the graph-only pass tries to write pips."""
        _ = args, kwargs
        self.write_methods_called = True
        raise AssertionError("routing pattern pass must not write pips")


def _tile_model() -> RoutingTileModel:
    """Create a compact tile model with BEL and routing resources."""
    return RoutingTileModel(
        tile_type="Toy",
        tile_csv_path=Path("Toy.csv"),
        tile_dir=Path(),
        matrix_path=Path("Toy_switch_matrix.list"),
        matrix_config_bits=0,
        with_user_clk=False,
        ports=(
            RoutingTilePortModel(
                direction=Direction.NORTH,
                source_name="NBEG",
                x_offset=0,
                y_offset=-1,
                destination_name="NEND",
                wire_count=4,
                name="N",
                io=IO.INPUT,
                side=Side.NORTH,
            ),
            RoutingTilePortModel(
                direction=Direction.EAST,
                source_name="EBEG",
                x_offset=1,
                y_offset=0,
                destination_name="EEND",
                wire_count=4,
                name="E",
                io=IO.INPUT,
                side=Side.EAST,
            ),
        ),
        bels=(
            RoutingTileBelModel(
                source_path=Path("toy_bel.v"),
                prefix="A_",
                name="toy_bel",
                module_name="toy_bel",
                inputs=("A_I0", "A_I1"),
                outputs=("A_O",),
                external_inputs=(),
                external_outputs=(),
                config_bits=0,
                feature_names=(),
                with_user_clk=False,
            ),
        ),
        gen_ios=(),
    )


def _expected_hierarchy_shape(
    input_fanin: int,
    hierarchy_levels: list[int],
) -> tuple[int, int, int]:
    """Return expected per-BEL hierarchy counts for one fanin shape."""
    current_sources = input_fanin
    added_jump_wires = 0
    generated_pips = 0
    generated_levels = 0
    for fanin in hierarchy_levels:
        if current_sources <= 1:
            break
        next_sources = (current_sources + fanin - 1) // fanin
        added_jump_wires += next_sources
        generated_pips += current_sources
        current_sources = next_sources
        generated_levels += 1
    generated_pips += current_sources
    return added_jump_wires, generated_pips, generated_levels


def _expected_source_prefix(row_index: int, input_fanin: int) -> list[str]:
    """Return the deterministic source prefix selected for one BEL input row."""
    sources = [
        "NEND0",
        "NEND1",
        "NEND2",
        "NEND3",
        "EEND0",
        "EEND1",
        "EEND2",
        "EEND3",
    ]
    return [
        sources[(row_index + offset) % len(sources)] for offset in range(input_fanin)
    ]


def _copy_demo_opt_project_or_skip(tmp_path: Path) -> Path:
    """Copy ``demo_opt`` into a temporary directory or skip when unavailable."""
    source_project = Path("demo_opt").resolve()
    if not source_project.exists():
        pytest.skip("demo_opt project is not available")
    if shutil.which("yosys") is None:
        pytest.skip("Yosys is required to parse demo_opt BEL files")

    project_dir = tmp_path / "demo_opt"
    shutil.copytree(source_project, project_dir)
    return project_dir


def _load_demo_opt_graph(project_dir: Path) -> FabGraph:
    """Load a copied ``demo_opt`` project through the public graph facade."""
    fabulous_settings._context_instance = (  # noqa: SLF001
        fabulous_settings.FABulousSettings.model_construct(
            proj_dir=project_dir,
            nix_shell=None,
        )
    )
    fab = FABulous_API(VerilogCodeGenerator())
    fab.loadFabric(project_dir / "fabric.csv")
    return FabGraph(fab, project_dir)


def _base_available_wires() -> list[str]:
    """Return matrix-visible wires for the fake graph."""
    return [
        "A_I0",
        "A_I1",
        "A_O",
        "GND",
        "GND0",
        "VCC",
        "VCC0",
        "NBEG0",
        "NBEG1",
        "NBEG2",
        "NBEG3",
        "NEND0",
        "NEND1",
        "NEND2",
        "NEND3",
        "EBEG0",
        "EBEG1",
        "EBEG2",
        "EBEG3",
        "EEND0",
        "EEND1",
        "EEND2",
        "EEND3",
    ]


def _use_rich_lut_tile_model(
    graph: _FakePnRBridge,
    *,
    bel_count: int = 2,
) -> None:
    """Swap the fake graph to an N-BEL LUT/carry/control tile model."""
    prefixes = ("A", "B", "C", "D", "E", "F", "G", "H")[:bel_count]
    graph.model = RoutingTileModel(
        tile_type="Toy",
        tile_csv_path=Path("Toy.csv"),
        tile_dir=Path(),
        matrix_path=Path("Toy_switch_matrix.list"),
        matrix_config_bits=0,
        with_user_clk=False,
        ports=graph.model.ports,
        bels=tuple(
            RoutingTileBelModel(
                source_path=Path("toy_bel.v"),
                prefix=f"{prefix}_",
                name=f"toy_bel_{prefix.lower()}",
                module_name="toy_bel",
                inputs=(
                    f"{prefix}_I0",
                    f"{prefix}_I1",
                    f"{prefix}_B0",
                    f"{prefix}_Ci",
                    f"{prefix}_SR",
                    f"{prefix}_EN",
                ),
                outputs=(f"{prefix}_O", f"{prefix}_O1", f"{prefix}_Co"),
                external_inputs=(),
                external_outputs=(),
                config_bits=0,
                feature_names=(),
                with_user_clk=False,
            )
            for prefix in prefixes
        ),
        gen_ios=(),
    )
    graph.available_wires.update(
        wire
        for prefix in prefixes
        for wire in (
            f"{prefix}_I0",
            f"{prefix}_I1",
            f"{prefix}_B0",
            f"{prefix}_Ci",
            f"{prefix}_SR",
            f"{prefix}_EN",
            f"{prefix}_O",
            f"{prefix}_O1",
            f"{prefix}_Co",
        )
    )


def _add_dense_routing_resources(graph: _FakePnRBridge) -> None:
    """Add enough synthetic routing families to exercise rich-pattern capping."""
    directions = (
        (Direction.NORTH, 0, -1),
        (Direction.EAST, 1, 0),
        (Direction.SOUTH, 0, 1),
        (Direction.WEST, -1, 0),
    )
    for index in range(48):
        direction, x_offset, y_offset = directions[index % len(directions)]
        graph.add_external_resource(
            "Toy",
            direction,
            f"R{index}BEG",
            x_offset,
            y_offset,
            f"R{index}END",
            16,
        )
