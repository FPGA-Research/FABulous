"""Progress reporting for LUT decomposition runs."""

from loguru import logger


class LutDecomposerProcessTracker:
    """Track and log decomposer progress in chunks.

    Parameters
    ----------
    enabled : bool
        Whether progress messages are emitted.
    chunk_size : int
        Number of processed candidates between progress messages.
    """

    def __init__(self, enabled: bool = True, chunk_size: int = 100) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self.total = 0
        self.processed = 0
        self.replaced = 0
        self.failed = 0
        self.apply_total = 0
        self.applied = 0

    def start(self, total: int) -> None:
        """Start tracking a run.

        Parameters
        ----------
        total : int
            Number of selected LUT candidates.
        """
        self.total = total
        self.processed = 0
        self.replaced = 0
        self.failed = 0
        if self.enabled:
            logger.info(f"[LutDecomposer] Start LUT decomposition: candidates={total}")

    def record(self, replaced: bool) -> None:
        """Record one processed candidate.

        Parameters
        ----------
        replaced : bool
            Whether the candidate was successfully decomposed.
        """
        self.processed += 1
        if replaced:
            self.replaced += 1
        else:
            self.failed += 1
        if self.enabled and (
            self.processed % self.chunk_size == 0 or self.processed == self.total
        ):
            pct = 100.0 * self.processed / self.total if self.total else 100.0
            logger.info(
                "[LutDecomposer] "
                f"Processed {self.processed}/{self.total} ({pct:.1f}%): "
                f"decomposed={self.replaced}, failed={self.failed}"
            )

    def done(self) -> None:
        """Emit a final progress message."""
        if self.enabled:
            logger.info(
                "[LutDecomposer] Done LUT decomposition: "
                f"decomposed={self.replaced}, failed={self.failed}"
            )

    def start_apply(self, total: int) -> None:
        """Start tracking live-design mutation.

        Parameters
        ----------
        total : int
            Number of decompositions that will be applied.
        """
        self.apply_total = total
        self.applied = 0
        if self.enabled:
            logger.info(f"[LutDecomposer] Start applying decompositions: total={total}")

    def record_apply(self) -> None:
        """Record one applied decomposition."""
        self.applied += 1
        if self.enabled and (
            self.applied % self.chunk_size == 0 or self.applied == self.apply_total
        ):
            pct = 100.0 * self.applied / self.apply_total if self.apply_total else 100.0
            logger.info(
                "[LutDecomposer] "
                f"Applied {self.applied}/{self.apply_total} ({pct:.1f}%)"
            )

    def done_apply(self) -> None:
        """Emit a final live-design mutation progress message."""
        if self.enabled:
            logger.info(
                f"[LutDecomposer] Done applying decompositions: applied={self.applied}"
            )
