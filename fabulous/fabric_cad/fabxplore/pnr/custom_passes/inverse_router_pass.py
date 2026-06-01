"""PnR pass wrapper for benchmark-driven inverse routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.inverse_router import (
    BenchmarkSource,
    InverseRouter,
    InverseRouterOptions,
    InverseRouterResult,
)
from fabulous.fabric_cad.fabxplore.pnr.pnr_pass import PnRPass

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


@dataclass
class InverseRouterPass(PnRPass):
    """Run benchmark-driven inverse routing on one FABulous tile type.

    Attributes
    ----------
    tile_name : str
        Tile type to score and optionally modify.
    training_benchmarks : dict[str, BenchmarkSource]
        Benchmarks used to learn routing-resource scores.
    test_benchmarks : dict[str, BenchmarkSource]
        Benchmarks used only for validation.
    io_seed_count : int
        Number of deterministic auto-PCF assignments per benchmark set.
    io_seed_start : int
        First auto-PCF assignment seed.
    optimize_switch_matrix : bool
        Whether switch-matrix pruning is applied to the graph.
    switch_matrix_remove_unused_ratio : float
        Ratio of score-zero matrix PIPs to remove.
    switch_matrix_remove_used_ratio : float
        Ratio of score-positive matrix PIPs to remove.
    switch_matrix_active_pip_value : int | None
        Value assigned to kept matrix PIPs. ``None`` keeps original delays.
    optimize_external_pips : bool
        Whether external PIP pruning is applied to the graph.
    external_remove_unused_ratio : float
        Ratio of score-zero external PIPs to remove.
    external_remove_used_ratio : float
        Ratio of score-positive external PIPs to remove.
    validate_training : bool
        Whether training benchmarks are rerun after graph updates.
    validate_test : bool
        Whether test benchmarks are run after graph updates.
    nextpnr_exec : Path | str | None
        Optional nextpnr executable.
    extra_args : tuple[str, ...] | list[str] | None
        Extra nextpnr command-line arguments.
    live_output : bool
        Whether nextpnr output should stream live.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of route cases between progress updates.
    """

    tile_name: str
    training_benchmarks: dict[str, BenchmarkSource] = field(default_factory=dict)
    test_benchmarks: dict[str, BenchmarkSource] = field(default_factory=dict)
    io_seed_count: int = 1
    io_seed_start: int = 1
    optimize_switch_matrix: bool = True
    switch_matrix_remove_unused_ratio: float = 1.0
    switch_matrix_remove_used_ratio: float = 0.0
    switch_matrix_active_pip_value: int | None = 1
    optimize_external_pips: bool = False
    external_remove_unused_ratio: float = 1.0
    external_remove_used_ratio: float = 0.0
    validate_training: bool = True
    validate_test: bool = True
    nextpnr_exec: Path | str | None = None
    extra_args: tuple[str, ...] | list[str] | None = None
    live_output: bool = False
    track_progress: bool = True
    progress_chunk_size: int = 1

    _result: InverseRouterResult | None = None

    def run_on(self, fpga_model: PnRBridge) -> None:
        """Run the inverse-router pass on the active PnR bridge.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and routing graph.
        """
        options = InverseRouterOptions(
            tile_name=self.tile_name,
            training_benchmarks=self.training_benchmarks,
            test_benchmarks=self.test_benchmarks,
            io_seed_count=self.io_seed_count,
            io_seed_start=self.io_seed_start,
            optimize_switch_matrix=self.optimize_switch_matrix,
            switch_matrix_remove_unused_ratio=(self.switch_matrix_remove_unused_ratio),
            switch_matrix_remove_used_ratio=self.switch_matrix_remove_used_ratio,
            switch_matrix_active_pip_value=self.switch_matrix_active_pip_value,
            optimize_external_pips=self.optimize_external_pips,
            external_remove_unused_ratio=self.external_remove_unused_ratio,
            external_remove_used_ratio=self.external_remove_used_ratio,
            validate_training=self.validate_training,
            validate_test=self.validate_test,
            nextpnr_exec=self.nextpnr_exec,
            extra_args=tuple(self.extra_args or ()),
            live_output=self.live_output,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
        )
        self._result = InverseRouter(options).run(fpga_model)

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
    def result_data(self) -> InverseRouterResult | None:
        """Return the latest structured result.

        Returns
        -------
        InverseRouterResult | None
            Latest result if available.
        """
        return self._result
