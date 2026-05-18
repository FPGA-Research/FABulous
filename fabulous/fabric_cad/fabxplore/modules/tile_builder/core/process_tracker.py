"""Progress logging for FABulous tile building."""

from pathlib import Path

from loguru import logger


class TileBuilderProcessTracker:
    """Track and print tile-builder progress.

    Parameters
    ----------
    enabled : bool
        Whether progress messages should be emitted.
    chunk_size : int
        Number of BEL instances between progress messages.
    """

    def __init__(self, enabled: bool = True, chunk_size: int = 25) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self.processed_bels = 0

    def start(self, tile_name: str, bel_instances: int) -> None:
        """Log the start of tile building.

        Parameters
        ----------
        tile_name : str
            Tile being generated.
        bel_instances : int
            Number of BEL instances expected.
        """
        self.processed_bels = 0
        if self.enabled:
            logger.info(
                "[TileBuilder] Building tile {} with {} BEL instance(s)",
                tile_name,
                bel_instances,
            )

    def record_bel(self) -> None:
        """Record one parsed BEL instance."""
        self.processed_bels += 1
        if self.enabled and self.processed_bels % self.chunk_size == 0:
            logger.info(
                "[TileBuilder] Parsed {} BEL instance(s)",
                self.processed_bels,
            )

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
            logger.info("[TileBuilder] Wrote {}: {}", label, path)

    def finish(self, tile_name: str, total_config_bits: int, capacity: int) -> None:
        """Log the end of tile building.

        Parameters
        ----------
        tile_name : str
            Tile that was generated.
        total_config_bits : int
            Total tile configuration bits.
        capacity : int
            Fabric configuration bit capacity for one tile.
        """
        if self.enabled:
            logger.info(
                "[TileBuilder] Done {}: config_bits={}/{}",
                tile_name,
                total_config_bits,
                capacity,
            )
