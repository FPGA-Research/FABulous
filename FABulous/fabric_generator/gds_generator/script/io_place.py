# Copyright 2020-2022 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Utilities for placing IO pins by expanding configuration segments."""

import logging
import math
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any, Protocol

import click
import odb  # type: ignore[import]
import yaml
from librelane.logging.logger import debug, err, info, warn
from librelane.scripts.odbpy.reader import click_odb

from FABulous.fabric_definition.define import PinSortMode, Side


class OdbReaderLike(Protocol):
    """Protocol describing the reader object provided by the click wrapper."""

    dbunits: float
    tech: Any
    block: Any
    name: str


def grid_to_tracks(origin: float, count: int, step: float) -> list[float]:
    """Return monotonically increasing track locations starting at origin."""
    tracks: list[float] = []
    pos = origin
    for _ in range(count):
        tracks.append(pos)
        pos += step
    assert len(tracks) > 0
    tracks.sort()

    return tracks


def equally_spaced_sequence(
    side: str, side_pin_placement: list, possible_locations: list
) -> tuple[list, list]:
    """Select evenly spaced slots for the given pins on a single side."""
    virtual_pin_count = 0
    actual_pin_count = len(side_pin_placement)
    total_pin_count = actual_pin_count + virtual_pin_count
    for i in range(len(side_pin_placement)):
        if isinstance(
            side_pin_placement[i], int
        ):  # This is an int value indicating virtual pins
            virtual_pin_count = virtual_pin_count + side_pin_placement[i]
            actual_pin_count = actual_pin_count - 1
            # Decrement actual pin count, this value was only there to
            # indicate virtual pin count
            total_pin_count = actual_pin_count + virtual_pin_count
    result = []
    tracks = len(possible_locations)

    if total_pin_count > tracks:
        err(
            f"The {side} side of the floorplan doesn't have enough slots for all "
            f"the pins: {total_pin_count} pins/{tracks} slots."
        )
        err(
            "Try re-assigning pins to other sides, enabling proportional allocation, "
            "or making the floorplan larger."
        )
        sys.exit(1)
    elif total_pin_count == tracks:
        return possible_locations, side_pin_placement  # All positions.
    elif total_pin_count == 0:
        return result, side_pin_placement

    # From this point, pin_count always < tracks.
    tracks_per_pin = math.floor(tracks / total_pin_count)  # >=1
    # O| | | O| | | O| | |
    # Example scenario where tracks_per_pin equals 3
    # notice the last two tracks are unused
    # thus:
    used_tracks = tracks_per_pin * (total_pin_count - 1) + 1
    unused_tracks = tracks - used_tracks

    # Place the pins at those tracks...
    current_track = unused_tracks // 2  # So that the tracks used are centered
    starting_track_index = current_track
    if virtual_pin_count == 0:  # No virtual pins
        for _ in range(total_pin_count):
            result.append(possible_locations[current_track])
            current_track += tracks_per_pin
    else:  # There are virtual pins
        for i in range(len(side_pin_placement)):
            if not isinstance(side_pin_placement[i], int):  # We have an actual pin
                result.append(possible_locations[current_track])
                current_track += tracks_per_pin
            else:  # Virtual Pins, so just leave their needed spaces
                current_track += tracks_per_pin * side_pin_placement[i]
        side_pin_placement = [
            pin for pin in side_pin_placement if not isinstance(pin, int)
        ]  # Remove the virtual pins from the side_pin_placement list

    info(
        f"Placement details {side} | "
        f"{virtual_pin_count=} {actual_pin_count=} {total_pin_count=} "
        f"possible_locations={len(possible_locations)} "
        f"{tracks_per_pin=} {used_tracks=} {unused_tracks=} {starting_track_index=}",
    )

    VISUALIZE_PLACEMENT = False
    if VISUALIZE_PLACEMENT:
        debug("Placement Map:")
        map_str = ["["]
        used_track_indices = []
        for i, location in enumerate(possible_locations):
            if location in result:
                map_str.append(f"*{location}, ")
                used_track_indices.append(i)
            else:
                map_str.append(f"{location}, ")
        map_str.append("]")
        debug("".join(map_str))
        debug("Used track indices: %s", used_track_indices)

    return result, side_pin_placement


identifiers = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")
standalone_numbers = re.compile(r"\b\d+\b")
trash = re.compile(r"^[^\w\d]+$")


def sorter(bterm: "odb.dbBTerm", order: PinSortMode) -> list[list[str | int]]:
    """Return sorting keys for a boundary term using the requested strategy."""
    text: str = bterm.getName()
    keys = []
    priority_keys = []
    # tokenize and add to key
    while trash.match(text) is None:
        if match := identifiers.search(text):
            bus = match[0]
            start, end = match.span(0)
            if order == PinSortMode.BUS_MAJOR:
                priority_keys.append(bus)
            else:
                keys.append(bus)
            text = text[:start] + text[end:]
        elif match := standalone_numbers.search(text):
            index = int(match[0])
            if order == PinSortMode.BIT_MINOR:
                priority_keys.append(index)
            else:
                keys.append(index)
            text = text[: match.start()] + text[match.end() :]
        else:
            break
    return [priority_keys, keys]


@dataclass(slots=True)
class SegmentInfo:
    """Fully processed data for one YAML-defined segment on a side."""

    side: Side
    sort_mode: PinSortMode
    min_distance: float | None
    max_distance: float | None
    reverse_result: bool
    pin_entries: list
    tile_index: int | None = None  # Enumerated index within this side
    tile_x: int | None = None  # Actual X coordinate of the tile
    tile_y: int | None = None  # Actual Y coordinate of the tile

    @classmethod
    def from_config(
        cls,
        side: Side,
        segment: dict,
        bterms: list,
        regex_by_bterm: dict,
        unmatched_regexes: set[str],
        tile_index: int | None = None,
        tile_x: int | None = None,
        tile_y: int | None = None,
    ) -> "SegmentInfo":
        """Build a fully populated segment from a raw YAML entry."""
        sort_mode_str = segment.get("sort_mode", "bus_major")
        if sort_mode_str == "bus_major":
            sort_mode = PinSortMode.BUS_MAJOR
        elif sort_mode_str == "bit_minor":
            sort_mode = PinSortMode.BIT_MINOR
        else:
            raise ValueError(f"Unknown sort mode {sort_mode_str}")

        entries: list = []
        for pattern in segment.get("pins", []):
            if isinstance(pattern, int):
                entries.append(pattern)
                continue

            anchored = f"^{pattern}$"
            matched_terms = [b for b in bterms if re.match(anchored, b.getName())]

            if not matched_terms:
                unmatched_regexes.add(pattern)
                continue

            for bterm in matched_terms:
                if bterm in regex_by_bterm:
                    raise SystemExit(
                        f"[ERROR] Multiple regexes matched {bterm.getName()}: "
                        f"{regex_by_bterm[bterm]} and {pattern}"
                    )
                regex_by_bterm[bterm] = pattern

            matched_terms.sort(key=partial(sorter, order=sort_mode))
            entries.extend(matched_terms)

        return cls(
            side=side,
            sort_mode=sort_mode,
            min_distance=segment.get("min_distance"),
            max_distance=segment.get("max_distance"),
            reverse_result=segment.get("reverse_result", False),
            pin_entries=entries,
            tile_index=tile_index,
            tile_x=tile_x,
            tile_y=tile_y,
        )

    @property
    def actual_pin_count(self) -> int:
        """Return the number of concrete pins in this segment."""
        return sum(1 for entry in self.pin_entries if not isinstance(entry, int))

    @property
    def has_virtual_placeholders(self) -> bool:
        """Return True if this segment reserves space using virtual pins."""
        return any(isinstance(entry, int) for entry in self.pin_entries)

    def ensure_min_distance(self, min_allowed: float) -> None:
        """Clamp the minimum spacing constraint to the technology limit."""
        if self.min_distance is None or self.min_distance < min_allowed:
            debug(
                "Adjusting min_distance for side %s segment (given=%s -> %s)",
                self.side.value,
                self.min_distance,
                min_allowed,
            )
            self.min_distance = min_allowed

    def apply_reverse(self) -> None:
        """Reverse pin order when requested by the configuration."""
        if self.reverse_result:
            self.pin_entries.reverse()

    def replace_pin_entries(self, entries: list) -> None:
        """Overwrite the stored pin list after track allocation."""
        self.pin_entries = entries


class PinPlacementPlan:
    """Collects processed segment definitions and related pin bookkeeping."""

    __slots__ = (
        "segments_by_side",
        "regex_by_bterm",
        "unmatched_config_patterns",
        "unmatched_design_bterms",
        "unmatched_design_pin_names",
        "critical_errors_found",
        "track_coordinates",
        "tile_counts_by_side",
        "fabric_dimensions",
    )

    def __init__(
        self,
        config_data: dict,
        bterms: list,
        unmatched_error: str,
    ) -> None:
        """Initialise the plan by expanding all regex patterns."""
        self.segments_by_side: dict[Side, list[SegmentInfo]] = {
            side: [] for side in Side
        }
        self.regex_by_bterm: dict = {}
        self.unmatched_config_patterns: set[str] = set()
        self.critical_errors_found = False
        self.track_coordinates: dict[Side, list[list[float]]] = {
            side: [] for side in Side
        }
        self.tile_counts_by_side: dict[Side, int] = {side: 0 for side in Side}
        self.fabric_dimensions: tuple[int, int] = (1, 1)  # (width, height)

        normalized_config, tile_counts, fabric_dims = self._normalize_config(
            config_data
        )
        self.tile_counts_by_side = tile_counts
        self.fabric_dimensions = fabric_dims
        for side, segment_list in normalized_config.items():
            for segment_data in segment_list:
                seg_info = SegmentInfo.from_config(
                    side,
                    segment_data["segment"],
                    bterms,
                    self.regex_by_bterm,
                    self.unmatched_config_patterns,
                    tile_index=segment_data.get("tile_index"),
                    tile_x=segment_data.get("tile_x"),
                    tile_y=segment_data.get("tile_y"),
                )
                self.segments_by_side[side].append(seg_info)

        self.unmatched_design_bterms: set = {
            bterm for bterm in bterms if bterm not in self.regex_by_bterm
        }
        self.unmatched_design_pin_names: set[str] = {
            bterm.getName() for bterm in self.unmatched_design_bterms
        }

        self._handle_unmatched(unmatched_error)

    def _handle_unmatched(self, unmatched_error: str) -> None:
        """Report unmatched pins and enforce error policy."""
        for pin_name in self.unmatched_config_patterns:
            should_error = unmatched_error in {"unmatched_cfg", "both"}
            if should_error:
                self.critical_errors_found = True
                err(f"{pin_name} not found in design but found in config.")
            else:
                warn(f"{pin_name} not found in design but found in config.")

        for pin_name in self.unmatched_design_pin_names:
            should_error = unmatched_error in {"unmatched_design", "both"}
            if should_error:
                self.critical_errors_found = True
                err(f"{pin_name} not found in config but found in design.")
            else:
                warn(f"{pin_name} not found in config but found in design.")

        if self.critical_errors_found:
            err("Critical mismatches found.")
            raise SystemExit(os.EX_DATAERR)

    @staticmethod
    def _normalize_config(
        config_data: dict,
    ) -> tuple[dict[Side, list[dict]], dict[Side, int], tuple[int, int]]:
        """Return side-indexed segment list, tile counts, and fabric dimensions.

        Returns
        -------
        tuple
            - config_by_side: Segments organized by side
            - tile_counts: Number of tiles per side
            - fabric_dims: (max_x + 1, max_y + 1) fabric dimensions in tiles
        """
        tile_counts = {side: 0 for side in Side}

        if not config_data:
            # Return empty list for each side
            return {side: [] for side in Side}, tile_counts, (1, 1)

        tile_pattern = re.compile(r"^X(?P<x>\d+)Y(?P<y>\d+)$")

        tiles: dict[tuple[int, int], dict] = {}
        max_x = 0
        max_y = 0
        for key, entry in config_data.items():
            match = tile_pattern.match(key)
            assert match is not None  # validated above
            tile_config = entry or {}
            if not isinstance(tile_config, dict):
                raise TypeError(
                    "Configuration for tile "
                    f"{key} must be a mapping of sides to segments"
                )
            x = int(match.group("x"))
            y = int(match.group("y"))
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            tiles[(x, y)] = tile_config

        # Fabric dimensions: max coordinate + 1
        fabric_width = max_x + 1
        fabric_height = max_y + 1

        neighbor_offsets = {
            Side.NORTH: (0, -1),
            Side.SOUTH: (0, 1),
            Side.EAST: (1, 0),
            Side.WEST: (-1, 0),
        }

        side_entries: dict[Side, list[tuple[int, int, list[dict]]]] = {
            side: [] for side in Side
        }

        for (x, y), tile_config in tiles.items():
            for side, (dx, dy) in neighbor_offsets.items():
                neighbor_exists = (x + dx, y + dy) in tiles

                value = None
                if side.name in tile_config:
                    value = tile_config[side.name]

                if value is None:
                    segments = []
                else:
                    if not isinstance(value, list):
                        raise TypeError(
                            "Segments for tile X"
                            f"{x}Y{y} side {side.value} must be provided as a list"
                        )  # Raise TypeError if segments are not a list
                    segments = value

                if neighbor_exists:
                    if segments:
                        raise ValueError(
                            f"Tile X{x}Y{y} side {side.value} is not on the boundary; "
                            "remove its configuration."
                        )
                    continue

                if segments:
                    side_entries[side].append((x, y, segments))

        config_by_side: dict[Side, list[dict]] = {side: [] for side in Side}

        for side, entries in side_entries.items():
            if side in (Side.NORTH, Side.SOUTH):
                entries.sort(key=lambda item: item[0])  # sort by x coordinate
            else:
                entries.sort(key=lambda item: item[1])  # sort by y coordinate

            tile_counts[side] = len(entries)

            for tile_idx, (x, y, segments) in enumerate(entries):
                for segment in segments:
                    config_by_side[side].append(
                        {
                            "segment": segment,
                            "tile_index": tile_idx,
                            "tile_x": x,
                            "tile_y": y,
                        }
                    )

        return config_by_side, tile_counts, (fabric_width, fabric_height)

    def allocate_tracks(
        self,
        specs: dict[Side, tuple[int, float, float, float]],
    ) -> None:
        """Allocate raw track coordinates for every segment on each side."""
        for side, segments in self.segments_by_side.items():
            if side not in specs:
                # Skip sides that don't have track specifications
                continue
            count_total, step, origin, physical_dimension = specs[side]
            self.track_coordinates[side] = self._build_tracks_for_segments(
                count_total, step, origin, physical_dimension, segments, side
            )

    def _build_tracks_for_segments(
        self,
        count_total: int,
        step: float,
        origin: float,
        physical_dimension: float,
        segments_for_side: list[SegmentInfo],
        side: Side,
    ) -> list[list[float]]:
        """Build track lists for segments using physical tile-based allocation.

        Matches the original librelane approach: uses DIE_AREA physical dimensions
        to compute tile offsets, ensuring tiles align based on actual physical size.

        Each tile gets tracks proportional to its position in the physical die area.
        """
        if not segments_for_side:
            return []

        # Get fabric dimensions to calculate per-tile allocation
        fabric_width, fabric_height = self.fabric_dimensions

        # For North/South sides, width determines horizontal divisions
        # For East/West sides, height determines vertical divisions
        num_divisions = (
            fabric_width if side in (Side.NORTH, Side.SOUTH) else fabric_height
        )
        if num_divisions <= 0:
            return []

        # Check if tracks can be evenly divided (librelane requirement)
        if count_total % num_divisions != 0:
            warn(
                f"Track count {count_total} not evenly divisible by "
                f"{num_divisions} tiles on {side.value} side. "
                f"This may cause alignment issues."
            )

        # Each tile gets equal track count
        tracks_per_tile = count_total // num_divisions

        # Group segments by their tile position
        segments_by_tile = self._group_segments_by_tile(segments_for_side)

        # Allocate tracks for each tile in order
        tracks_container: list[list[float]] = []
        for tile_idx in sorted(segments_by_tile.keys()):
            tile_x, tile_y, tile_segments = segments_by_tile[tile_idx]

            division_index = self._get_division_index(
                side, tile_x, tile_y, tile_idx, num_divisions
            )

            # Calculate offset based on PHYSICAL position (librelane approach)
            # Proportional positioning in the die area
            physical_offset = int(physical_dimension * division_index / num_divisions)
            tile_origin = origin + physical_offset

            tile_tracks = self._allocate_tracks_for_tile(
                tracks_per_tile, step, tile_origin, tile_segments
            )
            tracks_container.extend(tile_tracks)

        return tracks_container

    @staticmethod
    def _group_segments_by_tile(
        segments: list[SegmentInfo],
    ) -> dict[int, tuple[int | None, int | None, list[SegmentInfo]]]:
        """Group segments by their tile index.

        Returns
        -------
        dict[int, tuple[int | None, int | None, list[SegmentInfo]]]
            Maps tile_index -> (tile_x, tile_y, [segments])
        """
        segments_by_tile: dict[
            int, tuple[int | None, int | None, list[SegmentInfo]]
        ] = {}

        for segment in segments:
            tile_idx = segment.tile_index if segment.tile_index is not None else 0
            if tile_idx not in segments_by_tile:
                segments_by_tile[tile_idx] = (segment.tile_x, segment.tile_y, [])
            segments_by_tile[tile_idx][2].append(segment)

        return segments_by_tile

    @staticmethod
    def _get_division_index(
        side: Side,
        tile_x: int | None,
        tile_y: int | None,
        tile_idx: int,
        num_divisions: int,
    ) -> int:
        """Determine which division (tile position) a tile belongs to.

        For N/S sides, use X coordinate; for E/W sides, use Y coordinate.
        Falls back to tile_idx if coordinates are unavailable.
        Clamps to valid range [0, num_divisions).
        """
        # Select coordinate based on side orientation
        position_coord = tile_x if side in (Side.NORTH, Side.SOUTH) else tile_y
        division_index = position_coord if position_coord is not None else tile_idx

        # Clamp to valid range
        return max(0, min(division_index, num_divisions - 1))

    @staticmethod
    def _allocate_tracks_for_tile(
        track_count: int,
        step: float,
        origin: float,
        segments: list[SegmentInfo],
    ) -> list[list[float]]:
        """Allocate tracks within a single tile for its segments."""
        tracks_container: list[list[float]] = []
        num_segments = len(segments)
        if num_segments == 0:
            return tracks_container

        counts = [segment.actual_pin_count for segment in segments]
        total = sum(counts)

        if total == 0:
            base = track_count // num_segments if num_segments else 0
            remainder = track_count - base * num_segments
            slices = []
            start = 0
            for idx in range(num_segments):
                size = base + (1 if idx < remainder else 0)
                slices.append((start, size))
                start += size
        else:
            fractional = [c / total * track_count for c in counts]
            sizes = [max(1, int(round(fraction))) for fraction in fractional]
            delta = track_count - sum(sizes)

            while delta > 0:
                for idx in range(num_segments):
                    if delta == 0:
                        break
                    sizes[idx] += 1
                    delta -= 1
            while delta < 0:
                for idx in range(num_segments):
                    if delta == 0:
                        break
                    if sizes[idx] > 1:
                        sizes[idx] -= 1
                        delta += 1

            start = 0
            slices = []
            for size in sizes:
                slices.append((start, size))
                start += size

        for start_idx, size in slices:
            start_coord = origin + start_idx * step
            tracks_container.append(grid_to_tracks(start_coord, size, step))

        return tracks_container

    def tracks_for_segment(self, side: Side, index: int) -> list[float]:
        """Return the raw track coordinates allocated for a segment."""
        return self.track_coordinates[side][index]

    def segments(self, side: Side) -> list[SegmentInfo]:
        """Return the ordered list of segments for a given side."""
        return self.segments_by_side[side]

    def all_segments(self) -> Iterable[SegmentInfo]:
        """Iterate over all segments across every side."""
        for side in Side:
            yield from self.segments_by_side[side]

    def ensure_min_distances(self, min_by_side: dict[Side, float]) -> None:
        """Ensure each segment meets technology minimum spacing requirements."""
        for side, segments in self.segments_by_side.items():
            for segment in segments:
                segment.ensure_min_distance(min_by_side[side])

    def assign_unmatched_pins(self) -> None:
        """Place unmatched pins into the lowest-utilization segments."""
        if not self.unmatched_design_bterms:
            return
        warn(
            "Assigning unmatched pins to lowest-utilization segments (no regex match)…"
        )

        unmatched_terms = sorted(
            self.unmatched_design_bterms,
            key=lambda term: term.getName(),
        )
        self.unmatched_design_bterms.clear()

        for bterm in unmatched_terms:
            segment = self._select_segment_for_unmatched()
            segment.pin_entries.append(bterm)
            self.unmatched_design_pin_names.discard(bterm.getName())

    def _select_segment_for_unmatched(self) -> SegmentInfo:
        """Return the segment that currently has the lowest utilisation."""
        candidates: list[tuple[int, int, Side, int, SegmentInfo]] = []
        for side in Side:
            for index, segment in enumerate(self.segments_by_side[side]):
                candidates.append(
                    (
                        segment.actual_pin_count,
                        len(segment.pin_entries),
                        side,
                        index,
                        segment,
                    )
                )

        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1], item[2].value, item[3]))
            return candidates[0][4]

        side_choice = min(Side, key=lambda side: len(self.segments_by_side[side]))
        return self._create_empty_segment(side_choice)

    def _create_empty_segment(self, side: Side) -> SegmentInfo:
        """Create a placeholder segment for unmatched pins on the given side."""
        # Use tile_index=0 for single-tile fallback
        segment = SegmentInfo(
            side=side,
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
            pin_entries=[],
            tile_index=0,
        )
        self.segments_by_side[side].append(segment)
        # Ensure this side has at least 1 tile count
        if self.tile_counts_by_side[side] == 0:
            self.tile_counts_by_side[side] = 1
        return segment


@click.command()
@click.option(
    "-u",
    "--unmatched-error",
    type=click.Choice(["none", "unmatched_design", "unmatched_cfg", "both"]),
    default="both",
    help="Treat unmatched pins as error",
)
@click.option(
    "-c",
    "--config",
    required=True,
    type=click.Path(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    help="Input configuration file",
)
@click.option(
    "-v",
    "--ver-length",
    default=None,
    type=float,
    help="Length for pins with N/S orientations in microns.",
)
@click.option(
    "-h",
    "--hor-length",
    default=None,
    type=float,
    help="Length for pins with E/S orientations in microns.",
)
@click.option(
    "-V",
    "--ver-layer",
    required=True,
    help="Name of metal layer to place vertical pins on.",
)
@click.option(
    "-H",
    "--hor-layer",
    required=True,
    help="Name of metal layer to place horizontal pins on.",
)
@click.option(
    "--hor-extension",
    default=0,
    type=float,
    help="Extension for vertical pins in microns.",
)
@click.option(
    "--ver-extension",
    default=0,
    type=float,
    help="Extension for horizontal pins in microns.",
)
@click.option(
    "--ver-width-mult", default=2, type=float, help="Multiplier for vertical pins."
)
@click.option(
    "--hor-width-mult", default=2, type=float, help="Multiplier for horizontal pins."
)
@click.option(
    "--verbose/--no-verbose",
    default=False,
    help="Enable verbose (DEBUG) logging output.",
)
@click_odb
def io_place(
    reader: OdbReaderLike,
    config: str,
    ver_layer: str,
    hor_layer: str,
    ver_width_mult: float,
    hor_width_mult: float,
    hor_length: float | None,
    ver_length: float | None,
    hor_extension: float,
    ver_extension: float,
    unmatched_error: str,
    verbose: bool,
) -> None:
    """
    Places the IOs in an input def with a config file using tile-based format.

    Config format (YAML):
    X0Y0:
      N: [pin1_regex, pin2_regex, ...]
      E: [pin3_regex, ...]
      S: [...]
      W: [...]
    X1Y0:
      N: [...]
      ...

    Pins are placed from low to high coordinates (bottom to top, left to right).
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config_file_name = Path(config)
    micron_in_units = reader.dbunits

    h_extension = int(micron_in_units * hor_extension)
    v_extension = int(micron_in_units * ver_extension)

    if h_extension < 0:
        h_extension = 0

    if v_extension < 0:
        v_extension = 0

    h_layer = reader.tech.findLayer(hor_layer)
    v_layer = reader.tech.findLayer(ver_layer)

    h_width = int(Decimal(hor_width_mult) * h_layer.getWidth())
    v_width = int(Decimal(ver_width_mult) * v_layer.getWidth())

    if hor_length is not None:
        h_length = int(micron_in_units * hor_length)
    else:
        h_length = max(
            int(
                math.ceil(
                    h_layer.getArea() * micron_in_units * micron_in_units / h_width
                )
            ),
            h_width,
        )

    if ver_length is not None:
        v_length = int(micron_in_units * ver_length)
    else:
        v_length = max(
            int(
                math.ceil(
                    v_layer.getArea() * micron_in_units * micron_in_units / v_width
                )
            ),
            v_width,
        )

    with config_file_name.open(encoding="utf8") as file:
        config_data = yaml.safe_load(file)

    info(f"Top-level design name: {reader.name}")

    bterms = [
        bterm
        for bterm in reader.block.getBTerms()
        if bterm.getSigType() not in ["POWER", "GROUND"]
    ]

    plan = PinPlacementPlan(config_data, bterms, unmatched_error)
    debug("Segment plan: %s", plan.segments_by_side)

    min_by_side = {
        Side.NORTH: (v_width + v_layer.getSpacing()) / reader.dbunits,
        Side.SOUTH: (v_width + v_layer.getSpacing()) / reader.dbunits,
        Side.EAST: (h_width + h_layer.getSpacing()) / reader.dbunits,
        Side.WEST: (h_width + h_layer.getSpacing()) / reader.dbunits,
    }
    plan.assign_unmatched_pins()
    plan.ensure_min_distances(min_by_side)

    # generate slots
    DIE_AREA = reader.block.getDieArea()
    BLOCK_LL_X = DIE_AREA.xMin()
    BLOCK_LL_Y = DIE_AREA.yMin()
    BLOCK_UR_X = DIE_AREA.xMax()
    BLOCK_UR_Y = DIE_AREA.yMax()

    # Physical dimensions for proportional track allocation
    die_width = BLOCK_UR_X - BLOCK_LL_X
    die_height = BLOCK_UR_Y - BLOCK_LL_Y

    origin_h: float
    count_h: int
    h_step: float
    origin_v: float
    count_v: int
    v_step: float

    origin_h, count_h, h_step = reader.block.findTrackGrid(h_layer).getGridPatternY(0)
    origin_v, count_v, v_step = reader.block.findTrackGrid(v_layer).getGridPatternX(0)

    # Allocate tracks for all segments on each side
    track_specs = {
        Side.NORTH: (count_v, v_step, origin_v, die_width),
        Side.SOUTH: (count_v, v_step, origin_v, die_width),
        Side.EAST: (count_h, h_step, origin_h, die_height),
        Side.WEST: (count_h, h_step, origin_h, die_height),
    }
    plan.allocate_tracks(track_specs)

    step_by_side = {
        Side.EAST: h_step,
        Side.WEST: h_step,
        Side.NORTH: v_step,
        Side.SOUTH: v_step,
    }

    pin_tracks: dict[Side, list[list[float]]] = {side: [] for side in Side}

    for side in Side:
        for segment_index, segment in enumerate(plan.segments(side)):
            min_distance_value = segment.min_distance
            if min_distance_value is None:
                raise AssertionError("min_distance must be defined before placement")
            min_distance = min_distance_value * micron_in_units
            max_distance = segment.max_distance
            if max_distance is not None:
                max_distance = max_distance * micron_in_units

            raw_tracks = plan.tracks_for_segment(side, segment_index)
            step = step_by_side[side]

            stride = max(1, math.ceil(min_distance / step))
            filtered = [raw_tracks[i] for i in range(0, len(raw_tracks), stride)]

            if max_distance is not None:
                max_stride = max(1, math.floor(max_distance / step))
                enforced = []
                last_index = None
                for idx, track in enumerate(raw_tracks):
                    if idx % stride == 0:
                        if last_index is None:
                            enforced.append(track)
                            last_index = idx
                        else:
                            if idx - last_index > max_stride:
                                interim = last_index + max_stride
                                while interim < idx:
                                    enforced.append(raw_tracks[interim])
                                    interim += max_stride
                            enforced.append(track)
                            last_index = idx
                filtered = enforced

            needed = segment.actual_pin_count
            if needed > len(filtered):
                err(
                    "Insufficient tracks: "
                    f"min_distance={segment.min_distance:.3f} µm "
                    f"side={side.value} seg={segment_index} pins={needed} "
                    f"got {len(filtered)} slots "
                    f"stride={stride} raw={len(raw_tracks)}"
                )
                err("Hint: reduce min_distance, enlarge die, or redistribute pins.")
                raise SystemExit(os.EX_DATAERR)

            pin_tracks[side].append(filtered)

    for segment in plan.all_segments():
        segment.apply_reverse()

    for side in Side:
        for segment_index, segment in enumerate(plan.segments(side)):
            debug(
                "Placing side=%s seg=%d pins=%d slots=%d",
                side.value,
                segment_index,
                segment.actual_pin_count,
                len(pin_tracks[side][segment_index]) if pin_tracks[side] else 0,
            )

            slots, resolved_pins = equally_spaced_sequence(
                side.value,
                segment.pin_entries,
                pin_tracks[side][segment_index],
            )
            segment.replace_pin_entries(resolved_pins)

            debug(
                "Slots assigned = %d (pins=%d)",
                len(slots),
                len(segment.pin_entries),
            )
            assert len(slots) == len(segment.pin_entries)

            for pin_index, bterm in enumerate(segment.pin_entries):
                slot = slots[pin_index]
                pin_name = bterm.getName()
                debug(f"{pin_name} -> {slot}")
                pins = bterm.getBPins()
                if len(pins) > 0:
                    warn(f"{pin_name} already has shapes. Modifying existing shape.")
                    assert len(pins) == 1
                    pin_bpin = pins[0]
                else:
                    pin_bpin = odb.dbBPin_create(bterm)

                pin_bpin.setPlacementStatus("PLACED")

                if side in {Side.NORTH, Side.SOUTH}:
                    rect = odb.Rect(0, 0, v_width, v_length + v_extension)
                    if side is Side.NORTH:
                        y = BLOCK_UR_Y - v_length
                    else:
                        y = BLOCK_LL_Y - v_extension
                    rect.moveTo(slot - v_width // 2, y)
                    odb.dbBox_create(pin_bpin, v_layer, *rect.ll(), *rect.ur())
                else:
                    rect = odb.Rect(0, 0, h_length + h_extension, h_width)
                    if side is Side.EAST:
                        x = BLOCK_UR_X - h_length
                    else:
                        x = BLOCK_LL_X - h_extension
                    rect.moveTo(x, slot - h_width // 2)
                    odb.dbBox_create(pin_bpin, h_layer, *rect.ll(), *rect.ur())


if __name__ == "__main__":
    io_place()
