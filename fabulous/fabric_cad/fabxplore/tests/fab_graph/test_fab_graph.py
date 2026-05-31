"""Tests for the fast public routing fabric optimizer facade."""

from __future__ import annotations

import logging
import shutil
from statistics import mean, median
from time import perf_counter
from typing import TYPE_CHECKING

import pytest  # noqa: DEP004

import fabulous.fabulous_settings as fabulous_settings
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core import (
    fab_graph,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingConfigBits,
    RoutingPipKind,
    RoutingResourceCounts,
    RoutingSwitchMatrix,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.writer import (
    render_matrix_csv,
    render_matrix_list,
    render_tile_csv,
)
from fabulous.fabric_cad.fabxplore.tests.fab_graph.test_rgraph import (
    _parse_fabric_project,
    _resized_external_key,
    _write_and_parse_project,
    _write_and_parse_project_with_standalone_tile,
)
from fabulous.fabric_cad.fabxplore.tests.fab_graph.test_writer import (
    _copy_demo_opt_project_or_skip,
    _line_set,
    _read_csv_rows,
)
from fabulous.fabric_cad.gen_npnr_model import genNextpnrModel
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import parseMatrix
from fabulous.fabulous_api import FABulous_API

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

FabGraph = fab_graph.FabGraph
LOGGER = logging.getLogger(__name__)


def _write_and_load_api(project_dir: Path) -> FABulous_API:
    """Write the synthetic project and load it through FABulous API."""
    _write_and_parse_project(project_dir)
    fab = FABulous_API(VerilogCodeGenerator())
    _set_test_project_context(project_dir)
    fab.loadFabric(project_dir / "fabric.csv")
    return fab


def _write_and_load_api_with_standalone_tile(project_dir: Path) -> FABulous_API:
    """Write a synthetic project with a standalone tile and load it."""
    _write_and_parse_project_with_standalone_tile(project_dir)
    fab = FABulous_API(VerilogCodeGenerator())
    _set_test_project_context(project_dir)
    fab.loadFabric(project_dir / "fabric.csv")
    return fab


def _set_test_project_context(project_dir: Path) -> None:
    """Set FABulous global context for tests that load a project."""
    fabulous_settings._context_instance = (  # noqa: SLF001
        fabulous_settings.FABulousSettings.model_construct(
            proj_dir=project_dir,
            nix_shell=None,
        )
    )


def _load_demo_opt_facade(project_dir: Path) -> FabGraph:
    """Load a copied ``demo_opt`` project into the public graph facade.

    Parameters
    ----------
    project_dir : Path
        Copied ``demo_opt`` project directory.

    Returns
    -------
    FabGraph
        Public graph facade for the project.
    """
    fab = FABulous_API(VerilogCodeGenerator())
    _set_test_project_context(project_dir)
    fab.loadFabric(project_dir / "fabric.csv")
    return FabGraph(fab, project_dir)


def test_fab_graph_query_and_parameter_modify_api(tmp_path: Path) -> None:
    """Use public query and parameter-based modification methods."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)
    active_before = facade.stats().active_pips

    facade.add_external_resource(
        "Toy",
        Direction.JUMP,
        "FG_BEG",
        0,
        0,
        "FG_END",
        1,
    )
    facade.add_matrix_resource("Toy", "FG_END0", "LOCAL_BEG0")
    external_key = facade.routing_graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "FG_BEG",
        0,
        0,
        "FG_END",
        1,
    )
    matrix_key = facade.routing_graph.matrix_resource_key(
        "Toy",
        "FG_END0",
        "LOCAL_BEG0",
    )

    assert external_key in facade.external_resources("Toy")
    assert matrix_key in facade.matrix_resources("Toy")
    assert "FG_END0" in facade.matrix_sources("Toy")
    assert facade.stats().active_pips == active_before + 4

    facade.delete_matrix_resource("Toy", "FG_END0", "LOCAL_BEG0")
    assert matrix_key not in facade.matrix_resources("Toy")
    facade.restore_matrix_resource("Toy", "FG_END0", "LOCAL_BEG0")
    assert matrix_key in facade.matrix_resources("Toy")

    facade.resize_external_resource(
        "Toy",
        Direction.JUMP,
        "FG_BEG",
        0,
        0,
        "FG_END",
        2,
        wire_count=1,
    )
    resized_key = _resized_external_key(external_key, 2)

    assert resized_key in facade.external_resources("Toy")
    assert external_key not in facade.external_resources("Toy")
    assert all(
        key.kind is RoutingPipKind.EXTERNAL_WIRE for key in facade.external_resources()
    )


def test_fab_graph_query_api_accepts_callable_filters(tmp_path: Path) -> None:
    """Filter public query results with user-provided predicates."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)
    facade.add_external_resource(
        "Toy",
        Direction.JUMP,
        "FILTER_BEG",
        0,
        0,
        "FILTER_END",
        1,
    )
    facade.add_matrix_resource("Toy", "FILTER_END0", "LOCAL_BEG0")
    external_key = facade.routing_graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "FILTER_BEG",
        0,
        0,
        "FILTER_END",
        1,
    )
    matrix_key = facade.routing_graph.matrix_resource_key(
        "Toy",
        "FILTER_END0",
        "LOCAL_BEG0",
    )
    facade.disable_matrix_resource("Toy", "FILTER_END0", "LOCAL_BEG0")

    assert facade.tile_types(where=lambda name: name == "Toy") == ["Toy"]
    assert facade.external_resources(
        "Toy",
        where=lambda key: key.source_name == "FILTER_BEG",
    ) == [external_key]
    assert facade.matrix_resources(
        "Toy",
        active_only=False,
        where=lambda key: key.source_name == "FILTER_END0",
    ) == [matrix_key]
    assert set(
        facade.matrix_sources(
            "Toy",
            where=lambda name: name.startswith("FILTER_"),
        )
    ) == {"FILTER_BEG0", "FILTER_END0"}
    assert facade.matrix_sinks(
        "Toy",
        where=lambda name: name == "LOCAL_BEG0",
    ) == ["LOCAL_BEG0"]
    assert facade.active_pips(
        where=lambda pip: pip.resource_key == external_key,
    )
    assert facade.disabled_pips(
        where=lambda pip: pip.resource_key == matrix_key,
    )


def test_fab_graph_iter_active_pips_yields_filtered_pips_lazily(
    tmp_path: Path,
) -> None:
    """Expose lazy active PIP iteration through the public facade."""
    facade = FabGraph(_write_and_load_api_with_standalone_tile(tmp_path), tmp_path)
    active_external = facade.active_pips(
        where=lambda pip: pip.kind is RoutingPipKind.EXTERNAL_WIRE,
    )
    iter_external = list(
        facade.iter_active_pips(
            where=lambda pip: pip.kind is RoutingPipKind.EXTERNAL_WIRE,
        )
    )

    assert iter_external == active_external
    assert next(facade.iter_active_pips()).kind in set(RoutingPipKind)


def test_fab_graph_distinguishes_placed_and_standalone_tile_types(
    tmp_path: Path,
) -> None:
    """Expose declared standalone tiles without concrete routing instances."""
    facade = FabGraph(_write_and_load_api_with_standalone_tile(tmp_path), tmp_path)

    assert facade.tile_types() == ["Toy", "Standalone"]
    assert facade.placed_tile_types() == ["Toy"]
    assert facade.standalone_tile_types() == ["Standalone"]
    filtered_standalone = facade.standalone_tile_types(
        where=lambda name: name.startswith("Stand")
    )

    assert filtered_standalone == ["Standalone"]
    assert all(pip.tile_type != "Standalone" for pip in facade.active_pips())
    assert facade.get_resource_counts("Standalone").total_active == 2


def test_fab_graph_exposes_tile_lookup_by_coordinate(tmp_path: Path) -> None:
    """Expose placed tile lookup through the public facade."""
    facade = FabGraph(_write_and_load_api_with_standalone_tile(tmp_path), tmp_path)
    toy = facade.tile_model("Toy")

    assert facade.tile_type_at(0, 0) == "Toy"
    assert facade.tile_type_at(1, 0) == "Toy"
    assert facade.tile_model_at(0, 0) is toy
    assert facade.tile_model_at(1, 0) is toy
    assert facade.tile_type_at(0, 1) is None
    assert facade.tile_model_at(0, 1) is None
    assert facade.tile_type_at(-1, 0) is None
    assert facade.tile_model_at(99, 99) is None


def test_fab_graph_exposes_demo_opt_supertile_queries(tmp_path: Path) -> None:
    """Expose loaded supertile names and their child tile types."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    facade = _load_demo_opt_facade(project_dir)

    assert "DSP" in facade.supertile_types()
    assert facade.supertile_types(where=lambda name: name == "DSP") == ["DSP"]
    assert facade.supertile_subtiles("DSP") == ["DSP_top", "DSP_bot"]
    with pytest.raises(ValueError, match="Unknown supertile type"):
        facade.supertile_subtiles("Missing")


def test_fab_graph_exposes_config_bit_queries(tmp_path: Path) -> None:
    """Expose tile-local config-bit counts through the public facade."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)

    initial = facade.get_config_bits("Toy")

    assert isinstance(initial, RoutingConfigBits)
    assert initial.matrix_config_bits == 0
    assert initial.fixed_config_bits == 0
    assert initial.total_config_bits == 0

    facade.add_matrix_resource("Toy", "LONG_END0", "LONG_BEG0")
    facade.add_matrix_resource("Toy", "LONG_END0", "LONG_BEG1")
    changed = facade.get_config_bits("Toy")
    all_bits = facade.get_config_bits()

    assert changed.matrix_config_bits == 2
    assert changed.total_config_bits == 2
    assert isinstance(all_bits, dict)
    assert all_bits["Toy"] == changed


def test_fab_graph_exposes_resource_count_queries(tmp_path: Path) -> None:
    """Expose cheap tile-local resource counts through the public facade."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)

    initial = facade.get_resource_counts("Toy")

    assert isinstance(initial, RoutingResourceCounts)
    assert initial.total_active == 4
    assert initial.total_disabled == 0

    key = facade.matrix_resources("Toy")[0]
    facade.delete_matrix_resource(key=key)
    changed = facade.get_resource_counts("Toy")
    all_counts = facade.get_resource_counts()

    assert changed.matrix_active == initial.matrix_active - 1
    assert changed.matrix_disabled == initial.matrix_disabled + 1
    assert changed.total_active == initial.total_active - 1
    assert changed.total_disabled == initial.total_disabled + 1
    assert isinstance(all_counts, dict)
    assert all_counts["Toy"] == changed


def test_fab_graph_exposes_switch_matrix_query(tmp_path: Path) -> None:
    """Expose switch-matrix rows, columns, and delay-valued cells."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)

    switch_matrix = facade.switch_matrix("Toy")

    assert isinstance(switch_matrix, RoutingSwitchMatrix)
    assert switch_matrix.tile_type == "Toy"
    assert _switch_matrix_value(switch_matrix, "LOCAL_END0", "LONG_BEG0") == 8.0
    assert _switch_matrix_value(switch_matrix, "LONG_END0", "LOCAL_BEG0") == 8.0

    facade.delete_matrix_resource("Toy", "LONG_END0", "LOCAL_BEG0")
    disabled_matrix = facade.switch_matrix("Toy")

    assert "LONG_END0" in disabled_matrix.rows
    assert "LOCAL_BEG0" in disabled_matrix.columns
    assert _switch_matrix_value(disabled_matrix, "LOCAL_END0", "LONG_BEG0") == 8.0
    assert _switch_matrix_value(disabled_matrix, "LONG_END0", "LOCAL_BEG0") == 0.0

    facade.add_matrix_resource("Toy", "LOCAL_END0", "LOCAL_BEG0", delay=12.5)
    updated_matrix = facade.switch_matrix("Toy")

    assert _switch_matrix_value(updated_matrix, "LOCAL_END0", "LOCAL_BEG0") == 12.5


def test_fab_graph_set_switch_matrix_updates_tile_matrix(tmp_path: Path) -> None:
    """Replace a switch matrix from row/column labels and delay values."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)
    switch_matrix = facade.switch_matrix("Toy")
    matrix = [list(row) for row in switch_matrix.matrix]

    matrix[switch_matrix.rows.index("LONG_END0")][
        switch_matrix.columns.index("LOCAL_BEG0")
    ] = 0.0
    matrix[switch_matrix.rows.index("LOCAL_END0")][
        switch_matrix.columns.index("LOCAL_BEG0")
    ] = 12.5

    facade.set_switch_matrix(
        "Toy",
        switch_matrix.columns,
        switch_matrix.rows,
        matrix,
    )
    updated_matrix = facade.switch_matrix("Toy")

    assert _switch_matrix_value(updated_matrix, "LONG_END0", "LOCAL_BEG0") == 0.0
    assert _switch_matrix_value(updated_matrix, "LOCAL_END0", "LOCAL_BEG0") == 12.5
    assert ("LOCAL_END0", "LOCAL_BEG0") in {
        (key.source_name, key.destination_name)
        for key in facade.matrix_resources("Toy")
    }

    with pytest.raises(ValueError, match="row count"):
        facade.set_switch_matrix("Toy", switch_matrix.columns, switch_matrix.rows, [])
    with pytest.raises(ValueError, match="column count"):
        facade.set_switch_matrix(
            "Toy",
            switch_matrix.columns,
            switch_matrix.rows,
            [[0.0] for _row in switch_matrix.rows],
        )
    invalid_matrix = [list(row) for row in switch_matrix.matrix]
    invalid_matrix[0][0] = -1.0
    with pytest.raises(ValueError, match="non-negative"):
        facade.set_switch_matrix(
            "Toy",
            switch_matrix.columns,
            switch_matrix.rows,
            invalid_matrix,
        )


def test_fab_graph_demo_opt_switch_matrix_query_matches_rendered_csv(
    tmp_path: Path,
) -> None:
    """Compare queried ``LUT4AB`` switch matrix with rendered CSV content."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    facade = _load_demo_opt_facade(project_dir)
    tile_type = "LUT4AB"
    switch_matrix = facade.switch_matrix(tile_type)
    matrix_csv = tmp_path / f"{tile_type}_switch_matrix.csv"

    matrix_csv.write_text(
        render_matrix_csv(facade.routing_graph, tile_type),
        encoding="utf-8",
    )
    parsed_csv = parseMatrix(matrix_csv, tile_type)
    csv_pairs = {
        (source_name, destination_name)
        for source_name, destination_names in parsed_csv.items()
        for destination_name in destination_names
    }

    assert _switch_matrix_active_pairs(switch_matrix) == csv_pairs


def test_fab_graph_demo_opt_set_switch_matrix_round_trips_rendered_csv(
    tmp_path: Path,
) -> None:
    """Set ``LUT4AB`` from its queried matrix and compare rendered CSV pairs."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    facade = _load_demo_opt_facade(project_dir)
    tile_type = "LUT4AB"
    switch_matrix = facade.switch_matrix(tile_type)
    matrix_csv = tmp_path / f"{tile_type}_switch_matrix.csv"

    facade.set_switch_matrix(
        tile_type,
        switch_matrix.columns,
        switch_matrix.rows,
        [list(row) for row in switch_matrix.matrix],
    )
    matrix_csv.write_text(
        render_matrix_csv(facade.routing_graph, tile_type),
        encoding="utf-8",
    )
    parsed_csv = parseMatrix(matrix_csv, tile_type)
    csv_pairs = {
        (source_name, destination_name)
        for source_name, destination_names in parsed_csv.items()
        for destination_name in destination_names
    }

    assert _switch_matrix_active_pairs(facade.switch_matrix(tile_type)) == csv_pairs


def test_fab_graph_delete_and_restore_external_resource_by_parameters(
    tmp_path: Path,
) -> None:
    """Delete and restore an external resource without constructing its key."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)
    facade.add_external_resource(
        "Toy",
        Direction.JUMP,
        "DEL_BEG",
        0,
        0,
        "DEL_END",
        1,
    )
    external_key = facade.routing_graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "DEL_BEG",
        0,
        0,
        "DEL_END",
        1,
    )

    facade.delete_external_resource(
        "Toy",
        Direction.JUMP,
        "DEL_BEG",
        0,
        0,
        "DEL_END",
    )
    assert external_key not in facade.external_resources("Toy")
    facade.restore_external_resource(
        "Toy",
        Direction.JUMP,
        "DEL_BEG",
        0,
        0,
        "DEL_END",
    )

    assert external_key in facade.external_resources("Toy")


def test_fab_graph_modify_api_accepts_resource_keys(tmp_path: Path) -> None:
    """Use query-returned immutable resource keys directly in edit calls."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)
    facade.add_external_resource(
        "Toy",
        Direction.JUMP,
        "KEY_BEG",
        0,
        0,
        "KEY_END",
        1,
    )
    facade.add_external_resource(
        "Toy",
        Direction.JUMP,
        "KEY_RESIZE_BEG",
        0,
        0,
        "KEY_RESIZE_END",
        1,
    )
    external_key = facade.routing_graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "KEY_BEG",
        0,
        0,
        "KEY_END",
        1,
    )
    resize_external_key = facade.routing_graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "KEY_RESIZE_BEG",
        0,
        0,
        "KEY_RESIZE_END",
        1,
    )
    matrix_key = facade.matrix_resources("Toy")[0]

    facade.delete_external_resource(
        tile_type="ignored",
        key=external_key,
    )
    facade.restore_external_resource(key=external_key)
    facade.delete_matrix_resource(key=matrix_key)
    facade.restore_matrix_resource(key=matrix_key)
    facade.resize_external_resource(
        key=resize_external_key,
        new_wire_count=2,
    )
    resized_key = _resized_external_key(resize_external_key, 2)

    assert external_key in facade.external_resources("Toy")
    assert matrix_key in facade.matrix_resources("Toy")
    assert resized_key in facade.external_resources("Toy")
    assert resize_external_key not in facade.external_resources("Toy")
    with pytest.raises(ValueError, match="external_wire"):
        facade.delete_external_resource(key=matrix_key)
    with pytest.raises(ValueError, match="internal_matrix"):
        facade.delete_matrix_resource(key=external_key)


def test_fab_graph_add_matrix_rows_can_overwrite_matrix(
    tmp_path: Path,
) -> None:
    """Replace a switch matrix with matrix-resource triplets."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)
    existing_pairs = {
        (key.source_name, key.destination_name)
        for key in facade.matrix_resources("Toy")
    }

    facade.add_matrix_rows(
        "Toy",
        [
            ("LONG_END1", "LOCAL_BEG0", 12.0),
            ("LOCAL_END0", "LONG_BEG1", 13.5),
        ],
        overwrite=True,
    )
    current_keys = facade.matrix_resources("Toy")
    current_pairs = {(key.source_name, key.destination_name) for key in current_keys}
    new_delays = {
        pip.resource_key.source_name: pip.delay
        for pip in facade.active_pips(
            where=lambda pip: (
                pip.kind is RoutingPipKind.INTERNAL_MATRIX
                and pip.resource_key in current_keys
            )
        )
    }

    assert not existing_pairs & current_pairs
    assert current_pairs == {
        ("LONG_END1", "LOCAL_BEG0"),
        ("LOCAL_END0", "LONG_BEG1"),
    }
    assert new_delays == {"LONG_END1": 12.0, "LOCAL_END0": 13.5}


def test_fab_graph_add_matrix_rows_rolls_back_invalid_batch(
    tmp_path: Path,
) -> None:
    """Reject invalid matrix-resource triplets without partial mutation."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)
    pips_before = facade.render_pips_txt()

    with pytest.raises(ValueError, match="missing tile wire"):
        facade.add_matrix_rows(
            "Toy",
            [
                ("MISSING0", "LOCAL_BEG0", 13.0),
            ],
        )
    existing_key = facade.matrix_resources("Toy")[0]
    with pytest.raises(ValueError, match="matrix resource already exists"):
        facade.add_matrix_rows(
            "Toy",
            [
                (existing_key.source_name, existing_key.destination_name, 13.0),
            ],
        )

    assert facade.render_pips_txt() == pips_before


def test_fab_graph_repeated_operations_with_plain_loops(tmp_path: Path) -> None:
    """Apply repeated public facade operations with plain Python loops."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)
    stats_before = facade.stats()

    for edit in (
        lambda: facade.add_external_resource(
            "Toy",
            Direction.JUMP,
            "BATCH_FG_BEG",
            0,
            0,
            "BATCH_FG_END",
            1,
        ),
        lambda: facade.add_matrix_resource(
            "Toy",
            "BATCH_FG_END0",
            "LOCAL_BEG0",
        ),
    ):
        edit()
    external_key = facade.routing_graph.external_resource_key(
        "Toy",
        Direction.JUMP,
        "BATCH_FG_BEG",
        0,
        0,
        "BATCH_FG_END",
        1,
    )
    matrix_key = facade.routing_graph.matrix_resource_key(
        "Toy",
        "BATCH_FG_END0",
        "LOCAL_BEG0",
    )
    stats_after = facade.stats()
    pips_after = facade.render_pips_txt()

    assert external_key in facade.external_resources("Toy")
    assert matrix_key in facade.matrix_resources("Toy")
    assert stats_after.active_pips == stats_before.active_pips + 4

    with pytest.raises(ValueError, match="missing tile wire"):
        facade.add_matrix_resource(
            "Toy",
            "MISSING0",
            "LOCAL_BEG0",
        )

    with pytest.raises(ValueError, match="matrix resource already exists"):
        facade.add_matrix_resource(
            "Toy",
            "BATCH_FG_END0",
            "LOCAL_BEG0",
        )

    assert facade.stats() == stats_after
    assert facade.render_pips_txt() == pips_after


def test_fab_graph_demo_opt_operation_timing_characterization(
    tmp_path: Path,
    record_property: Callable[[str, object], None],
) -> None:
    """Measure median public operation costs on real ``demo_opt``."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    tile_type = "LUT4AB"
    metrics: dict[str, dict[str, float | int]] = {}

    delete_single = _load_demo_opt_facade(project_dir)
    delete_keys = _require_count(
        delete_single.matrix_resources(tile_type),
        60,
        "single matrix delete resources",
    )
    delete_samples: list[tuple[float, int]] = []
    for key in delete_keys[:60]:
        elapsed, _result = _time_call(
            lambda key=key: delete_single.delete_matrix_resource(key=key)
        )
        delete_samples.append((elapsed, 1))
    metrics["delete_single_matrix_resource"] = _timing_summary(
        delete_samples,
        "resource",
    )

    resize_single = _load_demo_opt_facade(project_dir)
    resize_keys = _require_count(
        resize_single.external_resources(
            tile_type,
            where=lambda key: (
                key.wire_count is not None
                and key.wire_count > 2
                and key.source_name != "Co"
            ),
        ),
        30,
        "single external resize resources",
    )
    resize_samples: list[tuple[float, int]] = []
    for key in resize_keys[:30]:
        elapsed, _result = _time_call(
            lambda key=key: resize_single.resize_external_resource(
                key=key,
                new_wire_count=key.wire_count - 1,
            )
        )
        resize_samples.append((elapsed, 1))
    metrics["resize_single_external_resource"] = _timing_summary(
        resize_samples,
        "resource",
    )

    add_external_single = _load_demo_opt_facade(project_dir)
    elapsed, _result = _time_call(
        lambda: add_external_single.add_external_resource(
            tile_type,
            Direction.JUMP,
            "TIMING_PROBE_BEG",
            0,
            0,
            "TIMING_PROBE_END",
            1,
        )
    )
    metrics["add_single_external_resource"] = _timing_summary(
        [(elapsed, 1)],
        "resource",
    )

    add_single = _load_demo_opt_facade(project_dir)
    add_entries = _require_count(
        _missing_matrix_triplets_for_tile(add_single, tile_type, limit=60),
        60,
        "single matrix add triplets",
    )
    add_samples: list[tuple[float, int]] = []
    for source_name, destination_name, delay in add_entries[:60]:

        def add_one(
            source_name: str = source_name,
            destination_name: str = destination_name,
            delay: float = delay,
        ) -> None:
            add_single.add_matrix_resource(
                tile_type,
                source_name,
                destination_name,
                delay=delay,
            )

        elapsed, _result = _time_call(add_one)
        add_samples.append((elapsed, 1))
    metrics["add_single_matrix_resource"] = _timing_summary(
        add_samples,
        "resource",
    )

    query_facade = _load_demo_opt_facade(project_dir)
    query_samples: list[tuple[float, int]] = []
    query_result_count = 0
    for _index in range(100):
        elapsed, result = _time_call(
            lambda: query_facade.matrix_resources(
                tile_type,
                where=lambda key: (
                    key.source_name.startswith("J")
                    or key.destination_name.startswith("L")
                ),
            )
        )
        query_result_count += len(result)
        query_samples.append((elapsed, 1))
    metrics["query_matrix_resources_with_where"] = _timing_summary(
        query_samples,
        "query",
    )

    config_bits_samples: list[tuple[float, int]] = []
    config_bits_total = 0
    for _index in range(100):
        elapsed, result = _time_call(lambda: query_facade.get_config_bits(tile_type))
        config_bits_total += result.total_config_bits
        config_bits_samples.append((elapsed, 1))
    metrics["query_config_bits_lut4ab"] = _timing_summary(
        config_bits_samples,
        "query",
    )

    resource_counts_samples: list[tuple[float, int]] = []
    resource_counts_total = 0
    for _index in range(100):
        elapsed, result = _time_call(
            lambda: query_facade.get_resource_counts(tile_type)
        )
        resource_counts_total += result.total_active
        resource_counts_samples.append((elapsed, 1))
    metrics["query_resource_counts_lut4ab"] = _timing_summary(
        resource_counts_samples,
        "query",
    )

    switch_matrix_samples: list[tuple[float, int]] = []
    switch_matrix_nonzero_total = 0
    for _index in range(100):
        elapsed, result = _time_call(lambda: query_facade.switch_matrix(tile_type))
        switch_matrix_nonzero_total += sum(
            1 for row in result.matrix for value in row if value != 0.0
        )
        switch_matrix_samples.append((elapsed, 1))
    metrics["query_switch_matrix_lut4ab"] = _timing_summary(
        switch_matrix_samples,
        "query",
    )

    set_switch_matrix = _load_demo_opt_facade(project_dir)
    switch_matrix = set_switch_matrix.switch_matrix(tile_type)
    replacement_matrix = [list(row) for row in switch_matrix.matrix]
    cleared_cell = False
    for row in replacement_matrix:
        for column_index, value in enumerate(row):
            if value != 0.0:
                row[column_index] = 0.0
                cleared_cell = True
                break
        if cleared_cell:
            break
    assert cleared_cell
    set_switch_matrix_samples: list[tuple[float, int]] = []
    for _index in range(10):
        elapsed, _result = _time_call(
            lambda: set_switch_matrix.set_switch_matrix(
                tile_type,
                list(switch_matrix.columns),
                list(switch_matrix.rows),
                [list(row) for row in replacement_matrix],
            )
        )
        set_switch_matrix_samples.append((elapsed, 1))
    metrics["set_switch_matrix_lut4ab"] = _timing_summary(
        set_switch_matrix_samples,
        "matrix",
    )

    batch_delete = _load_demo_opt_facade(project_dir)
    batch_delete_keys = _require_count(
        batch_delete.matrix_resources(tile_type),
        50,
        "batch matrix delete resources",
    )
    batch_delete_samples: list[tuple[float, int]] = []
    for batch in _chunks(batch_delete_keys[:50], 10):
        elapsed, _result = _time_call(
            lambda batch=batch: [
                batch_delete.delete_matrix_resource(key=key) for key in batch
            ]
        )
        batch_delete_samples.append((elapsed, len(batch)))
    metrics["batch_delete_10_matrix_resources"] = _timing_summary(
        batch_delete_samples,
        "resource",
    )

    batch_restore = _load_demo_opt_facade(project_dir)
    batch_restore_keys = _require_count(
        batch_restore.matrix_resources(tile_type),
        50,
        "batch matrix restore resources",
    )
    batch_restore_samples: list[tuple[float, int]] = []
    for batch in _chunks(batch_restore_keys[:50], 10):
        for key in batch:
            batch_restore.delete_matrix_resource(key=key)
        elapsed, _result = _time_call(
            lambda batch=batch: [
                batch_restore.restore_matrix_resource(key=key) for key in batch
            ]
        )
        batch_restore_samples.append((elapsed, len(batch)))
    metrics["batch_restore_10_matrix_resources"] = _timing_summary(
        batch_restore_samples,
        "resource",
    )

    batch_delete_restore = _load_demo_opt_facade(project_dir)
    batch_delete_restore_keys = _require_count(
        batch_delete_restore.matrix_resources(tile_type),
        50,
        "batch matrix delete and restore resources",
    )
    batch_delete_restore_samples: list[tuple[float, int]] = []
    for batch in _chunks(batch_delete_restore_keys[:50], 10):
        elapsed, _result = _time_call(
            lambda batch=batch: [
                operation(key=key)
                for key in batch
                for operation in (
                    batch_delete_restore.delete_matrix_resource,
                    batch_delete_restore.restore_matrix_resource,
                )
            ]
        )
        batch_delete_restore_samples.append((elapsed, len(batch) * 2))
    metrics["batch_delete_restore_10_matrix_resources"] = _timing_summary(
        batch_delete_restore_samples,
        "operation",
    )

    batch_resize = _load_demo_opt_facade(project_dir)
    batch_resize_keys = _require_count(
        batch_resize.external_resources(
            tile_type,
            where=lambda key: (
                key.wire_count is not None
                and key.wire_count > 2
                and key.source_name != "Co"
            ),
        ),
        30,
        "batch external resize resources",
    )
    batch_resize_samples: list[tuple[float, int]] = []
    for batch in _chunks(batch_resize_keys[:30], 10):
        elapsed, _result = _time_call(
            lambda batch=batch: [
                batch_resize.resize_external_resource(
                    key=key,
                    new_wire_count=key.wire_count - 1,
                )
                for key in batch
            ]
        )
        batch_resize_samples.append((elapsed, len(batch)))
    metrics["batch_resize_10_external_resources"] = _timing_summary(
        batch_resize_samples,
        "resource",
    )

    batch_add = _load_demo_opt_facade(project_dir)
    batch_add_entries = _require_count(
        _missing_matrix_triplets_for_tile(batch_add, tile_type, limit=50),
        50,
        "batch matrix add triplets",
    )
    batch_add_samples: list[tuple[float, int]] = []
    for batch in _chunks(batch_add_entries[:50], 10):
        elapsed, _result = _time_call(
            lambda batch=batch: [
                batch_add.add_matrix_resource(
                    tile_type,
                    source_name,
                    destination_name,
                    delay=delay,
                )
                for source_name, destination_name, delay in batch
            ]
        )
        batch_add_samples.append((elapsed, len(batch)))
    metrics["batch_add_10_matrix_resources"] = _timing_summary(
        batch_add_samples,
        "resource",
    )

    overwrite_add = _load_demo_opt_facade(project_dir)
    overwrite_entries = _require_count(
        _missing_matrix_triplets_for_tile(overwrite_add, tile_type, limit=10),
        10,
        "overwrite matrix add triplets",
    )
    overwrite_samples: list[tuple[float, int]] = []
    for entry in overwrite_entries[:10]:
        elapsed, _result = _time_call(
            lambda entry=entry: overwrite_add.add_matrix_rows(
                tile_type,
                [entry],
                overwrite=True,
            )
        )
        overwrite_samples.append((elapsed, 1))
    metrics["overwrite_matrix_with_one_resource"] = _timing_summary(
        overwrite_samples,
        "resource",
    )

    assert query_result_count > 0
    assert config_bits_total > 0
    assert resource_counts_total > 0
    assert switch_matrix_nonzero_total > 0
    for metric in metrics.values():
        assert metric["samples"] > 0
        assert metric["median_seconds"] >= 0
        assert metric["average_seconds"] >= 0

    record_property("fab_graph_demo_opt_operation_timings", metrics)
    LOGGER.info("FabGraph demo_opt operation timings: %s", metrics)


def _time_call[ResultT](call: Callable[[], ResultT]) -> tuple[float, ResultT]:
    """Time one callable execution.

    Parameters
    ----------
    call : Callable[[], ResultT]
        Callable to execute.

    Returns
    -------
    tuple[float, ResultT]
        Elapsed seconds and callable result.
    """
    start = perf_counter()
    result = call()
    return perf_counter() - start, result


def _switch_matrix_value(
    switch_matrix: RoutingSwitchMatrix,
    row: str,
    column: str,
) -> float:
    """Return one switch-matrix cell by row and column label.

    Parameters
    ----------
    switch_matrix : RoutingSwitchMatrix
        Matrix to inspect.
    row : str
        Row label.
    column : str
        Column label.

    Returns
    -------
    float
        Cell value.
    """
    return switch_matrix.matrix[switch_matrix.rows.index(row)][
        switch_matrix.columns.index(column)
    ]


def _switch_matrix_active_pairs(
    switch_matrix: RoutingSwitchMatrix,
) -> set[tuple[str, str]]:
    """Return active ``(row, column)`` matrix pairs.

    Parameters
    ----------
    switch_matrix : RoutingSwitchMatrix
        Matrix to inspect.

    Returns
    -------
    set[tuple[str, str]]
        Active row and column labels.
    """
    return {
        (row_name, column_name)
        for row_index, row_name in enumerate(switch_matrix.rows)
        for column_index, column_name in enumerate(switch_matrix.columns)
        if switch_matrix.matrix[row_index][column_index] != 0.0
    }


def _tile_generated_artifact_paths(
    project_dir: Path, tile_type: str
) -> tuple[Path, ...]:
    """Return generated tile artifact paths controlled by ``generate_rtl``.

    Parameters
    ----------
    project_dir : Path
        FABulous project root.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    tuple[Path, ...]
        Generated RTL and config-memory artifact paths.
    """
    return _tile_generated_artifact_paths_in_dir(
        project_dir / "Tile" / tile_type, tile_type
    )


def _tile_generated_rtl_paths(project_dir: Path, tile_type: str) -> tuple[Path, ...]:
    """Return generated tile RTL paths required for every generated tile.

    Parameters
    ----------
    project_dir : Path
        FABulous project root.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    tuple[Path, ...]
        Tile and switch-matrix RTL paths.
    """
    return _tile_generated_rtl_paths_in_dir(project_dir / "Tile" / tile_type, tile_type)


def _tile_generated_artifact_paths_in_dir(
    tile_dir: Path, tile_type: str
) -> tuple[Path, ...]:
    """Return generated artifact paths below an explicit tile directory.

    Parameters
    ----------
    tile_dir : Path
        Tile source directory.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    tuple[Path, ...]
        Generated RTL and config-memory artifact paths.
    """
    return (
        *_tile_generated_rtl_paths_in_dir(tile_dir, tile_type),
        tile_dir / f"{tile_type}_ConfigMem.csv",
        tile_dir / f"{tile_type}_ConfigMem.v",
    )


def _tile_generated_rtl_paths_in_dir(
    tile_dir: Path, tile_type: str
) -> tuple[Path, ...]:
    """Return generated RTL paths below an explicit tile directory.

    Parameters
    ----------
    tile_dir : Path
        Tile source directory.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    tuple[Path, ...]
        Tile and switch-matrix RTL paths.
    """
    return (
        tile_dir / f"{tile_type}.v",
        tile_dir / f"{tile_type}_switch_matrix.v",
    )


def _timing_summary(
    samples: list[tuple[float, int]],
    unit_name: str,
) -> dict[str, float | int]:
    """Summarize operation timing samples.

    Parameters
    ----------
    samples : list[tuple[float, int]]
        Pairs of elapsed seconds and operation unit counts.
    unit_name : str
        Unit name for the per-unit average field.

    Returns
    -------
    dict[str, float | int]
        Timing summary containing sample counts, median, average, and per-unit
        average seconds.

    Raises
    ------
    ValueError
        If ``samples`` is empty or has no units.
    """
    if not samples:
        raise ValueError("cannot summarize empty timing samples")
    durations = [duration for duration, _units in samples]
    total_units = sum(units for _duration, units in samples)
    if total_units <= 0:
        raise ValueError("cannot summarize timing samples without units")
    return {
        "samples": len(samples),
        "units": total_units,
        "median_seconds": median(durations),
        "average_seconds": mean(durations),
        f"average_seconds_per_{unit_name}": sum(durations) / total_units,
    }


def _chunks[ItemT](items: list[ItemT], size: int) -> list[list[ItemT]]:
    """Split a list into fixed-size chunks.

    Parameters
    ----------
    items : list[ItemT]
        Items to split.
    size : int
        Maximum chunk size.

    Returns
    -------
    list[list[ItemT]]
        Chunks in input order.

    Raises
    ------
    ValueError
        If ``size`` is not positive.
    """
    if size <= 0:
        raise ValueError(f"chunk size must be positive: {size}")
    return [items[index : index + size] for index in range(0, len(items), size)]


def _missing_matrix_triplets_for_tile(
    facade: FabGraph,
    tile_type: str,
    *,
    limit: int,
) -> list[tuple[str, str, float]]:
    """Return missing legal matrix-resource triplets for a tile type.

    Parameters
    ----------
    facade : FabGraph
        Public graph facade.
    tile_type : str
        Tile type whose matrix should be inspected.
    limit : int
        Maximum number of triplets to return.

    Returns
    -------
    list[tuple[str, str, float]]
        Missing ``(source_name, destination_name, delay)`` triplets.

    Raises
    ------
    AssertionError
        If there are not enough missing candidates.
    """
    existing_pairs = {
        (key.source_name, key.destination_name)
        for key in facade.matrix_resources(tile_type, active_only=False)
    }
    candidates = [
        (source, sink, 8.0)
        for source in facade.matrix_sources(tile_type)
        for sink in facade.matrix_sinks(tile_type)
        if source != sink and (source, sink) not in existing_pairs
    ]
    if len(candidates) < limit:
        raise AssertionError(
            f"{tile_type} has only {len(candidates)} missing matrix candidates"
        )
    return candidates[:limit]


def _require_count[ItemT](
    items: list[ItemT],
    count: int,
    label: str,
) -> list[ItemT]:
    """Require at least ``count`` items for a real-project stress test.

    Parameters
    ----------
    items : list[ItemT]
        Candidate items.
    count : int
        Required minimum count.
    label : str
        Human-readable candidate label.

    Returns
    -------
    list[ItemT]
        Original item list.

    Raises
    ------
    AssertionError
        If not enough items are available.
    """
    if len(items) < count:
        raise AssertionError(f"Need {count} {label}, got {len(items)}")
    return items


def test_fab_graph_writer_facade_round_trips_synthetic_project(
    tmp_path: Path,
) -> None:
    """Write tile sources through the public facade and reparse the project."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)

    facade.delete_matrix_resource("Toy", "LONG_END0", "LOCAL_BEG0")
    facade.write_tile_sources()
    pips_path = tmp_path / ".FABulous" / "pips.txt"
    facade.write_pips_txt(pips_path)
    reparsed = _parse_fabric_project(tmp_path)

    assert (tmp_path / "Tile" / "Toy" / "Toy.csv").exists()
    assert pips_path.read_text(encoding="utf-8") == facade.render_pips_txt()
    assert genNextpnrModel(reparsed)[0] == facade.render_pips_txt()


def test_fab_graph_write_pips_uses_default_metadata_path(tmp_path: Path) -> None:
    """Write only current graph PIPs to the current project's metadata dir."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)

    facade.delete_matrix_resource("Toy", "LONG_END0", "LOCAL_BEG0")
    facade.write_pips()

    pips_path = tmp_path / ".FABulous" / "pips.txt"
    assert pips_path.read_text(encoding="utf-8") == facade.render_pips_txt()


def test_fab_graph_write_tile_requires_explicit_name_and_path(
    tmp_path: Path,
) -> None:
    """Write one tile only when both tile name and destination are explicit."""
    facade = FabGraph(_write_and_load_api(tmp_path), tmp_path)

    with pytest.raises(ValueError, match="tile name"):
        facade.write_tile(path=tmp_path / "tile_export")
    with pytest.raises(ValueError, match="output path"):
        facade.write_tile(name="Toy")

    tile_dir = tmp_path / "tile_export"
    facade.write_tile(name="Toy", path=tile_dir)

    assert (tile_dir / "Toy.csv").exists()
    assert (tile_dir / "Toy_switch_matrix.list").exists()
    assert (tile_dir / "Toy_switch_matrix.csv").exists()


def test_fab_graph_write_tile_exports_demo_opt_tile_to_custom_path(
    tmp_path: Path,
) -> None:
    """Write one real demo tile to an explicit directory and check contents."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    fab = FABulous_API(VerilogCodeGenerator())
    _set_test_project_context(project_dir)
    fab.loadFabric(project_dir / "fabric.csv")
    facade = FabGraph(fab, project_dir)
    tile_type = "LUT4AB"
    key = facade.matrix_resources(tile_type)[0]
    tile_dir = tmp_path / "single_tile_export"
    stale_rtl = tile_dir / f"{tile_type}.v"
    stale_matrix = tile_dir / f"{tile_type}_switch_matrix.csv"
    tile_dir.mkdir()
    stale_rtl.write_text("stale artifact", encoding="utf-8")
    stale_matrix.write_text("stale artifact", encoding="utf-8")

    facade.disable_matrix_resource(key=key)
    facade.write_tile(name=tile_type, path=tile_dir)

    tile_csv = tile_dir / f"{tile_type}.csv"
    matrix_list = tile_dir / f"{tile_type}_switch_matrix.list"
    matrix_csv = tile_dir / f"{tile_type}_switch_matrix.csv"
    assert not stale_rtl.exists()
    assert tile_csv.read_text(encoding="utf-8") == render_tile_csv(
        facade.routing_graph,
        tile_type,
        matrix_csv.name,
    )
    assert matrix_list.read_text(encoding="utf-8") == render_matrix_list(
        facade.routing_graph,
        tile_type,
    )
    assert matrix_csv.read_text(encoding="utf-8") == render_matrix_csv(
        facade.routing_graph,
        tile_type,
    )
    assert _read_csv_rows(tile_csv)[0] == ["TILE", tile_type]
    assert "INCLUDE" not in tile_csv.read_text(encoding="utf-8")
    assert "GENERATE" not in tile_csv.read_text(encoding="utf-8")


def test_fab_graph_write_tile_sources_generate_rtl_requires_project_root(
    tmp_path: Path,
) -> None:
    """Reject generated RTL output to a non-project tile-source directory."""
    project_dir = tmp_path / "project"
    facade = FabGraph(_write_and_load_api(project_dir), project_dir)
    output_root = tmp_path / "tile_sources"

    with pytest.raises(ValueError, match="valid FABulous project root"):
        facade.write_tile_sources(
            output_root=output_root,
            tile_types=("Toy",),
            generate_rtl=True,
        )

    assert not output_root.exists()


@pytest.mark.parametrize(
    ("in_place", "generate_rtl"),
    [
        (True, True),
        (False, True),
        (True, False),
        (False, False),
    ],
)
def test_fab_graph_write_tile_sources_updates_two_demo_tiles(
    tmp_path: Path,
    *,
    in_place: bool,
    generate_rtl: bool,
) -> None:
    """Write selected demo tiles in place and to a project copy."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    output_dir = project_dir if in_place else tmp_path / "tile_sources_project"
    if not in_place:
        shutil.copytree(project_dir, output_dir)
    facade = _load_demo_opt_facade(project_dir)
    tile_types = ("RegFile", "N_term_single")
    deleted_keys = {
        tile_type: facade.matrix_resources(tile_type)[0] for tile_type in tile_types
    }
    source_artifacts = {
        tile_type: {
            artifact_path: artifact_path.read_text(encoding="utf-8")
            for artifact_path in _tile_generated_artifact_paths(project_dir, tile_type)
            if artifact_path.exists()
        }
        for tile_type in tile_types
    }
    output_artifact_paths = {
        tile_type: _tile_generated_artifact_paths(output_dir, tile_type)
        for tile_type in tile_types
    }

    for tile_type in tile_types:
        for artifact_path in output_artifact_paths[tile_type]:
            artifact_path.write_text("stale artifact", encoding="utf-8")
        facade.disable_matrix_resource(key=deleted_keys[tile_type])

    facade.write_tile_sources(
        output_root=None if in_place else output_dir,
        tile_types=tile_types,
        generate_rtl=generate_rtl,
    )
    exported = _load_demo_opt_facade(output_dir)

    assert facade.project_dir == project_dir
    for tile_type in tile_types:
        assert deleted_keys[tile_type] not in exported.matrix_resources(tile_type)
        assert (output_dir / "Tile" / tile_type / f"{tile_type}.csv").exists()
        assert (
            output_dir / "Tile" / tile_type / f"{tile_type}_switch_matrix.list"
        ).exists()
        assert (
            output_dir / "Tile" / tile_type / f"{tile_type}_switch_matrix.csv"
        ).read_text(encoding="utf-8") != "stale artifact"

        if generate_rtl:
            assert all(
                path.exists()
                for path in _tile_generated_rtl_paths(output_dir, tile_type)
            )
            assert all(
                not path.exists()
                or path.read_text(encoding="utf-8") != "stale artifact"
                for path in output_artifact_paths[tile_type]
            )
        else:
            assert all(not path.exists() for path in output_artifact_paths[tile_type])

        if not in_place:
            for artifact_path, text in source_artifacts[tile_type].items():
                assert artifact_path.read_text(encoding="utf-8") == text


def test_fab_graph_write_tile_sources_rejects_supertile_subtile_rtl(
    tmp_path: Path,
) -> None:
    """Reject selected RTL generation for tiles inside a supertile wrapper."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    facade = _load_demo_opt_facade(project_dir)

    with pytest.raises(ValueError, match="supertile wrapper"):
        facade.write_tile_sources(
            tile_types=("DSP_top",),
            generate_rtl=True,
        )

    facade.write_tile_sources(
        tile_types=("DSP_top",),
        generate_rtl=False,
    )


@pytest.mark.parametrize("in_place", [True, False])
def test_fab_graph_write_supertile_sources_regenerates_wrapper_and_subtiles(
    tmp_path: Path,
    *,
    in_place: bool,
) -> None:
    """Write a supertile and regenerate its wrapper plus selected subtiles."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    output_dir = project_dir if in_place else tmp_path / "supertile_sources_project"
    if not in_place:
        shutil.copytree(project_dir, output_dir)
    facade = _load_demo_opt_facade(project_dir)
    supertile_type = "DSP"
    subtile_types = ("DSP_top", "DSP_bot")
    output_tile_dirs = {
        tile_type: output_dir
        / facade.tile_model(tile_type)
        .tile_dir.resolve()
        .relative_to(project_dir.resolve())
        for tile_type in subtile_types
    }
    source_tile_dirs = {
        tile_type: facade.tile_model(tile_type).tile_dir for tile_type in subtile_types
    }
    deleted_keys = {
        tile_type: facade.matrix_resources(tile_type)[0] for tile_type in subtile_types
    }
    stale_paths = [
        output_dir / "Tile" / supertile_type / f"{supertile_type}.v",
        *(
            artifact_path
            for tile_type in subtile_types
            for artifact_path in _tile_generated_artifact_paths_in_dir(
                output_tile_dirs[tile_type],
                tile_type,
            )
        ),
    ]
    required_rtl_paths = [
        output_dir / "Tile" / supertile_type / f"{supertile_type}.v",
        *(
            rtl_path
            for tile_type in subtile_types
            for rtl_path in _tile_generated_rtl_paths_in_dir(
                output_tile_dirs[tile_type], tile_type
            )
        ),
    ]
    source_artifacts = {
        source_path: source_path.read_text(encoding="utf-8")
        for source_path in [
            project_dir / "Tile" / supertile_type / f"{supertile_type}.v",
            *(
                artifact_path
                for tile_type in subtile_types
                for artifact_path in _tile_generated_artifact_paths_in_dir(
                    source_tile_dirs[tile_type],
                    tile_type,
                )
            ),
        ]
        if not in_place and source_path.exists()
    }

    for stale_path in stale_paths:
        stale_path.write_text("stale artifact", encoding="utf-8")
    for tile_type in subtile_types:
        facade.disable_matrix_resource(key=deleted_keys[tile_type])

    facade.write_supertile_sources(
        output_root=None if in_place else output_dir,
        supertile_types=(supertile_type,),
        generate_rtl=True,
    )
    exported = _load_demo_opt_facade(output_dir)

    assert (output_dir / "Tile" / supertile_type / f"{supertile_type}.csv").exists()
    assert all(path.exists() for path in required_rtl_paths)
    assert all(
        not path.exists() or path.read_text(encoding="utf-8") != "stale artifact"
        for path in stale_paths
    )
    for tile_type in subtile_types:
        assert deleted_keys[tile_type] not in exported.matrix_resources(tile_type)

    if not in_place:
        for artifact_path, text in source_artifacts.items():
            assert artifact_path.read_text(encoding="utf-8") == text


def test_fab_graph_write_project_copy_writes_metadata_from_written_files(
    tmp_path: Path,
) -> None:
    """Export a complete synthetic project and regenerate metadata from it."""
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    facade = FabGraph(_write_and_load_api(source_dir), source_dir)

    facade.delete_matrix_resource("Toy", "LONG_END0", "LOCAL_BEG0")
    facade.write_project(output_dir, generate_rtl=False)

    assert facade.project_dir == source_dir
    assert (output_dir / "fabric.csv").exists()
    assert (output_dir / "Tile" / "Toy" / "Toy.csv").exists()
    assert (output_dir / ".FABulous" / "pips.txt").exists()
    assert (output_dir / ".FABulous" / "bel.txt").exists()
    assert (output_dir / ".FABulous" / "bel.v2.txt").exists()
    assert (output_dir / ".FABulous" / "template.pcf").exists()
    assert (output_dir / ".FABulous" / "bitStreamSpec.bin").exists()
    assert (output_dir / ".FABulous" / "bitStreamSpec.csv").exists()
    assert genNextpnrModel(_parse_fabric_project(output_dir))[0] == (
        output_dir / ".FABulous" / "pips.txt"
    ).read_text(encoding="utf-8")
    assert facade.render_pips_txt() == (
        output_dir / ".FABulous" / "pips.txt"
    ).read_text(encoding="utf-8")


def test_fab_graph_write_project_exports_demo_opt_to_custom_path(
    tmp_path: Path,
) -> None:
    """Export real demo project to a custom path and regenerate all artifacts."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    output_dir = tmp_path / "exported_demo_opt"
    fab = FABulous_API(VerilogCodeGenerator())
    _set_test_project_context(project_dir)
    fab.loadFabric(project_dir / "fabric.csv")
    facade = FabGraph(fab, project_dir)
    tile_type = "LUT4AB"
    key = facade.matrix_resources(tile_type)[0]
    output_tile_dir = output_dir / "Tile" / tile_type
    stale_paths = [
        output_tile_dir / f"{tile_type}.v",
        output_tile_dir / f"{tile_type}_switch_matrix.v",
        output_tile_dir / f"{tile_type}_ConfigMem.csv",
        output_tile_dir / f"{tile_type}_ConfigMem.v",
        output_dir / ".FABulous" / "pips.txt",
    ]
    for stale_path in stale_paths:
        stale_path.parent.mkdir(parents=True, exist_ok=True)
        stale_path.write_text("stale artifact", encoding="utf-8")

    facade.disable_matrix_resource(key=key)
    facade.write_project(output_dir, generate_rtl=True)

    metadata_dir = output_dir / ".FABulous"
    generated_tile_paths = [
        output_dir / "Tile" / "DSP" / "DSP.csv",
        output_tile_dir / f"{tile_type}.csv",
        output_tile_dir / f"{tile_type}_switch_matrix.list",
        output_tile_dir / f"{tile_type}_switch_matrix.csv",
        output_tile_dir / f"{tile_type}.v",
        output_tile_dir / f"{tile_type}_switch_matrix.v",
        output_tile_dir / f"{tile_type}_ConfigMem.csv",
        output_tile_dir / f"{tile_type}_ConfigMem.v",
    ]
    metadata_paths = [
        metadata_dir / "pips.txt",
        metadata_dir / "bel.txt",
        metadata_dir / "bel.v2.txt",
        metadata_dir / "template.pcf",
        metadata_dir / "bitStreamSpec.bin",
        metadata_dir / "bitStreamSpec.csv",
    ]

    assert facade.project_dir == project_dir
    assert all(path.exists() for path in generated_tile_paths)
    assert all(path.exists() for path in metadata_paths)
    assert all(
        path.read_text(encoding="utf-8") != "stale artifact"
        for path in stale_paths
        if path.suffix != ".bin"
    )
    assert _line_set((metadata_dir / "pips.txt").read_text(encoding="utf-8")) == (
        _line_set(facade.render_pips_txt())
    )
    assert _line_set(genNextpnrModel(_parse_fabric_project(output_dir))[0]) == (
        _line_set(facade.render_pips_txt())
    )


def test_fab_graph_write_project_exports_set_switch_matrix_with_rtl(
    tmp_path: Path,
) -> None:
    """Write a project after setting a real matrix without shrinking it."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    output_dir = tmp_path / "exported_set_switch_matrix"
    facade = _load_demo_opt_facade(project_dir)
    tile_type = "LUT4AB"
    switch_matrix = facade.switch_matrix(tile_type)
    matrix = [list(row) for row in switch_matrix.matrix]
    changed_cells: list[tuple[str, str, float]] = []

    for row_index, row_name in enumerate(switch_matrix.rows):
        for column_index, column_name in enumerate(switch_matrix.columns):
            if matrix[row_index][column_index] == 0.0:
                continue
            new_delay = matrix[row_index][column_index] + 1.25
            matrix[row_index][column_index] = new_delay
            changed_cells.append((row_name, column_name, new_delay))
            if len(changed_cells) == 10:
                break
        if len(changed_cells) == 10:
            break

    assert len(changed_cells) == 10
    facade.set_switch_matrix(
        tile_type,
        switch_matrix.columns,
        switch_matrix.rows,
        matrix,
    )
    updated_matrix = facade.switch_matrix(tile_type)
    for row_name, column_name, expected_delay in changed_cells:
        assert _switch_matrix_value(updated_matrix, row_name, column_name) == (
            expected_delay
        )

    facade.write_project(output_dir, generate_rtl=True)

    output_tile_dir = output_dir / "Tile" / tile_type
    matrix_csv = output_tile_dir / f"{tile_type}_switch_matrix.csv"
    parsed_csv = parseMatrix(matrix_csv, tile_type)
    csv_pairs = {
        (source_name, destination_name)
        for source_name, destination_names in parsed_csv.items()
        for destination_name in destination_names
    }

    assert (output_tile_dir / f"{tile_type}.v").exists()
    assert (output_tile_dir / f"{tile_type}_switch_matrix.v").exists()
    assert (output_tile_dir / f"{tile_type}_ConfigMem.csv").exists()
    assert _switch_matrix_active_pairs(updated_matrix) == csv_pairs


def test_fab_graph_write_project_regenerates_demo_opt_rtl(
    tmp_path: Path,
) -> None:
    """Commit a real project graph and regenerate FABulous tile artifacts."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    fab = FABulous_API(VerilogCodeGenerator())
    _set_test_project_context(project_dir)
    fab.loadFabric(project_dir / "fabric.csv")
    facade = FabGraph(fab, project_dir)
    tile_type = "LUT4AB"
    key = facade.matrix_resources(tile_type)[0]
    tile_dir = project_dir / "Tile" / tile_type
    stale_paths = [
        tile_dir / f"{tile_type}.v",
        tile_dir / f"{tile_type}_switch_matrix.v",
        tile_dir / f"{tile_type}_ConfigMem.csv",
        tile_dir / f"{tile_type}_ConfigMem.v",
    ]
    for stale_path in stale_paths:
        stale_path.write_text("stale artifact", encoding="utf-8")

    facade.disable_matrix_resource(key=key)
    facade.write_project(generate_rtl=True)

    assert all(path.exists() for path in stale_paths)
    assert all(
        path.read_text(encoding="utf-8") != "stale artifact" for path in stale_paths
    )
    assert _line_set((project_dir / ".FABulous" / "pips.txt").read_text()) == (
        _line_set(facade.render_pips_txt())
    )
