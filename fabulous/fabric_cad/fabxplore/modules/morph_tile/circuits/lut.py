"""Morph-tile circuit adapter for normal Yosys ``$lut`` cells.

This adapter preserves the original morph-tile behavior: each selected ``$lut``
is checked as one fixed truth table against the configurable morph-tile module.
The adapter can use the shared input-permutation cache to avoid repeated SAT
solves for input-reordered LUT functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.truth_table import (
    parse_init_literal,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphCircuitAdapter,
    MorphCircuitEnvironment,
    MorphCircuitKind,
    MorphSolveOutcome,
    MorphTileContext,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
        CutSolveResult,
        MorphTileNetlistCell,
        MorphTileReplacement,
        ReplacementPortRef,
    )


class LutCircuitOptions(BaseModel):
    """Options for the normal ``$lut`` circuit adapter.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    widths : list[int]
        LUT widths that should be considered for morphing.
    enable_permute_cache : bool
        Whether input-permutation-equivalent LUT INIT functions may share cache
        entries.
    """

    model_config = ConfigDict(frozen=True)

    widths: list[int] = Field(default_factory=list)
    enable_permute_cache: bool = True


@dataclass(frozen=True)
class LutCandidate:
    """Represent one normal ``$lut`` candidate.

    Attributes
    ----------
    cell_id : str
        Cell name in the selected top module.
    width : int
        LUT input width.
    init : int
        Parsed LSB-first INIT value.
    """

    cell_id: str
    width: int
    init: int


class LutCircuit(MorphCircuitAdapter[LutCandidate]):
    """Describe and solve normal ``$lut`` morph candidates.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared adapter environment.
    options : LutCircuitOptions
        Adapter-local configuration.

    Attributes
    ----------
    kind
        Adapter kind identifier.
    """

    kind = MorphCircuitKind.LUT

    def __init__(
        self,
        env: MorphCircuitEnvironment,
        options: LutCircuitOptions,
    ) -> None:
        super().__init__(env)
        self.options = options
        self._width_set = set(options.widths)

    def filter_summary(self) -> dict[str, list[str]]:
        """Return LUT width filters selected by this adapter.

        Returns
        -------
        dict[str, list[str]]
            Selected LUT adapter options.
        """
        return {
            "lut.enable_permute_cache": [str(self.options.enable_permute_cache)],
            "lut.widths": [_lut_label(width) for width in self.options.widths],
        }

    def iter_candidates(self, context: MorphTileContext) -> Iterable[LutCandidate]:
        """Yield normal LUT candidates from the design.

        Parameters
        ----------
        context : MorphTileContext
            Runtime mapping context.

        Yields
        ------
        LutCandidate
            Normal LUT cell candidates in reader order.
        """
        for cell in context.design.cells:
            candidate = _parse_lut_candidate(cell)
            if candidate is not None:
                yield candidate

    def is_enabled_candidate(self, candidate: LutCandidate) -> bool:
        """Return whether the LUT width is selected.

        Parameters
        ----------
        candidate : LutCandidate
            LUT candidate.

        Returns
        -------
        bool
            ``True`` if the candidate width is in ``options.widths``.
        """
        return candidate.width in self._width_set

    def solve(
        self,
        candidate: LutCandidate,
    ) -> MorphSolveOutcome:
        """Solve one normal LUT candidate.

        Parameters
        ----------
        candidate : LutCandidate
            LUT candidate to solve.

        Returns
        -------
        MorphSolveOutcome
            SAT result plus cache status.
        """
        return self.solve_truth_table_cached(
            name="lut_spec",
            input_names=[f"A{i}" for i in range(candidate.width)],
            output_inits={"X": candidate.init},
            enable_permute_cache=self.options.enable_permute_cache,
        )

    def make_replacement(
        self,
        candidate: LutCandidate,
        result: CutSolveResult,
    ) -> MorphTileReplacement:
        """Build a replacement for one SAT LUT candidate.

        Parameters
        ----------
        candidate : LutCandidate
            LUT candidate that was solved.
        result : CutSolveResult
            SAT result for the candidate.

        Returns
        -------
        MorphTileReplacement
            Replacement payload consumed by the writer.
        """
        return self.replacement(
            original_cell_id=candidate.cell_id,
            width=candidate.width,
            init=candidate.init,
            input_ports=self._input_ports_from_mapping(result.input_mapping),
            output_ports={
                tile_output: self.src_port("Y", 0)
                for tile_output in result.output_mapping.values()
            },
            result=result,
        )

    def width_label(self, candidate: LutCandidate) -> str:
        """Return the LUT-width report label.

        Parameters
        ----------
        candidate : LutCandidate
            LUT candidate to label.

        Returns
        -------
        str
            Label such as ``"LUT2"``.
        """
        return _lut_label(candidate.width)

    def init_label(self, candidate: LutCandidate) -> str:
        """Return the LUT INIT report label.

        Parameters
        ----------
        candidate : LutCandidate
            LUT candidate to label.

        Returns
        -------
        str
            Label such as ``"LUT2:0x8"``.
        """
        return f"{_lut_label(candidate.width)}:0x{candidate.init:x}"

    def _input_ports_from_mapping(
        self,
        input_mapping: dict[str, str],
    ) -> dict[str, ReplacementPortRef]:
        """Translate solved LUT input names into replacement port references.

        Parameters
        ----------
        input_mapping : dict[str, str]
            Candidate tile input to logical LUT input mapping.

        Returns
        -------
        dict[str, ReplacementPortRef]
            Concrete replacement input wiring for the writer.
        """
        ports = {}
        for tile_input, source in input_mapping.items():
            ref = self._source_to_ref(source)
            if ref is not None:
                ports[tile_input] = ref
        return ports

    def _source_to_ref(self, source: str) -> ReplacementPortRef | None:
        """Convert one solved source name to a replacement reference."""
        if source in {"0", "1"}:
            return self.const(int(source))
        if not source.startswith("A"):
            return None
        index_text = source.removeprefix("A")
        if not index_text.isdigit():
            return None
        return self.src_port("A", int(index_text))


def _lut_label(width: int) -> str:
    """Return a report label for a LUT width."""
    return f"LUT{width}"


def _parse_lut_candidate(cell: MorphTileNetlistCell) -> LutCandidate | None:
    """Parse one generic cell into a LUT candidate.

    Parameters
    ----------
    cell : MorphTileNetlistCell
        Generic source-design cell.

    Returns
    -------
    LutCandidate | None
        Parsed LUT candidate, or ``None`` for non-LUT cells.

    Raises
    ------
    RuntimeError
        If a ``$lut`` cell has an invalid output connection.
    """
    if cell.cell_type != "$lut":
        return None

    input_bits = list(cell.connections.get("A", ()))
    output_bits = list(cell.connections.get("Y", ()))
    if len(output_bits) != 1:
        raise RuntimeError(f"$lut '{cell.cell_id}' must have exactly one Y bit")

    width = len(input_bits)
    init = parse_init_literal(str(cell.parameters.get("LUT", "0")), width)
    return LutCandidate(cell_id=cell.cell_id, width=width, init=init)
