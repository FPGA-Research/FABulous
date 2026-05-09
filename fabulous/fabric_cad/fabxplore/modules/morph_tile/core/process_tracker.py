"""Track morph-tile mapping progress.

Morph-tile mapping can spend noticeable time in SAT solving. This helper keeps progress
counters and user-facing log messages outside the mapper so the core planning loop can
stay focused on replacement decisions.
"""

from loguru import logger

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileDesign,
    MorphTileResult,
)


class MorphTileProcessTracker:
    """Report batched morph-tile mapping progress.

    Parameters
    ----------
    enabled : bool
        Whether progress lines are emitted.
    chunk_size : int
        Number of processed candidate LUTs between progress updates.
    """

    def __init__(self, enabled: bool, chunk_size: int) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self._total_luts = 0
        self._candidate_luts = 0
        self._processed_candidates = 0
        self._skipped_width_luts = 0
        self._skipped_limit_luts = 0
        self._replaced_luts = 0
        self._failed_luts = 0
        self._cache_hits = 0
        self._cache_misses = 0

    def start(
        self,
        morph_design: MorphTileDesign,
        considered_lut_widths: list[int],
    ) -> None:
        """Start progress tracking for one morph-tile plan.

        Parameters
        ----------
        morph_design : MorphTileDesign
            Internal design view to process.
        considered_lut_widths : list[int]
            LUT widths selected for replacement attempts.
        """
        self._total_luts = len(morph_design.lut_cells)
        considered = set(considered_lut_widths)
        self._candidate_luts = sum(
            1 for lut in morph_design.lut_cells if lut.width in considered
        )
        self._print(
            "Start morph-tile mapping: "
            f"top={morph_design.top_name}, "
            f"total_luts={self._total_luts}, "
            f"candidate_luts={self._candidate_luts}, "
            f"considered_widths={considered_lut_widths}"
        )

    def skipped_width(self) -> None:
        """Record one LUT skipped because its width was not selected."""
        self._skipped_width_luts += 1

    def skipped_limit(self) -> None:
        """Record one candidate skipped after the replacement cap was reached."""
        self._skipped_limit_luts += 1

    def cache_hit(self) -> None:
        """Record one candidate served from cache."""
        self._cache_hits += 1

    def cache_miss(self) -> None:
        """Record one unique SAT solve."""
        self._cache_misses += 1

    def solved(self, sat: bool) -> None:
        """Record one processed candidate and emit progress when due.

        Parameters
        ----------
        sat : bool
            ``True`` if the candidate was replaced.
        """
        self._processed_candidates += 1
        if sat:
            self._replaced_luts += 1
        else:
            self._failed_luts += 1

        if self._should_emit():
            self._print_progress()

    def finish(self, result: MorphTileResult) -> None:
        """Emit a final progress summary.

        Parameters
        ----------
        result : MorphTileResult
            Final mapper result.
        """
        stats = result.stats
        self._print(
            "Done morph-tile mapping: "
            f"replaced={stats.replaced_luts}, "
            f"failed={stats.failed_luts}, "
            f"skipped_width={stats.skipped_width_luts}, "
            f"skipped_limit={stats.skipped_limit_luts}, "
            f"cache_hits={stats.cache_hits}, "
            f"unique_solves={stats.cache_misses}"
        )

    def _print_progress(self) -> None:
        """Print one candidate-progress update."""
        if self._candidate_luts <= 0:
            self._print("Candidates: 0/0")
            return
        pct = (100.0 * self._processed_candidates) / float(self._candidate_luts)
        self._print(
            "Candidates: "
            f"{self._processed_candidates}/{self._candidate_luts} "
            f"({pct:.1f}%), "
            f"replaced={self._replaced_luts}, "
            f"failed={self._failed_luts}, "
            f"skipped_width={self._skipped_width_luts}, "
            f"skipped_limit={self._skipped_limit_luts}, "
            f"cache_hits={self._cache_hits}, "
            f"unique_solves={self._cache_misses}"
        )

    def _should_emit(self) -> bool:
        """Return whether the current candidate count should be logged.

        Returns
        -------
        bool
            ``True`` when a progress update should be printed.
        """
        return (
            self._processed_candidates % self.chunk_size == 0
            or self._processed_candidates == self._candidate_luts
        )

    def _print(self, message: str) -> None:
        """Emit one progress line when tracking is enabled.

        Parameters
        ----------
        message : str
            Message body without the standard prefix.
        """
        if self.enabled:
            logger.info(f"[MorphTileMapper] {message}")
