# Only real world on project tests.
"""Real-world project stress tests for the fast public ``FabGraph`` API."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from random import Random
from typing import TYPE_CHECKING

import pytest  # noqa: DEP004 - test-only dependency

import fabulous.fabulous_settings as fabulous_settings
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core import FabGraph
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingConfigBits,
    RoutingModelText,
    RoutingPipKind,
    RoutingResourceKey,
)
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabulous_api import FABulous_API

if TYPE_CHECKING:
    from collections.abc import Iterable


def test_demo_opt_fast_api_sweep_all_tile_types(tmp_path: Path) -> None:
    """Exercise public fast graph edits and queries across every demo tile type."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    output_project = tmp_path / "api_sweep_export"
    graph = _load_fab_graph(source_project)
    tile_types = graph.tile_types()
    placed_tile_types = set(graph.placed_tile_types())
    operations_per_api = 10

    assert tile_types
    for tile_type in tile_types:
        prefix = _safe_name_fragment(tile_type)

        for _index in range(operations_per_api):
            assert graph.tile_types(where=lambda name, t=tile_type: name == t) == [
                tile_type
            ]
            assert graph.tile_model(tile_type).tile_type == tile_type
            assert (
                graph.external_resources(
                    tile_type,
                    where=lambda key, t=tile_type: key.tile_type == t,
                )
                is not None
            )
            assert (
                graph.matrix_resources(
                    tile_type,
                    where=lambda key, t=tile_type: key.tile_type == t,
                )
                is not None
            )
            assert graph.matrix_sources(tile_type, where=lambda name: bool(name))
            assert graph.matrix_sinks(tile_type, where=lambda name: bool(name))

        added_external = _add_synthetic_external_resources(
            graph,
            tile_type,
            prefix=f"{prefix}_ADD_EXT",
            count=operations_per_api,
            wire_count=1,
        )
        assert all(key in graph.external_resources(tile_type) for key in added_external)

        resize_external = _add_synthetic_external_resources(
            graph,
            tile_type,
            prefix=f"{prefix}_RESIZE_EXT",
            count=operations_per_api,
            wire_count=4,
        )
        for key in resize_external:
            graph.resize_external_resource(key=key, new_wire_count=3)
            resized_key = graph.routing_graph.external_resource_key(
                tile_type,
                Direction.JUMP,
                key.source_name,
                key.x_offset,
                key.y_offset,
                key.destination_name,
                3,
            )
            assert resized_key in graph.external_resources(tile_type)
            assert key not in graph.external_resources(tile_type)

        matrix_keys = _add_synthetic_matrix_resources(
            graph,
            tile_type,
            prefix=f"{prefix}_ADD_MATRIX",
            count=operations_per_api,
        )
        assert all(key in graph.matrix_resources(tile_type) for key in matrix_keys)

        for key in matrix_keys:
            graph.disable_matrix_resource(key=key)
        assert all(key not in graph.matrix_resources(tile_type) for key in matrix_keys)
        for key in matrix_keys:
            graph.enable_matrix_resource(key=key)
        assert all(key in graph.matrix_resources(tile_type) for key in matrix_keys)

        for key in matrix_keys:
            graph.delete_matrix_resource(key=key)
        assert all(key not in graph.matrix_resources(tile_type) for key in matrix_keys)
        for key in matrix_keys:
            graph.restore_matrix_resource(key=key)
        assert all(key in graph.matrix_resources(tile_type) for key in matrix_keys)

        toggled_external = _add_synthetic_external_resources(
            graph,
            tile_type,
            prefix=f"{prefix}_TOGGLE_EXT",
            count=operations_per_api,
            wire_count=1,
        )
        for key in toggled_external:
            graph.disable_external_resource(key=key)
        assert all(
            key not in graph.external_resources(tile_type) for key in toggled_external
        )
        for key in toggled_external:
            graph.restore_external_resource(key=key)
        assert all(
            key in graph.external_resources(tile_type) for key in toggled_external
        )

        rows = _add_synthetic_matrix_row_inputs(
            graph,
            tile_type,
            prefix=f"{prefix}_ROWS",
            count=operations_per_api,
        )
        graph.add_matrix_rows(tile_type, rows)
        assert all(
            graph.routing_graph.matrix_resource_key(
                tile_type,
                source_name,
                destination_name,
            )
            in graph.matrix_resources(tile_type)
            for source_name, destination_name, _delay in rows
        )

        pips_for_tile_type = graph.active_pips(
            where=lambda pip, t=tile_type: pip.tile_type == t
        )
        if tile_type in placed_tile_types:
            assert pips_for_tile_type
        else:
            assert not pips_for_tile_type

    graph.routing_graph.validate()
    assert graph.stats().active_pips > 0
    graph.write_project(output_project, generate_rtl=True)
    _assert_export_matches_graph(output_project, graph)
    assert any((output_project / "Tile").glob("**/*.v"))


def test_demo_opt_standalone_tile_edits_do_not_emit_routing_metadata(
    tmp_path: Path,
) -> None:
    """Edit an unused tile definition without adding concrete routing metadata."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    output_project = tmp_path / "standalone_tile_export"
    pips_snapshot = tmp_path / "standalone_tile_pips.txt"
    graph = _load_fab_graph(source_project)
    standalone_types = graph.standalone_tile_types()

    if not standalone_types:
        pytest.skip("demo_opt has no standalone tile declarations")

    tile_type = standalone_types[0]
    unique_standalone_bels = _unique_standalone_bel_modules(graph, tile_type)
    baseline_pips = graph.render_pips_txt()
    initial_counts = graph.get_resource_counts(tile_type)

    assert tile_type in graph.tile_types()
    assert tile_type not in graph.placed_tile_types()
    assert graph.tile_model(tile_type).tile_type == tile_type
    assert graph.switch_matrix(tile_type).tile_type == tile_type
    assert graph.matrix_sources(tile_type)
    assert graph.matrix_sinks(tile_type)
    assert initial_counts.total_active > 0
    assert not graph.active_pips(where=lambda pip, t=tile_type: pip.tile_type == t)

    added_external = _add_synthetic_external_resources(
        graph,
        tile_type,
        prefix=f"STANDALONE_{_safe_name_fragment(tile_type)}_EXT",
        count=1,
        wire_count=2,
    )[0]
    graph.resize_external_resource(key=added_external, new_wire_count=3)
    resized_external = graph.routing_graph.external_resource_key(
        tile_type,
        Direction.JUMP,
        added_external.source_name,
        added_external.x_offset,
        added_external.y_offset,
        added_external.destination_name,
        3,
    )
    graph.disable_external_resource(key=resized_external)
    assert resized_external not in graph.external_resources(tile_type)
    graph.enable_external_resource(key=resized_external)
    assert resized_external in graph.external_resources(tile_type)
    graph.delete_external_resource(key=resized_external)
    assert resized_external not in graph.external_resources(tile_type)
    graph.restore_external_resource(key=resized_external)
    assert resized_external in graph.external_resources(tile_type)

    matrix_key = _add_synthetic_matrix_resources(
        graph,
        tile_type,
        prefix=f"STANDALONE_{_safe_name_fragment(tile_type)}_MATRIX",
        count=1,
    )[0]
    assert matrix_key in graph.matrix_resources(tile_type)
    graph.disable_matrix_resource(key=matrix_key)
    assert matrix_key not in graph.matrix_resources(tile_type)
    graph.enable_matrix_resource(key=matrix_key)
    assert matrix_key in graph.matrix_resources(tile_type)
    graph.delete_matrix_resource(key=matrix_key)
    assert matrix_key not in graph.matrix_resources(tile_type)
    graph.restore_matrix_resource(key=matrix_key)
    assert matrix_key in graph.matrix_resources(tile_type)

    assert (
        graph.get_resource_counts(tile_type).total_active > initial_counts.total_active
    )
    assert graph.render_pips_txt() == baseline_pips
    graph.write_pips_txt(pips_snapshot)
    assert pips_snapshot.read_text(encoding="utf-8") == baseline_pips

    graph.write_project(output_project, generate_rtl=True)

    assert _line_set((output_project / ".FABulous" / "pips.txt").read_text()) == (
        _line_set(baseline_pips)
    )
    _assert_export_matches_graph(output_project, graph)
    _assert_standalone_tile_absent_from_routing_metadata(
        output_project,
        tile_type,
        unique_standalone_bels,
    )
    assert (output_project / "Tile" / tile_type / f"{tile_type}.v").exists()


def test_demo_opt_mixed_batch_edits_export_about_ten_percent_smaller(
    tmp_path: Path,
) -> None:
    """Mix internal/external add, resize, and delete batches on real demo_opt."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    output_project = tmp_path / "mixed_ten_percent"
    graph = _load_fab_graph(source_project)
    tile_type = "LUT4AB"
    active_before = graph.stats().active_pips

    add_entries = _missing_matrix_triplets(graph, tile_type, limit=16, seed=11)
    graph.add_matrix_rows(tile_type, add_entries)
    added_pairs = {(source, sink) for source, sink, _delay in add_entries}
    active_pairs_after_add = {
        (key.source_name, key.destination_name)
        for key in graph.matrix_resources(tile_type)
    }
    active_after_add = graph.stats().active_pips
    resize_keys = graph.external_resources(
        tile_type,
        where=lambda key: key.wire_count is not None and key.wire_count > 2,
    )[:8]
    for key in resize_keys:
        graph.resize_external_resource(
            key=key,
            new_wire_count=key.wire_count - 1,
        )
    active_after_resize = graph.stats().active_pips
    target_active = active_before * 9 // 10
    delete_batches = _delete_matrix_until_target(
        graph,
        tile_type,
        target_active,
        batch_size=9,
        seed=17,
    )

    graph.write_project(output_project, generate_rtl=False)
    exported = _load_fab_graph(output_project)
    removal_fraction = 1.0 - (graph.stats().active_pips / active_before)

    assert added_pairs <= active_pairs_after_add
    assert active_after_add > active_before
    assert active_after_resize < active_after_add
    assert delete_batches > 1
    assert 0.09 <= removal_fraction <= 0.12
    _assert_export_matches_graph(output_project, graph)
    assert exported.stats().active_pips == graph.stats().active_pips


def test_demo_opt_matrix_batch_add_and_overwrite_empty_matrix(
    tmp_path: Path,
) -> None:
    """Add matrix resources in a batch, then overwrite the matrix with empty."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    output_project = tmp_path / "empty_matrix"
    graph = _load_fab_graph(source_project)
    tile_type = "LUT4AB"
    external_before = len(graph.external_resources(tile_type))

    entries = _missing_matrix_triplets(graph, tile_type, limit=8, seed=23)
    active_before = graph.stats().active_pips
    graph.add_matrix_rows(tile_type, entries)
    active_after_add = graph.stats().active_pips
    added_pairs = {(source, sink) for source, sink, _delay in entries}
    active_pairs = {
        (key.source_name, key.destination_name)
        for key in graph.matrix_resources(tile_type)
    }

    graph.add_matrix_rows(tile_type, [], overwrite=True)
    active_after_overwrite = graph.stats().active_pips

    assert added_pairs <= active_pairs
    assert active_after_add > active_before
    assert active_after_overwrite < active_after_add
    assert graph.matrix_resources(tile_type) == []
    assert graph.external_resources(tile_type)
    assert len(graph.external_resources(tile_type)) == external_before
    assert not graph.active_pips(
        where=lambda pip: (
            pip.tile_type == tile_type and pip.kind is RoutingPipKind.INTERNAL_MATRIX
        ),
    )

    graph.write_project(output_project, generate_rtl=False)
    exported = _load_fab_graph(output_project)

    assert exported.matrix_resources(tile_type) == []
    assert len(exported.external_resources(tile_type)) == external_before
    _assert_export_matches_graph(output_project, graph)


def test_demo_opt_delete_all_external_resources_for_one_tile_type(
    tmp_path: Path,
) -> None:
    """Delete every external routing resource for one real tile type."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    output_project = tmp_path / "no_lut4ab_external"
    graph = _load_fab_graph(source_project)
    tile_type = "LUT4AB"
    external_keys = graph.external_resources(tile_type)

    active_before = graph.stats().active_pips
    for key in external_keys:
        graph.delete_external_resource(key=key)
    active_after_delete = graph.stats().active_pips

    assert external_keys
    assert active_after_delete < active_before
    assert graph.external_resources(tile_type) == []
    assert not graph.active_pips(
        where=lambda pip: (
            pip.tile_type == tile_type and pip.kind is RoutingPipKind.EXTERNAL_WIRE
        ),
    )
    graph.write_project(output_project, generate_rtl=False)
    exported = _load_fab_graph(output_project)

    assert not exported.active_pips(
        where=lambda pip: (
            pip.tile_type == tile_type and pip.kind is RoutingPipKind.EXTERNAL_WIRE
        ),
    )
    _assert_export_matches_graph(output_project, graph)


def test_demo_opt_query_driven_stress_export_thirty_percent_smaller(
    tmp_path: Path,
) -> None:
    """Use query results and predicates to drive a larger 30 percent shrink."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    output_project = tmp_path / "query_thirty_percent"
    graph = _load_fab_graph(source_project)
    tile_type = "LUT4AB"
    active_before = graph.stats().active_pips

    assert tile_type in graph.tile_types(where=lambda name: name.startswith("LUT"))
    wide_external = graph.external_resources(
        tile_type,
        where=lambda key: (
            key.wire_count is not None
            and key.wire_count >= 4
            and key.direction is not None
        ),
    )
    matrix_sources = graph.matrix_sources(
        tile_type,
        where=lambda name: name.endswith("0"),
    )
    matrix_sinks = graph.matrix_sinks(
        tile_type,
        where=lambda name: name.startswith(("LA_", "LB_", "LC_", "LD_")),
    )

    assert wide_external
    assert matrix_sources
    assert matrix_sinks

    graph.add_external_resource(
        tile_type,
        Direction.JUMP,
        "QSTRESS_BEG",
        0,
        0,
        "QSTRESS_END",
        2,
    )
    added_key = graph.routing_graph.external_resource_key(
        tile_type,
        Direction.JUMP,
        "QSTRESS_BEG",
        0,
        0,
        "QSTRESS_END",
        2,
    )
    graph.add_matrix_resource(tile_type, "QSTRESS_END0", matrix_sinks[0])
    for key in wide_external[:10]:
        graph.resize_external_resource(
            key=key,
            new_wire_count=max(1, key.wire_count - 2),
        )
    graph.delete_external_resource(key=added_key)

    queried_matrix = graph.matrix_resources(
        tile_type,
        where=lambda key: (
            key.source_name in set(matrix_sources)
            or key.destination_name in set(matrix_sinks)
        ),
    )
    assert queried_matrix

    target_active = active_before * 7 // 10
    delete_batches = _delete_matrix_until_target(
        graph,
        tile_type,
        target_active,
        batch_size=13,
        seed=41,
        preferred_keys=queried_matrix,
    )
    disabled_lut_pips = graph.disabled_pips(
        where=lambda pip: pip.tile_type == tile_type,
    )
    removal_fraction = 1.0 - (graph.stats().active_pips / active_before)

    assert delete_batches > 1
    assert disabled_lut_pips
    assert 0.29 <= removal_fraction <= 0.32
    graph.write_project(output_project, generate_rtl=False)
    exported = _load_fab_graph(output_project)

    assert exported.stats().active_pips == graph.stats().active_pips
    _assert_export_matches_graph(output_project, graph)


def test_demo_opt_config_bits_match_generated_rtl_after_tile_mutations(
    tmp_path: Path,
) -> None:
    """Compare queried config bits to generated RTL after real tile mutations."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    output_project = tmp_path / "config_bits_rtl"
    graph = _load_fab_graph(source_project)
    tile_types = ("LUT4AB", "N_term_single2")
    resources_before = {
        tile_type: _active_resource_count(graph, tile_type) for tile_type in tile_types
    }

    for seed, tile_type in enumerate(tile_types, start=101):
        _mutate_tile_resources_for_config_bit_export(
            graph,
            tile_type,
            seed=seed,
        )

    resources_after = {
        tile_type: _active_resource_count(graph, tile_type) for tile_type in tile_types
    }
    expected_bits = {
        tile_type: graph.get_config_bits(tile_type) for tile_type in tile_types
    }

    for tile_type in tile_types:
        reduction = 1.0 - (resources_after[tile_type] / resources_before[tile_type])

        assert 0.04 <= reduction <= 0.06
        assert expected_bits[tile_type].matrix_config_bits > 0

    graph.write_project(output_project, generate_rtl=True)

    for tile_type in tile_types:
        bits = expected_bits[tile_type]

        assert _read_switch_matrix_config_bits(output_project, tile_type) == (
            bits.matrix_config_bits
        )
        assert _read_tile_no_config_bits(output_project, tile_type) == (
            bits.total_config_bits
        )

    exported = _load_fab_graph(output_project)
    for tile_type in tile_types:
        assert exported.get_config_bits(tile_type) == expected_bits[tile_type]


def test_demo_opt_oversized_lut4ab_config_bits_fail_rtl_generation(
    tmp_path: Path,
) -> None:
    """Confirm FABulous rejects oversized config bits during RTL generation."""
    tile_type = "LUT4AB"
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    graph = _load_fab_graph(source_project)
    oversized_bits = _inflate_switch_matrix_past_fabric_capacity(graph, tile_type)
    tile_dir = source_project / "Tile" / tile_type
    stale_switch_matrix_rtl = tile_dir / f"{tile_type}_switch_matrix.v"

    stale_switch_matrix_rtl.write_text("// stale switch matrix rtl\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exceeds fabric capacity"):
        graph.write_tile_sources(tile_types=(tile_type,), generate_rtl=True)

    assert (tile_dir / f"{tile_type}.csv").exists()
    assert (tile_dir / f"{tile_type}_switch_matrix.list").exists()
    assert (tile_dir / f"{tile_type}_switch_matrix.csv").exists()
    switch_matrix_rtl = stale_switch_matrix_rtl.read_text(encoding="utf-8")
    assert "stale switch matrix rtl" not in switch_matrix_rtl
    assert (
        f"NumberOfConfigBits: {oversized_bits.matrix_config_bits}" in switch_matrix_rtl
    )
    assert not (tile_dir / f"{tile_type}_ConfigMem.csv").exists()

    project_source = _copy_demo_opt_project_or_skip(tmp_path / "project_write")
    project_graph = _load_fab_graph(project_source)
    project_bits = _inflate_switch_matrix_past_fabric_capacity(
        project_graph,
        tile_type,
    )
    output_project = tmp_path / "oversized_project"

    with pytest.raises(ValueError, match="exceeds fabric capacity"):
        project_graph.write_project(output_project, generate_rtl=True)

    output_tile_dir = output_project / "Tile" / tile_type
    assert (output_tile_dir / f"{tile_type}.csv").exists()
    assert (output_tile_dir / f"{tile_type}_switch_matrix.list").exists()
    assert (output_tile_dir / f"{tile_type}_switch_matrix.csv").exists()
    output_switch_matrix_rtl = (
        output_tile_dir / f"{tile_type}_switch_matrix.v"
    ).read_text(encoding="utf-8")
    assert (
        f"NumberOfConfigBits: {project_bits.matrix_config_bits}"
        in output_switch_matrix_rtl
    )
    assert not (output_project / ".FABulous").exists()


def test_demo_opt_written_routing_model_matches_fabulous_generator(
    tmp_path: Path,
) -> None:
    """Write demo_opt routing metadata and compare it to FABulous generation."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    output_dir = tmp_path / "routing_model"
    graph = _load_fab_graph(source_project)
    expected_pips, expected_bel, expected_bel_v2, expected_pcf = (
        graph.fab.genRoutingModel()
    )

    graph.write_routing_model(output_dir)

    assert (output_dir / "pips.txt").read_text(encoding="utf-8") == expected_pips
    assert (output_dir / "bel.txt").read_text(encoding="utf-8") == expected_bel
    assert (output_dir / "bel.v2.txt").read_text(encoding="utf-8") == expected_bel_v2
    assert (output_dir / "template.pcf").read_text(encoding="utf-8") == expected_pcf


def test_demo_opt_resized_fabric_writes_larger_routing_model(
    tmp_path: Path,
) -> None:
    """Resize real demo_opt placement and check routing metadata grows cleanly."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    baseline_dir = tmp_path / "routing_model_before_resize"
    resized_dir = tmp_path / "routing_model_after_resize"
    graph = _load_fab_graph(source_project)
    baseline_model = graph.render_routing_model()
    baseline_pcf_coords = _pcf_tile_coordinates(baseline_model.template_pcf)

    if not baseline_pcf_coords:
        pytest.skip("demo_opt routing model has no auto-PCF coordinates to duplicate")

    column_index, row_index = baseline_pcf_coords[0]
    row_copies = 10
    column_copies = 20
    baseline_rows = graph.routing_graph.rows
    baseline_columns = graph.routing_graph.columns
    baseline_placements = dict(graph.routing_graph.tile_types_by_xy)
    expected_placements = _expected_placement_count_after_resize(
        baseline_placements,
        row_index=row_index,
        row_copies=row_copies,
        column_index=column_index,
        column_copies=column_copies,
    )
    expected_pcf_lines = _expected_feature_lines_after_resize(
        baseline_pcf_coords,
        row_index=row_index,
        row_copies=row_copies,
        column_index=column_index,
        column_copies=column_copies,
    )

    graph.write_routing_model(baseline_dir)
    graph.resize_fabric(
        copy_row_after=(row_index, row_copies),
        copy_column_after=(column_index, column_copies),
    )
    graph.write_routing_model(resized_dir)
    resized_model = graph.render_routing_model()

    assert len(graph.routing_graph.tile_types_by_xy) == expected_placements
    assert graph.routing_graph.rows == baseline_rows + row_copies
    assert graph.routing_graph.columns == baseline_columns + column_copies
    assert (
        _count_prefixed_lines(
            resized_model.pips,
            "#Tile-internal pips on tile ",
        )
        == expected_placements
    )
    assert (
        _count_prefixed_lines(
            resized_model.pips,
            "#Tile-external pips on tile ",
        )
        == expected_placements
    )
    assert _count_prefixed_lines(resized_model.bel, "#Tile_X") == expected_placements
    assert _count_prefixed_lines(resized_model.bel_v2, "#Tile_X") == expected_placements
    assert len(resized_model.template_pcf.splitlines()) == expected_pcf_lines
    assert len(resized_model.pips.splitlines()) > len(baseline_model.pips.splitlines())
    assert len(resized_model.bel.splitlines()) > len(baseline_model.bel.splitlines())
    assert len(resized_model.bel_v2.splitlines()) > len(
        baseline_model.bel_v2.splitlines()
    )
    assert len(resized_model.template_pcf.splitlines()) > len(
        baseline_model.template_pcf.splitlines()
    )
    assert _active_pip_line_count(resized_model.pips) == graph.stats().active_pips

    _assert_routing_model_files_match(baseline_dir, baseline_model)
    _assert_routing_model_files_match(resized_dir, resized_model)
    assert (resized_dir / "pips.txt").stat().st_size > (
        baseline_dir / "pips.txt"
    ).stat().st_size
    assert (resized_dir / "bel.txt").stat().st_size > (
        baseline_dir / "bel.txt"
    ).stat().st_size
    assert (resized_dir / "bel.v2.txt").stat().st_size > (
        baseline_dir / "bel.v2.txt"
    ).stat().st_size
    assert (resized_dir / "template.pcf").stat().st_size > (
        baseline_dir / "template.pcf"
    ).stat().st_size


def test_demo_opt_resize_remove_and_restore_lut4ab_column_routing_model(
    tmp_path: Path,
) -> None:
    """Remove and restore a real LUT4AB column without changing metadata text."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    baseline_dir = tmp_path / "demo_opt_lut4ab_column_baseline"
    restored_dir = tmp_path / "demo_opt_lut4ab_column_restored"
    graph = _load_fab_graph(source_project)
    lut4ab_column = _first_column_with_tile_type(graph, "LUT4AB")
    baseline_model = graph.render_routing_model()

    graph.write_routing_model(baseline_dir)
    graph.resize_fabric(copy_column_after=(lut4ab_column, 1))
    graph.resize_fabric(remove_columns=(lut4ab_column,))
    restored_model = graph.render_routing_model()
    graph.write_routing_model(restored_dir)

    assert restored_model == baseline_model
    _assert_routing_model_files_match(baseline_dir, baseline_model)
    _assert_routing_model_files_match(restored_dir, baseline_model)


def test_demo_opt_resize_removals_shrink_routing_model(
    tmp_path: Path,
) -> None:
    """Remove real demo_opt rows/columns and check routing metadata shrinks."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    baseline_graph = _load_fab_graph(source_project)
    baseline_model = baseline_graph.render_routing_model()
    remove_io_column = _load_fab_graph(source_project)

    remove_io_column.resize_fabric(remove_columns=(0,))
    no_west_io_model = remove_io_column.render_routing_model()

    assert len(no_west_io_model.template_pcf.splitlines()) < len(
        baseline_model.template_pcf.splitlines()
    )
    assert len(no_west_io_model.pips.splitlines()) < len(
        baseline_model.pips.splitlines()
    )
    assert len(no_west_io_model.bel.splitlines()) < len(baseline_model.bel.splitlines())
    assert len(no_west_io_model.bel_v2.splitlines()) < len(
        baseline_model.bel_v2.splitlines()
    )

    mixed_resize = _load_fab_graph(source_project)
    mixed_dir = tmp_path / "demo_opt_mixed_resize"
    mixed_resize.resize_fabric(
        remove_rows=(1, 2),
        remove_columns=(0, 1),
        copy_row_after=(0, 1),
        copy_column_after=(1, 1),
    )
    mixed_model = mixed_resize.render_routing_model()
    mixed_resize.write_routing_model(mixed_dir)

    assert len(mixed_model.pips.splitlines()) < len(baseline_model.pips.splitlines())
    assert len(mixed_model.bel.splitlines()) < len(baseline_model.bel.splitlines())
    assert len(mixed_model.bel_v2.splitlines()) < len(
        baseline_model.bel_v2.splitlines()
    )
    assert _active_pip_line_count(mixed_model.pips) == mixed_resize.stats().active_pips
    _assert_routing_model_files_match(mixed_dir, mixed_model)


def test_demo_opt_remove_external_resource_tracks_compacts_real_vectors(
    tmp_path: Path,
) -> None:
    """Remove first, middle, and final tracks from real demo_opt vectors."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    graph = _load_fab_graph(source_project)
    tile_type = "LUT4AB"
    baseline_model = graph.render_routing_model()
    candidates: list[RoutingResourceKey] = []
    seen_bases: set[tuple[str, str]] = set()
    for key in graph.external_resources(
        tile_type,
        where=lambda key: (
            key.wire_count is not None
            and key.wire_count > 2
            and key.source_name != "NULL"
            and key.destination_name != "NULL"
        ),
    ):
        base_pair = (key.source_name, key.destination_name)
        if base_pair in seen_bases:
            continue
        seen_bases.add(base_pair)
        candidates.append(key)
    if len(candidates) < 6:
        pytest.skip("demo_opt has too few removable LUT4AB external vectors")

    removed: list[RoutingResourceKey] = []
    for index, key in enumerate(candidates[:6]):
        assert key.wire_count is not None
        track_index = (0, key.wire_count // 2, key.wire_count - 1)[index % 3]
        pips_before = graph.routing_graph.by_resource_key(key)

        compact_key = graph.remove_external_resource_track(
            key=key,
            track_index=track_index,
        )

        assert compact_key.wire_count == key.wire_count - 1
        assert key not in graph.external_resources(tile_type)
        assert compact_key in graph.external_resources(tile_type)
        assert graph.routing_graph.by_resource_key(key) == ()
        assert len(graph.routing_graph.by_resource_key(compact_key)) < len(pips_before)
        removed.append(compact_key)

    compact_model = graph.render_routing_model()
    output_dir = tmp_path / "demo_opt_external_track_remove"
    graph.write_routing_model(output_dir)

    assert removed
    assert compact_model.bel == baseline_model.bel
    assert compact_model.bel_v2 == baseline_model.bel_v2
    assert compact_model.template_pcf == baseline_model.template_pcf
    assert len(compact_model.pips.splitlines()) < len(baseline_model.pips.splitlines())
    assert _active_pip_line_count(compact_model.pips) == graph.stats().active_pips
    graph.routing_graph.validate()
    _assert_routing_model_files_match(output_dir, compact_model)


def test_demo_opt_reset_fabric_layout_restores_routing_model_files(
    tmp_path: Path,
) -> None:
    """Resize demo_opt, reset layout, and compare routing metadata to baseline."""
    source_project = _copy_demo_opt_project_or_skip(tmp_path)
    baseline_dir = tmp_path / "demo_opt_reset_baseline"
    reset_dir = tmp_path / "demo_opt_reset_restored"
    graph = _load_fab_graph(source_project)
    baseline_model = graph.render_routing_model()

    graph.write_routing_model(baseline_dir)
    graph.resize_fabric(
        remove_rows=(1,),
        remove_columns=(0,),
        copy_row_after=(0, 2),
        copy_column_after=(1, 3),
    )
    assert graph.render_routing_model() != baseline_model

    graph.reset_fabric_layout()
    reset_model = graph.render_routing_model()
    graph.write_routing_model(reset_dir)

    assert reset_model == baseline_model
    _assert_routing_model_files_match(baseline_dir, baseline_model)
    _assert_routing_model_files_match(reset_dir, baseline_model)


def _copy_demo_opt_project_or_skip(tmp_path: Path) -> Path:
    """Copy ``demo_opt`` into the test temp directory.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.

    Returns
    -------
    Path
        Copied FABulous project directory.
    """
    source_project = Path("demo_opt").resolve()
    if not source_project.exists():
        pytest.skip("demo_opt project is not available")
    if shutil.which("yosys") is None:
        pytest.skip("Yosys is required to parse demo_opt BEL files")

    project_dir = tmp_path / "demo_opt"
    shutil.copytree(source_project, project_dir)
    return project_dir


def _load_fab_graph(project_dir: Path) -> FabGraph:
    """Load a FABulous project and return the public graph facade.

    Parameters
    ----------
    project_dir : Path
        FABulous project directory.

    Returns
    -------
    FabGraph
        Loaded public graph facade.
    """
    fabulous_settings._context_instance = (  # noqa: SLF001
        fabulous_settings.FABulousSettings.model_construct(
            proj_dir=project_dir,
            nix_shell=None,
        )
    )
    fab = FABulous_API(VerilogCodeGenerator())
    fab.loadFabric(project_dir / "fabric.csv")
    return FabGraph(fab, project_dir)


def _first_column_with_tile_type(graph: FabGraph, tile_type: str) -> int:
    """Return the first placed column containing a tile type.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type to search for.

    Returns
    -------
    int
        First X coordinate containing ``tile_type``.

    Raises
    ------
    AssertionError
        If the tile type has no placed instance.
    """
    columns = sorted(
        x
        for (x, _y), placed_tile_type in graph.routing_graph.tile_types_by_xy.items()
        if placed_tile_type == tile_type
    )
    if not columns:
        raise AssertionError(f"{tile_type} has no placed column")
    return columns[0]


def _safe_name_fragment(tile_type: str) -> str:
    """Return a Verilog-style name fragment for synthetic test wires.

    Parameters
    ----------
    tile_type : str
        Tile type name.

    Returns
    -------
    str
        Identifier-safe name fragment.
    """
    return "".join(character if character.isalnum() else "_" for character in tile_type)


def _add_synthetic_external_resources(
    graph: FabGraph,
    tile_type: str,
    *,
    prefix: str,
    count: int,
    wire_count: int,
) -> list[RoutingResourceKey]:
    """Add synthetic external JUMP resources and return their keys.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type to edit.
    prefix : str
        Unique wire-name prefix.
    count : int
        Number of resources to add.
    wire_count : int
        Wire count for each resource.

    Returns
    -------
    list[RoutingResourceKey]
        Added resource keys.
    """
    keys: list[RoutingResourceKey] = []
    for index in range(count):
        source_name = f"FG_{prefix}_BEG_{index}"
        destination_name = f"FG_{prefix}_END_{index}"
        graph.add_external_resource(
            tile_type,
            Direction.JUMP,
            source_name,
            0,
            0,
            destination_name,
            wire_count,
        )
        keys.append(
            graph.routing_graph.external_resource_key(
                tile_type,
                Direction.JUMP,
                source_name,
                0,
                0,
                destination_name,
                wire_count,
            )
        )
    return keys


def _add_synthetic_matrix_resources(
    graph: FabGraph,
    tile_type: str,
    *,
    prefix: str,
    count: int,
) -> list[RoutingResourceKey]:
    """Add synthetic matrix resources backed by synthetic external wires.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type to edit.
    prefix : str
        Unique wire-name prefix.
    count : int
        Number of matrix resources to add.

    Returns
    -------
    list[RoutingResourceKey]
        Added matrix resource keys.
    """
    rows = _add_synthetic_matrix_row_inputs(
        graph,
        tile_type,
        prefix=prefix,
        count=count,
    )
    keys: list[RoutingResourceKey] = []
    for source_name, destination_name, delay in rows:
        graph.add_matrix_resource(
            tile_type,
            source_name,
            destination_name,
            delay=delay,
        )
        keys.append(
            graph.routing_graph.matrix_resource_key(
                tile_type,
                source_name,
                destination_name,
            )
        )
    return keys


def _add_synthetic_matrix_row_inputs(
    graph: FabGraph,
    tile_type: str,
    *,
    prefix: str,
    count: int,
) -> list[tuple[str, str, float]]:
    """Declare synthetic wires and return legal matrix row triplets.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type to edit.
    prefix : str
        Unique wire-name prefix.
    count : int
        Number of row triplets to return.

    Returns
    -------
    list[tuple[str, str, float]]
        Matrix ``(source, destination, delay)`` triplets.
    """
    rows: list[tuple[str, str, float]] = []
    for index in range(count):
        source_base = f"FG_{prefix}_SRC_{index}"
        destination_base = f"FG_{prefix}_DST_{index}"
        graph.add_external_resource(
            tile_type,
            Direction.JUMP,
            source_base,
            0,
            0,
            destination_base,
            1,
        )
        rows.append((f"{destination_base}0", f"{source_base}0", 8.0))
    return rows


def _assert_export_matches_graph(project_dir: Path, graph: FabGraph) -> None:
    """Check exported metadata and reparsed project match the source graph.

    Parameters
    ----------
    project_dir : Path
        Exported FABulous project directory.
    graph : FabGraph
        Graph that produced the export.
    """
    pips_path = project_dir / ".FABulous" / "pips.txt"
    exported_graph = _load_fab_graph(project_dir)

    assert pips_path.exists()
    assert _line_set(pips_path.read_text(encoding="utf-8")) == _line_set(
        graph.render_pips_txt()
    )
    assert _line_set(exported_graph.render_pips_txt()) == _line_set(
        graph.render_pips_txt()
    )


def _assert_routing_model_files_match(
    output_dir: Path,
    model: RoutingModelText,
) -> None:
    """Check written routing-model files exactly match rendered text.

    Parameters
    ----------
    output_dir : Path
        Directory containing routing-model files.
    model : RoutingModelText
        Expected rendered routing-model text.
    """
    expected = {
        "pips.txt": model.pips,
        "bel.txt": model.bel,
        "bel.v2.txt": model.bel_v2,
        "template.pcf": model.template_pcf,
    }
    for file_name, text in expected.items():
        path = output_dir / file_name

        assert path.exists()
        assert path.read_text(encoding="utf-8") == text
        assert path.stat().st_size > 0


def _pcf_tile_coordinates(template_pcf: str) -> list[tuple[int, int]]:
    """Return tile coordinates referenced by auto-PCF constraints.

    Parameters
    ----------
    template_pcf : str
        Rendered ``template.pcf`` text.

    Returns
    -------
    list[tuple[int, int]]
        ``(x, y)`` coordinates, one entry per template-PCF line.
    """
    coordinates: list[tuple[int, int]] = []
    for line in template_pcf.splitlines():
        match = re.search(r"\bTile_X(?P<x>\d+)Y(?P<y>\d+)_", line)
        if match is None:
            continue
        coordinates.append((int(match.group("x")), int(match.group("y"))))
    return coordinates


def _expected_placement_count_after_resize(
    placements: dict[tuple[int, int], str],
    *,
    row_index: int,
    row_copies: int,
    column_index: int,
    column_copies: int,
) -> int:
    """Return expected placed-tile count after row-then-column duplication.

    Parameters
    ----------
    placements : dict[tuple[int, int], str]
        Initial placed tile-type lookup.
    row_index : int
        Row copied first.
    row_copies : int
        Number of inserted row copies.
    column_index : int
        Column copied after the row insertion.
    column_copies : int
        Number of inserted column copies.

    Returns
    -------
    int
        Expected placement count after resize.
    """
    row_entries = sum(1 for _x, y in placements if y == row_index)
    column_entries = sum(1 for x, _y in placements if x == column_index)
    intersection = int((column_index, row_index) in placements)
    column_entries_after_row_copy = column_entries + intersection * row_copies
    return (
        len(placements)
        + row_entries * row_copies
        + column_entries_after_row_copy * column_copies
    )


def _expected_feature_lines_after_resize(
    coordinates: list[tuple[int, int]],
    *,
    row_index: int,
    row_copies: int,
    column_index: int,
    column_copies: int,
) -> int:
    """Return expected coordinate-owned feature count after resize.

    Parameters
    ----------
    coordinates : list[tuple[int, int]]
        Initial feature coordinates, one entry per feature line.
    row_index : int
        Row copied first.
    row_copies : int
        Number of inserted row copies.
    column_index : int
        Column copied after the row insertion.
    column_copies : int
        Number of inserted column copies.

    Returns
    -------
    int
        Expected feature line count after resize.
    """
    row_entries = sum(1 for _x, y in coordinates if y == row_index)
    column_entries = sum(1 for x, _y in coordinates if x == column_index)
    intersection_entries = sum(
        1 for x, y in coordinates if x == column_index and y == row_index
    )
    column_entries_after_row_copy = column_entries + (intersection_entries * row_copies)
    return (
        len(coordinates)
        + row_entries * row_copies
        + column_entries_after_row_copy * column_copies
    )


def _count_prefixed_lines(text: str, prefix: str) -> int:
    """Count rendered text lines with a given prefix.

    Parameters
    ----------
    text : str
        Text to inspect.
    prefix : str
        Required line prefix.

    Returns
    -------
    int
        Number of matching lines.
    """
    return sum(1 for line in text.splitlines() if line.startswith(prefix))


def _active_pip_line_count(pips_txt: str) -> int:
    """Count non-comment PIP lines in rendered ``pips.txt`` text.

    Parameters
    ----------
    pips_txt : str
        Rendered PIP metadata.

    Returns
    -------
    int
        Number of concrete PIP lines.
    """
    return sum(1 for line in pips_txt.splitlines() if line and not line.startswith("#"))


def _active_resource_count(graph: FabGraph, tile_type: str) -> int:
    """Return the number of active tile-local routing resources.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type to count.

    Returns
    -------
    int
        Active external plus active matrix resource count.
    """
    return len(graph.external_resources(tile_type)) + len(
        graph.matrix_resources(tile_type)
    )


def _unique_standalone_bel_modules(graph: FabGraph, tile_type: str) -> set[str]:
    """Return BEL module names that appear only on one standalone tile.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Standalone tile type.

    Returns
    -------
    set[str]
        BEL module names not used by any placed tile type.
    """
    placed_bels = {
        bel.module_name
        for placed_tile_type in graph.placed_tile_types()
        for bel in graph.tile_model(placed_tile_type).bels
    }
    return {
        bel.module_name
        for bel in graph.tile_model(tile_type).bels
        if bel.module_name not in placed_bels
    }


def _assert_standalone_tile_absent_from_routing_metadata(
    project_dir: Path,
    tile_type: str,
    unique_bel_modules: set[str],
) -> None:
    """Check nextpnr routing metadata does not mention a standalone tile.

    Parameters
    ----------
    project_dir : Path
        Exported project directory.
    tile_type : str
        Standalone tile type.
    unique_bel_modules : set[str]
        BEL module names that uniquely identify the standalone tile.
    """
    metadata_dir = project_dir / ".FABulous"
    metadata_files = (
        metadata_dir / "pips.txt",
        metadata_dir / "bel.txt",
        metadata_dir / "bel.v2.txt",
        metadata_dir / "template.pcf",
        metadata_dir / "bitStreamSpec.csv",
    )
    for metadata_file in metadata_files:
        text = metadata_file.read_text(encoding="utf-8")

        assert tile_type not in text
        for module_name in unique_bel_modules:
            assert module_name not in text


def _mutate_tile_resources_for_config_bit_export(
    graph: FabGraph,
    tile_type: str,
    *,
    seed: int,
) -> None:
    """Apply deterministic add/delete/resize edits with about 5% shrink.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type to mutate.
    seed : int
        Deterministic seed and name component.

    Raises
    ------
    AssertionError
        If the selected tile type does not have enough removable resources.
    """
    resources_before = _active_resource_count(graph, tile_type)
    original_matrix = graph.matrix_resources(tile_type)
    prefix = f"CFG_{_safe_name_fragment(tile_type)}_{seed}"
    probe_source = f"{prefix}_SRC"
    probe_destination = f"{prefix}_DST"

    graph.add_external_resource(
        tile_type,
        Direction.JUMP,
        probe_source,
        0,
        0,
        probe_destination,
        4,
    )
    probe_key = graph.routing_graph.external_resource_key(
        tile_type,
        Direction.JUMP,
        probe_source,
        0,
        0,
        probe_destination,
        4,
    )
    for index in range(3):
        graph.add_matrix_resource(
            tile_type,
            f"{probe_destination}0",
            f"{probe_source}{index}",
        )

    for index in range(2):
        removable_source = f"{prefix}_REMOVE_SRC_{index}"
        removable_destination = f"{prefix}_REMOVE_DST_{index}"
        graph.add_external_resource(
            tile_type,
            Direction.JUMP,
            removable_source,
            0,
            0,
            removable_destination,
            1,
        )
        graph.add_matrix_resource(
            tile_type,
            f"{removable_destination}0",
            f"{removable_source}0",
        )
        graph.delete_external_resource(
            key=graph.routing_graph.external_resource_key(
                tile_type,
                Direction.JUMP,
                removable_source,
                0,
                0,
                removable_destination,
                1,
            )
        )

    graph.resize_external_resource(key=probe_key, new_wire_count=3)

    target_resources = round(resources_before * 0.95)
    candidates = list(original_matrix)
    Random(seed).shuffle(candidates)
    while _active_resource_count(graph, tile_type) > target_resources and candidates:
        graph.delete_matrix_resource(key=candidates.pop())

    if _active_resource_count(graph, tile_type) > target_resources:
        raise AssertionError(f"not enough {tile_type} resources to reach target")


def _inflate_switch_matrix_past_fabric_capacity(
    graph: FabGraph,
    tile_type: str,
) -> RoutingConfigBits:
    """Replace a switch matrix with enough active PIPs to exceed capacity.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type to inflate.

    Returns
    -------
    RoutingConfigBits
        Oversized config-bit summary after the matrix replacement.

    Raises
    ------
    AssertionError
        If the tile cannot be inflated beyond the fabric config-bit capacity.
    """
    switch_matrix = graph.switch_matrix(tile_type)
    capacity = graph.fab.fabric.frameBitsPerRow * graph.fab.fabric.maxFramesPerCol
    fixed_bits = graph.get_config_bits(tile_type).fixed_config_bits
    fanin_bits = (len(switch_matrix.columns) - 1).bit_length()
    if fanin_bits <= 0:
        raise AssertionError(f"{tile_type} does not have matrix columns to inflate")

    rows_needed = min(
        len(switch_matrix.rows),
        max(1, ((capacity - fixed_bits) // fanin_bits) + 2),
    )
    matrix = [
        [
            8.0 if row_index < rows_needed and row_name != column_name else 0.0
            for column_name in switch_matrix.columns
        ]
        for row_index, row_name in enumerate(switch_matrix.rows)
    ]
    graph.set_switch_matrix(
        tile_type,
        list(switch_matrix.columns),
        list(switch_matrix.rows),
        matrix,
    )

    oversized_bits = graph.get_config_bits(tile_type)
    nonzero_pips = sum(1 for row in matrix for delay in row if delay > 0.0)

    if oversized_bits.total_config_bits <= capacity:
        raise AssertionError(
            f"{tile_type} has only {oversized_bits.total_config_bits} config bits; "
            f"expected more than fabric capacity {capacity}"
        )
    if nonzero_pips <= len(switch_matrix.rows):
        raise AssertionError(f"{tile_type} was not inflated with enough active PIPs")
    return oversized_bits


def _read_switch_matrix_config_bits(project_dir: Path, tile_type: str) -> int:
    """Read ``NumberOfConfigBits`` from generated switch-matrix RTL.

    Parameters
    ----------
    project_dir : Path
        Exported project directory.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    int
        Switch-matrix config-bit count.

    Raises
    ------
    AssertionError
        If the generated RTL does not contain a config-bit comment.
    """
    rtl = (project_dir / "Tile" / tile_type / f"{tile_type}_switch_matrix.v").read_text(
        encoding="utf-8"
    )
    match = re.search(r"NumberOfConfigBits:\s*(\d+)", rtl)
    if match is None:
        raise AssertionError(f"missing NumberOfConfigBits comment for {tile_type}")
    return int(match.group(1))


def _read_tile_no_config_bits(project_dir: Path, tile_type: str) -> int:
    """Read top-level ``NoConfigBits`` from generated tile RTL.

    Parameters
    ----------
    project_dir : Path
        Exported project directory.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    int
        Tile-level config-bit count, or zero if the parameter is absent.
    """
    rtl = (project_dir / "Tile" / tile_type / f"{tile_type}.v").read_text(
        encoding="utf-8"
    )
    match = re.search(r"parameter\s+NoConfigBits\s*=\s*(\d+)", rtl)
    if match is None:
        return 0
    return int(match.group(1))


def _missing_matrix_triplets(
    graph: FabGraph,
    tile_type: str,
    *,
    limit: int,
    seed: int,
) -> list[tuple[str, str, float]]:
    """Return legal missing matrix triplets for one tile type.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type whose matrix should be expanded.
    limit : int
        Maximum number of triplets.
    seed : int
        Deterministic shuffle seed.

    Returns
    -------
    list[tuple[str, str, float]]
        Missing ``(source, destination, delay)`` triplets.

    Raises
    ------
    AssertionError
        If fewer than ``limit`` legal missing triplets are available.
    """
    existing_pairs = {
        (key.source_name, key.destination_name)
        for key in graph.matrix_resources(tile_type, active_only=False)
    }
    candidates = [
        (source, sink, 8.0)
        for source in graph.matrix_sources(tile_type)
        for sink in graph.matrix_sinks(tile_type)
        if source != sink and (source, sink) not in existing_pairs
    ]
    Random(seed).shuffle(candidates)
    if len(candidates) < limit:
        raise AssertionError(
            f"{tile_type} has only {len(candidates)} missing matrix candidates"
        )
    return candidates[:limit]


def _delete_matrix_until_target(
    graph: FabGraph,
    tile_type: str,
    target_active_pips: int,
    *,
    batch_size: int,
    seed: int,
    preferred_keys: Iterable[RoutingResourceKey] = (),
) -> int:
    """Delete matrix resources in batches until an active-PIP target is reached.

    Parameters
    ----------
    graph : FabGraph
        Public graph facade.
    tile_type : str
        Tile type whose matrix resources should be deleted.
    target_active_pips : int
        Stop once active PIPs are at or below this value.
    batch_size : int
        Maximum resource keys per batch.
    seed : int
        Deterministic shuffle seed.
    preferred_keys : Iterable[RoutingResourceKey]
        Preferred keys to try before the remaining active matrix resources.

    Returns
    -------
    int
        Number of applied delete batches.

    Raises
    ------
    AssertionError
        If matrix deletions cannot reach the requested active-PIP target.
    """
    preferred = [
        key for key in preferred_keys if key in graph.matrix_resources(tile_type)
    ]
    remaining = [
        key for key in graph.matrix_resources(tile_type) if key not in set(preferred)
    ]
    Random(seed).shuffle(remaining)
    candidates = preferred + remaining
    batches = 0
    while graph.stats().active_pips > target_active_pips and candidates:
        batch = candidates[:batch_size]
        del candidates[:batch_size]
        active_keys = set(graph.matrix_resources(tile_type))
        for key in batch:
            if key in active_keys:
                graph.delete_matrix_resource(key=key)
        batches += 1
    if graph.stats().active_pips > target_active_pips:
        raise AssertionError("not enough matrix resources to reach target")
    return batches


def _line_set(text: str) -> set[str]:
    """Return non-empty lines as a set.

    Parameters
    ----------
    text : str
        Text to split.

    Returns
    -------
    set[str]
        Non-empty line set.
    """
    return {line for line in text.splitlines() if line}
