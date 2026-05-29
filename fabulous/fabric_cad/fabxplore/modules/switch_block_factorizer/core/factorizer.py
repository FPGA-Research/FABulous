"""Factorize FABulous switch-matrix rows into JUMP-based mux stages."""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer.core.models import (
    MuxReductionRule,
    SwitchBlockFactorizerArtifact,
    SwitchBlockFactorizerOptions,
    SwitchBlockFactorizerResult,
    SwitchBlockFactorizerStats,
)
from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer.core.process_tracker import (  # noqa: E501
    SwitchBlockFactorizerProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer.core.report import (
    render_switch_block_factorizer_report,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge
    from fabulous.fabric_definition.tile import Tile
    from fabulous.fabulous_api import FABulous_API


Connections = dict[str, list[str]]
JumpRows = list[tuple[str, str]]


class SwitchBlockFactorizer:
    """Factorize active FABulous switch matrices in place.

    Parameters
    ----------
    options : SwitchBlockFactorizerOptions
        Normalized factorizer options.
    """

    def __init__(self, options: SwitchBlockFactorizerOptions) -> None:
        self.options = options

    def run(self, fpga_model: PnRBridge) -> SwitchBlockFactorizerResult:
        """Run switch-block factorization on the active FABulous project.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and routing graph.
            The current factorizer records the design dependency but does not
            mutate the design.

        Returns
        -------
        SwitchBlockFactorizerResult
            Structured result and report.

        Raises
        ------
        RuntimeError
            If guardrails are exceeded or reachability is not preserved.
        """
        design = fpga_model.user_design
        fab = fpga_model.fab
        _ = design
        tracker = SwitchBlockFactorizerProcessTracker(
            enabled=self.options.track_progress
        )
        tracker.start(self.options.tile_name)

        tile = _get_tile(fab, self.options.tile_name)
        tile_dir = self.options.tile_dir or _tile_dir(tile)
        tile_csv = self.options.tile_csv or tile_dir / f"{self.options.tile_name}.csv"
        source_matrix = self.options.switch_matrix or tile.matrixDir
        output_list = tile_dir / f"{self.options.tile_name}_switch_matrix.list"

        connections = _read_connections(source_matrix, self.options.tile_name)
        before_connections = _copy_connections(connections)
        transformed, jump_rows, warnings = _factorize_connections(
            connections,
            self.options,
        )

        if self.options.max_added_jump_wires is not None and (
            len(jump_rows) > self.options.max_added_jump_wires
        ):
            raise RuntimeError(
                "switch-block factorization would add "
                f"{len(jump_rows)} JUMP wires, but max_added_jump_wires is "
                f"{self.options.max_added_jump_wires}."
            )

        if not _preserves_reachability(before_connections, transformed, jump_rows):
            raise RuntimeError(
                "switch-block factorization did not preserve reachability."
            )

        output_list.write_text(
            _render_list(self.options.tile_name, transformed),
            encoding="utf-8",
        )
        tracker.wrote_file("switch matrix list", output_list)

        _rewrite_tile_csv(tile_csv, output_list, self.options.jump_prefix, jump_rows)
        tracker.wrote_file("tile csv", tile_csv)

        _remove_generated_artifacts(tile_dir, self.options.tile_name, fab.fileExtension)

        project_dir = get_context().proj_dir
        fab.loadFabric(project_dir / "fabric.csv")
        refreshed_tile = _get_tile(fab, self.options.tile_name)
        _check_config_limit(
            refreshed_tile.globalConfigBits,
            _config_capacity(fab, self.options.config_bit_capacity_override),
            self.options.config_bit_margin,
        )

        artifacts = [
            SwitchBlockFactorizerArtifact(kind="switch_matrix_list", path=output_list),
            SwitchBlockFactorizerArtifact(kind="tile_csv", path=tile_csv),
        ]
        artifacts.extend(
            _run_fabulous_generation(
                fab=fab,
                tile_name=self.options.tile_name,
                tile_dir=tile_dir,
                file_extension=fab.fileExtension,
            )
        )
        for artifact in artifacts[2:]:
            tracker.wrote_file(artifact.kind, artifact.path)

        after_connections = _read_connections(output_list, self.options.tile_name)
        stats = SwitchBlockFactorizerStats(
            mux_rows_before=len(before_connections),
            mux_rows_after=len(after_connections),
            pips_before=_count_pips(before_connections),
            pips_after=_count_pips(after_connections),
            max_fanin_before=_max_fanin(before_connections),
            max_fanin_after=_max_fanin(after_connections),
            matrix_config_bits_before=_estimate_config_bits(before_connections),
            matrix_config_bits_after=refreshed_tile.matrixConfigBits,
            total_config_bits_after=refreshed_tile.globalConfigBits,
            added_jump_wires=len(jump_rows),
            factorized_rows=_count_factorized_rows(before_connections, transformed),
            generated_hierarchy_pips=_count_hierarchy_pips(transformed, jump_rows),
            fanin_histogram_before=_fanin_histogram(before_connections),
            fanin_histogram_after=_fanin_histogram(after_connections),
            reachability_preserved=True,
        )

        result = SwitchBlockFactorizerResult(
            options=self.options.model_copy(
                update={
                    "tile_dir": tile_dir,
                    "tile_csv": tile_csv,
                    "switch_matrix": output_list,
                }
            ),
            tile_name=self.options.tile_name,
            tile_dir=tile_dir,
            tile_csv=tile_csv,
            switch_matrix_list=output_list,
            source_matrix=source_matrix,
            artifacts=tuple(artifacts),
            stats=stats,
            warnings=tuple(warnings),
        )
        result = result.model_copy(
            update={"report_summary": render_switch_block_factorizer_report(result)}
        )
        tracker.finish(self.options.tile_name, stats.added_jump_wires)
        return result


def _get_tile(fab: FABulous_API, tile_name: str) -> Tile:
    """Return one tile from a loaded FABulous project.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.
    tile_name : str
        Tile name.

    Returns
    -------
    Tile
        Matching FABulous tile.

    Raises
    ------
    ValueError
        If the tile does not exist.
    """
    tile = fab.fabric.getTileByName(tile_name)
    if tile is None:
        raise ValueError(f"Tile {tile_name} not found")
    return tile


def _tile_dir(tile: Tile) -> Path:
    """Return the directory containing one tile CSV.

    Parameters
    ----------
    tile : Tile
        FABulous tile.

    Returns
    -------
    Path
        Tile directory.
    """
    if tile.matrixDir:
        return tile.matrixDir.parent
    return tile.tileDir.parent


def _read_connections(matrix_path: Path, tile_name: str) -> Connections:
    """Read switch-matrix connectivity with FABulous parsers.

    Parameters
    ----------
    matrix_path : Path
        Active switch-matrix list or CSV.
    tile_name : str
        Tile name for CSV validation.

    Returns
    -------
    Connections
        Mapping from mux output row to selectable sources.

    Raises
    ------
    ValueError
        If the matrix format is unsupported.
    """
    match matrix_path.suffix:
        case ".list":
            return {
                row: list(sources)
                for row, sources in parseList(matrix_path, collect="source").items()
            }
        case ".csv":
            return {
                row: list(sources)
                for row, sources in parseMatrix(matrix_path, tile_name).items()
            }
        case _:
            raise ValueError(
                "switch-block factorizer supports only .list and .csv matrices, "
                f"got {matrix_path}"
            )


def _copy_connections(connections: Connections) -> Connections:
    """Return a deep copy of switch-matrix connections.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connectivity.

    Returns
    -------
    Connections
        Copied connectivity.
    """
    return {row: list(sources) for row, sources in connections.items()}


def _factorize_connections(
    connections: Connections,
    options: SwitchBlockFactorizerOptions,
) -> tuple[Connections, JumpRows, list[str]]:
    """Factorize connections according to configured rules.

    Parameters
    ----------
    connections : Connections
        Original connectivity.
    options : SwitchBlockFactorizerOptions
        Factorizer options.

    Returns
    -------
    tuple[Connections, JumpRows, list[str]]
        Factorized connectivity, generated JUMP rows, and warnings.
    """
    state = _copy_connections(connections)
    jump_rows: JumpRows = []
    warnings: list[str] = []
    counter = 0

    if options.global_reduction is not None:
        for level in range(options.global_reduction):
            state, jump_rows, counter = _apply_global_reduction(
                state,
                options,
                jump_rows,
                counter,
                level,
            )

    for rule_index, rule in enumerate(options.reduction_rules):
        state, jump_rows, counter = _apply_reduction_rule(
            state,
            options,
            jump_rows,
            counter,
            rule,
            rule_index,
        )

    if not jump_rows:
        warnings.append("No mux rows met the configured factorization criteria.")
    return state, jump_rows, warnings


def _apply_global_reduction(
    connections: Connections,
    options: SwitchBlockFactorizerOptions,
    jump_rows: JumpRows,
    counter: int,
    level: int,
) -> tuple[Connections, JumpRows, int]:
    """Apply one global fanin-halving factorization pass.

    Parameters
    ----------
    connections : Connections
        Current connectivity.
    options : SwitchBlockFactorizerOptions
        Factorizer options.
    jump_rows : JumpRows
        JUMP rows accumulated so far.
    counter : int
        Unique JUMP counter.
    level : int
        Global reduction level.

    Returns
    -------
    tuple[Connections, JumpRows, int]
        Updated connectivity, JUMP rows, and counter.
    """
    next_connections: Connections = {}
    for row, sources in connections.items():
        if len(sources) < options.min_mux_fanin_to_factorize or len(sources) <= 2:
            next_connections[row] = list(sources)
            continue
        target_fanin = math.ceil(len(sources) / 2)
        rows, new_jump_rows, counter = _factorize_row(
            row=row,
            sources=sources,
            target_fanin=target_fanin,
            jump_prefix=options.jump_prefix,
            counter=counter,
            stage_label=f"G{level}",
        )
        next_connections.update(rows)
        jump_rows.extend(new_jump_rows)
    return next_connections, jump_rows, counter


def _apply_reduction_rule(
    connections: Connections,
    options: SwitchBlockFactorizerOptions,
    jump_rows: JumpRows,
    counter: int,
    rule: MuxReductionRule,
    rule_index: int,
) -> tuple[Connections, JumpRows, int]:
    """Apply one exact fanin reduction rule.

    Parameters
    ----------
    connections : Connections
        Current connectivity.
    options : SwitchBlockFactorizerOptions
        Factorizer options.
    jump_rows : JumpRows
        JUMP rows accumulated so far.
    counter : int
        Unique JUMP counter.
    rule : MuxReductionRule
        Exact fanin reduction rule.
    rule_index : int
        Rule index for generated labels.

    Returns
    -------
    tuple[Connections, JumpRows, int]
        Updated connectivity, JUMP rows, and counter.
    """
    next_connections: Connections = {}
    for row, sources in connections.items():
        if len(sources) != rule.from_fanin:
            next_connections[row] = list(sources)
            continue
        if len(sources) < options.min_mux_fanin_to_factorize:
            next_connections[row] = list(sources)
            continue
        rows, new_jump_rows, counter = _factorize_row(
            row=row,
            sources=sources,
            target_fanin=rule.to_fanin,
            jump_prefix=options.jump_prefix,
            counter=counter,
            stage_label=f"R{rule_index}",
        )
        next_connections.update(rows)
        jump_rows.extend(new_jump_rows)
    return next_connections, jump_rows, counter


def _factorize_row(
    row: str,
    sources: list[str],
    target_fanin: int,
    jump_prefix: str,
    counter: int,
    stage_label: str,
) -> tuple[Connections, JumpRows, int]:
    """Factor one mux row into generated JUMP stages.

    Parameters
    ----------
    row : str
        Original mux output row.
    sources : list[str]
        Original selectable sources.
    target_fanin : int
        Maximum source count for first-stage generated muxes.
    jump_prefix : str
        Prefix for generated JUMP wires.
    counter : int
        Unique JUMP counter.
    stage_label : str
        Label for this factorization stage.

    Returns
    -------
    tuple[Connections, JumpRows, int]
        Generated rows, generated JUMP CSV rows, and next counter.
    """
    chunks = [
        sources[start : start + target_fanin]
        for start in range(0, len(sources), target_fanin)
    ]
    if len(chunks) <= 1:
        return {row: list(sources)}, [], counter

    generated: Connections = {}
    jump_rows: JumpRows = []
    final_sources: list[str] = []
    for chunk in chunks:
        base = f"{jump_prefix}_{stage_label}_{counter}"
        begin = f"{base}_BEG"
        end = f"{base}_END"
        generated[f"{begin}0"] = list(chunk)
        final_sources.append(f"{end}0")
        jump_rows.append((begin, end))
        counter += 1
    generated[row] = final_sources
    return generated, jump_rows, counter


def _preserves_reachability(
    original: Connections,
    transformed: Connections,
    jump_rows: JumpRows,
) -> bool:
    """Check that original row sources can still reach each row.

    Parameters
    ----------
    original : Connections
        Original connectivity.
    transformed : Connections
        Factorized connectivity.
    jump_rows : JumpRows
        Generated JUMP rows.

    Returns
    -------
    bool
        ``True`` if each original source can still reach its original row.
    """
    for row, sources in original.items():
        reachable = _reachable_leaf_sources(row, transformed, jump_rows, set())
        if not set(sources).issubset(reachable):
            return False
    return True


def _reachable_leaf_sources(
    row: str,
    connections: Connections,
    jump_rows: JumpRows,
    seen: set[str],
) -> set[str]:
    """Return leaf sources that can reach one mux row.

    Parameters
    ----------
    row : str
        Mux output row.
    connections : Connections
        Switch-matrix connectivity.
    jump_rows : JumpRows
        Generated JUMP rows.
    seen : set[str]
        Rows already visited during recursion.

    Returns
    -------
    set[str]
        Reachable non-generated leaf sources.
    """
    if row in seen:
        return set()
    seen.add(row)
    end_to_begin = {f"{end}0": f"{begin}0" for begin, end in jump_rows}
    reachable: set[str] = set()
    for source in connections.get(row, []):
        if source in end_to_begin:
            reachable.update(
                _reachable_leaf_sources(
                    end_to_begin[source],
                    connections,
                    jump_rows,
                    seen,
                )
            )
        else:
            reachable.add(source)
    return reachable


def _render_list(tile_name: str, connections: Connections) -> str:
    """Render normalized FABulous list text.

    Parameters
    ----------
    tile_name : str
        Tile name.
    connections : Connections
        Switch-matrix connectivity.

    Returns
    -------
    str
        List-file text.
    """
    lines = [
        "# --------------WARNING-----------------",
        "# This is a generated list file!",
        "# Your changes will be overwritten!",
        "# Generated by fabxplore switch_block_factorizer.",
        "# --------------WARNING-----------------",
        f"# Tile: {tile_name}",
        "",
    ]
    for row, sources in connections.items():
        unique_sources = list(dict.fromkeys(sources))
        if len(unique_sources) == 1:
            lines.append(f"{row},{unique_sources[0]}")
        else:
            lines.append(f"{{{len(unique_sources)}}}{row},[{'|'.join(unique_sources)}]")
    return "\n".join(lines) + "\n"


def _rewrite_tile_csv(
    tile_csv: Path,
    switch_matrix_list: Path,
    jump_prefix: str,
    jump_rows: JumpRows,
) -> None:
    """Rewrite tile CSV with generated JUMP rows and active MATRIX line.

    Parameters
    ----------
    tile_csv : Path
        Tile CSV path.
    switch_matrix_list : Path
        Active normalized switch-matrix list path.
    jump_prefix : str
        Prefix for generated JUMP rows from previous runs.
    jump_rows : JumpRows
        Generated JUMP rows for this run.

    Raises
    ------
    FileNotFoundError
        If the tile CSV does not exist.
    ValueError
        If the tile CSV has no MATRIX row.
    """
    if not tile_csv.is_file():
        raise FileNotFoundError(f"tile CSV does not exist: {tile_csv}")

    lines = tile_csv.read_text(encoding="utf-8").splitlines()
    cleaned: list[str] = []
    matrix_inserted = False
    matrix_line = f"MATRIX,./{switch_matrix_list.name}"
    jump_lines = [f"JUMP,{begin},0,0,{end},1," for begin, end in jump_rows]
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"JUMP,{jump_prefix}_"):
            continue
        if stripped.startswith("MATRIX,"):
            cleaned.extend(jump_lines)
            cleaned.append(matrix_line)
            matrix_inserted = True
            continue
        cleaned.append(line)

    if not matrix_inserted:
        raise ValueError(f"tile CSV has no MATRIX row: {tile_csv}")
    tile_csv.write_text("\n".join(cleaned) + "\n", encoding="utf-8")


def _remove_generated_artifacts(
    tile_dir: Path,
    tile_name: str,
    file_extension: str,
) -> None:
    """Remove generated files that FABulous will recreate.

    Parameters
    ----------
    tile_dir : Path
        Tile directory.
    tile_name : str
        Tile name.
    file_extension : str
        FABulous HDL file extension.
    """
    for path in (
        tile_dir / f"{tile_name}_switch_matrix.csv",
        tile_dir / f"{tile_name}_switch_matrix{file_extension}",
        tile_dir / f"{tile_name}_ConfigMem.csv",
        tile_dir / f"{tile_name}_ConfigMem{file_extension}",
        tile_dir / f"{tile_name}{file_extension}",
    ):
        if path.exists():
            path.unlink()


def _run_fabulous_generation(
    fab: FABulous_API,
    tile_name: str,
    tile_dir: Path,
    file_extension: str,
) -> list[SwitchBlockFactorizerArtifact]:
    """Regenerate FABulous outputs for one factorized tile.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.
    tile_name : str
        Tile name.
    tile_dir : Path
        Tile directory.
    file_extension : str
        FABulous HDL file extension.

    Returns
    -------
    list[SwitchBlockFactorizerArtifact]
        Generated artifact records.
    """
    switch_matrix = tile_dir / f"{tile_name}_switch_matrix{file_extension}"
    config_mem = tile_dir / f"{tile_name}_ConfigMem{file_extension}"
    config_mem_csv = tile_dir / f"{tile_name}_ConfigMem.csv"
    tile_rtl = tile_dir / f"{tile_name}{file_extension}"

    fab.setWriterOutputFile(switch_matrix)
    fab.genSwitchMatrix(tile_name)
    fab.setWriterOutputFile(config_mem)
    fab.genConfigMem(tile_name, config_mem_csv)
    fab.setWriterOutputFile(tile_rtl)
    fab.genTile(tile_name)

    return [
        artifact
        for artifact in (
            SwitchBlockFactorizerArtifact(
                kind="switch_matrix_csv",
                path=tile_dir / f"{tile_name}_switch_matrix.csv",
            ),
            SwitchBlockFactorizerArtifact(
                kind="switch_matrix_rtl",
                path=switch_matrix,
            ),
            SwitchBlockFactorizerArtifact(kind="config_mem_csv", path=config_mem_csv),
            SwitchBlockFactorizerArtifact(kind="config_mem_rtl", path=config_mem),
            SwitchBlockFactorizerArtifact(kind="tile_rtl", path=tile_rtl),
        )
        if artifact.path.exists()
    ]


def _check_config_limit(
    total_config_bits: int,
    capacity: int,
    config_bit_margin: int,
) -> None:
    """Check the configured total config-bit limit.

    Parameters
    ----------
    total_config_bits : int
        Total tile config bits after factorization.
    capacity : int
        Total config-bit capacity.
    config_bit_margin : int
        Margin reserved below the maximum.

    Raises
    ------
    RuntimeError
        If the total config bits exceed the configured maximum.
    """
    usable = capacity - config_bit_margin
    if total_config_bits > usable:
        raise RuntimeError(
            f"Tile uses {total_config_bits} config bits, but only {usable} "
            f"of {capacity} are usable with margin {config_bit_margin}."
        )


def _config_capacity(fab: FABulous_API, override: int | None = None) -> int:
    """Return the fabric config-bit capacity for one tile.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.
    override : int | None
        Optional capacity override.

    Returns
    -------
    int
        Config-bit capacity.
    """
    if override is not None:
        return override
    return fab.fabric.frameBitsPerRow * fab.fabric.maxFramesPerCol


def _count_pips(connections: Connections) -> int:
    """Count switch-matrix PIPs.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connectivity.

    Returns
    -------
    int
        Total PIPs.
    """
    return sum(len(sources) for sources in connections.values())


def _max_fanin(connections: Connections) -> int:
    """Return the maximum mux fanin.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connectivity.

    Returns
    -------
    int
        Maximum source count on one row.
    """
    return max((len(sources) for sources in connections.values()), default=0)


def _estimate_config_bits(connections: Connections) -> int:
    """Estimate FABulous switch-matrix configuration bits.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connectivity.

    Returns
    -------
    int
        Estimated config bits.
    """
    return sum(
        (len(sources) - 1).bit_length()
        for sources in connections.values()
        if len(sources) >= 2
    )


def _fanin_histogram(connections: Connections) -> dict[int, int]:
    """Return mux-fanin histogram.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connectivity.

    Returns
    -------
    dict[int, int]
        Mapping from fanin to row count.
    """
    return dict(Counter(len(sources) for sources in connections.values()))


def _count_factorized_rows(original: Connections, transformed: Connections) -> int:
    """Count original rows whose direct source list changed.

    Parameters
    ----------
    original : Connections
        Original connectivity.
    transformed : Connections
        Factorized connectivity.

    Returns
    -------
    int
        Number of factorized original rows.
    """
    return sum(
        1
        for row, sources in original.items()
        if row in transformed and transformed[row] != sources
    )


def _count_hierarchy_pips(connections: Connections, jump_rows: JumpRows) -> int:
    """Count PIPs involving generated hierarchy rows.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connectivity.
    jump_rows : JumpRows
        Generated JUMP rows.

    Returns
    -------
    int
        PIPs connected to generated JUMP stages.
    """
    jump_begins = {f"{begin}0" for begin, _end in jump_rows}
    jump_ends = {f"{end}0" for _begin, end in jump_rows}
    return sum(
        len(sources) for row, sources in connections.items() if row in jump_begins
    ) + sum(
        1
        for sources in connections.values()
        for source in sources
        if source in jump_ends
    )
