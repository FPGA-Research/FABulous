"""Define the FABulousTimingModelInterface class.

It provides an interface to compute and cache timing delays for pips in a FABulous
fabric.

It uses the FABulousTileTimingModel to compute delays for individual tiles and caches
the results for efficient retrieval.
"""

from loguru import logger

from fabulous.fabric_cad.timing_model.FABulous_timing_model import (
    FABulousTileTimingModel,
)
from fabulous.fabric_cad.timing_model.models import (
    TimingModelConfig,
)
from fabulous.fabric_definition.fabric import Fabric


class FABulousTimingModelInterface:
    """Interface for computing and caching timing delays in a FABulous fabric.

    Initialize the FABulousTimingModelInterface with the given configuration and
    fabric.

    Allows for efficient retrieval of pip delays by caching previously computed
    results, and supports different timing models for different (super)
    tile types based on the configuration.

    Parameters
    ----------
    config : TimingModelConfig
        Configuration object for the timing model.
    fabric : Fabric
        The FABulous fabric object.
    """

    def __init__(self, config: TimingModelConfig, fabric: Fabric) -> None:
        self.config: TimingModelConfig = config
        self.fabric: Fabric = fabric
        self.tile_delay_dict: dict[str, dict[str, float]] = {}

        self.timing_models: dict[str, FABulousTileTimingModel] = {}

        logger.info(
            f"Initializing timing models for tiles, with mode: {self.config.mode}"
        )

        for tile_name, _tile in self.fabric.tileDic.items():
            model_config = self.config.model_copy(deep=True)
            timing_model = FABulousTileTimingModel(
                config=model_config, fabric=self.fabric, tile_name=tile_name
            )
            self.timing_models[tile_name] = timing_model

    def pip_delay(self, tile_name: str, src_pip: str, dst_pip: str) -> float:
        """Get the delay for a given pip in the timing model.

        If the delay for the specified pip was already computed before,
        return the cached value. Otherwise, compute the delay, cache it,
        and return it.

        Parameters
        ----------
        tile_name : str
            The name of the tile (with super tile type if applicable).
        src_pip : str
            The source pip name.
        dst_pip : str
            The destination pip name.

        Returns
        -------
        float
            The delay of the specified pip.

        Raises
        ------
        ValueError
            If the timing model for the specified tile is not found.
        """
        # The used key to store/retrieve the delay, if the delay for the
        # same src and dst pip was already computed before, the delay
        # will be retrieved from the cache.
        key: str = f"{src_pip}.{dst_pip}"

        if tile_name not in self.timing_models:
            raise ValueError(f"Timing model for tile {tile_name!r} not found.")

        if tile_name not in self.tile_delay_dict:
            self.tile_delay_dict[tile_name] = {}

        if key in self.tile_delay_dict[tile_name]:
            logger.info(
                f"Using cached delay for key {key!r} in tile {tile_name!r} "
                f"with delay {self.tile_delay_dict[tile_name][key]}"
            )
            return self.tile_delay_dict[tile_name][key]

        timing_model = self.timing_models[tile_name]
        delay = timing_model.pip_delay(src_pip, dst_pip)
        self.tile_delay_dict[tile_name][key] = delay
        return delay
