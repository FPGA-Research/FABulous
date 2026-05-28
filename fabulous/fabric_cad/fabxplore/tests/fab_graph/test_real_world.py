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
from fabulous.fabric_cad.fabxplore.modules.fab_graph.core import FabGraph
from fabulous.fabric_cad.fabxplore.modules.fab_graph.core.models import (
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

        assert graph.active_pips(where=lambda pip, t=tile_type: pip.tile_type == t)

    graph.routing_graph.validate()
    assert graph.stats().active_pips > 0
    graph.write_project(output_project, generate_rtl=True)
    _assert_export_matches_graph(output_project, graph)
    assert any((output_project / "Tile").glob("**/*.v"))


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
        where=lambda pip: pip.tile_type == tile_type
        and pip.kind is RoutingPipKind.INTERNAL_MATRIX,
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
        where=lambda pip: pip.tile_type == tile_type
        and pip.kind is RoutingPipKind.EXTERNAL_WIRE,
    )
    graph.write_project(output_project, generate_rtl=False)
    exported = _load_fab_graph(output_project)

    assert not exported.active_pips(
        where=lambda pip: pip.tile_type == tile_type
        and pip.kind is RoutingPipKind.EXTERNAL_WIRE,
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
        where=lambda key: key.wire_count is not None
        and key.wire_count >= 4
        and key.direction is not None,
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
        where=lambda key: key.source_name in set(matrix_sources)
        or key.destination_name in set(matrix_sinks),
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
