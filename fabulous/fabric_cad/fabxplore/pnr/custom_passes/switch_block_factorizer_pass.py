"""PnR pass wrapper for FABulous switch-block factorization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer import (
    MuxReductionRule,
    SwitchBlockFactorizer,
    SwitchBlockFactorizerOptions,
    SwitchBlockFactorizerResult,
)
from fabulous.fabric_cad.fabxplore.pnr.pnr_pass import PnRPass

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


@dataclass
class SwitchBlockFactorizerPass(PnRPass):
    """Factorize active FABulous switch-block mux rows in the graph.

    Attributes
    ----------
    tile_name : str
        Name of the FABulous tile to factorize.
    global_reduction : int | None
        Number of global fanin-halving passes to apply before explicit rules.
    reduction_rules : list[MuxReductionRule | dict[str, int]]
        Exact fanin reduction rules applied after global reduction.
    min_mux_fanin_to_factorize : int
        Smallest mux fanin eligible for factorization.
    jump_prefix : str
        Prefix for generated JUMP rows.
    max_added_jump_wires : int | None
        Optional maximum number of generated JUMP wires.
    config_bit_margin : int | None
        Optional relative config-bit budget from the starting tile bits.
    config_bit_limit : int | None
        Optional absolute config-bit budget.
    track_progress : bool
        Whether progress should be logged.
    """

    tile_name: str
    global_reduction: int | None = 1
    reduction_rules: list[MuxReductionRule | dict[str, int]] = field(
        default_factory=list
    )
    min_mux_fanin_to_factorize: int = 3
    jump_prefix: str = "J_FAC"
    max_added_jump_wires: int | None = None
    config_bit_margin: int | None = None
    config_bit_limit: int | None = None
    track_progress: bool = True

    _result: SwitchBlockFactorizerResult | None = None

    def run_on(self, fpga_model: PnRBridge) -> None:
        """Run the factorizer on the active routing graph.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and routing graph.
        """
        options = SwitchBlockFactorizerOptions(
            tile_name=self.tile_name,
            global_reduction=self.global_reduction,
            reduction_rules=[
                rule if isinstance(rule, MuxReductionRule) else MuxReductionRule(**rule)
                for rule in self.reduction_rules
            ],
            min_mux_fanin_to_factorize=self.min_mux_fanin_to_factorize,
            jump_prefix=self.jump_prefix,
            max_added_jump_wires=self.max_added_jump_wires,
            config_bit_margin=self.config_bit_margin,
            config_bit_limit=self.config_bit_limit,
            track_progress=self.track_progress,
        )
        self._result = SwitchBlockFactorizer(options).run(fpga_model)

    @property
    def report_summary(self) -> str:
        """Return the latest report summary.

        Returns
        -------
        str
            Report text, or a placeholder if the pass has not run.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> SwitchBlockFactorizerResult | None:
        """Return the latest structured result.

        Returns
        -------
        SwitchBlockFactorizerResult | None
            Latest result if available.
        """
        return self._result
