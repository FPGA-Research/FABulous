"""Progress logging for switch-block factorization."""

from pathlib import Path

from loguru import logger


class SwitchBlockFactorizerProcessTracker:
    """Track and print switch-block factorizer progress.

    Parameters
    ----------
    enabled : bool
        Whether progress messages should be emitted.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def start(self, tile_name: str) -> None:
        """Log the start of factorization.

        Parameters
        ----------
        tile_name : str
            Tile being factorized.
        """
        if self.enabled:
            logger.info("[SwitchBlockFactorizer] Factorizing tile {}", tile_name)

    def wrote_file(self, label: str, path: Path) -> None:
        """Log a generated or updated file.

        Parameters
        ----------
        label : str
            Human-readable artifact label.
        path : Path
            Artifact path.
        """
        if self.enabled:
            logger.info("[SwitchBlockFactorizer] Wrote {}: {}", label, path)

    def finish(self, tile_name: str, added_jump_wires: int) -> None:
        """Log the end of factorization.

        Parameters
        ----------
        tile_name : str
            Tile that was factorized.
        added_jump_wires : int
            Number of generated JUMP wires.
        """
        if self.enabled:
            logger.info(
                "[SwitchBlockFactorizer] Done {}: added_jump_wires={}",
                tile_name,
                added_jump_wires,
            )
