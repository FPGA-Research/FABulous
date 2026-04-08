"""Helper utilities for GDS generation: die area rounding and pitch parsing.

This module exposes utilities used by the GDS generator flows.
"""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from librelane.config.config import Config
from librelane.logging.logger import info


def get_layer_info(config: Config) -> dict[str, dict[str, tuple[Decimal, Decimal]]]:
    """Read the FP_TRACKS_INFO file and return layer information.

    Returns a dictionary mapping layer names to their cardinal directions and
    corresponding (offset, pitch) tuples.
    """
    with Path(config["FP_TRACKS_INFO"]).open() as f:
        lines = f.readlines()

    layers: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
    for line in lines:
        if line.strip() == "":
            continue
        layer, cardinal, offset, pitch = line.split()
        layers[layer] = layers.get(layer) or {}
        layers[layer][cardinal] = (Decimal(offset), Decimal(pitch))

    return layers


def get_pitch(config: Config) -> tuple[Decimal, Decimal]:
    """Read the FP_TRACKS_INFO file and return min pitches for X and Y.

    Returns a tuple (x_pitch, y_pitch) where x_pitch is the minimum pitch along X-axis
    (IO_PIN_V_LAYER X direction) and y_pitch is minimum pitch along Y-axis
    (IO_PIN_H_LAYER Y direction). The cardinal field in FP_TRACKS_INFO is expected to be
    'X' or 'Y' (case-insensitive).
    """
    layers = get_layer_info(config)

    x_pitch = layers[config["IO_PIN_V_LAYER"]]["X"][1]
    y_pitch = layers[config["IO_PIN_H_LAYER"]]["Y"][1]

    return x_pitch, y_pitch


def get_offset(config: Config) -> tuple[Decimal, Decimal]:
    """Read the FP_TRACKS_INFO file and return track offsets for X and Y.

    Returns a tuple (x_offset, y_offset) where x_offset is the track offset along X-axis
    (IO_PIN_V_LAYER X direction) and y_offset is the track offset along Y-axis
    (IO_PIN_H_LAYER Y direction). The cardinal field in FP_TRACKS_INFO is expected to be
    'X' or 'Y' (case-insensitive).
    """
    layers = get_layer_info(config)

    x_offset = layers[config["IO_PIN_V_LAYER"]]["X"][0]
    y_offset = layers[config["IO_PIN_H_LAYER"]]["Y"][0]

    return x_offset, y_offset


def round_up_decimal(value: Decimal, pitch: Decimal) -> Decimal:
    """Round up value to the next multiple of pitch."""
    if pitch == 0:
        return value
    quotient = value // pitch

    remainder = value % pitch
    if remainder > 0:
        quotient += 1
    return quotient * pitch


def _merge_two_mappings(
    base_config: dict[str, Any],
    override_config: dict[str, Any],
) -> dict[str, Any]:
    """Merge two mappings with one-level nested dict merging semantics."""
    merged_config = dict(base_config)
    for key, override_value in override_config.items():
        base_value = merged_config.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            merged_config[key] = {**base_value, **override_value}
        else:
            merged_config[key] = override_value
    return merged_config


def merge_config_mappings(
    base_config: dict[str, Any], *configs: Path, **kwargs: dict
) -> dict[str, Any]:
    """Merge a base dict with YAML config files and keyword overrides.

    Applies one-level nested dict merging: when both the base and override
    values for a key are dicts, their entries are shallow-merged (override wins).
    All other types are replaced outright.

    Precedence (last wins): base_config < config files (in order) < kwargs.

    Parameters
    ----------
    base_config : dict[str, Any]
        Base configuration dictionary.
    *configs : Path
        YAML configuration file paths to merge in order on top of base.
    **kwargs : dict
        Final keyword overrides applied after all file-based configs.

    Raises
    ------
    TypeError
        If any of the config files contains a non-mapping at the top level.

    Returns
    -------
    dict[str, Any]
        The merged configuration dictionary.
    """
    merged_config = dict(base_config)
    for config_path in configs:
        loaded_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded_config is None:
            continue
        if not isinstance(loaded_config, dict):
            raise TypeError(f"Config YAML at {config_path} must contain a mapping")
        merged_config = _merge_two_mappings(merged_config, loaded_config)
    return _merge_two_mappings(merged_config, kwargs)


def round_die_area(config: Config) -> Config:
    """Round the DIE_AREA to multiples of the minimum pitch.

    This reads the minimum pitch from FP_TRACKS_INFO and updates the config DIE_AREA to
    start at (0,0) with width/height rounded up to the next multiple of that pitch.
    """
    x_pitch, y_pitch = get_pitch(config)

    die_area = config.get("DIE_AREA")
    if die_area is None:
        raise ValueError("DIE_AREA metric not found in state.")
    _, _, width, height = die_area
    width = Decimal(width)
    height = Decimal(height)

    # Round width (X) and height (Y) to the next multiple of the
    # respective minimum pitches using pure Decimal arithmetic

    mWidth = int(config["FABULOUS_TILE_LOGICAL_WIDTH"])
    mHeight = int(config["FABULOUS_TILE_LOGICAL_HEIGHT"])
    width_rounded = round_up_decimal(width / mWidth, x_pitch) * mWidth
    height_rounded = round_up_decimal(height / mHeight, y_pitch) * mHeight
    info(
        f"Rounding DIE_AREA from ({width}, {height}) to "
        f"({width_rounded}, {height_rounded}) "
        f"(pitch_x={x_pitch}, pitch_y={y_pitch})"
    )
    return config.copy(DIE_AREA=(0, 0, width_rounded, height_rounded))


def get_routing_obstructions(
    config: Config,
) -> list[tuple[str, Decimal, Decimal, Decimal, Decimal]]:
    """Get the routing obstructions from the config.

    Returns a list of tuples (layer, x1, y1, x2, y2) representing the obstructions in
    the routing area.

    Parameters
    ----------
    config : Config
        The configuration object from liberlane.

    Returns
    -------
    list[tuple[str, Decimal, Decimal, Decimal, Decimal]]
        A list of obstruction tuples.

    Raises
    ------
    ValueError
        If the entry is not a valid obstruction.
    """
    obstructions = config.get("ROUTING_OBSTRUCTIONS") or []
    _, _, width, height = config["DIE_AREA"]
    layers = get_layer_info(config)
    parsed_obstructions = defaultdict(list)
    for obs in obstructions:
        if len(obs) != 5:
            raise ValueError(
                f"Invalid obstruction {obs}. Each obstruction must be a tuple of "
                "the metal layer followed by 4 decimals"
            )
        met, *box = obs
        parsed_obstructions[met].append(box)

    zero = Decimal(0)
    # Add thin obstructions at all the edges
    for layer_name, layer_data in layers.items():
        x_pitch = layer_data["X"][1]
        y_pitch = layer_data["Y"][1]

        # horizontal obstructions
        parsed_obstructions[layer_name].append((zero, -y_pitch / 2, width, zero))
        parsed_obstructions[layer_name].append(
            (zero, height, width, height + y_pitch / 2)
        )

        # vertical obstructions
        parsed_obstructions[layer_name].append((-x_pitch / 2, zero, zero, height))
        parsed_obstructions[layer_name].append(
            (width, zero, width + x_pitch / 2, height)
        )

    result = []
    for layer, boxes in parsed_obstructions.items():
        for box in boxes:
            result.append((layer, *box))

    return result
