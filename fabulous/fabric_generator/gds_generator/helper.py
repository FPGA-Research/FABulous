"""Helper utilities for GDS generation: die area, pitch, step substitution.

This module exposes utilities used by the GDS generator flows.
"""

import fnmatch
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from librelane.config.config import Config
from librelane.flows.flow import FlowException
from librelane.flows.sequential import Substitution, SubstitutionsObject
from librelane.logging.logger import info
from librelane.steps.step import Step


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


def round_die_dimension(dimension: Decimal, pitch: Decimal, divisions: int) -> Decimal:
    """Round `dimension` up so each of its `divisions` equal parts is pitch-aligned.

    A super tile is split into `divisions` equal parts during IO placement, so
    `dimension / divisions` (not just `dimension`) must be a `pitch` multiple.
    """
    return round_up_decimal(dimension / divisions, pitch) * divisions


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
    width_rounded = round_die_dimension(width, x_pitch, mWidth)
    height_rounded = round_die_dimension(height, y_pitch, mHeight)
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


def merge_layered_substitutions(
    config_sources: list[Any],
) -> SubstitutionsObject | None:
    """Merge `meta.substituting_steps` across layered config sources.

    `Config.load()` overwrites `Config.meta` wholesale for each source in its
    configs list rather than merging, so a later source with no `meta:` key
    (e.g. a tile-specific or custom override dict) silently drops an earlier
    source's `substituting_steps`. This walks the same sources ourselves, in
    the same order, and concatenates each source's own substitutions so a
    later source's entries still apply after an earlier source's.
    """
    merged: list[tuple[str, Substitution]] = []
    for source in config_sources:
        if source is None:
            continue
        if isinstance(source, Path | str):
            if not Path(source).exists():
                # A missing base/override config file is tolerated elsewhere
                # in these flows (Config.load treats it as contributing
                # nothing), so mirror that here instead of letting
                # Config.get_meta's open() raise on a path that legitimately
                # may not exist.
                continue
            # Config.get_meta only special-cases `str`, not other PathLikes.
            source = str(source)
        meta = Config.get_meta(source)
        if not meta.substituting_steps:
            continue
        items = (
            meta.substituting_steps.items()
            if isinstance(meta.substituting_steps, dict)
            else meta.substituting_steps
        )
        merged.extend(items)
    return merged or None


def _substitute_one(
    steps: list[type[Step]],
    id: str,  # noqa: A002
    with_step: Substitution,
) -> None:
    mode = "replace"
    if id.startswith("+"):
        id = id[1:]  # noqa: A001
        mode = "append"
        if with_step is None:
            raise FlowException("Cannot prepend or append None.")
    elif id.startswith("-"):
        id = id[1:]  # noqa: A001
        mode = "prepend"
        if with_step is None:
            raise FlowException("Cannot prepend or append None.")

    step_indices = [
        i
        for i, step in enumerate(steps)
        if step.id != NotImplemented and fnmatch.fnmatch(step.id.lower(), id.lower())
    ]
    if not step_indices:
        if with_step is None:
            raise FlowException(
                f"Could not remove '{id}': no steps with ID '{id}' found in loop body"
            )
        raise FlowException(
            f"Could not {mode} '{id}' with '{with_step}': no steps with ID "
            f"'{id}' found in loop body."
        )

    if with_step is None:
        for index in reversed(step_indices):
            del steps[index]
        return

    resolved_step = with_step
    if isinstance(resolved_step, str):
        found = Step.factory.get(resolved_step)
        if found is None:
            raise FlowException(
                f"Could not {mode} '{id}' with '{resolved_step}': no replacement "
                f"step with ID '{resolved_step}' found."
            )
        resolved_step = found

    for i in step_indices:
        if mode == "replace":
            steps[i] = resolved_step
        elif mode == "append":
            steps.insert(i + 1, resolved_step)
        elif mode == "prepend":
            steps.insert(i, resolved_step)


def apply_step_substitutions(
    steps: list[type[Step]],
    substitutions: SubstitutionsObject,
) -> list[type[Step]]:
    """Apply LibreLane-style step substitutions to a nested step list.

    LibreLane's `SequentialFlow.Substitute`/`meta.substituting_steps` only walks
    a flow's top-level `Steps` list, so it cannot see steps nested inside a
    `WhileStep` (a FABulous-authored composite, not a LibreLane built-in). This
    reproduces the same matching/replace semantics for that nested list, so
    `gds_config.yaml` can target loop-internal steps with identical syntax.

    Parameters
    ----------
    steps : list[type[Step]]
        The loop body to substitute into. Not mutated; a copy is returned.
    substitutions : SubstitutionsObject
        A dict or list of (id, step) tuples, using the same syntax as
        LibreLane's `meta.substituting_steps`: a bare id replaces, `+id`
        appends after, `-id` prepends before, and a `None` value removes.

    Returns
    -------
    list[type[Step]]
        The resulting step list.
    """
    result = list(steps)
    items = substitutions.items() if isinstance(substitutions, dict) else substitutions
    for id, with_step in items:  # noqa: A001
        _substitute_one(result, id, with_step)
    return result
