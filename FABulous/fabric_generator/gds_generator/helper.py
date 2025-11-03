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


def get_routing_obstructions(config: Config) -> list[tuple[int, int, int, int]]:
    """Get the routing obstructions from the config.

    Returns a list of tuples (x1, y1, x2, y2) representing the obstructions in the
    routing area.
    """
    obstructions = config.get("ROUTING_OBSTRUCTIONS") or []
    _, _, width, height = config["DIE_AREA"]

    parsed_obstructions = defaultdict(list)
    for obs in obstructions:
        if len(obs) != 4:
            raise ValueError(
                f"Invalid obstruction {obs}. Each obstruction must be a tuple of "
                "4 integers."
            )
        met, *box = obs
        parsed_obstructions[met].append(box)

    if (layer := config["FP_IO_VLAYER"]) not in parsed_obstructions:
        # Add thin horizontal obstructions just outside bottom and top edges
        parsed_obstructions[layer].append((0, -1, width, 0))
        parsed_obstructions[layer].append((0, height, width, height + 1))

    if (layer := config["FP_IO_HLAYER"]) not in parsed_obstructions:
        # Add thin vertical obstructions just outside left and right edges
        parsed_obstructions[layer].append((-1, 0, 0, height))
        parsed_obstructions[layer].append((width, 0, width + 1, height))

    result = []
    for layer, boxes in parsed_obstructions.items():
        for box in boxes:
            result.append((layer, *box))

    return result
