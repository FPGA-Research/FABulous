"""Factorize FABulous switch-matrix rows into JUMP-based mux stages."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
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
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge
    from fabulous.fabric_definition.tile import Tile
    from fabulous.fabulous_api import FABulous_API


Connections = dict[str, list[str]]
JumpRows = list[tuple[str, str]]


@dataclass(frozen=True, slots=True)
class _ReductionStep:
    """One configured reduction action in cyclic evaluation order."""

    label: str
    rule: MuxReductionRule | None = None
    global_level: int | None = None


@dataclass(frozen=True, slots=True)
class _BudgetReport:
    """Local config-budget accounting for one factorizer run."""

    fixed_config_bits: int
    matrix_config_bits_before: int
    total_config_bits_before: int
    effective_config_bit_limit: int | None
    blocked_reductions: int = 0


class SwitchBlockFactorizer:
    """Factorize active FABulous switch matrices in the graph.

    Parameters
    ----------
    options : SwitchBlockFactorizerOptions
        Normalized factorizer options.
    """

    def __init__(self, options: SwitchBlockFactorizerOptions) -> None:
        self.options = options

    def run(self, fpga_model: PnRBridge) -> SwitchBlockFactorizerResult:
        """Run switch-block factorization on the active routing graph.

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
            If reachability is not preserved.
        """
        tracker = SwitchBlockFactorizerProcessTracker(
            enabled=self.options.track_progress
        )
        tracker.start(self.options.tile_name)

        switch_matrix = fpga_model.switch_matrix(self.options.tile_name)
        connections, base_rows, base_columns, delays = _connections_from_matrix(
            switch_matrix
        )
        before_connections = _copy_connections(connections)
        current_config = fpga_model.get_config_bits(self.options.tile_name)
        transformed, jump_rows, warnings, budget = _factorize_connections(
            connections,
            self.options,
            fixed_config_bits=current_config.fixed_config_bits,
        )

        if not _preserves_reachability(before_connections, transformed, jump_rows):
            raise RuntimeError(
                "switch-block factorization did not preserve reachability."
            )

        for begin, end in jump_rows:
            fpga_model.add_external_resource(
                self.options.tile_name,
                Direction.JUMP,
                begin,
                0,
                0,
                end,
                1,
            )

        columns, rows, matrix = _matrix_from_connections(
            transformed,
            base_rows=base_rows,
            base_columns=base_columns,
            delays=delays,
        )
        fpga_model.set_switch_matrix(
            self.options.tile_name,
            columns,
            rows,
            matrix,
        )

        after_config = fpga_model.get_config_bits(self.options.tile_name)
        stats = SwitchBlockFactorizerStats(
            mux_rows_before=len(before_connections),
            mux_rows_after=len(transformed),
            pips_before=_count_pips(before_connections),
            pips_after=_count_pips(transformed),
            max_fanin_before=_max_fanin(before_connections),
            max_fanin_after=_max_fanin(transformed),
            matrix_config_bits_before=budget.matrix_config_bits_before,
            matrix_config_bits_after=after_config.matrix_config_bits,
            fixed_config_bits=budget.fixed_config_bits,
            total_config_bits_before=budget.total_config_bits_before,
            total_config_bits_after=after_config.total_config_bits,
            effective_config_bit_limit=budget.effective_config_bit_limit,
            blocked_reductions=budget.blocked_reductions,
            added_jump_wires=len(jump_rows),
            factorized_rows=_count_factorized_rows(before_connections, transformed),
            generated_hierarchy_pips=_count_hierarchy_pips(transformed, jump_rows),
            fanin_histogram_before=_fanin_histogram(before_connections),
            fanin_histogram_after=_fanin_histogram(transformed),
            reachability_preserved=True,
        )

        result = SwitchBlockFactorizerResult(
            options=self.options,
            tile_name=self.options.tile_name,
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


def _connections_from_matrix(
    switch_matrix: object,
) -> tuple[Connections, list[str], list[str], dict[tuple[str, str], float]]:
    """Extract active connections from a graph switch-matrix view.

    Parameters
    ----------
    switch_matrix : object
        Graph switch-matrix object with ``rows``, ``columns``, and ``matrix``.

    Returns
    -------
    tuple[Connections, list[str], list[str], dict[tuple[str, str], float]]
        Active connections, original row labels, original column labels, and
        per-PIP delays.
    """
    connections: Connections = {}
    delays: dict[tuple[str, str], float] = {}
    rows = list(switch_matrix.rows)
    columns = list(switch_matrix.columns)
    for row_index, row in enumerate(rows):
        sources: list[str] = []
        for column_index, column in enumerate(columns):
            delay = float(switch_matrix.matrix[row_index][column_index])
            if delay <= 0:
                continue
            sources.append(column)
            delays[(row, column)] = delay
        if sources:
            connections[row] = sources
    return connections, rows, columns, delays


def _factorize_connections(
    connections: Connections,
    options: SwitchBlockFactorizerOptions,
    *,
    fixed_config_bits: int,
) -> tuple[Connections, JumpRows, list[str], _BudgetReport]:
    """Factorize connections with local config-budget checks.

    Parameters
    ----------
    connections : Connections
        Original connectivity.
    options : SwitchBlockFactorizerOptions
        Factorizer options.
    fixed_config_bits : int
        Non-matrix config bits preserved from the graph tile model.

    Returns
    -------
    tuple[Connections, JumpRows, list[str], _BudgetReport]
        Factorized connectivity, generated JUMP rows, warnings, and budget
        accounting.
    """
    state = _copy_connections(connections)
    jump_rows: JumpRows = []
    warnings: list[str] = []
    counter = _next_jump_counter(state, options.jump_prefix)
    blocked_reductions = 0
    start_matrix_bits = _estimate_config_bits(state)
    start_total_bits = start_matrix_bits + fixed_config_bits
    effective_limit = _effective_config_bit_limit(start_total_bits, options)
    steps = _reduction_steps(options)

    if not steps:
        warnings.append("No reduction steps were configured.")
        return (
            state,
            jump_rows,
            warnings,
            _BudgetReport(
                fixed_config_bits=fixed_config_bits,
                matrix_config_bits_before=start_matrix_bits,
                total_config_bits_before=start_total_bits,
                effective_config_bit_limit=effective_limit,
            ),
        )

    while True:
        accepted_in_round = False
        for step in steps:
            move = _first_accepted_move(
                connections=state,
                options=options,
                step=step,
                jump_rows=jump_rows,
                counter=counter,
                fixed_config_bits=fixed_config_bits,
                effective_limit=effective_limit,
            )
            if move is None:
                blocked_reductions += _count_blocked_moves(
                    connections=state,
                    options=options,
                    step=step,
                    jump_rows=jump_rows,
                    counter=counter,
                    fixed_config_bits=fixed_config_bits,
                    effective_limit=effective_limit,
                )
                continue
            state, new_jump_rows, counter = move
            jump_rows.extend(new_jump_rows)
            accepted_in_round = True
        if not accepted_in_round:
            break

    if not jump_rows:
        warnings.append("No mux rows met the configured factorization criteria.")
    if blocked_reductions:
        warnings.append(
            f"Skipped {blocked_reductions} candidate reduction(s) that exceeded "
            "the configured graph-local limits."
        )
    return (
        state,
        jump_rows,
        warnings,
        _BudgetReport(
            fixed_config_bits=fixed_config_bits,
            matrix_config_bits_before=start_matrix_bits,
            total_config_bits_before=start_total_bits,
            effective_config_bit_limit=effective_limit,
            blocked_reductions=blocked_reductions,
        ),
    )


def _reduction_steps(options: SwitchBlockFactorizerOptions) -> list[_ReductionStep]:
    """Return configured reduction steps in cyclic order.

    Parameters
    ----------
    options : SwitchBlockFactorizerOptions
        Factorizer options.

    Returns
    -------
    list[_ReductionStep]
        Ordered reduction steps.
    """
    steps: list[_ReductionStep] = []
    if options.global_reduction is not None:
        steps.extend(
            _ReductionStep(label=f"G{level}", global_level=level)
            for level in range(options.global_reduction)
        )
    steps.extend(
        _ReductionStep(label=f"R{index}", rule=rule)
        for index, rule in enumerate(options.reduction_rules)
    )
    return steps


def _effective_config_bit_limit(
    total_config_bits_before: int,
    options: SwitchBlockFactorizerOptions,
) -> int | None:
    """Return the active graph-local config-bit budget.

    Parameters
    ----------
    total_config_bits_before : int
        Total config bits before factorization.
    options : SwitchBlockFactorizerOptions
        Factorizer options.

    Returns
    -------
    int | None
        Effective limit, or ``None`` when no config-bit budget is configured.
    """
    limits: list[int] = []
    if options.config_bit_margin is not None:
        limits.append(total_config_bits_before + options.config_bit_margin)
    if options.config_bit_limit is not None:
        limits.append(options.config_bit_limit)
    return min(limits) if limits else None


def _first_accepted_move(
    *,
    connections: Connections,
    options: SwitchBlockFactorizerOptions,
    step: _ReductionStep,
    jump_rows: JumpRows,
    counter: int,
    fixed_config_bits: int,
    effective_limit: int | None,
) -> tuple[Connections, JumpRows, int] | None:
    """Return the first factorization move accepted by configured limits.

    Parameters
    ----------
    connections : Connections
        Current local connectivity.
    options : SwitchBlockFactorizerOptions
        Factorizer options.
    step : _ReductionStep
        Reduction step to try.
    jump_rows : JumpRows
        Already accepted generated JUMP rows.
    counter : int
        Next generated JUMP counter.
    fixed_config_bits : int
        Non-matrix config bits.
    effective_limit : int | None
        Optional total config-bit budget.

    Returns
    -------
    tuple[Connections, JumpRows, int] | None
        Accepted connectivity, newly generated JUMP rows, and next counter.
        ``None`` means no eligible move fit the configured limits.
    """
    for row, sources in connections.items():
        candidate = _candidate_factorization(
            connections=connections,
            options=options,
            step=step,
            row=row,
            sources=sources,
            counter=counter,
        )
        if candidate is None:
            continue
        candidate_connections, new_jump_rows, next_counter = candidate
        if _exceeds_limits(
            connections=candidate_connections,
            jump_count=len(jump_rows) + len(new_jump_rows),
            options=options,
            fixed_config_bits=fixed_config_bits,
            effective_limit=effective_limit,
        ):
            continue
        return candidate_connections, new_jump_rows, next_counter
    return None


def _count_blocked_moves(
    *,
    connections: Connections,
    options: SwitchBlockFactorizerOptions,
    step: _ReductionStep,
    jump_rows: JumpRows,
    counter: int,
    fixed_config_bits: int,
    effective_limit: int | None,
) -> int:
    """Count eligible moves rejected by configured limits.

    Parameters
    ----------
    connections : Connections
        Current local connectivity.
    options : SwitchBlockFactorizerOptions
        Factorizer options.
    step : _ReductionStep
        Reduction step to try.
    jump_rows : JumpRows
        Already accepted generated JUMP rows.
    counter : int
        Next generated JUMP counter.
    fixed_config_bits : int
        Non-matrix config bits.
    effective_limit : int | None
        Optional total config-bit budget.

    Returns
    -------
    int
        Number of eligible moves rejected by limits.
    """
    blocked = 0
    for row, sources in connections.items():
        candidate = _candidate_factorization(
            connections=connections,
            options=options,
            step=step,
            row=row,
            sources=sources,
            counter=counter,
        )
        if candidate is None:
            continue
        candidate_connections, new_jump_rows, _next_counter = candidate
        if _exceeds_limits(
            connections=candidate_connections,
            jump_count=len(jump_rows) + len(new_jump_rows),
            options=options,
            fixed_config_bits=fixed_config_bits,
            effective_limit=effective_limit,
        ):
            blocked += 1
    return blocked


def _candidate_factorization(
    *,
    connections: Connections,
    options: SwitchBlockFactorizerOptions,
    step: _ReductionStep,
    row: str,
    sources: list[str],
    counter: int,
) -> tuple[Connections, JumpRows, int] | None:
    """Build one candidate row factorization.

    Parameters
    ----------
    connections : Connections
        Current local connectivity.
    options : SwitchBlockFactorizerOptions
        Factorizer options.
    step : _ReductionStep
        Reduction step to try.
    row : str
        Candidate matrix row.
    sources : list[str]
        Current row sources.
    counter : int
        Next generated JUMP counter.

    Returns
    -------
    tuple[Connections, JumpRows, int] | None
        Candidate connectivity, generated JUMP rows, and next counter.
    """
    target_fanin = _target_fanin_for_step(row, sources, step, options)
    if target_fanin is None:
        return None
    replacement, new_jump_rows, next_counter = _factorize_row(
        row=row,
        sources=sources,
        target_fanin=target_fanin,
        jump_prefix=options.jump_prefix,
        counter=counter,
        stage_label=step.label,
    )
    if not new_jump_rows:
        return None
    next_connections: Connections = {}
    for current_row, current_sources in connections.items():
        if current_row == row:
            next_connections.update(replacement)
        else:
            next_connections[current_row] = list(current_sources)
    return next_connections, new_jump_rows, next_counter


def _target_fanin_for_step(
    row: str,
    sources: list[str],
    step: _ReductionStep,
    options: SwitchBlockFactorizerOptions,
) -> int | None:
    """Return the target fanin for a row and reduction step.

    Parameters
    ----------
    row : str
        Candidate matrix row.
    sources : list[str]
        Current row sources.
    step : _ReductionStep
        Reduction step to try.
    options : SwitchBlockFactorizerOptions
        Factorizer options.

    Returns
    -------
    int | None
        Target fanin, or ``None`` when the step does not apply.
    """
    if len(sources) < options.min_mux_fanin_to_factorize:
        return None
    if step.rule is not None:
        if len(sources) != step.rule.from_fanin:
            return None
        return step.rule.to_fanin
    if len(sources) <= 2:
        return None
    if step.global_level is not None and (
        _global_depth(row, options.jump_prefix) != step.global_level
    ):
        return None
    return math.ceil(len(sources) / 2)


def _global_depth(row: str, jump_prefix: str) -> int | None:
    """Return how many global stages produced a generated row.

    Parameters
    ----------
    row : str
        Matrix row name.
    jump_prefix : str
        Generated JUMP prefix.

    Returns
    -------
    int | None
        ``0`` for original rows, ``1`` for ``G0`` rows, and so on. ``None``
        means the row was generated by a non-global factorizer stage.
    """
    if row.startswith(f"{jump_prefix}_") and not row.startswith(f"{jump_prefix}_G"):
        return None
    pattern = re.compile(rf"^{re.escape(jump_prefix)}_G(\d+)_")
    match = pattern.match(row)
    if match is None:
        return 0
    return int(match.group(1)) + 1


def _exceeds_limits(
    *,
    connections: Connections,
    jump_count: int,
    options: SwitchBlockFactorizerOptions,
    fixed_config_bits: int,
    effective_limit: int | None,
) -> bool:
    """Return whether a candidate exceeds local guardrails.

    Parameters
    ----------
    connections : Connections
        Candidate local connectivity.
    jump_count : int
        Candidate generated JUMP count.
    options : SwitchBlockFactorizerOptions
        Factorizer options.
    fixed_config_bits : int
        Non-matrix config bits.
    effective_limit : int | None
        Optional total config-bit budget.

    Returns
    -------
    bool
        ``True`` when the candidate exceeds a configured limit.
    """
    if (
        options.max_added_jump_wires is not None
        and jump_count > options.max_added_jump_wires
    ):
        return True
    if effective_limit is None:
        return False
    return _estimate_config_bits(connections) + fixed_config_bits > effective_limit


def _next_jump_counter(connections: Connections, jump_prefix: str) -> int:
    """Return the next generated JUMP counter for a prefix.

    Parameters
    ----------
    connections : Connections
        Current local connectivity.
    jump_prefix : str
        Generated JUMP prefix.

    Returns
    -------
    int
        Next unused counter.
    """
    pattern = re.compile(rf"^{re.escape(jump_prefix)}_[GR]\d+_(\d+)_(?:BEG|END)0$")
    counters: list[int] = []
    for row, sources in connections.items():
        names = [row, *sources]
        for name in names:
            match = pattern.match(name)
            if match is not None:
                counters.append(int(match.group(1)))
    return max(counters, default=-1) + 1


def _matrix_from_connections(
    connections: Connections,
    *,
    base_rows: list[str],
    base_columns: list[str],
    delays: dict[tuple[str, str], float],
    default_delay: float = 8.0,
) -> tuple[list[str], list[str], list[list[float]]]:
    """Build a graph switch-matrix table from local connections.

    Parameters
    ----------
    connections : Connections
        Active local connectivity.
    base_rows : list[str]
        Existing graph matrix rows to preserve.
    base_columns : list[str]
        Existing graph matrix columns to preserve.
    delays : dict[tuple[str, str], float]
        Original active PIP delays.
    default_delay : float
        Delay assigned to generated PIPs.

    Returns
    -------
    tuple[list[str], list[str], list[list[float]]]
        Columns, rows, and delay matrix for ``set_switch_matrix``.
    """
    rows = list(dict.fromkeys([*base_rows, *connections.keys()]))
    columns = list(
        dict.fromkeys(
            [
                *base_columns,
                *(source for sources in connections.values() for source in sources),
            ]
        )
    )
    row_index = {row: index for index, row in enumerate(rows)}
    column_index = {column: index for index, column in enumerate(columns)}
    matrix = [[0.0 for _column in columns] for _row in rows]
    for row, sources in connections.items():
        for source in sources:
            matrix[row_index[row]][column_index[source]] = delays.get(
                (row, source),
                default_delay,
            )
    return columns, rows, matrix


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
        if len(chunk) == 1:
            final_sources.append(chunk[0])
            continue
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
