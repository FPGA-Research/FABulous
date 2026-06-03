"""Progress logging for benchmark-driven inverse routing."""

from loguru import logger


class InverseRouterProcessTracker:
    """Track inverse-router progress.

    Parameters
    ----------
    enabled : bool
        Whether progress messages should be emitted.
    chunk_size : int
        Number of route cases between progress messages.
    """

    def __init__(self, enabled: bool = True, chunk_size: int = 1) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self.routes_seen = 0

    def start(self, tile_name: str) -> None:
        """Log the start of inverse routing.

        Parameters
        ----------
        tile_name : str
            Tile type being optimized.
        """
        self.routes_seen = 0
        if self.enabled:
            logger.info("[InverseRouter] Start tile={}", tile_name)

    def batch(self, phase: str, seed: int, count: int) -> None:
        """Log the start of one benchmark batch.

        Parameters
        ----------
        phase : str
            Route phase name.
        seed : int
            Auto-PCF assignment seed.
        count : int
            Number of benchmark cases in the batch.
        """
        if self.enabled:
            logger.info(
                "[InverseRouter] {} seed={} cases={}",
                phase,
                seed,
                count,
            )

    def route(self, phase: str, benchmark_name: str, passed: bool) -> None:
        """Record one route result.

        Parameters
        ----------
        phase : str
            Route phase name.
        benchmark_name : str
            Benchmark name.
        passed : bool
            Whether the route succeeded.
        """
        previous_chunks = self.routes_seen // self.chunk_size
        self.routes_seen += 1
        current_chunks = self.routes_seen // self.chunk_size
        if self.enabled and current_chunks > previous_chunks:
            logger.info(
                "[InverseRouter] routes={} last={}:{} passed={}",
                self.routes_seen,
                phase,
                benchmark_name,
                passed,
            )

    def scoring(self, matrix_pips: int) -> None:
        """Log score-collection totals.

        Parameters
        ----------
        matrix_pips : int
            Number of matrix candidates with positive score.
        """
        if self.enabled:
            logger.info(
                "[InverseRouter] Scored matrix_pips={}",
                matrix_pips,
            )

    def applied(self, matrix_removed: int) -> None:
        """Log graph update totals.

        Parameters
        ----------
        matrix_removed : int
            Number of matrix PIPs selected for removal.
        """
        if self.enabled:
            logger.info(
                "[InverseRouter] Applied matrix_removed={}",
                matrix_removed,
            )

    def finish(self, tile_name: str) -> None:
        """Log the end of inverse routing.

        Parameters
        ----------
        tile_name : str
            Tile type that was optimized.
        """
        if self.enabled:
            logger.info("[InverseRouter] Done tile={}", tile_name)
