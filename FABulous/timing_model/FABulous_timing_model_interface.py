#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# This module serves as an interface for other cad tools to interact with the FABulous timing model.

from pathlib import Path
import os
import re

from .FABulous_timing_model import FABulousTileTimingModel

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile

class FABulousTimingModelInterface:
    def __init__(self, config: dict, fabric: Fabric):
        self.config = config
        self.fabric = fabric
        self.tile_delay_dict: dict[str, dict[str, float]] = {}
        self.tiles: dict[str, list[str]] = self.collect_subdirs(
            Path(self.config["project_dir"]) / "Tile", 
            name_pattern=r".*_bot|.*_top",
            exclude_dirs=["include"]
        )
        
        print(f"Initializing timing models for tiles, with mode: {self.config['mode']}")
        
        self.timing_models: dict[str, FABulousTileTimingModel] = {}
        for tile_name, super_tile_types in self.tiles.items():
            model_config = self.config.copy()
            model_config["tile_name"] = tile_name
            if super_tile_types:
                for super_tile_type in super_tile_types:
                    model_config["super_tile_type"] = "bot" if super_tile_type.endswith("_bot") else "top"
                    timing_model = FABulousTileTimingModel(config=model_config)
                self.timing_models[f"{tile_name}_{super_tile_type}"] = timing_model
            else:
                model_config["super_tile_type"] = None
                timing_model = FABulousTileTimingModel(config=model_config)
                self.timing_models[f"{tile_name}"] = timing_model
        
    def collect_subdirs(self, root: Path, name_pattern: str = None, exclude_dirs: list[str] = None
    ) -> dict[str, list[str]]:
        """
        Given a root directory (as a Path), return a dict mapping each
        *direct* subdirectory name of `root` to a list of directory names
        (any depth below it) whose names match `name_pattern` (regex).

        If `name_pattern` is None, all lists are empty.

        Example output:
            {
            "dir1": ["foo_match", "bar_match"],
            "dir2": [],
            "dir3": [],
            }
        """
        if not isinstance(root, Path):
            raise ValueError("root must be a Path object.")
        
        if not root.is_dir():
            raise NotADirectoryError(f"{root!r} is not a directory")

        pattern = re.compile(name_pattern) if name_pattern is not None else None
        result: dict[str, list[str]] = {}

        # iterate only over direct subdirs of root
        for direct_subdir in sorted(p for p in root.iterdir() if p.is_dir()):
            if exclude_dirs is not None and direct_subdir.name in exclude_dirs:
                continue
            matches: list[str] = []
            if pattern is not None:
                # walk recursively under this direct subdir
                for dirpath, dirnames, _ in os.walk(direct_subdir):
                    for dname in dirnames:
                        if pattern.search(dname):
                            matches.append(dname)

            result[direct_subdir.name] = matches

        return result
    
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
            print(f"Using cached delay for key {key!r} in tile {tile_name!r} "
                  f"with delay {self.tile_delay_dict[tile_name][key]}")
            return self.tile_delay_dict[tile_name][key]
        
        timing_model = self.timing_models[tile_name]
        delay = timing_model.pip_delay(src_pip, dst_pip)
        self.tile_delay_dict[tile_name][key] = delay
        return delay
        
        
