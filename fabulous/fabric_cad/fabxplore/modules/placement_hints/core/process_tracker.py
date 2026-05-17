"""Progress logging for placement hint generation."""

from loguru import logger


class PlacementHintsProcessTracker:
    """Track progress for placement hint generation.

    Parameters
    ----------
    enabled : bool
        Whether progress logging is enabled.
    chunk_size : int
        Number of processed items between progress logs.
    """

    def __init__(self, enabled: bool, chunk_size: int) -> None:
        self.enabled = enabled
        self.chunk_size = chunk_size
        self._count = 0

    def start(self, rules: int, cells: int) -> None:
        """Log the start of hint generation.

        Parameters
        ----------
        rules : int
            Number of rules to apply.
        cells : int
            Number of cells in the selected design.
        """
        if self.enabled:
            logger.info(
                "[PlacementHints] Applying {} rule(s) to {} cell(s)",
                rules,
                cells,
            )

    def tick(self) -> None:
        """Record one processed candidate cell."""
        self._count += 1
        if self.enabled and self._count % self.chunk_size == 0:
            logger.info("[PlacementHints] Processed {} candidate cell(s)", self._count)

    def finish(self, clusters: int, assigned_cells: int) -> None:
        """Log the end of hint generation.

        Parameters
        ----------
        clusters : int
            Number of emitted clusters.
        assigned_cells : int
            Number of cells that received placement attributes.
        """
        if self.enabled:
            logger.info(
                "[PlacementHints] Emitted {} cluster(s), assigned {} cell(s)",
                clusters,
                assigned_cells,
            )
