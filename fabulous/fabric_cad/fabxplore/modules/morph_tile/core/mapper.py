"""Plan and apply morph-tile replacements for compatible LUT cells.

The mapper coordinates the morph-tile flow without depending on any concrete netlist
storage format. A reader extracts stable Python objects from the design, this mapper
solves and records replacement decisions, and a writer applies the result to the live
pyosys design object.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.canonical import (
    canonicalize_lut_init,
    remap_cut_solve_result,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.cut_solver import (
    CutSolver,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    CutSolveResult,
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
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.report import (
    render_morph_tile_report,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.writer import (
    MorphTileWriter,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class MorphTileMapper:
    """Replace implementable ``$lut`` cells with morph-tile instances.

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
    considered_lut_widths : list[int]
        LUT widths that should be checked for replacement.
    tile_configs : list[str] | None
        Explicit tile configuration input names.
    tile_config_prefixes : list[str] | None
        Prefixes used to detect configuration inputs in BLIF.
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
    use_canonical_cache : bool
        Whether cache entries are shared across input-permutation-equivalent
        LUT INIT functions.
    canonical_cache_max_width : int
        Maximum LUT width where permutation canonicalization is attempted.
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
        considered_lut_widths: list[int],
        tile_configs: list[str] | None = None,
        tile_config_prefixes: list[str] | None = None,
        include_unused_inputs: bool = False,
        max_replacements: int | None = None,
        map_luts_first: bool = False,
        lut_map_size: int | None = None,
        allow_input_reuse: bool = True,
        allow_input_constants: bool = False,
        allow_output_reuse: bool = False,
        use_canonical_cache: bool = True,
        canonical_cache_max_width: int = 6,
        track_progress: bool = True,
        progress_chunk_size: int = 50,
        debug: bool = False,
    ) -> None:
        self.tile_verilog_path = tile_verilog_path
        self.tile_top_name = tile_top_name
        self.tile_inputs = tile_inputs
        self.tile_outputs = tile_outputs
        self.considered_lut_widths = considered_lut_widths
        self._considered_lut_width_set = set(considered_lut_widths)
        self.tile_configs = tile_configs
        self.tile_config_prefixes = tile_config_prefixes
        self.include_unused_inputs = include_unused_inputs
        self.max_replacements = max_replacements
        self.map_luts_first = map_luts_first
        self.lut_map_size = lut_map_size
        self.allow_input_reuse = allow_input_reuse
        self.allow_input_constants = allow_input_constants
        self.allow_output_reuse = allow_output_reuse
        self.use_canonical_cache = use_canonical_cache
        self.canonical_cache_max_width = canonical_cache_max_width
        self.track_progress = track_progress
        self.progress_chunk_size = progress_chunk_size
        self.debug = debug
        self._cache: dict[tuple[int, int], CutSolveResult] = {}

    def map_from_design(
        self,
        design: PyosysBridge,
        top_name: str | None = None,
    ) -> MorphTileResult:
        """Run morph-tile mapping on a pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Design containing ``$lut`` cells.
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
            debug=self.debug,
        )
        tracker = MorphTileProcessTracker(
            enabled=self.track_progress,
            chunk_size=self.progress_chunk_size,
        )
        tracker.start(morph_design, self.considered_lut_widths)

        total_luts = 0
        candidate_luts = 0
        failed_luts = 0
        skipped_luts = 0
        skipped_width_luts = 0
        skipped_limit_luts = 0
        cache_hits = 0
        cache_misses = 0
        replacements: list[MorphTileReplacement] = []
        replacements_by_width: dict[str, int] = {}
        failures_by_width: dict[str, int] = {}
        mapped_init_count: dict[str, int] = {}

        for lut_cell in morph_design.lut_cells:
            total_luts += 1
            width = lut_cell.width
            init = lut_cell.init
            if width not in self._considered_lut_width_set:
                skipped_luts += 1
                skipped_width_luts += 1
                tracker.skipped_width()
                continue
            if (
                self.max_replacements is not None
                and len(replacements) >= self.max_replacements
            ):
                skipped_luts += 1
                skipped_limit_luts += 1
                tracker.skipped_limit()
                continue

            candidate_luts += 1
            canonical = canonicalize_lut_init(
                init=init,
                width=width,
                enabled=(
                    self.use_canonical_cache and width <= self.canonical_cache_max_width
                ),
            )
            cache_key = canonical.cache_key
            if cache_key in self._cache:
                canonical_result = self._cache[cache_key]
                cache_hits += 1
                tracker.cache_hit()
            else:
                canonical_result = solver.solve_lut(
                    init=canonical.canonical_init,
                    lut_size=width,
                    allow_input_reuse=self.allow_input_reuse,
                    allow_input_constants=self.allow_input_constants,
                    allow_output_reuse=self.allow_output_reuse,
                )
                self._cache[cache_key] = canonical_result
                cache_misses += 1
                tracker.cache_miss()
            solve_result = remap_cut_solve_result(canonical_result, canonical)

            if not solve_result.sat:
                failed_luts += 1
                _increment(failures_by_width, _lut_label(width))
                tracker.solved(sat=False)
                continue

            replacement = MorphTileReplacement(
                original_cell_id=lut_cell.cell_id,
                replacement_cell_id=f"{lut_cell.cell_id}__morph_tile",
                width=width,
                init=init,
                input_mapping=solve_result.input_mapping,
                output_mapping=solve_result.output_mapping,
                config_bits=solve_result.config_bits,
            )
            replacements.append(replacement)
            _increment(replacements_by_width, _lut_label(width))
            _increment(mapped_init_count, f"{_lut_label(width)}:0x{init:x}")
            tracker.solved(sat=True)

        stats = MorphTileStats(
            total_luts=total_luts,
            candidate_luts=candidate_luts,
            replaced_luts=len(replacements),
            failed_luts=failed_luts,
            skipped_luts=skipped_luts,
            skipped_width_luts=skipped_width_luts,
            skipped_limit_luts=skipped_limit_luts,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            replacements_by_width=replacements_by_width,
            failures_by_width=failures_by_width,
            mapped_init_count=mapped_init_count,
        )
        result = MorphTileResult(
            top_name=morph_design.top_name,
            tile_top_name=self.tile_top_name,
            considered_lut_widths=self.considered_lut_widths,
            max_replacements=self.max_replacements,
            use_canonical_cache=self.use_canonical_cache,
            stats=stats,
            replacements=tuple(replacements),
        )
        result = replace(result, report_summary=render_morph_tile_report(result))
        tracker.finish(result)
        return result


def _increment(counts: dict[str, int], label: str) -> None:
    """Increment a histogram entry."""
    counts[label] = counts.get(label, 0) + 1


def _lut_label(width: int) -> str:
    """Return a report label for a LUT width."""
    return f"LUT{width}"
