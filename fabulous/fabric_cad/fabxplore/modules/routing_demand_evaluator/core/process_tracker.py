"""Progress tracking for routing-demand evaluation."""

from __future__ import annotations

from loguru import logger


class RoutingDemandProcessTracker:
    """Log routing-demand evaluator progress.

    Parameters
    ----------
    enabled : bool
        Whether logging is enabled.
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def start(self, tile_name: str) -> None:
        """Log pass start.

        Parameters
        ----------
        tile_name : str
            Tile name.
        """
        if self.enabled:
            logger.info(f"[RoutingDemandEvaluator] Start {tile_name}")

    def loaded_matrix(self, path: object, pips: int) -> None:
        """Log matrix load.

        Parameters
        ----------
        path : object
            Matrix path.
        pips : int
            PIP count.
        """
        if self.enabled:
            logger.info(f"[RoutingDemandEvaluator] Loaded {path} with {pips} PIPs")

    def generated_demands(self, count: int) -> None:
        """Log demand generation.

        Parameters
        ----------
        count : int
            Demand count.
        """
        if self.enabled:
            logger.info(f"[RoutingDemandEvaluator] Generated {count} demands")

    def done(self, hard_failed: int, soft_failed: int) -> None:
        """Log pass completion.

        Parameters
        ----------
        hard_failed : int
            Failed hard demands.
        soft_failed : int
            Failed soft demands.
        """
        if self.enabled:
            logger.info(
                "[RoutingDemandEvaluator] Done "
                f"hard_failed={hard_failed}, soft_failed={soft_failed}"
            )
