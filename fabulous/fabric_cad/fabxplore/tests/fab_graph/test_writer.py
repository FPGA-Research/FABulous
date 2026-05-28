"""Tests for fast routing fabric optimizer artifact writers."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path
from random import Random
from typing import TYPE_CHECKING

import pytest  # noqa: DEP004 - test-only dependency

import fabulous.fabulous_settings as fabulous_settings
from fabulous.fabric_cad.fabxplore.modules.fab_graph.core.models import (
    RoutingPipKind,
    RoutingResourceKey,
)
from fabulous.fabric_cad.fabxplore.modules.fab_graph.core.rgraph import (
    RoutingFabricGraph,
)
from fabulous.fabric_cad.fabxplore.modules.fab_graph.core.writer import (
    render_matrix_csv,
    render_matrix_list,
    render_pips_txt,
    render_tile_csv,
    write_pips_txt,
    write_tile_sources,
)
from fabulous.fabric_cad.fabxplore.tests.fab_graph.test_rgraph import (
    _demo_resizable_external_keys,
    _parse_fabric_project,
    _resized_external_key,
    _write_and_parse_project,
)
from fabulous.fabric_cad.gen_npnr_model import genNextpnrModel
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix
from fabulous.fabulous_api import FABulous_API

if TYPE_CHECKING:
    from fabulous.fabric_definition.fabric import Fabric


def test_render_pips_txt_delegates_to_graph(tmp_path: Path) -> None:
    """Render writer output exactly like the graph renderer."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))

    assert render_pips_txt(graph) == graph.render_pips_txt()


def test_write_pips_txt_creates_file_and_returns_metadata(tmp_path: Path) -> None:
    """Write a ``pips.txt`` file and return path, PIP count, and byte count."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    output_path = tmp_path / "out" / ".FABulous" / "pips.txt"

    result = write_pips_txt(graph, output_path, count_pips=True)

    assert result.path == output_path
    assert result.pip_count == graph.stats().active_pips
    assert result.byte_count == output_path.stat().st_size
    assert output_path.read_text(encoding="utf-8") == graph.render_pips_txt()


def test_write_pips_txt_reflects_disabled_resources(tmp_path: Path) -> None:
    """Write only active graph PIPs after a resource is disabled."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    key = next(
        pip.resource_key
        for pip in graph.active_pips()
        if pip.kind is RoutingPipKind.EXTERNAL_WIRE
        and pip.resource_key.source_name == "LONG_BEG"
    )
    removed_lines = {pip.render() for pip in graph.by_resource_key(key)}
    active_before = graph.stats().active_pips

    graph.disable_resource(key)
    result = write_pips_txt(graph, tmp_path / "pips.txt", count_pips=True)
    written_lines = set(result.path.read_text(encoding="utf-8").splitlines())

    assert result.pip_count == graph.stats().active_pips
    assert result.pip_count < active_before
    assert not removed_lines & written_lines


def test_render_tile_sources_flatten_synthetic_project(tmp_path: Path) -> None:
    """Render standalone tile CSV and list text from active graph resources."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    internal_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.INTERNAL_MATRIX
    )
    external_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.EXTERNAL_WIRE and key.source_name == "LONG_BEG"
    )

    graph.disable_resource(internal_key)
    graph.disable_resource(external_key)

    tile_csv = render_tile_csv(graph, "Toy")
    matrix_list = render_matrix_list(graph, "Toy")

    assert "INCLUDE" not in tile_csv
    assert "GENERATE" not in tile_csv
    assert "MATRIX,./Toy_switch_matrix.list" in tile_csv
    assert f"{external_key.direction.value},{external_key.source_name}," not in tile_csv
    disabled_pair = f"{internal_key.source_name},{internal_key.destination_name}"
    assert disabled_pair not in matrix_list


def test_write_tile_sources_round_trips_synthetic_project(tmp_path: Path) -> None:
    """Write flattened sources in place and reparse an equivalent graph."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    internal_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.INTERNAL_MATRIX
    )
    external_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.EXTERNAL_WIRE and key.source_name == "LONG_BEG"
    )
    generated_artifact = tmp_path / "Tile" / "Toy" / "Toy_switch_matrix.csv"
    generated_artifact.write_text("stale", encoding="utf-8")

    graph.disable_resource(internal_key)
    graph.disable_resource(external_key)
    result = write_tile_sources(graph)
    reparsed_graph = RoutingFabricGraph.from_fabric(_parse_fabric_project(tmp_path))

    toy_result = result.tile_results[0]
    assert toy_result.tile_type == "Toy"
    assert toy_result.routing_rows == 1
    assert toy_result.matrix_pairs == 0
    assert generated_artifact in toy_result.removed_artifacts
    assert generated_artifact.exists()
    assert generated_artifact.read_text(encoding="utf-8") != "stale"
    assert "INCLUDE" not in toy_result.tile_csv_path.read_text(encoding="utf-8")
    assert "MATRIX,./Toy_switch_matrix.csv" in toy_result.tile_csv_path.read_text(
        encoding="utf-8"
    )
    assert toy_result.matrix_list_path.read_text(
        encoding="utf-8"
    ) == render_matrix_list(graph, "Toy")
    assert toy_result.matrix_csv_path.read_text(encoding="utf-8") == render_matrix_csv(
        graph, "Toy"
    )
    assert parseMatrix(toy_result.matrix_csv_path, "Toy") == {}
    assert reparsed_graph.render_pips_txt() == graph.render_pips_txt()
    generated_pips = genNextpnrModel(_parse_fabric_project(tmp_path))[0]
    assert generated_pips == graph.render_pips_txt()


def test_write_tile_sources_preserves_null_declaration_rows(
    tmp_path: Path,
) -> None:
    """Round-trip NULL declaration rows used by active matrix resources."""
    graph = RoutingFabricGraph.from_fabric(
        _write_and_parse_null_declaration_project(tmp_path)
    )
    matrix_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.INTERNAL_MATRIX
    )

    graph.validate()
    assert matrix_key.source_name == "S1BEG0"
    assert matrix_key.destination_name == "N1END3"
    assert "N1END3" in graph.matrix_sinks("NullTerm")

    result = write_tile_sources(graph)
    tile_csv = result.tile_results[0].tile_csv_path.read_text(encoding="utf-8")

    assert "NORTH,NULL,0,-1,N1END,4" in tile_csv
    assert "S1BEG0,N1END3" in result.tile_results[0].matrix_list_path.read_text(
        encoding="utf-8"
    )
    reparsed_graph = RoutingFabricGraph.from_fabric(_parse_fabric_project(tmp_path))

    assert _line_set(reparsed_graph.render_pips_txt()) == _line_set(
        graph.render_pips_txt()
    )


def test_write_tile_sources_round_trips_resized_external_resource(
    tmp_path: Path,
) -> None:
    """Write a resized external vector as a smaller standalone CSV row."""
    graph = RoutingFabricGraph.from_fabric(_write_and_parse_project(tmp_path))
    external_key = next(
        key
        for key in graph.resource_keys()
        if key.kind is RoutingPipKind.EXTERNAL_WIRE and key.source_name == "LONG_BEG"
    )

    graph.resize_external_resource(external_key, 1)
    resized_key = _resized_external_key(external_key, 1)
    write_result = write_tile_sources(graph)
    tile_result = write_result.tile_results[0]
    rewritten_fabric = _parse_fabric_project(tmp_path)
    rewritten_pips = genNextpnrModel(rewritten_fabric)[0]

    assert _external_row(resized_key) in _read_csv_rows(tile_result.tile_csv_path)
    assert _external_row(external_key) not in _read_csv_rows(tile_result.tile_csv_path)
    assert _line_set(rewritten_pips) == _line_set(graph.render_pips_txt())


def test_write_tile_sources_round_trips_added_external_and_matrix_resources(
    tmp_path: Path,
) -> None:
    """Write high-level added external CSV and switch-matrix resources."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    original_fabric = _parse_fabric_project(project_dir)
    original_pips = genNextpnrModel(original_fabric)[0]
    graph = RoutingFabricGraph.from_fabric(original_fabric)
    tile_type = "LUT4AB"

    graph.add_external_resource(
        tile_type,
        Direction.EAST,
        "XADD_BEG",
        1,
        0,
        "XADD_END",
        2,
    )
    graph.add_matrix_resource(tile_type, "XADD_END0", "LA_I0")
    graph.add_matrix_resource(tile_type, "LA_O", "XADD_BEG0")
    external = graph.external_resource_key(
        tile_type,
        Direction.EAST,
        "XADD_BEG",
        1,
        0,
        "XADD_END",
        2,
    )
    result = write_tile_sources(graph, tile_types=(tile_type,))
    tile_result = result.tile_results[0]
    rewritten_pips = genNextpnrModel(_parse_fabric_project(project_dir))[0]
    matrix_pairs = parseList(tile_result.matrix_list_path)
    input_matrix = graph.matrix_resource_key(tile_type, "XADD_END0", "LA_I0")
    output_matrix = graph.matrix_resource_key(tile_type, "LA_O", "XADD_BEG0")

    assert graph.by_resource_key(external)
    assert graph.by_resource_key(input_matrix)
    assert graph.by_resource_key(output_matrix)
    assert _external_row(external) in _read_csv_rows(tile_result.tile_csv_path)
    assert ("XADD_END0", "LA_I0") in matrix_pairs
    assert ("LA_O", "XADD_BEG0") in matrix_pairs
    assert _line_set(rewritten_pips) == _line_set(graph.render_pips_txt())
    assert _line_set(rewritten_pips) != _line_set(original_pips)


def test_write_tile_sources_round_trips_real_demo_without_edits(
    tmp_path: Path,
) -> None:
    """Write a copied real project without graph edits and keep PIPs unchanged."""
    source_project = Path("demo_opt").resolve()
    if not source_project.exists():
        pytest.skip("demo_opt project is not available")
    if shutil.which("yosys") is None:
        pytest.skip("Yosys is required to parse demo_opt BEL files")

    project_dir = tmp_path / "demo_opt"
    shutil.copytree(source_project, project_dir)
    original_fabric = _parse_fabric_project(project_dir)
    original_pips = genNextpnrModel(original_fabric)[0]
    graph = RoutingFabricGraph.from_fabric(original_fabric)

    result = write_tile_sources(graph)
    rewritten_fabric = _parse_fabric_project(project_dir)
    rewritten_pips = genNextpnrModel(rewritten_fabric)[0]

    assert len(result.tile_results) == len(graph.tile_types())
    assert _line_set(graph.render_pips_txt()) == _line_set(original_pips)
    assert _line_set(rewritten_pips) == _line_set(original_pips)


def test_write_tile_sources_handles_randomized_demo_optimizer_shrink(
    tmp_path: Path,
) -> None:
    """Simulate batched optimizer removals and write 10 percent fewer PIPs."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    original_fabric = _parse_fabric_project(project_dir)
    original_pips = genNextpnrModel(original_fabric)[0]
    graph = RoutingFabricGraph.from_fabric(original_fabric)
    active_before = graph.stats().active_pips
    target_active = active_before * 9 // 10

    iterations = _disable_random_internal_batches(
        graph,
        "LUT4AB",
        target_active,
        seed=17,
    )
    write_tile_sources(graph, tile_types=("LUT4AB",))
    rewritten_pips = genNextpnrModel(_parse_fabric_project(project_dir))[0]

    assert iterations > 1
    assert graph.stats().active_pips <= target_active
    assert graph.stats().active_pips < active_before
    assert _line_set(rewritten_pips) == _line_set(graph.render_pips_txt())
    assert _line_set(rewritten_pips) < _line_set(original_pips)


def test_write_tile_sources_handles_randomized_demo_optimizer_growth(
    tmp_path: Path,
) -> None:
    """Simulate batched optimizer additions and write 10 percent more PIPs."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    original_fabric = _parse_fabric_project(project_dir)
    original_pips = genNextpnrModel(original_fabric)[0]
    graph = RoutingFabricGraph.from_fabric(original_fabric)
    active_before = graph.stats().active_pips
    target_active = active_before + active_before // 10

    iterations = _add_random_internal_batches(
        graph,
        "LUT4AB",
        target_active,
        seed=31,
    )
    write_tile_sources(graph, tile_types=("LUT4AB",))
    rewritten_pips = genNextpnrModel(_parse_fabric_project(project_dir))[0]

    assert iterations > 1
    assert graph.stats().active_pips >= target_active
    assert graph.stats().active_pips > active_before
    assert _line_set(rewritten_pips) == _line_set(graph.render_pips_txt())
    assert _line_set(original_pips) < _line_set(rewritten_pips)


def test_write_tile_sources_handles_mixed_demo_optimizer_stress(
    tmp_path: Path,
) -> None:
    """Write real demo after mixed external/internal shrink and growth edits."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    original_fabric = _parse_fabric_project(project_dir)
    original_pips = genNextpnrModel(original_fabric)[0]
    graph = RoutingFabricGraph.from_fabric(original_fabric)
    tile_type = "LUT4AB"
    active_before = graph.stats().active_pips
    target_active = active_before * 7 // 10
    external_keys = list(
        _demo_resizable_external_keys(graph, tile_type, min_wire_count=4)
    )

    assert len(external_keys) >= 7

    resized_keys = external_keys[:5]
    for _iteration in range(2):
        for index, key in enumerate(resized_keys):
            assert key.wire_count is not None
            next_count = key.wire_count - 1
            graph.resize_external_resource(key, next_count)
            resized_keys[index] = _resized_external_key(key, next_count)
        graph.validate()

    grow_key = resized_keys[0]
    assert grow_key.wire_count is not None
    grow_count = grow_key.wire_count + 2
    graph.resize_external_resource(grow_key, grow_count)
    grown_key = _resized_external_key(grow_key, grow_count)
    resized_keys[0] = grown_key

    toggled_external_key = external_keys[5]
    graph.disable_resource(toggled_external_key)
    graph.enable_resource(toggled_external_key)

    removed_external_key = external_keys[6]
    graph.disable_resource(removed_external_key)

    added_internal_key = _add_first_missing_internal_resource(
        graph,
        tile_type,
        seed=97,
    )
    iterations = _disable_random_internal_batches(
        graph,
        tile_type,
        target_active,
        seed=103,
        batch_size=17,
        excluded_keys=(added_internal_key,),
    )
    graph.validate()

    removal_fraction = 1.0 - (graph.stats().active_pips / active_before)
    result = write_tile_sources(graph, tile_types=(tile_type,))
    tile_result = result.tile_results[0]
    rewritten_pips = genNextpnrModel(_parse_fabric_project(project_dir))[0]
    rows = _read_csv_rows(tile_result.tile_csv_path)

    assert iterations > 1
    assert 0.30 <= removal_fraction <= 0.35
    assert graph.by_resource_key(added_internal_key)
    assert _external_row(grown_key) in rows
    assert _external_row(toggled_external_key) in rows
    assert _external_row(removed_external_key) not in rows
    assert graph.stats().active_pips <= target_active
    assert _line_set(rewritten_pips) == _line_set(graph.render_pips_txt())
    assert _line_set(rewritten_pips) != _line_set(original_pips)


def test_write_tile_sources_regenerates_real_demo_project(tmp_path: Path) -> None:
    """Write a real copied project, regenerate artifacts, and compare routing."""
    source_project = Path("demo_opt").resolve()
    if not source_project.exists():
        pytest.skip("demo_opt project is not available")
    if shutil.which("yosys") is None:
        pytest.skip("Yosys is required to parse demo_opt BEL files")

    project_dir = tmp_path / "demo_opt"
    shutil.copytree(source_project, project_dir)
    graph = RoutingFabricGraph.from_fabric(_parse_fabric_project(project_dir))
    tile_type = "LUT4AB"
    internal_key = next(
        key
        for key in graph.resource_keys()
        if key.tile_type == tile_type and key.kind is RoutingPipKind.INTERNAL_MATRIX
    )
    external_key = next(
        key
        for key in graph.resource_keys()
        if key.tile_type == tile_type and key.kind is RoutingPipKind.EXTERNAL_WIRE
    )
    tile_dir = project_dir / "Tile" / tile_type
    stale_paths = [
        tile_dir / f"{tile_type}.v",
        tile_dir / f"{tile_type}_switch_matrix.csv",
        tile_dir / f"{tile_type}_switch_matrix.v",
        tile_dir / f"{tile_type}_ConfigMem.csv",
        tile_dir / f"{tile_type}_ConfigMem.v",
    ]
    for path in stale_paths:
        path.write_text("stale artifact", encoding="utf-8")

    graph.disable_resource(internal_key)
    result = write_tile_sources(graph, tile_types=(tile_type,))
    tile_result = result.tile_results[0]

    assert set(stale_paths).issubset(tile_result.removed_artifacts)
    assert tile_result.matrix_csv_path.exists()
    assert tile_result.matrix_csv_path.read_text(encoding="utf-8") != "stale artifact"
    assert all(not path.exists() for path in stale_paths if path.suffix != ".csv")
    assert "INCLUDE" not in tile_result.tile_csv_path.read_text(encoding="utf-8")
    assert "GENERATE" not in tile_result.tile_csv_path.read_text(encoding="utf-8")
    matrix_row = f"MATRIX,./{tile_type}_switch_matrix.csv"
    assert matrix_row in tile_result.tile_csv_path.read_text(encoding="utf-8")
    assert [internal_key.source_name, internal_key.destination_name] not in [
        list(pair) for pair in parseList(tile_result.matrix_list_path)
    ]
    assert parseMatrix(tile_result.matrix_csv_path, tile_type)
    assert _external_row(external_key) in _read_csv_rows(tile_result.tile_csv_path)

    rewritten_fabric = _parse_fabric_project(project_dir)
    assert _line_set(genNextpnrModel(rewritten_fabric)[0]) == _line_set(
        graph.render_pips_txt()
    )

    fab = FABulous_API(VerilogCodeGenerator())
    fabulous_settings.reset_context()
    context = fabulous_settings.FABulousSettings.model_construct(
        proj_dir=project_dir,
        nix_shell=None,
    )
    fabulous_settings._context_instance = context  # noqa: SLF001
    fab.loadFabric(project_dir / "fabric.csv")
    fab.setWriterOutputFile(tile_dir / f"{tile_type}_switch_matrix.v")
    fab.genSwitchMatrix(tile_type)
    fab.setWriterOutputFile(tile_dir / f"{tile_type}_ConfigMem.v")
    fab.genConfigMem(tile_type, tile_dir / f"{tile_type}_ConfigMem.csv")
    fab.setWriterOutputFile(tile_dir / f"{tile_type}.v")
    fab.genTile(tile_type)
    pips, _bel, _bel_v2, _pcf = fab.genRoutingModel()

    assert _line_set(pips) == _line_set(graph.render_pips_txt())
    assert all(path.exists() for path in stale_paths)
    assert all(
        path.read_text(encoding="utf-8") != "stale artifact" for path in stale_paths
    )


def test_write_tile_sources_handles_real_external_resource_cascade(
    tmp_path: Path,
) -> None:
    """Write a real project after removing an external resource with dependents."""
    project_dir = _copy_demo_opt_project_or_skip(tmp_path)
    fabric = _parse_fabric_project(project_dir)
    graph = RoutingFabricGraph.from_fabric(fabric)
    tile_type = "LUT4AB"
    external_key = _external_resource_with_matrix_dependencies(graph, tile_type)
    removed_wires = _expanded_external_wires(external_key)
    direct_pips = graph.by_resource_key(external_key)
    active_before = graph.stats().active_pips

    graph.disable_resource(external_key)
    result = write_tile_sources(graph, tile_types=(tile_type,))
    tile_result = result.tile_results[0]
    rewritten_pips = genNextpnrModel(_parse_fabric_project(project_dir))[0]

    assert graph.stats().active_pips < active_before - len(direct_pips)
    assert _external_row(external_key) not in _read_csv_rows(tile_result.tile_csv_path)
    assert not [
        pair
        for pair in parseList(tile_result.matrix_list_path)
        if pair[0] in removed_wires or pair[1] in removed_wires
    ]
    assert _line_set(rewritten_pips) == _line_set(graph.render_pips_txt())


def _read_csv_rows(path: Path) -> list[list[str]]:
    """Read CSV rows from a path.

    Parameters
    ----------
    path : Path
        CSV path.

    Returns
    -------
    list[list[str]]
        Parsed CSV rows.
    """
    with path.open(encoding="utf-8", newline="") as csv_file:
        return list(csv.reader(csv_file))


def _copy_demo_opt_project_or_skip(tmp_path: Path) -> Path:
    """Copy ``demo_opt`` into a temporary directory or skip when unavailable.

    Parameters
    ----------
    tmp_path : Path
        Test temporary directory.

    Returns
    -------
    Path
        Copied project directory.
    """
    source_project = Path("demo_opt").resolve()
    if not source_project.exists():
        pytest.skip("demo_opt project is not available")
    if shutil.which("yosys") is None:
        pytest.skip("Yosys is required to parse demo_opt BEL files")

    project_dir = tmp_path / "demo_opt"
    shutil.copytree(source_project, project_dir)
    return project_dir


def _write_and_parse_null_declaration_project(project_dir: Path) -> Fabric:
    """Write a project with NULL declaration rows used by a matrix.

    Parameters
    ----------
    project_dir : Path
        Temporary project directory.

    Returns
    -------
    Fabric
        Parsed FABulous fabric.
    """
    tile_dir = project_dir / "Tile" / "NullTerm"
    tile_dir.mkdir(parents=True)

    (project_dir / "fabric.csv").write_text(
        """\
FabricBegin
NullTerm
FabricEnd

ParametersBegin
ConfigBitMode,frame_based
GenerateDelayInSwitchMatrix,80
MultiplexerStyle,custom
SuperTileEnable,FALSE
Tile,./Tile/NullTerm/NullTerm.csv
ParametersEnd
""",
        encoding="utf-8",
    )
    (tile_dir / "NullTerm.csv").write_text(
        """\
TILE,NullTerm
NORTH,NULL,0,-1,N1END,4,
SOUTH,S1BEG,0,1,NULL,4,
MATRIX,./NullTerm_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (tile_dir / "NullTerm_switch_matrix.list").write_text(
        "S1BEG0,N1END3\n",
        encoding="utf-8",
    )
    return _parse_fabric_project(project_dir)


def _disable_random_internal_batches(
    graph: RoutingFabricGraph,
    tile_type: str,
    target_active_pips: int,
    *,
    seed: int,
    batch_size: int = 11,
    excluded_keys: tuple[RoutingResourceKey, ...] = (),
) -> int:
    """Disable active internal resource keys in deterministic random batches.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Graph to mutate.
    tile_type : str
        Tile type whose internal resources should be disabled.
    target_active_pips : int
        Stop once the graph has no more than this many active PIPs.
    seed : int
        Random seed for deterministic candidate order.
    batch_size : int
        Number of resources to disable per iteration.
    excluded_keys : tuple[RoutingResourceKey, ...]
        Resource keys that should stay active during the batch sequence.

    Returns
    -------
    int
        Number of completed batch iterations.

    Raises
    ------
    AssertionError
        If the target cannot be reached with the available internal resources.
    """
    excluded = set(excluded_keys)
    candidates = [
        key for key in _internal_resource_keys(graph, tile_type) if key not in excluded
    ]
    Random(seed).shuffle(candidates)
    iterations = 0
    while graph.stats().active_pips > target_active_pips and candidates:
        batch = candidates[:batch_size]
        del candidates[:batch_size]
        for key in batch:
            if graph.by_resource_key(key):
                graph.disable_resource(key)
        iterations += 1

    if graph.stats().active_pips > target_active_pips:
        raise AssertionError("not enough internal resources to reach shrink target")
    return iterations


def _add_random_internal_batches(
    graph: RoutingFabricGraph,
    tile_type: str,
    target_active_pips: int,
    *,
    seed: int,
    batch_size: int = 13,
) -> int:
    """Add new internal resource keys in deterministic random batches.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Graph to mutate.
    tile_type : str
        Tile type whose internal resources should be expanded.
    target_active_pips : int
        Stop once the graph has at least this many active PIPs.
    seed : int
        Random seed for deterministic candidate order.
    batch_size : int
        Number of resources to add per iteration.

    Returns
    -------
    int
        Number of completed batch iterations.

    Raises
    ------
    AssertionError
        If the target cannot be reached with legal internal source/sink pairs.
    """
    existing_keys = _internal_resource_keys(graph, tile_type)
    all_internal_keys = tuple(
        key
        for key in graph.resource_keys(active_only=False)
        if key.tile_type == tile_type and key.kind is RoutingPipKind.INTERNAL_MATRIX
    )
    sources = list(dict.fromkeys(key.source_name for key in existing_keys))
    sinks = list(dict.fromkeys(key.destination_name for key in existing_keys))
    existing_pairs = {
        (key.source_name, key.destination_name) for key in all_internal_keys
    }
    candidates = [
        (source, sink)
        for source in sources
        for sink in sinks
        if (source, sink) not in existing_pairs
    ]
    Random(seed).shuffle(candidates)

    iterations = 0
    while graph.stats().active_pips < target_active_pips and candidates:
        batch = candidates[:batch_size]
        del candidates[:batch_size]
        for source, sink in batch:
            _add_internal_resource(graph, tile_type, source, sink)
        iterations += 1

    if graph.stats().active_pips < target_active_pips:
        raise AssertionError("not enough candidate resources to reach growth target")
    return iterations


def _add_first_missing_internal_resource(
    graph: RoutingFabricGraph,
    tile_type: str,
    *,
    seed: int,
) -> RoutingResourceKey:
    """Add one legal missing internal resource to every placed tile of a type.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Graph to mutate.
    tile_type : str
        Tile type whose matrix should receive the new edge.
    seed : int
        Random seed for deterministic candidate order.

    Returns
    -------
    RoutingResourceKey
        Added internal resource key.

    Raises
    ------
    AssertionError
        If no legal missing matrix source/sink pair can be added.
    """
    existing_keys = _internal_resource_keys(graph, tile_type)
    all_internal_keys = tuple(
        key
        for key in graph.resource_keys(active_only=False)
        if key.tile_type == tile_type and key.kind is RoutingPipKind.INTERNAL_MATRIX
    )
    sources = list(dict.fromkeys(key.source_name for key in existing_keys))
    sinks = list(dict.fromkeys(key.destination_name for key in existing_keys))
    existing_pairs = {
        (key.source_name, key.destination_name) for key in all_internal_keys
    }
    candidates = [
        (source, sink)
        for source in sources
        for sink in sinks
        if (source, sink) not in existing_pairs
    ]
    Random(seed).shuffle(candidates)
    matrix_path = graph.tile_model(tile_type).matrix_path

    for source, sink in candidates:
        resource_key = RoutingResourceKey(
            tile_type=tile_type,
            kind=RoutingPipKind.INTERNAL_MATRIX,
            source_name=source,
            destination_name=sink,
            matrix_path=matrix_path,
        )
        _add_internal_resource(graph, tile_type, source, sink)
        graph.validate()
        return resource_key

    raise AssertionError(f"{tile_type} has no missing internal resource candidates")


def _internal_resource_keys(
    graph: RoutingFabricGraph,
    tile_type: str,
) -> tuple[RoutingResourceKey, ...]:
    """Return active internal matrix resource keys for one tile type.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to select.

    Returns
    -------
    tuple[RoutingResourceKey, ...]
        Matching resource keys.
    """
    return tuple(
        key
        for key in graph.resource_keys()
        if key.tile_type == tile_type and key.kind is RoutingPipKind.INTERNAL_MATRIX
    )


def _add_internal_resource(
    graph: RoutingFabricGraph,
    tile_type: str,
    source: str,
    sink: str,
) -> None:
    """Add one internal matrix resource to every placed tile of a type.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Graph to mutate.
    tile_type : str
        Tile type that owns the matrix resource.
    source : str
        Matrix source name.
    sink : str
        Matrix destination name.
    """
    graph.add_matrix_resource(tile_type, source, sink)


def _line_set(text: str) -> set[str]:
    """Return non-empty lines as a set.

    Parameters
    ----------
    text : str
        Text to split.

    Returns
    -------
    set[str]
        Set of non-empty lines.
    """
    return {line for line in text.splitlines() if line}


def _external_row(key: RoutingResourceKey) -> list[str]:
    """Return the standalone CSV row expected for an external resource key.

    Parameters
    ----------
    key : RoutingResourceKey
        Routing resource key.

    Returns
    -------
    list[str]
        Expected CSV row.
    """
    return [
        key.direction.value,
        key.source_name,
        str(key.x_offset),
        str(key.y_offset),
        key.destination_name,
        str(key.wire_count),
        "",
    ]


def _external_resource_with_matrix_dependencies(
    graph: RoutingFabricGraph,
    tile_type: str,
) -> RoutingResourceKey:
    """Return an external key whose wires are used by active matrix resources.

    Parameters
    ----------
    graph : RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to select.

    Returns
    -------
    RoutingResourceKey
        External resource with at least one active dependent matrix resource.

    Raises
    ------
    AssertionError
        If no suitable resource exists.
    """
    internal_keys = tuple(_internal_resource_keys(graph, tile_type))
    for key in graph.resource_keys():
        if key.tile_type != tile_type or key.kind is not RoutingPipKind.EXTERNAL_WIRE:
            continue
        wires = _expanded_external_wires(key)
        if any(
            internal.source_name in wires or internal.destination_name in wires
            for internal in internal_keys
        ):
            return key
    raise AssertionError(f"{tile_type} has no external resource with dependencies")


def _expanded_external_wires(key: RoutingResourceKey) -> set[str]:
    """Return local matrix-visible wires declared by an external resource.

    Parameters
    ----------
    key : RoutingResourceKey
        External routing resource key.

    Returns
    -------
    set[str]
        Expanded wire names.
    """
    if key.wire_count is None:
        return {name for name in (key.source_name, key.destination_name) if name}

    wire_count = key.wire_count
    if (
        key.direction is not None
        and key.direction.name != "JUMP"
        and (key.source_name == "NULL" or key.destination_name == "NULL")
    ):
        wire_count *= abs(key.x_offset) + abs(key.y_offset)

    wires: set[str] = set()
    for index in range(wire_count):
        if key.source_name != "NULL":
            wires.add(f"{key.source_name}{index}")
        if key.destination_name != "NULL":
            wires.add(f"{key.destination_name}{index}")
    return wires
