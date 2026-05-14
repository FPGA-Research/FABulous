"""Progress reporting for FF materialization."""

from loguru import logger


class FfMaterializerProcessTracker:
    """Track and print FF materialization progress.

    Parameters
    ----------
    enabled : bool
        Whether progress messages should be emitted.
    chunk_size : int
        Number of processed FFs between messages.
    """

    def __init__(self, enabled: bool = True, chunk_size: int = 100) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self.total = 0
        self.processed = 0
        self.materialized = 0
        self.inserted = 0

    def start(self, total: int) -> None:
        """Start tracking a run.

        Parameters
        ----------
        total : int
            Number of FF candidates expected.
        """
        self.total = total
        self.processed = 0
        self.materialized = 0
        self.inserted = 0
        if self.enabled:
            logger.info("[FfMaterializer] Processing {} FF candidates", self.total)

    def record(self, materialized: bool, inserted_tiles: int) -> None:
        """Record one processed FF.

        Parameters
        ----------
        materialized : bool
            Whether the FF was materialized.
        inserted_tiles : int
            Current number of planned replacement tile instances.
        """
        self.processed += 1
        self.inserted = inserted_tiles
        if materialized:
            self.materialized += 1
        if self.enabled and (
            self.processed == self.total or self.processed % self.chunk_size == 0
        ):
            pct = 100.0 if self.total == 0 else self.processed / self.total * 100.0
            logger.info(
                "[FfMaterializer] FFs: {}/{} ({:.1f}%), materialized={}, "
                "inserted_tiles={}",
                self.processed,
                self.total,
                pct,
                self.materialized,
                self.inserted,
            )

    def done(self) -> None:
        """Emit the final progress message."""
        if self.enabled:
            logger.info(
                "[FfMaterializer] Done FF materialization: materialized={}, "
                "inserted_tiles={}",
                self.materialized,
                self.inserted,
            )
