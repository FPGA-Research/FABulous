"""Progress reporting for register absorption."""

from loguru import logger


class RegAbsorberProcessTracker:
    """Track and print register absorption progress.

    Parameters
    ----------
    enabled : bool
        Whether progress messages should be emitted.
    chunk_size : int
        Number of processed primitive/rule checks between messages.
    """

    def __init__(self, enabled: bool = True, chunk_size: int = 100) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self.total = 0
        self.processed = 0
        self.absorbed = 0

    def start(self, total: int) -> None:
        """Start tracking a run.

        Parameters
        ----------
        total : int
            Number of primitive/rule checks expected.
        """
        self.total = total
        self.processed = 0
        self.absorbed = 0
        if self.enabled:
            logger.info(
                "[RegAbsorber] Processing {} primitive/rule checks",
                self.total,
            )

    def record(self, absorbed: bool) -> None:
        """Record one processed check.

        Parameters
        ----------
        absorbed : bool
            Whether the check produced an absorption.
        """
        self.processed += 1
        if absorbed:
            self.absorbed += 1
        if self.enabled and (
            self.processed == self.total or self.processed % self.chunk_size == 0
        ):
            pct = 100.0 if self.total == 0 else self.processed / self.total * 100.0
            logger.info(
                "[RegAbsorber] Checks: {}/{} ({:.1f}%), absorbed={}",
                self.processed,
                self.total,
                pct,
                self.absorbed,
            )

    def done(self) -> None:
        """Emit the final progress message."""
        if self.enabled:
            logger.info(
                "[RegAbsorber] Done register absorption: absorbed={}",
                self.absorbed,
            )
