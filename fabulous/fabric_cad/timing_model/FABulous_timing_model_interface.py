"""
This module defines the FABulousTimingModelInterface class, which provides an interface to compute and cache
timing delays for pips in a FABulous fabric. It uses the FABulousTileTimingModel to compute 
delays for individual tiles and caches the results for efficient retrieval.
"""

from pathlib import Path
import os
import re

from loguru import logger

from fabulous.fabric_cad.timing_model.FABulous_timing_model import FABulousTileTimingModel

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile


class FABulousTimingModelInterface:
    """
    Interface for computing and caching timing delays for pips in a FABulous fabric.
    """
    
    def __init__(self, config: dict, fabric: Fabric):
        """
        Initialize the FABulousTimingModelInterface with the given configuration and fabric.

        Args:
            config (dict): Configuration dictionary for the timing model.
            fabric (Fabric): The FABulous fabric object.
        """
        
        self.config = config
        self.fabric = fabric
        self.tile_delay_dict: dict[str, dict[str, float]] = {}

        self.timing_models: dict[str, FABulousTileTimingModel] = {}

        logger.info(
            f"Initializing timing models for tiles, with mode: {self.config['mode']}"
        )

        for tile_name, tile in fabric.tileDic.items():
            model_config = self.config.copy()
            model_config["tile_name"] = tile_name
            timing_model = FABulousTileTimingModel(
                config=model_config, fabric=self.fabric
            )
            self.timing_models[tile_name] = timing_model

    def pip_delay(self, tile_name: str, key: str, src_pip: str, dst_pip: str) -> float:
        """
        Get the delay for a given pip in the timing model and save
        the result delay with key. If the delay for the key was already
        computed before, return the cached value.

        Args:
            key (str): The key to store/retrieve the delay.
            src_pip (str): The source pip name.
            dst_pip (str): The destination pip name.
            tile_name (str): The name of the tile (with super tile type if applicable).

        Returns:
            float: The delay of the specified pip.
        """
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
