"""Track morph-tile mapping progress.

Morph-tile mapping can spend noticeable time in SAT solving. This helper keeps progress
counters and user-facing log messages outside the mapper so the core planning loop can
stay focused on replacement decisions.
"""

from loguru import logger

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileResult,
)


class MorphTileProcessTracker:
    """Report batched morph-tile mapping progress.

    Parameters
    ----------
    enabled : bool
        Whether progress lines are emitted.
    chunk_size : int
        Number of processed candidates between progress updates.
    """

    def __init__(self, enabled: bool, chunk_size: int) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self._total_candidates = 0
        self._checked_candidates = 0
        self._processed_candidates = 0
        self._skipped_filter_candidates = 0
        self._skipped_limit_candidates = 0
        self._replaced_candidates = 0
        self._failed_candidates = 0
        self._cache_hits = 0
        self._cache_misses = 0

    def start(
        self,
        top_name: str,
        total_candidates: int,
        checked_candidates: int,
        filter_summary: dict[str, list[str]],
    ) -> None:
        """Start progress tracking for one morph-tile plan.

        Parameters
        ----------
        top_name : str
            Processed top module.
        total_candidates : int
            Candidates yielded by enabled adapters.
        checked_candidates : int
            Candidates selected for SAT solving.
        filter_summary : dict[str, list[str]]
            User-facing filters selected by enabled adapters.
        """
        self._total_candidates = total_candidates
        self._checked_candidates = checked_candidates
        filters = _format_filters(filter_summary)
        self._print(
            "Start morph-tile mapping: "
            f"top={top_name}, "
            f"total_candidates={self._total_candidates}, "
            f"checked_candidates={self._checked_candidates}, "
            f"filters={filters}"
        )

    def skipped_filter(self) -> None:
        """Record one candidate skipped by adapter-local filters."""
        self._skipped_filter_candidates += 1

    def skipped_limit(self) -> None:
        """Record one candidate skipped after the replacement cap was reached."""
        self._skipped_limit_candidates += 1

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
            self._replaced_candidates += 1
        else:
            self._failed_candidates += 1

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
            f"replaced={stats.replaced_candidates}, "
            f"failed={stats.failed_candidates}, "
            f"skipped_filter={stats.skipped_filter_candidates}, "
            f"skipped_limit={stats.skipped_limit_candidates}, "
            f"cache_hits={stats.cache_hits}, "
            f"unique_solves={stats.cache_misses}"
        )

    def _print_progress(self) -> None:
        """Print one candidate-progress update."""
        if self._checked_candidates <= 0:
            self._print("Candidates: 0/0")
            return
        pct = (100.0 * self._processed_candidates) / float(self._checked_candidates)
        self._print(
            "Candidates: "
            f"{self._processed_candidates}/{self._checked_candidates} "
            f"({pct:.1f}%), "
            f"replaced={self._replaced_candidates}, "
            f"failed={self._failed_candidates}, "
            f"skipped_filter={self._skipped_filter_candidates}, "
            f"skipped_limit={self._skipped_limit_candidates}, "
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
            or self._processed_candidates == self._checked_candidates
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


def _format_filters(filter_summary: dict[str, list[str]]) -> str:
    """Format adapter filters for compact progress output.

    Parameters
    ----------
    filter_summary : dict[str, list[str]]
        Filters selected by enabled adapters.

    Returns
    -------
    str
        Compact filter string.
    """
    if not filter_summary:
        return "none"
    parts = []
    for key, values in sorted(filter_summary.items()):
        parts.append(f"{key}=[{', '.join(values) if values else 'none'}]")
    return "; ".join(parts)
