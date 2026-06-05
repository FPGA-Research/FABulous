"""Morph-tile registry adapter for the multi-map flow.

The actual multi-map implementation is self-contained and uses its own writer.
This adapter exists so ``multi_map`` is a registered morph-tile circuit kind and
its options are validated consistently with other circuit adapters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphCircuitAdapter,
    MorphCircuitEnvironment,
    MorphCircuitKind,
    MorphSolveOutcome,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import CutSolveResult
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.mapper import (
    MultiMapMapper,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
        MorphTileContext,
    )
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
        MultiMapResult,
    )
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.options import (
        MultiMapOptions,
    )
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class MultiMapCircuit(MorphCircuitAdapter[object]):
    """Registered wrapper for the dedicated multi-map mapper.

    The normal morph-tile loop calls this adapter, which then runs the
    self-contained multi-map flow once and returns no normal-loop candidates.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared morph-tile environment.
    options : MultiMapOptions
        Multi-map options.
    design : PyosysBridge
        Live pyosys design mutated by the dedicated multi-map writer.

    Attributes
    ----------
    kind : MorphCircuitKind
        Adapter kind identifier.

    Raises
    ------
    ValueError
        If no live design is provided, or if ``multi_map`` is enabled together
        with another morph circuit kind.
    """

    kind: MorphCircuitKind = MorphCircuitKind.MULTI_MAP

    def __init__(
        self,
        env: MorphCircuitEnvironment,
        options: MultiMapOptions,
        design: PyosysBridge,
    ) -> None:
        super().__init__(env)
        self.options = options
        if design is None:
            raise ValueError(
                "MultiMapCircuit requires a design for its dedicated mapper"
            )
        self.design: PyosysBridge = design
        self.result: MultiMapResult | None = None
        self._ran = False
        self._check_exclusive_mode()

    def filter_summary(self) -> dict[str, list[str]]:
        """Return selected multi-map options.

        Returns
        -------
        dict[str, list[str]]
            Report-friendly option labels for this adapter.
        """
        return {
            "multi_map.luts_per_group": [
                str(size) for size in self.options.group_sizes()
            ],
            "multi_map.boundary_inputs": [
                f"{self.options.min_boundary_inputs}..{self.options.max_boundary_inputs}"
            ],
            "multi_map.boundary_outputs": [
                f"{self.options.min_boundary_outputs}..{self.options.max_boundary_outputs}"
            ],
            "multi_map.max_graph_frontier": [str(self.options.max_graph_frontier)],
        }

    def iter_candidates(self, context: MorphTileContext) -> Iterable[object]:
        """Run the dedicated mapper once and yield no normal candidates.

        Parameters
        ----------
        context : MorphTileContext
            Normal morph-tile context containing the selected top name.

        Returns
        -------
        Iterable[object]
            Always empty, because the dedicated mapper writes replacements
            itself.
        """
        if not self._ran:
            self._ran = True
            self.result = self._build_mapper().map_from_design(
                self.design,
                top_name=context.design.top_name,
            )
        return ()

    def is_enabled_candidate(self, candidate: object) -> bool:
        """Return false because this adapter does not use the normal loop.

        Parameters
        ----------
        candidate : object
            Unused normal-loop candidate.

        Returns
        -------
        bool
            Always ``False``.
        """
        del candidate
        return False

    def solve(self, candidate: object) -> MorphSolveOutcome:
        """Return an UNSAT placeholder.

        Parameters
        ----------
        candidate : object
            Unused candidate.

        Returns
        -------
        MorphSolveOutcome
            Placeholder result.
        """
        del candidate
        return MorphSolveOutcome(result=CutSolveResult(sat=False), cache_hit=False)

    def make_replacement(
        self,
        candidate: object,
        result: CutSolveResult,
    ) -> NoReturn:
        """Reject normal-loop replacement construction.

        Parameters
        ----------
        candidate : object
            Unused candidate.
        result : CutSolveResult
            Unused result.

        Raises
        ------
        RuntimeError
            Always, because multi-map owns its writer.
        """
        del candidate, result
        raise RuntimeError("multi_map uses its dedicated MultiMapMapper writer")

    def width_label(self, candidate: object) -> str:
        """Return the report width label.

        Parameters
        ----------
        candidate : object
            Unused normal-loop candidate.

        Returns
        -------
        str
            Static report label for the multi-map adapter.
        """
        del candidate
        return "multi_map"

    def init_label(self, candidate: object) -> str:
        """Return the report INIT label.

        Parameters
        ----------
        candidate : object
            Unused normal-loop candidate.

        Returns
        -------
        str
            Static INIT-like report label for the multi-map adapter.
        """
        del candidate
        return "multi_map"

    def side_effect_result(self) -> MultiMapResult | None:
        """Return the dedicated multi-map result after the wrapper has run.

        Returns
        -------
        MultiMapResult | None
            Dedicated mapper result, if available.
        """
        return self.result

    def _build_mapper(self) -> MultiMapMapper:
        """Build the self-contained multi-map mapper.

        Returns
        -------
        MultiMapMapper
            Dedicated mapper configured from the normal morph-tile environment.
        """
        return MultiMapMapper(
            env=self.env,
            options=self.options,
        )

    def _check_exclusive_mode(self) -> None:
        """Reject mixing side-effect multi-map with normal adapters.

        Raises
        ------
        ValueError
            If ``multi_map`` is enabled together with another circuit kind.
        """
        enabled = self.env.options.get("enabled_circuits")
        if enabled is None:
            return
        kinds = [
            value if isinstance(value, MorphCircuitKind) else MorphCircuitKind(value)
            for value in enabled
        ]
        if kinds != [MorphCircuitKind.MULTI_MAP]:
            raise ValueError("multi_map must be the only enabled morph circuit")
