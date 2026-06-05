"""SAT-backed feasibility checks for multi-map groups.

This module is the only multi-map layer that talks to ``CutSolver``. It keeps a
small permutation-aware cache so repeated group functions do not require fresh
SAT solves.
"""

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphSolveOptions,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.cut_solver import (
    CutSolver,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    CutSolveResult,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.permute_cache import (
    canonicalize_truth_table,
    remap_permuted_solve_result,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
    LutGroupTruth,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.options import (
    MultiMapOptions,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit


class MultiMapSatChecker:
    """Check and cache group feasibility against one candidate tile.

    Parameters
    ----------
    solver : CutSolver
        Shared morph-tile cut solver.
    solve_options : MorphSolveOptions
        Input and output routing options.
    options : MultiMapOptions
        Multi-map options controlling permutation cache use.
    """

    def __init__(
        self,
        solver: CutSolver,
        solve_options: MorphSolveOptions,
        options: MultiMapOptions,
    ) -> None:
        self.solver = solver
        self.solve_options = solve_options
        self.options = options
        self._cache: dict[object, CutSolveResult] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def check(self, truth: LutGroupTruth) -> CutSolveResult:
        """Check whether one group truth table fits the tile.

        Parameters
        ----------
        truth : LutGroupTruth
            Group truth table.

        Returns
        -------
        CutSolveResult
            SAT result, remapped back to the original group input order.
        """
        canonical = canonicalize_truth_table(
            input_names=truth.input_names,
            output_inits=truth.output_inits,
            enabled=self.options.enable_permute_cache,
        )
        cached = self._cache.get(canonical.cache_key)
        if cached is not None:
            self.cache_hits += 1
            return remap_permuted_solve_result(cached, canonical)

        self.cache_misses += 1
        spec = Circuit.fast_lut(
            name="multi_map_group_spec",
            inputs=list(canonical.input_names),
            outputs=canonical.canonical_output_inits,
            reduce_lut_symmetry=False,
        )
        result = self.solver.solve_spec(
            spec=spec,
            spec_inputs=list(canonical.input_names),
            spec_outputs=list(canonical.canonical_output_inits),
            allow_input_reuse=self.solve_options.allow_input_reuse,
            allow_input_constants=self.solve_options.allow_input_constants,
            allow_output_reuse=self.solve_options.allow_output_reuse,
        )
        self._cache[canonical.cache_key] = result
        return remap_permuted_solve_result(result, canonical)
