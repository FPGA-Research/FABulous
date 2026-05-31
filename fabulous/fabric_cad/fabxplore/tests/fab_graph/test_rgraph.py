"""Tests for fast tile-local routing fabric graph construction and edits."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest  # noqa: DEP004 - test-only dependency

import fabulous.fabulous_settings as fabulous_settings
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingConfigBits,
    RoutingEndpoint,
    RoutingPip,
    RoutingPipKind,
    RoutingResourceCounts,
    RoutingResourceKey,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.rgraph import (
    RoutingFabricGraph,
)
from fabulous.fabric_cad.gen_npnr_model import genNextpnrModel
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList

if TYPE_CHECKING:
    from fabulous.fabric_definition.fabric import Fabric


@pytest.fixture(scope="module")
def demo_opt_fabric() -> Fabric:
    """Return the parsed ``demo_opt`` fabric.

    Returns
    -------
    Fabric
        Parsed demo project fabric.
    """
    project_dir = Path("demo_opt").resolve()
    if not project_dir.exists():
        pytest.skip("demo_opt project is not available")
    if shutil.which("yosys") is None:
        pytest.skip("Yosys is required to parse demo_opt BEL files")
    return _parse_fabric_project(project_dir)


EAGER_PIP_API_REASON = "core_fast intentionally has no eager concrete-PIP mutation API"


def _resized_external_key(
    key: RoutingResourceKey,
    wire_count: int,
) -> RoutingResourceKey:
    """Return the key produced by a fast external resize operation.

    Parameters
    ----------
    key : RoutingResourceKey
        Input external key.
    wire_count : int
        New wire count.

    Returns
    -------
    RoutingResourceKey
        Expected resized key.
    """
    return replace(key, wire_count=wire_count)


def test_graph_matches_generated_nextpnr_pips(tmp_path: Path) -> None:
    """Build from ``Fabric`` and render the same PIP text as FABulous."""
    fabric = _write_and_parse_project(tmp_path)
    graph = RoutingFabricGraph.from_fabric(fabric)

    assert graph.render_pips_txt() == genNextpnrModel(fabric)[0]
    assert graph.stats().active_pips == graph.stats().total_pips
    assert graph.stats().internal_pips == 4
    assert graph.stats().external_pips > 0


def test_external_pips_keep_structured_resource_metadata(tmp_path: Path) -> None:
    """Check that external PIPs carry tile type, direction, offsets, and class."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    external = [
        pip for pip in graph.active_pips() if pip.kind is RoutingPipKind.EXTERNAL_WIRE
    ]
    east = [
        pip
        for pip in external
        if pip.resource_key.direction is Direction.EAST
        and pip.resource_key.source_name == "LONG_BEG"
    ]

    assert east
    assert {pip.tile_type for pip in east} == {"Toy"}
    assert {pip.resource_key.x_offset for pip in east} == {2}
    assert {pip.resource_key.y_offset for pip in east} == {0}
    assert {pip.resource_key.wire_count for pip in east} == {2}
    assert {pip.resource_key.wire_class for pip in east} == {2}
    assert {pip.emitted_x_offset for pip in east} == {0, 1}
    assert {pip.owner_tile for pip in east} >= {(0, 0), (1, 0)}


def test_internal_pips_keep_matrix_metadata(tmp_path: Path) -> None:
    """Check that matrix PIPs are grouped by tile type and matrix edge."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    internal = [
        pip for pip in graph.active_pips() if pip.kind is RoutingPipKind.INTERNAL_MATRIX
    ]

    assert internal
    assert {pip.tile_type for pip in internal} == {"Toy"}
    assert all(pip.matrix_path is not None for pip in internal)
    assert {
        (pip.resource_key.source_name, pip.resource_key.destination_name)
        for pip in internal
    } == {("LONG_END0", "LOCAL_BEG0"), ("LOCAL_END0", "LONG_BEG0")}


def test_tile_model_keeps_parsed_tile_metadata(tmp_path: Path) -> None:
    """Expose parsed tile paths and ports through stable graph metadata."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    toy = graph.tile_model("Toy")

    assert graph.tile_types() == ("Toy",)
    assert graph.tile_models() == (toy,)
    assert toy.tile_type == "Toy"
    assert toy.tile_csv_path == tmp_path / "Tile" / "Toy" / "Toy.csv"
    assert toy.tile_dir == tmp_path / "Tile" / "Toy"
    assert toy.matrix_path == tmp_path / "Tile" / "Toy" / "Toy_switch_matrix.list"
    assert toy.matrix_config_bits == 0
    assert not toy.with_user_clk
    assert {port.source_name for port in toy.ports} == {"LONG_BEG", "LOCAL_BEG"}
    assert {port.destination_name for port in toy.ports} == {
        "LONG_END",
        "LOCAL_END",
    }

    with pytest.raises(KeyError):
        graph.tile_model("Missing")


def test_tile_lookup_by_coordinate_uses_placed_grid_only(tmp_path: Path) -> None:
    """Look up placed tile metadata from fabric coordinates."""
    graph = RoutingFabricGraph.from_fabric(
        _write_and_parse_project_with_standalone_tile(tmp_path)
    )
    toy = graph.tile_model("Toy")

    assert graph.tile_type_at(0, 0) == "Toy"
    assert graph.tile_type_at(1, 0) == "Toy"
    assert graph.tile_model_at(0, 0) is toy
    assert graph.tile_model_at(1, 0) is toy
    assert graph.tile_type_at(0, 1) is None
    assert graph.tile_model_at(0, 1) is None
    assert graph.tile_type_at(-1, 0) is None
    assert graph.tile_model_at(99, 99) is None


def test_declared_standalone_tiles_are_queryable_without_emitting_pips(
    tmp_path: Path,
) -> None:
    """Load declared unplaced tile models without routing instances."""
    graph = RoutingFabricGraph.from_fabric(
        _write_and_parse_project_with_standalone_tile(tmp_path)
    )

    assert graph.tile_types() == ("Toy", "Standalone")
    assert graph.placed_tile_types() == ("Toy",)
    assert graph.standalone_tile_types() == ("Standalone",)
    assert graph.tile_model("Standalone").tile_type == "Standalone"

    standalone_matrix = graph.switch_matrix("Standalone")
    standalone_matrix_key = graph.matrix_resource_key(
        "Standalone",
        "FREE_END0",
        "FREE_BEG0",
    )
    standalone_external_key = graph.external_resource_key(
        "Standalone",
        Direction.JUMP,
        "FREE_BEG",
        0,
        0,
        "FREE_END",
        1,
    )

    assert standalone_matrix.rows == ["FREE_END0"]
    assert standalone_matrix.columns == ["FREE_BEG0"]
    assert standalone_matrix.matrix == [[8.0]]
    assert graph.by_resource_key(standalone_matrix_key) == ()
    assert graph.by_resource_key(standalone_external_key) == ()
    assert all(pip.tile_type != "Standalone" for pip in graph.active_pips())
    assert graph.get_resource_counts("Standalone").total_active == 2
    graph.validate()


def test_config_bits_track_active_matrix_resources(tmp_path: Path) -> None:
    """Recompute switch-matrix config bits from active tile-local resources."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))

    initial = graph.get_config_bits("Toy")

    assert isinstance(initial, RoutingConfigBits)
    assert initial.tile_type == "Toy"
    assert initial.matrix_config_bits == graph.tile_model("Toy").matrix_config_bits
    assert initial.fixed_config_bits == 0
    assert initial.total_config_bits == initial.matrix_config_bits

    graph.add_matrix_resource("Toy", "LONG_END0", "LONG_BEG0")
    two_way_mux = graph.get_config_bits("Toy")
    graph.add_matrix_resource("Toy", "LONG_END0", "LONG_BEG1")
    three_way_mux = graph.get_config_bits("Toy")

    assert two_way_mux.matrix_config_bits == 1
    assert two_way_mux.total_config_bits == 1
    assert three_way_mux.matrix_config_bits == 2
    assert three_way_mux.total_config_bits == 2

    graph.delete_resource(
        graph.matrix_resource_key(
            "Toy",
            "LONG_END0",
            "LONG_BEG1",
            active_only=False,
        )
    )

    assert graph.get_config_bits("Toy").matrix_config_bits == 1
    assert set(graph.get_config_bits()) == {"Toy"}


def test_resource_counts_track_tile_local_mutations(tmp_path: Path) -> None:
    """Count active and disabled resources without materializing PIPs."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))

    initial = graph.get_resource_counts("Toy")

    assert isinstance(initial, RoutingResourceCounts)
    assert initial.tile_type == "Toy"
    assert initial.external_active == 2
    assert initial.external_disabled == 0
    assert initial.matrix_active == 2
    assert initial.matrix_disabled == 0
    assert initial.total_active == 4
    assert initial.total_disabled == 0
    assert initial.total == 4

    graph.add_external_resource(
        "Toy",
        Direction.JUMP,
        "COUNT_BEG",
        0,
        0,
        "COUNT_END",
        2,
    )
    external_key = graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "COUNT_BEG",
        0,
        0,
        "COUNT_END",
        2,
    )
    graph.add_matrix_resource("Toy", "COUNT_END0", "COUNT_BEG0")
    matrix_key = graph.matrix_resource_key("Toy", "COUNT_END0", "COUNT_BEG0")
    after_add = graph.get_resource_counts("Toy")

    assert after_add.external_active == initial.external_active + 1
    assert after_add.matrix_active == initial.matrix_active + 1
    assert after_add.total_active == initial.total_active + 2

    graph.delete_resource(matrix_key)
    graph.resize_external_resource(external_key, 1)
    resized_key = _resized_external_key(external_key, 1)
    after_disable_and_resize = graph.get_resource_counts("Toy")

    assert after_disable_and_resize.external_active == after_add.external_active
    assert after_disable_and_resize.external_disabled == 1
    assert after_disable_and_resize.matrix_active == after_add.matrix_active - 1
    assert after_disable_and_resize.matrix_disabled == 1
    assert after_disable_and_resize.total == after_add.total + 1

    graph.enable_resource(matrix_key)
    graph.resize_external_resource(resized_key, 2)
    restored = graph.get_resource_counts("Toy")

    assert restored.external_active == after_add.external_active
    assert restored.matrix_active == after_add.matrix_active
    assert restored.total_active == after_add.total_active
    assert set(graph.get_resource_counts()) == {"Toy"}


def test_tile_model_keeps_gen_io_metadata(tmp_path: Path) -> None:
    """Expose parsed GEN_IO metadata through stable graph metadata."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_gen_io_project(tmp_path))
    gen_io = graph.tile_model("WithIO").gen_ios

    assert len(gen_io) == 1
    assert gen_io[0].prefix == "EXT"
    assert gen_io[0].pins == 4
    assert gen_io[0].io.name == "INPUT"
    assert gen_io[0].config_bits == 4
    assert gen_io[0].clocked_mux


def test_disable_and_enable_resource_operates_per_tile_type(tmp_path: Path) -> None:
    """Disabling a resource key affects every matching tile instance."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    key = next(
        pip.resource_key
        for pip in graph.active_pips()
        if pip.kind is RoutingPipKind.INTERNAL_MATRIX
    )
    matching_before = graph.by_resource_key(key)

    graph.disable_resource(key)

    assert graph.by_resource_key(key) == ()
    assert all(pip in graph.disabled_pips() for pip in matching_before)

    graph.enable_resource(key)

    assert graph.by_resource_key(key) == matching_before


def test_disable_external_resource_prunes_dangling_matrix_resources(
    tmp_path: Path,
) -> None:
    """Removing a tile-interface wire also removes matrix pairs that use it."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    key = next(
        pip.resource_key
        for pip in graph.active_pips()
        if pip.kind is RoutingPipKind.EXTERNAL_WIRE
        and pip.resource_key.source_name == "LONG_BEG"
    )
    graph.disable_resource(key)

    assert graph.by_resource_key(key) == ()
    assert not [
        pip for pip in graph.active_pips() if pip.kind is RoutingPipKind.INTERNAL_MATRIX
    ]


def test_resize_external_resource_shrinks_and_prunes_lane_dependencies(
    tmp_path: Path,
) -> None:
    """Shrink an external vector and prune matrix resources using removed lanes."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    external_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.EXTERNAL_WIRE and key.source_name == "LONG_BEG"
    )
    lane_key = RoutingResourceKey(
        tile_type="Toy",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        source_name="LONG_END1",
        destination_name="LOCAL_BEG0",
        matrix_path=graph.tile_model("Toy").matrix_path,
    )
    graph.add_matrix_resource("Toy", "LONG_END1", "LOCAL_BEG0")
    active_before = graph.stats().active_pips

    graph.resize_external_resource(external_key, 1)
    resized_key = _resized_external_key(external_key, 1)

    assert graph.by_resource_key(external_key) == ()
    assert graph.by_resource_key(resized_key)
    assert {
        pip.resource_key.wire_count for pip in graph.by_resource_key(resized_key)
    } == {1}
    assert graph.by_resource_key(lane_key) == ()
    assert graph.stats().active_pips < active_before
    graph.validate()


def test_resize_external_resource_grows_without_matrix_connections(
    tmp_path: Path,
) -> None:
    """Grow an external vector without inventing switch-matrix pairs."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    external_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.EXTERNAL_WIRE and key.source_name == "LONG_BEG"
    )
    internal_before = {
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.INTERNAL_MATRIX
    }
    active_before = graph.stats().active_pips

    graph.resize_external_resource(external_key, 3)
    resized_key = _resized_external_key(external_key, 3)

    assert graph.by_resource_key(external_key) == ()
    assert {
        pip.resource_key.wire_count for pip in graph.by_resource_key(resized_key)
    } == {3}
    assert {
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.INTERNAL_MATRIX
    } == internal_before
    assert graph.stats().active_pips > active_before
    graph.validate()


def test_resize_external_resource_can_restore_removed_lane_availability(
    tmp_path: Path,
) -> None:
    """Grow after shrink so matrix resources using restored lanes can re-enable."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    external_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.EXTERNAL_WIRE and key.source_name == "LONG_BEG"
    )
    lane_key = RoutingResourceKey(
        tile_type="Toy",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        source_name="LONG_END1",
        destination_name="LOCAL_BEG0",
        matrix_path=graph.tile_model("Toy").matrix_path,
    )
    graph.add_matrix_resource("Toy", "LONG_END1", "LOCAL_BEG0")

    graph.resize_external_resource(external_key, 1)
    shrink_key = _resized_external_key(external_key, 1)
    assert graph.by_resource_key(lane_key) == ()

    graph.resize_external_resource(shrink_key, 2)
    graph.enable_resource(lane_key)

    assert len(graph.by_resource_key(lane_key)) == 2
    graph.validate()


def test_resize_external_resource_to_zero_disables_resource(
    tmp_path: Path,
) -> None:
    """Treat resize-to-zero as a whole-resource disable."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    external_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.EXTERNAL_WIRE and key.source_name == "LONG_BEG"
    )

    graph.resize_external_resource(external_key, 0)

    assert graph.by_resource_key(external_key) == ()
    assert graph.by_resource_key(external_key, active_only=False)
    graph.validate()


def test_resource_query_helpers_return_lists(tmp_path: Path) -> None:
    """Return optimizer-friendly resource and candidate-wire lists."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))

    external = graph.external_resources(tile_type="Toy")
    matrix = graph.matrix_resources(tile_type="Toy")
    sources = graph.matrix_sources("Toy")
    sinks = graph.matrix_sinks("Toy")

    assert isinstance(external, list)
    assert isinstance(matrix, list)
    assert isinstance(sources, list)
    assert isinstance(sinks, list)
    assert external
    assert matrix
    assert all(key.kind is RoutingPipKind.EXTERNAL_WIRE for key in external)
    assert all(key.kind is RoutingPipKind.INTERNAL_MATRIX for key in matrix)
    assert "LONG_END0" in sources
    assert "LOCAL_BEG0" in sinks
    assert sources == sorted(sources)
    assert sinks == sorted(sinks)


def test_query_helpers_track_external_resource_mutations(tmp_path: Path) -> None:
    """Expose active resources and matrix candidates after external edits."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    external_key = next(
        key
        for key in graph.external_resources(tile_type="Toy")
        if key.source_name == "LONG_BEG"
    )

    graph.resize_external_resource(external_key, 1)
    resized_key = _resized_external_key(external_key, 1)
    assert external_key not in graph.external_resources(tile_type="Toy")
    assert resized_key in graph.external_resources(tile_type="Toy")
    assert "LONG_END1" not in graph.matrix_sources("Toy")
    assert "LONG_END0" in graph.matrix_sources("Toy")

    graph.add_external_resource(
        "Toy",
        Direction.JUMP,
        "QUERY_BEG",
        0,
        0,
        "QUERY_END",
        1,
    )
    added_key = graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "QUERY_BEG",
        0,
        0,
        "QUERY_END",
        1,
    )
    assert added_key in graph.external_resources(tile_type="Toy")
    assert "QUERY_END0" in graph.matrix_sinks("Toy")


def test_add_external_and_matrix_resources_update_graph(tmp_path: Path) -> None:
    """Add high-level CSV and switch-matrix resources to a graph."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    active_before = graph.stats().active_pips

    graph.add_external_resource(
        "Toy",
        Direction.JUMP,
        "EXTRA_BEG",
        0,
        0,
        "EXTRA_END",
        1,
    )
    graph.add_matrix_resource("Toy", "EXTRA_END0", "LOCAL_BEG0")
    external = graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "EXTRA_BEG",
        0,
        0,
        "EXTRA_END",
        1,
    )
    matrix = graph.matrix_resource_key("Toy", "EXTRA_END0", "LOCAL_BEG0")

    assert graph.by_resource_key(external)
    assert graph.by_resource_key(matrix)
    assert graph.stats().active_pips == active_before + 4
    assert "EXTRA_BEG0.EXTRA_END0" in graph.render_pips_txt()
    assert "LOCAL_BEG0.EXTRA_END0" in graph.render_pips_txt()
    graph.validate()


def test_add_matrix_resource_rejects_missing_wires_and_rolls_back(
    tmp_path: Path,
) -> None:
    """Reject high-level matrix rows that reference undeclared tile wires."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    stats_before = graph.stats()
    signatures_before = _active_signatures(graph)

    with pytest.raises(ValueError, match="missing tile wire"):
        graph.add_matrix_resource("Toy", "MISSING0", "LOCAL_BEG0")

    assert graph.stats() == stats_before
    assert _active_signatures(graph) == signatures_before


def test_add_external_resource_rolls_back_partial_insert_failure(
    tmp_path: Path,
) -> None:
    """Reject duplicate external resources without graph drift."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    graph.add_external_resource(
        "Toy",
        Direction.JUMP,
        "ROLL_BEG",
        0,
        0,
        "ROLL_END",
        1,
    )
    stats_before = graph.stats()
    signatures_before = _active_signatures(graph)

    with pytest.raises(ValueError, match="already exists"):
        graph.add_external_resource(
            "Toy",
            Direction.JUMP,
            "ROLL_BEG",
            0,
            0,
            "ROLL_END",
            1,
        )

    assert graph.stats() == stats_before
    assert _active_signatures(graph) == signatures_before


@pytest.mark.skip(reason=EAGER_PIP_API_REASON)
def test_partial_resource_disable_is_rejected(tmp_path: Path) -> None:
    """Reject edits that disable only one instance of a tile-type resource."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    target = next(
        pip
        for pip in graph.active_pips()
        if pip.kind is RoutingPipKind.EXTERNAL_WIRE
        and pip.resource_key.source_name == "LONG_BEG"
    )
    active_before = graph.stats().active_pips
    disabled_before = graph.stats().disabled_pips

    with pytest.raises(ValueError, match="tile-type-wide"):
        graph.disable_pips(lambda pip: pip.pip_id == target.pip_id)

    assert graph.stats().active_pips == active_before
    assert graph.stats().disabled_pips == disabled_before


@pytest.mark.skip(reason=EAGER_PIP_API_REASON)
def test_add_and_remove_pip_updates_graph(tmp_path: Path) -> None:
    """Add a synthetic PIP, render it, then remove it again."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    resource_key = RoutingResourceKey(
        tile_type="Toy",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        source_name="LOCAL_END0",
        destination_name="LONG_BEG1",
    )
    pip = RoutingPip(
        pip_id=None,
        kind=RoutingPipKind.INTERNAL_MATRIX,
        source=RoutingEndpoint(0, 0, "LONG_BEG1"),
        destination=RoutingEndpoint(0, 0, "LOCAL_END0"),
        delay=8,
        name="LONG_BEG1.LOCAL_END0",
        owner_tile=(0, 0),
        tile_type="Toy",
        resource_key=resource_key,
        source_tile_type="Toy",
        destination_tile_type="Toy",
    )

    inserted = graph.add_pip(pip)

    assert inserted.pip_id is not None
    assert "LONG_BEG1.LOCAL_END0" in graph.render_pips_txt()

    removed = graph.remove_pip(inserted.pip_id)

    assert removed == inserted
    assert "LONG_BEG1.LOCAL_END0" not in graph.render_pips_txt()


def test_add_dangling_internal_resource_is_rejected(tmp_path: Path) -> None:
    """Reject matrix additions that reference wires absent from the tile type."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    stats_before = graph.stats()

    with pytest.raises(ValueError, match="missing tile wire"):
        graph.add_matrix_resource("Toy", "MISSING0", "LOCAL_BEG0")

    assert graph.stats() == stats_before


def test_duplicate_pip_signature_is_rejected(tmp_path: Path) -> None:
    """Reject duplicate matrix resources."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    existing = next(
        key for key in graph.matrix_resources("Toy") if key.source_name == "LONG_END0"
    )

    with pytest.raises(ValueError, match="already exists"):
        graph.add_matrix_resource(
            existing.tile_type,
            existing.source_name,
            existing.destination_name,
        )


@pytest.mark.skip(reason=EAGER_PIP_API_REASON)
def test_endpoint_bounds_are_validated(tmp_path: Path) -> None:
    """Reject PIPs with endpoint coordinates outside FABulous model bounds."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    existing = graph.active_pips()[0]
    bad = replace(
        existing,
        pip_id=None,
        source=RoutingEndpoint(graph.columns + 1, 0, existing.source.wire),
    )
    total_before = graph.stats().total_pips

    with pytest.raises(ValueError, match="endpoint X coordinate"):
        graph.add_pip(bad)

    assert graph.stats().total_pips == total_before


def test_demo_opt_graph_matches_generated_nextpnr_pips(
    demo_opt_fabric: Fabric,
) -> None:
    """Build the real demo graph and compare it to FABulous nextpnr output."""
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    stats = graph.stats()

    assert graph.render_pips_txt() == genNextpnrModel(demo_opt_fabric)[0]
    assert stats.total_pips > 100_000
    assert stats.internal_pips > stats.external_pips
    assert stats.tile_types > 1
    assert stats.resource_keys > 1_000


def test_demo_opt_resource_disable_enable_round_trips(
    demo_opt_fabric: Fabric,
) -> None:
    """Disable a real resource across all related tile instances, then restore."""
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    key = _demo_multi_instance_internal_key(graph)
    matching_before = graph.by_resource_key(key)
    owners_before = {pip.owner_tile for pip in matching_before}
    active_signatures_before = _active_signatures(graph)

    graph.disable_resource(key)

    assert len(owners_before) > 1
    assert graph.by_resource_key(key) == ()
    disabled_owners = {
        pip.owner_tile for pip in graph.disabled_pips() if pip.resource_key == key
    }

    assert disabled_owners == owners_before

    graph.enable_resource(key)

    assert graph.by_resource_key(key) == matching_before
    assert _active_signatures(graph) == active_signatures_before


@pytest.mark.skip(reason=EAGER_PIP_API_REASON)
def test_demo_opt_remove_and_add_same_pip_restores_graph(
    demo_opt_fabric: Fabric,
) -> None:
    """Remove one real PIP and add the same PIP back without graph drift."""
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    target = next(
        pip for pip in graph.active_pips() if pip.kind is RoutingPipKind.INTERNAL_MATRIX
    )
    active_signatures_before = _active_signatures(graph)
    stats_before = graph.stats()

    assert target.pip_id is not None
    removed = graph.remove_pip(target.pip_id)

    assert removed == target
    assert graph.stats().total_pips == stats_before.total_pips - 1
    assert target.signature not in _active_signatures(graph)

    graph.add_pip(removed)

    assert graph.stats() == stats_before
    assert _active_signatures(graph) == active_signatures_before


@pytest.mark.skip(reason=EAGER_PIP_API_REASON)
def test_demo_opt_partial_real_resource_disable_is_rejected(
    demo_opt_fabric: Fabric,
) -> None:
    """Reject removing only one instance from a real tile-type resource."""
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    key = _demo_multi_instance_external_key(graph)
    target = graph.by_resource_key(key)[0]
    stats_before = graph.stats()

    with pytest.raises(ValueError, match="tile-type-wide"):
        graph.disable_pips(lambda pip: pip.pip_id == target.pip_id)

    assert graph.stats() == stats_before


def test_demo_opt_external_resize_stress_shrink_batches(
    demo_opt_fabric: Fabric,
) -> None:
    """Shrink real demo external wire vectors over several batched iterations."""
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    keys = list(_demo_resizable_external_keys(graph, "LUT4AB", min_wire_count=3))[:6]
    active_before = graph.stats().active_pips

    assert len(keys) >= 4

    for _iteration in range(3):
        for index, key in enumerate(keys):
            next_count = max(1, key.wire_count - 1)
            graph.resize_external_resource(key, next_count)
            keys[index] = _resized_external_key(key, next_count)
        graph.validate()

    assert graph.stats().active_pips < active_before
    assert all(key.wire_count >= 1 for key in keys)
    assert all(graph.by_resource_key(key) for key in keys)


def test_demo_opt_external_resize_stress_shrink_and_growth_batches(
    demo_opt_fabric: Fabric,
) -> None:
    """Shrink and grow real demo external vectors without adding matrix PIPs."""
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    keys = list(_demo_resizable_external_keys(graph, "LUT4AB", min_wire_count=4))[:5]

    assert len(keys) >= 3

    for index, key in enumerate(keys):
        next_count = key.wire_count - 2
        graph.resize_external_resource(key, next_count)
        keys[index] = _resized_external_key(key, next_count)
    active_after_shrink = graph.stats().active_pips
    internal_after_shrink = _active_internal_resource_keys(graph, "LUT4AB")

    for delta in (1, 3, -1):
        for index, key in enumerate(keys):
            next_count = max(1, key.wire_count + delta)
            graph.resize_external_resource(key, next_count)
            keys[index] = _resized_external_key(key, next_count)
        graph.validate()

    assert graph.stats().active_pips > active_after_shrink
    assert _active_internal_resource_keys(graph, "LUT4AB") == internal_after_shrink
    assert all(graph.by_resource_key(key) for key in keys)


def test_demo_opt_real_world_cross_tile_include_and_mutation_cases(
    demo_opt_fabric: Fabric,
) -> None:
    """Exercise real demo cross-tile, include, boundary, and mutation behavior."""
    project_dir = Path("demo_opt").resolve()
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    stats_before = graph.stats()
    signatures_before = _active_signatures(graph)
    cross_key = _demo_cross_tile_external_key(graph)
    cross_pips = graph.by_resource_key(cross_key)
    base_pair = parseList(project_dir / "Tile" / "include" / "Base.list")[0]

    assert len({pip.owner_tile for pip in cross_pips}) > 1
    assert all(pip.source_tile_type != pip.destination_tile_type for pip in cross_pips)
    assert not [
        pip
        for pip in graph.active_pips()
        if pip.kind is RoutingPipKind.EXTERNAL_WIRE
        and (pip.source_tile_type is None or pip.destination_tile_type is None)
    ]
    assert any(
        pip.kind is RoutingPipKind.INTERNAL_MATRIX
        and (pip.resource_key.source_name, pip.resource_key.destination_name)
        == base_pair
        for pip in graph.active_pips()
    )

    graph.disable_resource(cross_key)

    assert graph.by_resource_key(cross_key) == ()
    assert graph.by_resource_key(cross_key, active_only=False) == cross_pips
    assert graph.stats().active_pips < stats_before.active_pips

    graph.validate()
    assert _active_signatures(graph) != signatures_before


def test_demo_opt_tile_model_keeps_real_bel_metadata(
    demo_opt_fabric: Fabric,
) -> None:
    """Expose real demo BEL metadata through stable graph metadata."""
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    lut = graph.tile_model("LUT4AB")

    assert "LUT4AB" in graph.tile_types()
    assert lut.tile_csv_path.name == "LUT4AB.csv"
    assert lut.tile_dir.name == "LUT4AB"
    assert lut.matrix_path.name == "LUT4AB_switch_matrix.list"
    assert len(lut.bels) == 9
    assert lut.bels[0].prefix == "LA_"
    assert lut.bels[0].name == "LUT4c_frame_config_dffesr"
    assert lut.bels[0].config_bits > 0
    assert lut.bels[0].feature_names
    assert lut.with_user_clk


def test_demo_opt_config_bits_match_parsed_fabulous_tiles(
    demo_opt_fabric: Fabric,
) -> None:
    """Match FABulous tile-local matrix and total config-bit accounting."""
    graph = RoutingFabricGraph.from_fabric(demo_opt_fabric)
    all_bits = graph.get_config_bits()

    assert set(all_bits) == set(graph.tile_types())
    for tile_type in graph.tile_types():
        tile = demo_opt_fabric.getTileByName(tile_type)
        config_bits = all_bits[tile_type]

        assert config_bits.tile_type == tile_type
        assert config_bits.matrix_config_bits == tile.matrixConfigBits
        assert config_bits.total_config_bits == tile.globalConfigBits


def test_cross_tile_resource_disable_keeps_whole_tile_type_rule(
    tmp_path: Path,
) -> None:
    """Disable one cross-tile wire class across every owner tile instance."""
    graph = RoutingFabricGraph.from_fabric(
        _write_and_parse_cross_tile_project(tmp_path)
    )
    key = next(
        pip.resource_key
        for pip in graph.active_pips()
        if pip.kind is RoutingPipKind.EXTERNAL_WIRE
        and pip.tile_type == "Driver"
        and pip.destination_tile_type == "Sink"
    )
    matching_before = graph.by_resource_key(key)

    assert {pip.owner_tile for pip in matching_before} == {(0, 0), (2, 0)}
    assert {pip.source_tile_type for pip in matching_before} == {"Driver"}
    assert {pip.destination_tile_type for pip in matching_before} == {"Sink"}

    graph.disable_resource(key)

    assert graph.by_resource_key(key) == ()
    assert graph.by_resource_key(key, active_only=False) == matching_before
    assert {
        pip.owner_tile for pip in graph.disabled_pips() if pip.resource_key == key
    } == {(0, 0), (2, 0)}


def test_boundary_external_pips_preserve_missing_neighbor_metadata(
    tmp_path: Path,
) -> None:
    """Represent legal boundary PIPs whose destination has no placed tile."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_boundary_project(tmp_path))
    boundary = [
        pip
        for pip in graph.active_pips()
        if pip.kind is RoutingPipKind.EXTERNAL_WIRE
        and pip.destination_tile_type is None
    ]

    assert len(boundary) == 1
    assert boundary[0].owner_tile == (0, 0)
    assert boundary[0].source_tile_type == "Edge"
    assert boundary[0].destination.tile == (1, 0)
    assert boundary[0].resource_key.direction is Direction.EAST
    assert (
        graph.render_pips_txt()
        == genNextpnrModel(_write_and_parse_boundary_project(tmp_path / "reference"))[0]
    )


def test_base_csv_and_base_list_includes_are_visible_in_graph(
    tmp_path: Path,
) -> None:
    """Build graph metadata from included CSV wires and included list PIPs."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_include_project(tmp_path))
    active = graph.active_pips()

    assert any(
        pip.kind is RoutingPipKind.EXTERNAL_WIRE
        and pip.resource_key.source_name == "BASE_BEG"
        and pip.resource_key.destination_name == "BASE_END"
        for pip in active
    )
    assert any(
        pip.kind is RoutingPipKind.INTERNAL_MATRIX
        and pip.resource_key.source_name == "BASE_END0"
        and pip.resource_key.destination_name == "BASE_BEG0"
        for pip in active
    )
    assert (
        graph.render_pips_txt()
        == genNextpnrModel(_write_and_parse_include_project(tmp_path / "reference"))[0]
    )


def test_mutation_sequence_restores_signatures_and_stats(tmp_path: Path) -> None:
    """Run a deterministic disable/enable sequence without drift."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    stats_before = graph.stats()
    signatures_before = _active_signatures(graph)
    resource_keys = [
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.INTERNAL_MATRIX
    ]

    assert len(resource_keys) >= 2
    graph.disable_resource(resource_keys[0])
    graph.disable_resource(resource_keys[1])
    graph.enable_resource(resource_keys[0])
    graph.enable_resource(resource_keys[1])

    graph.validate()
    assert graph.stats() == stats_before
    assert _active_signatures(graph) == signatures_before


def _write_and_parse_project(project_dir: Path) -> Fabric:
    """Write a tiny FABulous project and parse it.

    Parameters
    ----------
    project_dir : Path
        Temporary project directory.

    Returns
    -------
    Fabric
        Parsed FABulous fabric.
    """
    include_dir = project_dir / "Tile" / "include"
    tile_dir = project_dir / "Tile" / "Toy"
    include_dir.mkdir(parents=True)
    tile_dir.mkdir(parents=True)

    (project_dir / "fabric.csv").write_text(
        """\
FabricBegin
Toy,Toy
FabricEnd

ParametersBegin
ConfigBitMode,frame_based
GenerateDelayInSwitchMatrix,80
MultiplexerStyle,custom
SuperTileEnable,FALSE
Tile,./Tile/Toy/Toy.csv
ParametersEnd
""",
        encoding="utf-8",
    )
    (include_dir / "Base.csv").write_text(
        """\
#direction,source_name,X-offset,Y-offset,destination_name,wires
EAST,LONG_BEG,2,0,LONG_END,2
JUMP,LOCAL_BEG,0,0,LOCAL_END,1
""",
        encoding="utf-8",
    )
    (tile_dir / "Toy.csv").write_text(
        """\
TILE,Toy
INCLUDE,../include/Base.csv
MATRIX,./Toy_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (tile_dir / "Toy_switch_matrix.list").write_text(
        """\
LOCAL_END0,LONG_BEG0
LONG_END0,LOCAL_BEG0
""",
        encoding="utf-8",
    )
    return _parse_fabric_project(project_dir)


def _write_and_parse_project_with_standalone_tile(project_dir: Path) -> Fabric:
    """Write a project with one placed and one standalone tile declaration.

    Parameters
    ----------
    project_dir : Path
        Temporary project directory.

    Returns
    -------
    Fabric
        Parsed FABulous fabric.
    """
    include_dir = project_dir / "Tile" / "include"
    toy_dir = project_dir / "Tile" / "Toy"
    standalone_dir = project_dir / "Tile" / "Standalone"
    include_dir.mkdir(parents=True)
    toy_dir.mkdir(parents=True)
    standalone_dir.mkdir(parents=True)

    (project_dir / "fabric.csv").write_text(
        """\
FabricBegin
Toy,Toy
FabricEnd

ParametersBegin
ConfigBitMode,frame_based
GenerateDelayInSwitchMatrix,80
MultiplexerStyle,custom
SuperTileEnable,FALSE
Tile,./Tile/Toy/Toy.csv
Tile,./Tile/Standalone/Standalone.csv
ParametersEnd
""",
        encoding="utf-8",
    )
    (include_dir / "ToyBase.csv").write_text(
        """\
#direction,source_name,X-offset,Y-offset,destination_name,wires
EAST,LONG_BEG,2,0,LONG_END,2
JUMP,LOCAL_BEG,0,0,LOCAL_END,1
""",
        encoding="utf-8",
    )
    (toy_dir / "Toy.csv").write_text(
        """\
TILE,Toy
INCLUDE,../include/ToyBase.csv
MATRIX,./Toy_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (toy_dir / "Toy_switch_matrix.list").write_text(
        """\
LOCAL_END0,LONG_BEG0
LONG_END0,LOCAL_BEG0
""",
        encoding="utf-8",
    )
    (include_dir / "StandaloneBase.csv").write_text(
        """\
#direction,source_name,X-offset,Y-offset,destination_name,wires
JUMP,FREE_BEG,0,0,FREE_END,1
""",
        encoding="utf-8",
    )
    (standalone_dir / "Standalone.csv").write_text(
        """\
TILE,Standalone
INCLUDE,../include/StandaloneBase.csv
MATRIX,./Standalone_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (standalone_dir / "Standalone_switch_matrix.list").write_text(
        "FREE_END0,FREE_BEG0\n",
        encoding="utf-8",
    )
    return _parse_fabric_project(project_dir)


def _write_and_parse_gen_io_project(project_dir: Path) -> Fabric:
    """Write a tiny FABulous project containing one GEN_IO declaration.

    Parameters
    ----------
    project_dir : Path
        Temporary project directory.

    Returns
    -------
    Fabric
        Parsed FABulous fabric.
    """
    tile_dir = project_dir / "Tile" / "WithIO"
    tile_dir.mkdir(parents=True)

    (project_dir / "fabric.csv").write_text(
        """\
FabricBegin
WithIO
FabricEnd

ParametersBegin
ConfigBitMode,frame_based
GenerateDelayInSwitchMatrix,80
MultiplexerStyle,custom
SuperTileEnable,FALSE
Tile,./Tile/WithIO/WithIO.csv
ParametersEnd
""",
        encoding="utf-8",
    )
    (tile_dir / "WithIO.csv").write_text(
        """\
TILE,WithIO
GEN_IO,4,INPUT,EXT,CLOCKED_MUX
MATRIX,./WithIO_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (tile_dir / "WithIO_switch_matrix.list").write_text("", encoding="utf-8")
    return _parse_fabric_project(project_dir)


def _write_and_parse_cross_tile_project(project_dir: Path) -> Fabric:
    """Write a project where repeated driver tiles route into sink tiles.

    Parameters
    ----------
    project_dir : Path
        Temporary project directory.

    Returns
    -------
    Fabric
        Parsed FABulous fabric.
    """
    include_dir = project_dir / "Tile" / "include"
    driver_dir = project_dir / "Tile" / "Driver"
    sink_dir = project_dir / "Tile" / "Sink"
    include_dir.mkdir(parents=True)
    driver_dir.mkdir(parents=True)
    sink_dir.mkdir(parents=True)

    (project_dir / "fabric.csv").write_text(
        """\
FabricBegin
Driver,Sink,Driver,Sink
FabricEnd

ParametersBegin
ConfigBitMode,frame_based
GenerateDelayInSwitchMatrix,80
MultiplexerStyle,custom
SuperTileEnable,FALSE
Tile,./Tile/Driver/Driver.csv
Tile,./Tile/Sink/Sink.csv
ParametersEnd
""",
        encoding="utf-8",
    )
    (include_dir / "Cross.csv").write_text(
        """\
#direction,source_name,X-offset,Y-offset,destination_name,wires
EAST,DRIVE,1,0,RECV,2
""",
        encoding="utf-8",
    )
    (driver_dir / "Driver.csv").write_text(
        """\
TILE,Driver
INCLUDE,../include/Cross.csv
MATRIX,./Driver_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (driver_dir / "Driver_switch_matrix.list").write_text("", encoding="utf-8")
    (sink_dir / "Sink.csv").write_text(
        """\
TILE,Sink
MATRIX,./Sink_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (sink_dir / "Sink_switch_matrix.list").write_text("", encoding="utf-8")
    return _parse_fabric_project(project_dir)


def _write_and_parse_boundary_project(project_dir: Path) -> Fabric:
    """Write a one-tile project with a legal PIP to the fabric boundary.

    Parameters
    ----------
    project_dir : Path
        Temporary project directory.

    Returns
    -------
    Fabric
        Parsed FABulous fabric.
    """
    tile_dir = project_dir / "Tile" / "Edge"
    tile_dir.mkdir(parents=True)

    (project_dir / "fabric.csv").write_text(
        """\
FabricBegin
Edge
FabricEnd

ParametersBegin
ConfigBitMode,frame_based
GenerateDelayInSwitchMatrix,80
MultiplexerStyle,custom
SuperTileEnable,FALSE
Tile,./Tile/Edge/Edge.csv
ParametersEnd
""",
        encoding="utf-8",
    )
    (tile_dir / "Edge.csv").write_text(
        """\
TILE,Edge
EAST,EDGE_BEG,1,0,EDGE_END,1,
MATRIX,./Edge_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (tile_dir / "Edge_switch_matrix.list").write_text("", encoding="utf-8")
    return _parse_fabric_project(project_dir)


def _write_and_parse_include_project(project_dir: Path) -> Fabric:
    """Write a project using both CSV and switch-matrix list includes.

    Parameters
    ----------
    project_dir : Path
        Temporary project directory.

    Returns
    -------
    Fabric
        Parsed FABulous fabric.
    """
    include_dir = project_dir / "Tile" / "include"
    tile_dir = project_dir / "Tile" / "Included"
    include_dir.mkdir(parents=True)
    tile_dir.mkdir(parents=True)

    (project_dir / "fabric.csv").write_text(
        """\
FabricBegin
Included
FabricEnd

ParametersBegin
ConfigBitMode,frame_based
GenerateDelayInSwitchMatrix,80
MultiplexerStyle,custom
SuperTileEnable,FALSE
Tile,./Tile/Included/Included.csv
ParametersEnd
""",
        encoding="utf-8",
    )
    (include_dir / "Base.csv").write_text(
        """\
#direction,source_name,X-offset,Y-offset,destination_name,wires
EAST,BASE_BEG,1,0,BASE_END,1
""",
        encoding="utf-8",
    )
    (include_dir / "Base.list").write_text(
        """\
BASE_END0,BASE_BEG0
""",
        encoding="utf-8",
    )
    (tile_dir / "Included.csv").write_text(
        """\
TILE,Included
INCLUDE,../include/Base.csv
MATRIX,./Included_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (tile_dir / "Included_switch_matrix.list").write_text(
        """\
INCLUDE,../include/Base.list
""",
        encoding="utf-8",
    )
    return _parse_fabric_project(project_dir)


def _parse_fabric_project(project_dir: Path) -> Fabric:
    """Parse a FABulous project with an API-mode project context.

    Parameters
    ----------
    project_dir : Path
        Project directory containing ``fabric.csv``.

    Returns
    -------
    Fabric
        Parsed fabric.
    """
    fabulous_settings.reset_context()
    context = fabulous_settings.FABulousSettings.model_construct(
        proj_dir=project_dir,
        nix_shell=None,
    )
    fabulous_settings._context_instance = context  # noqa: SLF001
    return parseFabricCSV(project_dir / "fabric.csv")


def _demo_multi_instance_external_key(
    graph: RoutingFabricGraph,
) -> RoutingResourceKey:
    """Pick a real external resource represented on multiple tile instances.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Demo routing graph.

    Returns
    -------
    RoutingResourceKey
        External resource key with PIPs on more than one owner tile.

    Raises
    ------
    AssertionError
        If no suitable key exists in the demo graph.
    """
    for key in graph.resource_keys():
        if key.kind is not RoutingPipKind.EXTERNAL_WIRE:
            continue
        owner_tiles = {pip.owner_tile for pip in graph.by_resource_key(key)}
        if len(owner_tiles) > 1:
            return key
    raise AssertionError("demo graph has no multi-instance external resource")


def _demo_multi_instance_internal_key(
    graph: RoutingFabricGraph,
) -> RoutingResourceKey:
    """Pick a real internal resource represented on multiple tile instances.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Demo routing graph.

    Returns
    -------
    RoutingResourceKey
        Internal matrix resource key with PIPs on more than one owner tile.

    Raises
    ------
    AssertionError
        If no suitable key exists in the demo graph.
    """
    for key in graph.resource_keys():
        if key.kind is not RoutingPipKind.INTERNAL_MATRIX:
            continue
        owner_tiles = {pip.owner_tile for pip in graph.by_resource_key(key)}
        if len(owner_tiles) > 1:
            return key
    raise AssertionError("demo graph has no multi-instance internal resource")


def _demo_cross_tile_external_key(
    graph: RoutingFabricGraph,
) -> RoutingResourceKey:
    """Pick a real external resource crossing between different tile types.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Demo routing graph.

    Returns
    -------
    RoutingResourceKey
        External resource key crossing tile types on more than one owner tile.

    Raises
    ------
    AssertionError
        If no suitable key exists in the demo graph.
    """
    for key in graph.resource_keys():
        if key.kind is not RoutingPipKind.EXTERNAL_WIRE:
            continue
        pips = graph.by_resource_key(key)
        owner_tiles = {pip.owner_tile for pip in pips}
        crosses_tile_type = any(
            pip.destination_tile_type is not None
            and pip.source_tile_type != pip.destination_tile_type
            for pip in pips
        )
        if len(owner_tiles) > 1 and crosses_tile_type:
            return key
    raise AssertionError("demo graph has no multi-instance cross-tile resource")


def _demo_resizable_external_keys(
    graph: RoutingFabricGraph,
    tile_type: str,
    *,
    min_wire_count: int,
) -> tuple[RoutingResourceKey, ...]:
    """Return active real external resources with enough vector lanes.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Demo routing graph.
    tile_type : str
        Tile type to select.
    min_wire_count : int
        Minimum CSV wire count.

    Returns
    -------
    tuple[RoutingResourceKey, ...]
        Matching active external resource keys.
    """
    return tuple(
        key
        for key in graph.resource_keys()
        if key.tile_type == tile_type
        and key.kind is RoutingPipKind.EXTERNAL_WIRE
        and key.wire_count is not None
        and key.wire_count >= min_wire_count
    )


def _active_internal_resource_keys(
    graph: RoutingFabricGraph,
    tile_type: str,
) -> tuple[RoutingResourceKey, ...]:
    """Return active internal resource keys for one tile type.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to select.

    Returns
    -------
    tuple[RoutingResourceKey, ...]
        Active internal matrix resource keys.
    """
    return tuple(
        key
        for key in graph.resource_keys()
        if key.tile_type == tile_type and key.kind is RoutingPipKind.INTERNAL_MATRIX
    )


def _synthetic_internal_pip(source_name: str, destination_name: str) -> RoutingPip:
    """Create a valid synthetic internal PIP for the tiny Toy project.

    Parameters
    ----------
    source_name : str
        Matrix source name.
    destination_name : str
        Matrix destination name.

    Returns
    -------
    RoutingPip
        Synthetic internal PIP without an assigned graph id.
    """
    resource_key = RoutingResourceKey(
        tile_type="Toy",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        source_name=source_name,
        destination_name=destination_name,
    )
    return RoutingPip(
        pip_id=None,
        kind=RoutingPipKind.INTERNAL_MATRIX,
        source=RoutingEndpoint(0, 0, destination_name),
        destination=RoutingEndpoint(0, 0, source_name),
        delay=8,
        name=f"{destination_name}.{source_name}",
        owner_tile=(0, 0),
        tile_type="Toy",
        resource_key=resource_key,
        source_tile_type="Toy",
        destination_tile_type="Toy",
    )


def _active_signatures(
    graph: RoutingFabricGraph,
) -> tuple[tuple[str, str, str, str], ...]:
    """Return active PIP signatures in graph order.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Graph to inspect.

    Returns
    -------
    tuple[tuple[str, str, str, str], ...]
        Active nextpnr PIP signatures.
    """
    return tuple(pip.signature for pip in graph.active_pips())
