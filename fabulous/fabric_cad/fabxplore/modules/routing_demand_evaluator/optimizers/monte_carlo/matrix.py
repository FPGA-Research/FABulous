"""Matrix helpers local to the Monte Carlo optimizer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
    MatrixData,
    MuxBucketStats,
    MuxCleanupRowStats,
    MuxCleanupStats,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
    RoutingGraph,
    RoutingGraphBuilder,
)
from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer.core.factorizer import (  # noqa: E501
    _remove_generated_artifacts,
    _run_fabulous_generation,
)
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.base import (  # noqa: E501
        OptimizerContext,
    )

Connections = dict[str, list[str]]
Pip = tuple[str, str]
ImportanceByPip = dict[Pip, float]
ImportanceMatrix = dict[str, dict[str, float]]


@dataclass(frozen=True)
class MonteCarloLimits:
    """Failure-rate limits for one optimizer run.

    Attributes
    ----------
    hard : float
        Allowed hard-demand failure rate.
    soft : float
        Allowed soft-demand failure rate.
    """

    hard: float
    soft: float


@dataclass
class MonteCarloCounters:
    """Mutable Monte Carlo optimizer counters.

    Attributes
    ----------
    iterations : int
        Total demand-oracle evaluations consumed by the optimizer.
    learning_iterations : int
        Temporary ablation evaluations used for importance learning.
    pruning_iterations : int
        Checked pruning evaluations.
    attempted_batches : int
        Candidate pruning batches evaluated.
    accepted_batches : int
        Candidate pruning batches accepted.
    rejected_batches : int
        Candidate pruning batches rejected.
    attempted_pips : int
        Candidate PIP removals attempted.
    accepted_pips : int
        Candidate PIP removals accepted.
    rejected_pips : int
        Candidate PIP removals rejected.
    sampled_batches : int
        Temporary ablation batches evaluated.
    importance_rounds : int
        Importance estimation rounds completed.
    best_iteration : int | None
        Iteration that produced the best accepted result.
    average_sample_loss : float
        Average loss observed during importance learning.
    max_sample_loss : float
        Maximum loss observed during importance learning.
    weight_change_rate : float
        Relative importance-weight change at the end of learning.
    sampled_pips : int
        Removable PIPs seen in at least one learning sample.
    unsampled_pips : int
        Removable PIPs not seen in learning samples.
    sampled_pip_rate : float
        Fraction of removable PIPs sampled during learning.
    min_samples_per_pip : int
        Minimum learning sample count across removable PIPs.
    average_samples_per_pip : float
        Average learning sample count across removable PIPs.
    max_samples_per_pip : int
        Maximum learning sample count across removable PIPs.
    """

    iterations: int = 0
    learning_iterations: int = 0
    pruning_iterations: int = 0
    attempted_batches: int = 0
    accepted_batches: int = 0
    rejected_batches: int = 0
    attempted_pips: int = 0
    accepted_pips: int = 0
    rejected_pips: int = 0
    sampled_batches: int = 0
    importance_rounds: int = 0
    best_iteration: int | None = None
    average_sample_loss: float = 0.0
    max_sample_loss: float = 0.0
    weight_change_rate: float = 0.0
    sampled_pips: int = 0
    unsampled_pips: int = 0
    sampled_pip_rate: float = 0.0
    min_samples_per_pip: int = 0
    average_samples_per_pip: float = 0.0
    max_samples_per_pip: int = 0


@dataclass(frozen=True)
class CandidateBatch:
    """One Monte Carlo pruning candidate.

    Attributes
    ----------
    pips : list[Pip]
        Candidate PIPs to remove.
    mux_cost_saved : int
        Estimated mux cost saved by this batch.
    config_bits_saved : int
        Estimated config bits saved by this batch.
    normalizes_power_of_two : bool
        Whether the batch removes a non-power-of-two mux row.
    """

    pips: list[Pip]
    mux_cost_saved: int = 0
    config_bits_saved: int = 0
    normalizes_power_of_two: bool = False


@dataclass(frozen=True)
class MonteCarloHyperParameters:
    """Internal Monte Carlo tuning constants.

    Attributes
    ----------
    learning_batch_size : int
        Number of PIPs in one temporary learning ablation.
    pruning_batch_size : int
        Maximum number of non-mux PIPs in one pruning candidate.
    pruning_candidate_pool_size : int
        Number of random non-mux pruning batches to rank per round.
    near_limit_pressure : float
        Failure-limit pressure where pruning batches are shrunk.
    critical_limit_pressure : float
        Failure-limit pressure where non-mux pruning becomes single-PIP.
    gradient_learning_rate : float
        Learning rate for the default online importance learner.
    rejected_penalty_rate : float
        Penalty scale for rejected pruning batches.
    high_loss_refinement_ratio : float
        Loss multiple over the running average that triggers attribution splits.
    high_loss_refinement_min_loss : float
        Minimum loss that can trigger attribution splits.
    """

    learning_batch_size: int = 8
    pruning_batch_size: int = 8
    pruning_candidate_pool_size: int = 32
    near_limit_pressure: float = 0.85
    critical_limit_pressure: float = 0.95
    gradient_learning_rate: float = 0.25
    rejected_penalty_rate: float = 1.0
    high_loss_refinement_ratio: float = 2.0
    high_loss_refinement_min_loss: float = 1.0


def copy_connections(connections: Connections) -> Connections:
    """Return a deep copy of switch-matrix connections.

    Parameters
    ----------
    connections : Connections
        Matrix connections.

    Returns
    -------
    Connections
        Copied connections.
    """
    return {sink: list(sources) for sink, sources in connections.items()}


def routing_pip_count(connections: Connections) -> int:
    """Return the number of switch-matrix routing PIPs.

    Parameters
    ----------
    connections : Connections
        Matrix connections.

    Returns
    -------
    int
        Routing PIP count.
    """
    return sum(len(sources) for sources in connections.values())


def remove_pips(connections: Connections, pips: list[Pip]) -> Connections:
    """Return connections with selected PIPs removed.

    Parameters
    ----------
    connections : Connections
        Current matrix connections.
    pips : list[Pip]
        PIPs to remove.

    Returns
    -------
    Connections
        Updated connections.
    """
    remove_by_row: dict[str, set[str]] = {}
    for source, row in pips:
        remove_by_row.setdefault(row, set()).add(source)
    return {
        row: [
            source for source in sources if source not in remove_by_row.get(row, set())
        ]
        for row, sources in connections.items()
    }


def remove_emptying_pips(connections: Connections, pips: list[Pip]) -> list[Pip]:
    """Filter removals so every row keeps at least one input.

    Parameters
    ----------
    connections : Connections
        Current matrix connections.
    pips : list[Pip]
        Candidate PIPs to remove.

    Returns
    -------
    list[Pip]
        PIPs that can be removed without emptying a row.
    """
    remaining_by_row = {row: len(sources) for row, sources in connections.items()}
    removable: list[Pip] = []
    for source, row in pips:
        if remaining_by_row.get(row, 0) <= 1:
            continue
        remaining_by_row[row] -= 1
        removable.append((source, row))
    return removable


def build_graph(matrix: MatrixData, connections: Connections) -> RoutingGraph:
    """Build a routing graph from candidate switch-matrix connections.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix metadata.
    connections : Connections
        Candidate switch-matrix connections.

    Returns
    -------
    RoutingGraph
        Candidate routing graph.
    """
    builder = RoutingGraphBuilder()
    builder.add_connection_rows(connections)
    builder.add_jump_edges(matrix.jump_edges)
    return builder.build()


def target_reached(
    removed_pips: int,
    target_remove: int,
) -> bool:
    """Return whether the optimizer stop target is satisfied.

    Parameters
    ----------
    removed_pips : int
        Accepted removed PIPs.
    target_remove : int
        Target number of PIPs to remove.

    Returns
    -------
    bool
        Whether pruning can stop.
    """
    return removed_pips >= target_remove


def target_mux_fanin(fanin: int) -> int:
    """Return the next lower mux fanin target.

    Parameters
    ----------
    fanin : int
        Current row fanin.

    Returns
    -------
    int
        Target fanin.
    """
    if fanin <= 1:
        return fanin
    return 2 ** ((fanin - 1).bit_length() - 1)


def is_allowed_mux_fanin(fanin: int) -> bool:
    """Return whether a fanin is direct or power-of-two sized.

    Parameters
    ----------
    fanin : int
        Row fanin.

    Returns
    -------
    bool
        Whether the row size is allowed.
    """
    return fanin <= 1 or fanin.bit_count() == 1


def non_power_of_two_mux_count(connections: Connections) -> int:
    """Return the count of non-power-of-two mux rows.

    Parameters
    ----------
    connections : Connections
        Matrix connections.

    Returns
    -------
    int
        Non-power-of-two row count.
    """
    return sum(
        1
        for sources in connections.values()
        if len(sources) > 1 and not is_allowed_mux_fanin(len(sources))
    )


def estimate_config_bits(connections: Connections) -> int:
    """Estimate FABulous switch-matrix selector bits.

    Parameters
    ----------
    connections : Connections
        Matrix connections.

    Returns
    -------
    int
        Estimated selector bits.
    """
    return sum(
        mux_config_bits(len(sources))
        for sources in connections.values()
        if len(sources) >= 2
    )


def mux_cleanup_stats(
    baseline_connections: Connections,
    final_connections: Connections,
    baseline_config_bits: int,
    final_config_bits: int,
) -> MuxCleanupStats:
    """Return mux bucket/cost statistics for accepted pruning.

    Parameters
    ----------
    baseline_connections : Connections
        Baseline connections.
    final_connections : Connections
        Final accepted connections.
    baseline_config_bits : int
        Baseline matrix config bits.
    final_config_bits : int
        Final matrix config bits.

    Returns
    -------
    MuxCleanupStats
        Mux cleanup statistics.
    """
    baseline_hist = mux_bucket_histogram(baseline_connections)
    final_hist = mux_bucket_histogram(final_connections)
    buckets = [
        MuxBucketStats(
            bucket=bucket,
            before_rows=baseline_hist.get(bucket, 0),
            after_rows=final_hist.get(bucket, 0),
        )
        for bucket in ["direct", "mux2", "mux4", "mux8", "mux16", "mux32+"]
        if baseline_hist.get(bucket, 0) or final_hist.get(bucket, 0)
    ]
    changed_rows: list[MuxCleanupRowStats] = []
    for row in sorted(set(baseline_connections) | set(final_connections)):
        before = len(baseline_connections.get(row, []))
        after = len(final_connections.get(row, []))
        before_bucket = mux_bucket_label(before)
        after_bucket = mux_bucket_label(after)
        if before_bucket == after_bucket:
            continue
        changed_rows.append(
            MuxCleanupRowStats(
                row=row,
                fanin_before=before,
                fanin_after=after,
                bucket_before=before_bucket,
                bucket_after=after_bucket,
                removed_pips=max(before - after, 0),
                config_bits_saved=max(
                    mux_config_bits(before) - mux_config_bits(after),
                    0,
                ),
                mux_cost_saved=max(mux_cost(before) - mux_cost(after), 0),
            )
        )
    baseline_cost = total_mux_cost(baseline_connections)
    final_cost = total_mux_cost(final_connections)
    return MuxCleanupStats(
        baseline_mux_cost=baseline_cost,
        final_mux_cost=final_cost,
        mux_cost_reduction=(
            (baseline_cost - final_cost) / baseline_cost if baseline_cost else 0.0
        ),
        rows_crossing_thresholds=len(changed_rows),
        direct_wire_conversions=sum(
            1 for row in changed_rows if row.bucket_after == "direct"
        ),
        config_bit_reduction=max(baseline_config_bits - final_config_bits, 0),
        non_power_of_two_mux_rows_before=non_power_of_two_mux_count(
            baseline_connections
        ),
        non_power_of_two_mux_rows_after=non_power_of_two_mux_count(final_connections),
        buckets=buckets,
        changed_rows=sorted(
            changed_rows,
            key=lambda row: (
                -row.mux_cost_saved,
                -row.config_bits_saved,
                -row.removed_pips,
                row.row,
            ),
        ),
    )


def mux_bucket_histogram(connections: Connections) -> dict[str, int]:
    """Return row counts by mux implementation bucket.

    Parameters
    ----------
    connections : Connections
        Matrix connections.

    Returns
    -------
    dict[str, int]
        Row counts keyed by bucket label.
    """
    histogram: dict[str, int] = {}
    for sources in connections.values():
        bucket = mux_bucket_label(len(sources))
        histogram[bucket] = histogram.get(bucket, 0) + 1
    return histogram


def total_mux_cost(connections: Connections) -> int:
    """Return estimated padded mux-input cost for all rows.

    Parameters
    ----------
    connections : Connections
        Matrix connections.

    Returns
    -------
    int
        Estimated mux cost.
    """
    return sum(mux_cost(len(sources)) for sources in connections.values())


def mux_bucket_label(fanin: int) -> str:
    """Return the implementation bucket label for one fanin.

    Parameters
    ----------
    fanin : int
        Row fanin.

    Returns
    -------
    str
        Bucket label.
    """
    cost = mux_cost(fanin)
    if cost == 0:
        return "direct"
    if cost > 32:
        return "mux32+"
    return f"mux{cost}"


def mux_cost(fanin: int) -> int:
    """Return padded mux input count, or zero for direct rows.

    Parameters
    ----------
    fanin : int
        Row fanin.

    Returns
    -------
    int
        Padded mux input count.
    """
    if fanin <= 1:
        return 0
    return 2 ** (fanin - 1).bit_length()


def mux_config_bits(fanin: int) -> int:
    """Return selector bits needed for a row.

    Parameters
    ----------
    fanin : int
        Row fanin.

    Returns
    -------
    int
        Selector bit count.
    """
    if fanin <= 1:
        return 0
    return (fanin - 1).bit_length()


def build_importance_matrix(
    baseline_connections: Connections,
    importance_by_pip: ImportanceByPip,
) -> ImportanceMatrix:
    """Return row/source PIP importance values.

    Parameters
    ----------
    baseline_connections : Connections
        Baseline switch-matrix connections.
    importance_by_pip : ImportanceByPip
        Importance values keyed by ``(source, row)``.

    Returns
    -------
    ImportanceMatrix
        Nested importance matrix.
    """
    return {
        row: {source: importance_by_pip.get((source, row), 0.0) for source in sources}
        for row, sources in baseline_connections.items()
    }


def write_back(
    context: OptimizerContext,
    connections: Connections,
    importance_by_pip: ImportanceByPip,
) -> Path:
    """Write optimized list files and the PIP importance matrix.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    connections : Connections
        Accepted optimized connections.
    importance_by_pip : ImportanceByPip
        PIP importance values.

    Returns
    -------
    Path
        Written importance matrix text file.
    """
    output_list = (
        context.matrix.tile_dir / f"{context.matrix.tile_name}_switch_matrix.list"
    )
    output_list.write_text(
        render_list(context.matrix.tile_name, connections),
        encoding="utf-8",
    )
    importance_file = write_importance_matrix(
        context.matrix.tile_dir,
        context.matrix.tile_name,
        context.matrix.connections,
        importance_by_pip,
    )
    rewrite_matrix_row(context.matrix.tile_csv, output_list)
    _remove_generated_artifacts(
        context.matrix.tile_dir,
        context.matrix.tile_name,
        context.fab.fileExtension,
    )
    context.fab.loadFabric(get_context().proj_dir / "fabric.csv")
    _run_fabulous_generation(
        fab=context.fab,
        tile_name=context.matrix.tile_name,
        tile_dir=context.matrix.tile_dir,
        file_extension=context.fab.fileExtension,
    )
    return importance_file


def render_list(tile_name: str, connections: Connections) -> str:
    """Render FABulous switch-matrix list text.

    Parameters
    ----------
    tile_name : str
        Tile name.
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    str
        List-file contents.
    """
    lines = [
        "# --------------WARNING-----------------",
        "# This is a generated list file!",
        "# Your changes will be overwritten!",
        "# Generated by fabxplore routing_demand_evaluator monte_carlo optimizer.",
        "# --------------WARNING-----------------",
        f"# Tile: {tile_name}",
        "",
    ]
    for row, sources in connections.items():
        unique_sources = list(dict.fromkeys(sources))
        if not unique_sources:
            continue
        if len(unique_sources) == 1:
            lines.append(f"{row},{unique_sources[0]}")
        else:
            lines.append(f"{{{len(unique_sources)}}}{row},[{'|'.join(unique_sources)}]")
    return "\n".join(lines) + "\n"


def rewrite_matrix_row(tile_csv: Path, switch_matrix_list: Path) -> None:
    """Point a tile CSV at the optimized switch-matrix list.

    Parameters
    ----------
    tile_csv : Path
        Tile CSV path.
    switch_matrix_list : Path
        Optimized switch-matrix list.

    Raises
    ------
    ValueError
        If no MATRIX row exists.
    """
    lines = tile_csv.read_text(encoding="utf-8").splitlines()
    rewritten: list[str] = []
    matrix_seen = False
    for line in lines:
        if line.strip().startswith("MATRIX,"):
            rewritten.append(f"MATRIX,./{switch_matrix_list.name}")
            matrix_seen = True
        else:
            rewritten.append(line)
    if not matrix_seen:
        raise ValueError(f"tile CSV has no MATRIX row: {tile_csv}")
    tile_csv.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def write_importance_matrix(
    tile_dir: Path,
    tile_name: str,
    baseline_connections: Connections,
    importance_by_pip: ImportanceByPip,
) -> Path:
    """Write a CSV-shaped importance matrix with a ``.txt`` extension.

    Parameters
    ----------
    tile_dir : Path
        Tile directory.
    tile_name : str
        Tile name.
    baseline_connections : Connections
        Baseline switch-matrix connections.
    importance_by_pip : ImportanceByPip
        PIP importance values.

    Returns
    -------
    Path
        Written matrix path.
    """
    path = tile_dir / f"{tile_name}_pip_importance.txt"
    path.write_text(
        render_importance_matrix(tile_name, baseline_connections, importance_by_pip),
        encoding="utf-8",
    )
    return path


def render_importance_matrix(
    tile_name: str,
    baseline_connections: Connections,
    importance_by_pip: ImportanceByPip,
) -> str:
    """Render a CSV-shaped PIP importance matrix.

    Parameters
    ----------
    tile_name : str
        Tile name.
    baseline_connections : Connections
        Baseline switch-matrix connections.
    importance_by_pip : ImportanceByPip
        PIP importance values.

    Returns
    -------
    str
        CSV-shaped text.
    """
    columns = sorted(
        {source for sources in baseline_connections.values() for source in sources}
    )
    lines = [
        "# Generated by fabxplore routing_demand_evaluator monte_carlo optimizer.",
        f"# Tile: {tile_name}",
        "row," + ",".join(columns),
    ]
    for row in sorted(baseline_connections):
        sources = set(baseline_connections[row])
        cells = [
            f"{importance_by_pip.get((source, row), 0.0):.8f}"
            if source in sources
            else ""
            for source in columns
        ]
        lines.append(row + "," + ",".join(cells))
    return "\n".join(lines) + "\n"
