"""Progress logging for graph-only switch-matrix pattern generation."""

from loguru import logger


class SwitchMatrixPatternProcessTracker:
    """Track and print switch-matrix pattern progress.

    Parameters
    ----------
    enabled : bool
        Whether progress messages should be emitted.
    chunk_size : int
        Number of generated pairs between progress messages.
    """

    def __init__(self, enabled: bool = True, chunk_size: int = 100) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self.generated_pairs = 0

    def start(self, tile_name: str) -> None:
        """Log the start of switch-matrix pattern generation.

        Parameters
        ----------
        tile_name : str
            Tile being modified.
        """
        self.generated_pairs = 0
        if self.enabled:
            logger.info("[SwitchMatrixPattern] Updating tile {}", tile_name)

    def record_pairs(self, count: int) -> None:
        """Record generated pairs.

        Parameters
        ----------
        count : int
            Number of newly generated pairs.
        """
        if count <= 0:
            return
        previous_chunks = self.generated_pairs // self.chunk_size
        self.generated_pairs += count
        current_chunks = self.generated_pairs // self.chunk_size
        if self.enabled and current_chunks > previous_chunks:
            logger.info(
                "[SwitchMatrixPattern] Generated {} matrix pair(s)",
                self.generated_pairs,
            )

    def generated(self, label: str, count: int) -> None:
        """Log one generated pair category.

        Parameters
        ----------
        label : str
            Human-readable category label.
        count : int
            Number of pairs in the category.
        """
        if self.enabled:
            logger.info("[SwitchMatrixPattern] {}: {}", label, count)

    def finish(self, tile_name: str, applied_pips: int) -> None:
        """Log the end of switch-matrix pattern generation.

        Parameters
        ----------
        tile_name : str
            Tile that was modified.
        applied_pips : int
            Number of unique generated pairs applied to the graph.
        """
        if self.enabled:
            logger.info(
                "[SwitchMatrixPattern] Done {}: applied_pips={}",
                tile_name,
                applied_pips,
            )
