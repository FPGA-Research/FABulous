"""Helper utilities for GDS generation: die area rounding and pitch parsing.

This module exposes utilities used by the GDS generator flows.
"""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

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
    (FP_IO_VLAYER X direction) and y_pitch is minimum pitch along Y-axis (FP_IO_HLAYER Y
    direction). The cardinal field in FP_TRACKS_INFO is expected to be 'X' or 'Y' (case-
    insensitive).
    """
    layers = get_layer_info(config)

    x_pitch = layers[config["FP_IO_VLAYER"]]["X"][1]
    y_pitch = layers[config["FP_IO_HLAYER"]]["Y"][1]

    return x_pitch, y_pitch


def get_offset(config: Config) -> tuple[Decimal, Decimal]:
    """Read the FP_TRACKS_INFO file and return min pitches for X and Y.

    Returns a tuple (x_pitch, y_pitch) where x_pitch is the minimum pitch along X-axis
    (FP_IO_VLAYER X direction) and y_pitch is minimum pitch along Y-axis (FP_IO_HLAYER Y
    direction). The cardinal field in FP_TRACKS_INFO is expected to be 'X' or 'Y' (case-
    insensitive).
    """
    layers = get_layer_info(config)

    x_offset = layers[config["FP_IO_VLAYER"]]["X"][0]
    y_offset = layers[config["FP_IO_HLAYER"]]["Y"][0]

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
        The configuration object from liberlane.config.config

    Returns
    -------
    list[tuple[str, Decimal | int, Decimal | int, Decimal | int, Decimal | int]]
        A list of obstruction tuples.
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
