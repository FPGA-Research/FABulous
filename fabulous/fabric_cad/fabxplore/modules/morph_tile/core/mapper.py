"""Plan and apply morph-tile replacements for compatible source cells.

The mapper coordinates the morph-tile flow without depending on any concrete netlist
storage format. A reader extracts stable Python objects from the design, this mapper
solves and records replacement decisions, and a writer applies the result to the live
pyosys design object.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphCircuitEnvironment,
    MorphCircuitKind,
    MorphSolveOptions,
    MorphTileContext,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.cut_solver import (
    CutSolver,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileDesign,
    MorphTileReplacement,
    MorphTileResult,
    MorphTileStats,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.process_tracker import (
    MorphTileProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.reader import (
    MorphTileReader,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.registry import (
    build_morph_circuits,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.report import (
    render_morph_tile_report,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.writer import (
    MorphTileWriter,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class MorphTileMapper:
    """Replace implementable source cells with morph-tile instances.

    Parameters
    ----------
    tile_verilog_path : Path
        Verilog source file containing the morph-tile module.
    tile_top_name : str
        Module name to instantiate for replacements.
    tile_inputs : list[str]
        Candidate tile data input ports available to the SAT solver.
    tile_outputs : list[str]
        Candidate tile output ports available to the SAT solver.
    enabled_circuits : list[str | MorphCircuitKind] | None
        Circuit adapters to enable. ``None`` enables only normal ``$lut``.
    circuit_options : dict[str, object] | None
        Generic adapter option payload. Future circuit adapters can read their
        own options from this dictionary without changing mapper orchestration.
    tile_configs : list[str] | None
        Explicit tile configuration input names.
    tile_config_prefixes : list[str] | None
        Prefixes used to detect configuration inputs in BLIF.
    tile_fixed_configs : dict[str, int | bool] | None
        Tile configuration bits fixed before SAT-fab imports the candidate
        BLIF. Fixed bits are also emitted on replacement instances.
    include_unused_inputs : bool
        Whether tile inputs unused by the solved mapping are tied to zero in
        replacement instances.
    max_replacements : int | None
        Optional cap on successful replacements.
    map_luts_first : bool
        Whether to run a simple LUT mapping flow before replacement.
    lut_map_size : int | None
        Maximum LUT size for the optional pre-mapping flow.
    allow_input_reuse : bool
        Whether SAT may map several tile inputs to the same LUT input.
    allow_input_constants : bool
        Whether SAT may tie tile inputs to constants.
    allow_output_reuse : bool
        Whether SAT may reuse tile outputs.
    track_progress : bool
        Whether to log progress updates while candidates are processed.
    progress_chunk_size : int
        Number of processed candidate LUTs between progress updates.
    debug : bool
        Enable verbose pyosys output for internal solver conversions.
    """

    def __init__(
        self,
        tile_verilog_path: Path,
        tile_top_name: str,
        tile_inputs: list[str],
        tile_outputs: list[str],
        enabled_circuits: list[str | MorphCircuitKind] | None = None,
        circuit_options: dict[str, object] | None = None,
        tile_configs: list[str] | None = None,
        tile_config_prefixes: list[str] | None = None,
        tile_fixed_configs: dict[str, int | bool] | None = None,
        include_unused_inputs: bool = False,
        max_replacements: int | None = None,
        map_luts_first: bool = False,
        lut_map_size: int | None = None,
        allow_input_reuse: bool = True,
        allow_input_constants: bool = False,
        allow_output_reuse: bool = False,
        track_progress: bool = True,
        progress_chunk_size: int = 50,
        debug: bool = False,
    ) -> None:
        self.tile_verilog_path = tile_verilog_path
        self.tile_top_name = tile_top_name
        self.tile_inputs = tile_inputs
        self.tile_outputs = tile_outputs
        self.enabled_circuits = enabled_circuits
        self.circuit_options = circuit_options or {}
        self.tile_configs = tile_configs
        self.tile_config_prefixes = tile_config_prefixes
        self.tile_fixed_configs = tile_fixed_configs
        self.include_unused_inputs = include_unused_inputs
        self.max_replacements = max_replacements
        self.map_luts_first = map_luts_first
        self.lut_map_size = lut_map_size
        self.allow_input_reuse = allow_input_reuse
        self.allow_input_constants = allow_input_constants
        self.allow_output_reuse = allow_output_reuse
        self.track_progress = track_progress
        self.progress_chunk_size = progress_chunk_size
        self.debug = debug

        self._design: PyosysBridge | None = None

    def map_from_design(
        self,
        design: PyosysBridge,
        top_name: str | None = None,
    ) -> MorphTileResult:
        """Run morph-tile mapping on a pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Design containing source cells for enabled circuit adapters.
        top_name : str | None
            Top module to process. If ``None``, use the bridge top.

        Returns
        -------
        MorphTileResult
            Structured mapping result and report summary.

        Raises
        ------
        ValueError
            If optional LUT mapping is requested without ``lut_map_size``.
        """
        self._design = design

        selected_top = top_name or design.top_name()
        if self.map_luts_first:
            if self.lut_map_size is None:
                raise ValueError("lut_map_size is required when map_luts_first=True")
            design.run_pass(f"hierarchy -check -top {selected_top}")
            design.run_pass("proc")
            design.run_pass("opt")
            design.run_pass("techmap")
            design.run_pass("opt")
            design.run_pass(f"abc9 -lut {self.lut_map_size}")
            design.run_pass("opt_lut")
            design.run_pass("clean")

        morph_design = MorphTileReader().read_design(design, selected_top)
        result = self.plan(morph_design)
        MorphTileWriter(
            tile_top_name=self.tile_top_name,
            tile_inputs=self.tile_inputs,
            include_unused_inputs=self.include_unused_inputs,
        ).apply(design, result)
        return result

    def plan(
        self,
        morph_design: MorphTileDesign,
    ) -> MorphTileResult:
        """Build a replacement plan for an internal morph-tile design.

        Parameters
        ----------
        morph_design : MorphTileDesign
            Internal design view produced by ``MorphTileReader``.

        Returns
        -------
        MorphTileResult
            Structured replacement plan and report summary.
        """
        solver = CutSolver(
            verilog_path=self.tile_verilog_path,
            top_name=self.tile_top_name,
            inputs=self.tile_inputs,
            outputs=self.tile_outputs,
            configs=self.tile_configs,
            config_prefixes=self.tile_config_prefixes,
            fixed_configs=self.tile_fixed_configs,
            debug=self.debug,
        )
        solve_options = MorphSolveOptions(
            allow_input_reuse=self.allow_input_reuse,
            allow_input_constants=self.allow_input_constants,
            allow_output_reuse=self.allow_output_reuse,
        )
        env = MorphCircuitEnvironment(
            solver=solver,
            solve_options=solve_options,
            tile_inputs=self.tile_inputs,
            tile_outputs=self.tile_outputs,
            include_unused_inputs=self.include_unused_inputs,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
            options={
                "enabled_circuits": self.enabled_circuits,
                "circuit_options": self.circuit_options,
            },
        )
        circuits = build_morph_circuits(
            env=env,
            enabled_circuits=self.enabled_circuits,
            design=self._design,
        )
        context = MorphTileContext(design=morph_design)
        candidate_groups = [
            (circuit, tuple(circuit.iter_candidates(context))) for circuit in circuits
        ]
        side_effect_reports = [
            result.report_summary
            for circuit in circuits
            if (result := circuit.side_effect_result()) is not None
            and hasattr(result, "report_summary")
        ]
        total_candidates = sum(
            len(candidates) for _circuit, candidates in candidate_groups
        )
        checked_candidate_count = sum(
            1
            for circuit, candidates in candidate_groups
            for candidate in candidates
            if circuit.is_enabled_candidate(candidate)
        )
        filter_summary = _merge_filter_summaries(
            circuit.filter_summary() for circuit in circuits
        )

        tracker = MorphTileProcessTracker(
            enabled=self.track_progress,
            chunk_size=self.progress_chunk_size,
        )
        tracker.start(
            top_name=morph_design.top_name,
            total_candidates=total_candidates,
            checked_candidates=checked_candidate_count,
            filter_summary=filter_summary,
        )

        checked_candidates = 0
        failed_candidates = 0
        skipped_candidates = 0
        skipped_filter_candidates = 0
        skipped_limit_candidates = 0
        cache_hits = 0
        cache_misses = 0
        replacements: list[MorphTileReplacement] = []
        replacements_by_width: dict[str, int] = {}
        failures_by_width: dict[str, int] = {}
        mapped_init_count: dict[str, int] = {}

        for circuit, candidates in candidate_groups:
            for candidate in candidates:
                if not circuit.is_enabled_candidate(candidate):
                    skipped_candidates += 1
                    skipped_filter_candidates += 1
                    tracker.skipped_filter()
                    continue
                if (
                    self.max_replacements is not None
                    and len(replacements) >= self.max_replacements
                ):
                    skipped_candidates += 1
                    skipped_limit_candidates += 1
                    tracker.skipped_limit()
                    continue

                checked_candidates += 1
                outcome = circuit.solve(candidate)
                if outcome.cache_hit:
                    cache_hits += 1
                    tracker.cache_hit()
                else:
                    cache_misses += 1
                    tracker.cache_miss()

                if not outcome.result.sat:
                    failed_candidates += 1
                    _increment(failures_by_width, circuit.width_label(candidate))
                    tracker.solved(sat=False)
                    continue

                replacement = circuit.make_replacement(candidate, outcome.result)
                replacements.append(replacement)
                _increment(replacements_by_width, circuit.width_label(candidate))
                _increment(mapped_init_count, circuit.init_label(candidate))
                tracker.solved(sat=True)

        stats = MorphTileStats(
            total_candidates=total_candidates,
            checked_candidates=checked_candidates,
            replaced_candidates=len(replacements),
            failed_candidates=failed_candidates,
            skipped_candidates=skipped_candidates,
            skipped_filter_candidates=skipped_filter_candidates,
            skipped_limit_candidates=skipped_limit_candidates,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            replacements_by_width=replacements_by_width,
            failures_by_width=failures_by_width,
            mapped_init_count=mapped_init_count,
        )
        result = MorphTileResult(
            top_name=morph_design.top_name,
            tile_top_name=self.tile_top_name,
            filter_summary=filter_summary,
            max_replacements=self.max_replacements,
            stats=stats,
            replacements=tuple(replacements),
        )
        report_summary = (
            "\n\n".join(side_effect_reports)
            if side_effect_reports
            else render_morph_tile_report(result)
        )
        result = replace(result, report_summary=report_summary)
        tracker.finish(result)
        return result


def _increment(counts: dict[str, int], label: str) -> None:
    """Increment a histogram entry.

    Parameters
    ----------
    counts : dict[str, int]
        Histogram dictionary to update.
    label : str
        Entry label to increment.
    """
    counts[label] = counts.get(label, 0) + 1


def _merge_filter_summaries(
    summaries: Iterable[dict[str, list[str]]],
) -> dict[str, list[str]]:
    """Merge adapter filter summaries while preserving value order.

    Parameters
    ----------
    summaries : Iterable[dict[str, list[str]]]
        Filter summaries returned by enabled adapters.

    Returns
    -------
    dict[str, list[str]]
        Combined filter summary.
    """
    merged: dict[str, list[str]] = {}
    for summary in summaries:
        for key, values in summary.items():
            target = merged.setdefault(key, [])
            seen = set(target)
            for value in values:
                if value not in seen:
                    target.append(value)
                    seen.add(value)
    return merged
