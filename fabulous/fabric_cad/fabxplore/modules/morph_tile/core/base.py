"""Common interfaces and helpers for morph-tile circuit adapters.

The morph-tile mapper works with adapter classes instead of hard-coding every
supported netlist cell kind. The base class keeps shared mechanics in one
place: solver access, cache helpers, source-port references, constants, and
replacement construction. Concrete adapters can therefore focus on describing
one cut shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    CutSolveResult,
    MorphTileReplacement,
    ReplacementPortRef,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.permute_cache import (
    canonicalize_truth_table,
    remap_permuted_solve_result,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.cut_solver import (
        CutSolver,
    )
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
        MorphTileDesign,
    )
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.truth import TruthTableSpec


class MorphCircuitKind(StrEnum):
    """Enumerate circuit adapter kinds supported by morph tile.

    Attributes
    ----------
    LUT
        Normal Yosys ``$lut`` cells.
    FRAC_LUT
        LUT-combinator fractional LUT cells. The adapter is reserved for the
        upcoming packed-cell path.
    """

    LUT = "lut"
    FRAC_LUT = "frac_lut"


@dataclass(frozen=True)
class MorphSolveOptions:
    """Options shared by circuit adapters when calling the cut solver.

    Attributes
    ----------
    allow_input_reuse : bool
        Whether SAT may map several tile inputs to the same spec input.
    allow_input_constants : bool
        Whether SAT may tie tile inputs to constants.
    allow_output_reuse : bool
        Whether SAT may reuse tile outputs for routed output matching.
    """

    allow_input_reuse: bool
    allow_input_constants: bool
    allow_output_reuse: bool


@dataclass(frozen=True)
class MorphTileContext:
    """Runtime context passed to all circuit adapters.

    Attributes
    ----------
    design : MorphTileDesign
        Generic internal view of the selected top module.
    extras : dict[str, object]
        Optional extension data for adapters. Future adapters can use this to
        consume richer analysis results, such as LUT-combinator mapping data,
        without changing the mapper loop.
    """

    design: MorphTileDesign
    extras: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MorphCircuitEnvironment:
    """Shared services and options available to every circuit adapter.

    Attributes
    ----------
    solver : CutSolver
        SAT-backed solver for the target morph-tile implementation.
    solve_options : MorphSolveOptions
        Generic input/output routing options.
    tile_inputs : list[str]
        Candidate tile input ports.
    tile_outputs : list[str]
        Candidate tile output ports.
    options : dict[str, object]
        Public pass options and adapter-specific options.
    """

    solver: CutSolver
    solve_options: MorphSolveOptions
    tile_inputs: list[str]
    tile_outputs: list[str]
    options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MorphSolveOutcome:
    """Return one adapter-level solve result.

    Attributes
    ----------
    result : CutSolveResult
        Decoded SAT result.
    cache_hit : bool
        Whether this candidate was served from an adapter cache.
    """

    result: CutSolveResult
    cache_hit: bool


class MorphCircuitAdapter[CandidateT](ABC):
    """Abstract base class for one morphable circuit kind.

    Concrete adapters should be small descriptions of one cut shape. The mapper
    owns orchestration, progress, and reporting; this base class owns common
    adapter services so new circuit files do not need to duplicate framework
    plumbing.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared solver, SAT options, tile ports, and pass options.

    Attributes
    ----------
    kind : MorphCircuitKind
        Stable adapter kind.
    """

    kind: MorphCircuitKind

    def __init__(self, env: MorphCircuitEnvironment) -> None:
        self.env = env
        self._cache: dict[Any, CutSolveResult] = {}

    @abstractmethod
    def filter_summary(self) -> dict[str, list[str]]:
        """Return user-facing filter labels for reports and progress.

        Returns
        -------
        dict[str, list[str]]
            Report-friendly filter values keyed by filter name.
        """

    @abstractmethod
    def iter_candidates(self, context: MorphTileContext) -> Iterable[CandidateT]:
        """Yield candidates owned by this adapter.

        Parameters
        ----------
        context : MorphTileContext
            Runtime mapping context.

        Returns
        -------
        Iterable[CandidateT]
            Candidate objects in deterministic processing order.
        """

    @abstractmethod
    def is_enabled_candidate(self, candidate: CandidateT) -> bool:
        """Return whether a candidate should be attempted.

        Parameters
        ----------
        candidate : CandidateT
            Candidate from ``iter_candidates``.

        Returns
        -------
        bool
            ``True`` when this candidate passes adapter-local filters.
        """

    @abstractmethod
    def solve(self, candidate: CandidateT) -> MorphSolveOutcome:
        """Solve one enabled candidate.

        Parameters
        ----------
        candidate : CandidateT
            Candidate selected for solving.

        Returns
        -------
        MorphSolveOutcome
            SAT result plus cache status.
        """

    @abstractmethod
    def make_replacement(
        self,
        candidate: CandidateT,
        result: CutSolveResult,
    ) -> MorphTileReplacement:
        """Build a replacement payload for a SAT candidate.

        Parameters
        ----------
        candidate : CandidateT
            Candidate that was solved.
        result : CutSolveResult
            SAT result for the candidate.

        Returns
        -------
        MorphTileReplacement
            Replacement record consumed by the writer.
        """

    @abstractmethod
    def width_label(self, candidate: CandidateT) -> str:
        """Return the report width label for a candidate.

        Parameters
        ----------
        candidate : CandidateT
            Candidate to label.

        Returns
        -------
        str
            Human-readable width label.
        """

    @abstractmethod
    def init_label(self, candidate: CandidateT) -> str:
        """Return the report INIT label for a replaced candidate.

        Parameters
        ----------
        candidate : CandidateT
            Candidate to label.

        Returns
        -------
        str
            Human-readable INIT label.
        """

    def solve_spec(
        self,
        spec: Circuit | TruthTableSpec,
        spec_inputs: list[str],
        spec_outputs: list[str],
    ) -> CutSolveResult:
        """Solve one custom spec circuit with the shared solver.

        Parameters
        ----------
        spec : Circuit | TruthTableSpec
            Fixed target behavior.
        spec_inputs : list[str]
            Spec inputs that may feed tile inputs.
        spec_outputs : list[str]
            Spec outputs that may be routed to tile outputs.

        Returns
        -------
        CutSolveResult
            SAT result for the custom spec.
        """
        return self.env.solver.solve_spec(
            spec=spec,
            spec_inputs=spec_inputs,
            spec_outputs=spec_outputs,
            allow_input_reuse=self.env.solve_options.allow_input_reuse,
            allow_input_constants=self.env.solve_options.allow_input_constants,
            allow_output_reuse=self.env.solve_options.allow_output_reuse,
        )

    def solve_truth_table_cached(
        self,
        name: str,
        input_names: list[str],
        output_inits: dict[str, int],
        enable_permute_cache: bool,
        reduce_lut_symmetry: bool = True,
    ) -> MorphSolveOutcome:
        """Solve a fixed truth-table spec through the shared adapter cache.

        Parameters
        ----------
        name : str
            SAT-fab spec name.
        input_names : list[str]
            Ordered spec input names.
        output_inits : dict[str, int]
            Output INITs keyed by spec output name.
        enable_permute_cache : bool
            Whether input-permutation-equivalent specs may share cache entries.
        reduce_lut_symmetry : bool
            Whether SAT-fab may reduce symmetric truth-table examples.

        Returns
        -------
        MorphSolveOutcome
            SAT result plus cache-hit status.
        """
        truth_table = canonicalize_truth_table(
            input_names=input_names,
            output_inits=output_inits,
            enabled=enable_permute_cache,
        )
        outcome = self.cached(
            truth_table.cache_key,
            lambda: self.solve_spec(
                spec=Circuit.fast_lut(
                    name=name,
                    inputs=list(truth_table.input_names),
                    outputs=truth_table.canonical_output_inits,
                    reduce_lut_symmetry=reduce_lut_symmetry,
                ),
                spec_inputs=list(truth_table.input_names),
                spec_outputs=list(truth_table.canonical_output_inits),
            ),
        )
        return MorphSolveOutcome(
            result=remap_permuted_solve_result(outcome.result, truth_table),
            cache_hit=outcome.cache_hit,
        )

    def cached(
        self,
        key: object,
        solve: Callable[[], CutSolveResult],
    ) -> MorphSolveOutcome:
        """Return a cached solve result or compute and store it.

        Parameters
        ----------
        key : object
            Hashable cache key.
        solve : Callable[[], CutSolveResult]
            Function used to compute a cache miss.

        Returns
        -------
        MorphSolveOutcome
            Result plus cache-hit status.
        """
        if key in self._cache:
            return MorphSolveOutcome(result=self._cache[key], cache_hit=True)

        result = solve()
        self._cache[key] = result
        return MorphSolveOutcome(result=result, cache_hit=False)

    def const(self, value: int | bool) -> ReplacementPortRef:
        """Return a constant replacement-port reference.

        Parameters
        ----------
        value : int | bool
            Boolean-like constant value.

        Returns
        -------
        ReplacementPortRef
            Constant source reference.
        """
        return ReplacementPortRef.const(value)

    def src_port(self, port: str, index: int = 0) -> ReplacementPortRef:
        """Return a reference to one bit of the original source cell.

        Parameters
        ----------
        port : str
            Source cell port name.
        index : int
            Bit index within the source port.

        Returns
        -------
        ReplacementPortRef
            Source-cell port reference.
        """
        return ReplacementPortRef.cell_port_bit(port, index)

    def replacement(
        self,
        original_cell_id: str,
        width: int,
        init: int,
        result: CutSolveResult,
        input_ports: dict[str, ReplacementPortRef],
        output_ports: dict[str, ReplacementPortRef],
    ) -> MorphTileReplacement:
        """Build a common replacement record.

        Parameters
        ----------
        original_cell_id : str
            Replaced source cell name.
        width : int
            Width-like report value.
        init : int
            INIT-like report value.
        result : CutSolveResult
            SAT result for the candidate.
        input_ports : dict[str, ReplacementPortRef]
            Concrete replacement input wiring.
        output_ports : dict[str, ReplacementPortRef]
            Concrete replacement output wiring.

        Returns
        -------
        MorphTileReplacement
            Replacement payload for the writer.
        """
        return MorphTileReplacement(
            original_cell_id=original_cell_id,
            replacement_cell_id=f"{original_cell_id}__morph_tile",
            width=width,
            init=init,
            input_mapping=result.input_mapping,
            output_mapping=result.output_mapping,
            input_ports=input_ports,
            output_ports=output_ports,
            config_bits=result.config_bits,
        )
