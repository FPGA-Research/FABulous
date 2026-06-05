"""Top-level multi-LUT morph-tile mapper.

The mapper is self-contained: it extracts LUT groups, checks them with sat_fab,
selects disjoint matches, and applies replacements with its own multi-cell
writer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.reader import (
    MorphTileReader,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.extractor import (
    extract_lut_graph,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.group_finder import (
    iter_group_candidates,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
    MultiMapMatch,
    MultiMapReplacement,
    MultiMapResult,
    MultiMapStats,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.process_tracker import (
    MultiMapProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.report import (
    render_multi_map_report,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.sat_check import (
    MultiMapSatChecker,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.selector import (
    match_score,
    prune_matches,
    select_disjoint_matches_with_report,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.truth import (
    CyclicGroupError,
    build_group_truth,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.writer import (
    MultiMapWriter,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
        MorphCircuitEnvironment,
    )
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
        MorphTileDesign,
    )
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.options import (
        MultiMapOptions,
    )
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class MultiMapMapper:
    """Pack LUT groups into one configurable tile candidate.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared morph-tile environment with solver, tile ports, and global
        mapper options.
    options : MultiMapOptions
        Multi-map grouping options.
    """

    def __init__(
        self,
        env: MorphCircuitEnvironment,
        options: MultiMapOptions,
    ) -> None:
        self.solver = env.solver
        self.tile_top_name = env.solver.top_name
        self.tile_inputs = env.tile_inputs
        self.tile_outputs = env.tile_outputs
        self.options = options
        self.include_unused_inputs = env.include_unused_inputs
        self.solve_options = env.solve_options
        self.track_progress = env.track_progress
        self.progress_chunk_size = env.progress_chunk_size

    def map_from_design(
        self,
        design: PyosysBridge,
        top_name: str | None = None,
    ) -> MultiMapResult:
        """Plan and apply multi-map replacements to a pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Live design to mutate.
        top_name : str | None
            Optional top module name.

        Returns
        -------
        MultiMapResult
            Multi-map result and report.
        """
        selected_top = top_name or design.top_name()
        morph_design = MorphTileReader().read_design(design, selected_top)
        result = self.plan(morph_design)
        MultiMapWriter(
            tile_top_name=self.tile_top_name,
            tile_inputs=self.tile_inputs,
            include_unused_inputs=self.include_unused_inputs,
        ).apply(
            design,
            selected_top,
            result.replacements,
            progress=(
                MultiMapProcessTracker(
                    enabled=self.track_progress,
                    chunk_size=self.progress_chunk_size,
                ).writer_event
                if self.track_progress
                else None
            ),
        )
        return result

    def plan(self, morph_design: MorphTileDesign) -> MultiMapResult:
        """Build a multi-map replacement plan.

        Parameters
        ----------
        morph_design : MorphTileDesign
            Generic morph-tile design view.

        Returns
        -------
        MultiMapResult
            Selected replacements without mutating the design.
        """
        graph = extract_lut_graph(morph_design)
        options_summary = _options_summary(self.options)
        tracker = MultiMapProcessTracker(
            enabled=self.track_progress,
            chunk_size=self.progress_chunk_size,
        )
        tracker.sampling_start(
            top_name=morph_design.top_name,
            total_luts=len(graph.nodes),
            options_summary=options_summary,
        )
        group_candidates = iter_group_candidates(
            graph,
            self.options,
            progress=tracker.sampled,
        )
        tracker.sampling_finish(len(group_candidates))
        checker = MultiMapSatChecker(
            solver=self.solver,
            solve_options=self.solve_options,
            options=self.options,
        )
        tracker.start(
            top_name=morph_design.top_name,
            total_luts=len(graph.nodes),
            sampled_groups=len(group_candidates),
            options_summary=options_summary,
        )
        matches: list[MultiMapMatch] = []
        checked_groups = 0
        sat_matches_total = 0
        for candidate in group_candidates:
            try:
                truth = build_group_truth(graph, candidate)
            except CyclicGroupError as exc:
                checked_groups += 1
                logger.warning(
                    "[MultiMapMapper] Skip cyclic LUT group {}: {}",
                    candidate.lut_ids,
                    exc,
                )
                tracker.checked(
                    sat=False,
                    cache_hit=False,
                    stored_matches=len(matches),
                )
                continue
            previous_cache_hits = checker.cache_hits
            result = checker.check(truth)
            checked_groups += 1
            if not result.sat:
                tracker.checked(
                    sat=False,
                    cache_hit=checker.cache_hits > previous_cache_hits,
                    stored_matches=len(matches),
                )
                continue
            match = MultiMapMatch(
                candidate=candidate,
                truth=truth,
                result=result,
                score=0,
            )
            match = replace(match, score=match_score(match))
            sat_matches_total += 1
            matches.append(match)
            matches = prune_matches(matches, self.options)
            tracker.checked(
                sat=True,
                cache_hit=checker.cache_hits > previous_cache_hits,
                stored_matches=len(matches),
            )

        selected, selector_metadata = select_disjoint_matches_with_report(
            matches,
            self.options,
            progress=tracker.selector_event if self.track_progress else None,
        )
        replacements = tuple(
            _replacement_from_match(index, match)
            for index, match in enumerate(selected)
        )
        stats = MultiMapStats(
            total_groups=len(group_candidates),
            checked_groups=checked_groups,
            sat_matches_total=sat_matches_total,
            matched_groups=len(matches),
            selected_groups=len(selected),
            replaced_luts=sum(len(match.candidate.lut_ids) for match in selected),
            cache_hits=checker.cache_hits,
            cache_misses=checker.cache_misses,
        )
        result = MultiMapResult(
            top_name=morph_design.top_name,
            tile_top_name=self.tile_top_name,
            options_summary=options_summary,
            stats=stats,
            replacements=replacements,
            metadata={"selector": selector_metadata},
        )
        result = replace(result, report_summary=render_multi_map_report(result))
        tracker.finish(result)
        return result


def _replacement_from_match(index: int, match: MultiMapMatch) -> MultiMapReplacement:
    """Build one replacement from a selected match.

    Parameters
    ----------
    index : int
        Stable replacement index used to form the new cell name.
    match : MultiMapMatch
        Selected SAT-positive disjoint match.

    Returns
    -------
    MultiMapReplacement
        Replacement payload consumed by the dedicated multi-map writer.
    """
    input_ports = {}
    for tile_input, source in match.result.input_mapping.items():
        if source in {"0", "1"}:
            input_ports[tile_input] = int(source)
            continue
        ref = match.candidate.boundary_refs.get(source)
        if ref is not None:
            input_ports[tile_input] = ref

    output_ports = {}
    for spec_output, tile_output in match.result.output_mapping.items():
        ref = match.candidate.output_refs.get(spec_output)
        if ref is not None:
            output_ports[tile_output] = ref

    cell_names = "__".join(_safe_name(lut_id) for lut_id in match.candidate.lut_ids)
    return MultiMapReplacement(
        original_cell_ids=match.candidate.lut_ids,
        replacement_cell_id=f"{cell_names}__multi_map_{index}",
        input_ports=input_ports,
        output_ports=output_ports,
        config_bits=match.result.config_bits,
        input_mapping=match.result.input_mapping,
        output_mapping=match.result.output_mapping,
    )


def _options_summary(options: MultiMapOptions) -> dict[str, list[str]]:
    """Return user-facing option labels.

    Parameters
    ----------
    options : MultiMapOptions
        Multi-map options to render.

    Returns
    -------
    dict[str, list[str]]
        Report-friendly option labels.
    """
    return {
        "multi_map.luts_per_group": [str(size) for size in options.group_sizes()],
        "multi_map.boundary_inputs": [
            f"{options.min_boundary_inputs}..{options.max_boundary_inputs}"
        ],
        "multi_map.boundary_outputs": [
            f"{options.min_boundary_outputs}..{options.max_boundary_outputs}"
        ],
        "multi_map.max_graph_frontier": [str(options.max_graph_frontier)],
        "multi_map.max_graph_hops": [str(options.max_graph_hops)],
        "multi_map.max_iterations": [str(options.max_iterations)],
        "multi_map.pure_random_match": [str(options.pure_random_match)],
        "multi_map.connected_only": [str(options.connected_only)],
        "multi_map.max_stored_matches": [str(options.max_stored_matches)],
        "multi_map.max_selected_groups": [str(options.max_selected_groups)],
        "multi_map.enable_permute_cache": [str(options.enable_permute_cache)],
    }


def _safe_name(name: str) -> str:
    """Return a replacement-safe cell name fragment.

    Parameters
    ----------
    name : str
        Original source cell id.

    Returns
    -------
    str
        Cell-name fragment containing only alphanumeric characters and
        underscores.
    """
    return "".join(char if char.isalnum() or char == "_" else "_" for char in name)
