"""Progress tracking for routing-demand evaluation."""

from __future__ import annotations

from loguru import logger


class RoutingDemandProcessTracker:
    """Log routing-demand evaluator progress.

    Parameters
    ----------
    enabled : bool
        Whether logging is enabled.
    chunk_size : int
        Number of optimizer iterations between progress updates.
    """

    def __init__(self, enabled: bool, chunk_size: int = 10) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)

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

    def evaluation_start(self, label: str) -> None:
        """Log one demand-oracle evaluation start.

        Parameters
        ----------
        label : str
            Evaluation label.
        """
        if self.enabled:
            logger.info("[RoutingDemandEvaluator] Evaluating {}", label)

    def optimizer_start(
        self,
        optimizer: str,
        target_pips: int,
        max_iterations: int,
    ) -> None:
        """Log optimizer start.

        Parameters
        ----------
        optimizer : str
            Optimizer name.
        target_pips : int
            Target number of removed PIPs.
        max_iterations : int
            Maximum optimizer iterations.
        """
        if self.enabled:
            logger.info(
                "[RoutingDemandEvaluator] Optimizer {} start: "
                "target_removed_pips={}, max_iterations={}",
                optimizer,
                target_pips,
                max_iterations,
            )

    def optimizer_iteration(
        self,
        iteration: int,
        max_iterations: int,
        current_pips: int,
        accepted_pips: int,
        accepted_batches: int,
        rejected_batches: int,
    ) -> None:
        """Log optimizer iteration progress in chunks.

        Parameters
        ----------
        iteration : int
            Current optimizer iteration.
        max_iterations : int
            Maximum optimizer iterations.
        current_pips : int
            Current accepted PIP count.
        accepted_pips : int
            Accepted removed PIPs.
        accepted_batches : int
            Accepted candidate batches.
        rejected_batches : int
            Rejected candidate batches.
        """
        if not self.enabled:
            return
        if iteration % self.chunk_size != 0 and iteration != max_iterations:
            return
        pct = 100.0 * iteration / max_iterations if max_iterations else 100.0
        logger.info(
            "[RoutingDemandEvaluator] Optimizer iterations: "
            "{}/{} ({:.1f}%), current_pips={}, removed_pips={}, "
            "accepted_batches={}, rejected_batches={}",
            iteration,
            max_iterations,
            pct,
            current_pips,
            accepted_pips,
            accepted_batches,
            rejected_batches,
        )

    def optimizer_finish(
        self,
        removed_pips: int,
        final_pips: int,
        stop_reason: str,
    ) -> None:
        """Log optimizer completion.

        Parameters
        ----------
        removed_pips : int
            Accepted removed PIPs.
        final_pips : int
            Final PIP count.
        stop_reason : str
            Reason optimization stopped.
        """
        if self.enabled:
            logger.info(
                "[RoutingDemandEvaluator] Optimizer done: "
                "removed_pips={}, final_pips={}, stop_reason={}",
                removed_pips,
                final_pips,
                stop_reason,
            )

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
