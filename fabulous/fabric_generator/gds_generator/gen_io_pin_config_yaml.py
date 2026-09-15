"""Generate IO pin order configuration files for FABulous tiles and fabrics."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

import yaml

from fabulous.fabric_definition.define import PinSortMode, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.tile_interface import FRAME_CHAIN_PAIRS

# Fallback priority for placing a sub-tile's BEL external ports when no
# explicit fabric-border side is known for that cell (an interior composite
# placement). `Side` is a `StrEnum`, so plain `next(iter(a_set_of_sides))`
# is not deterministic across process runs: Python randomises string hashes
# per-process by default, and for these members that can change which side a
# `set`'s iteration yields first. Picking from a fixed priority tuple instead
# keeps the choice stable regardless of hash seed or insertion order.
_EXTERNAL_SIDE_FALLBACK_PRIORITY = (Side.SOUTH, Side.EAST, Side.WEST, Side.NORTH)


@dataclass
class PinOrderConfig:
    """Container describing pin ordering constraints for a segment."""

    min_distance: int | None = None
    max_distance: int | None = None
    pins: list[str | int] = field(default_factory=list)
    sort_mode: PinSortMode = PinSortMode.BUS_MAJOR
    reverse_result: bool = False

    def __call__(self, pins: list[str | int]) -> Self:
        """Bind a concrete pin list to this configuration instance."""
        self.pins = pins
        return self

    def to_dict(self) -> dict:
        """Return a serialisable dictionary representation."""
        pins = list(getattr(self, "pins", []) or [])
        return {
            "min_distance": self.min_distance,
            "max_distance": self.max_distance,
            "pins": pins,
            "sort_mode": str(self.sort_mode),
            "reverse_result": self.reverse_result,
        }


def _side_segments(
    tile: Tile,
    side: Side,
    side_ports: list[TilePort],
    fixed_regexes: list[str],
    prefix: str,
) -> list[dict]:
    """Serialise the routing, frame and clock segments of one border.

    Every port is its own segment followed by the frame and clock segments,
    which is the layout every existing tile was hardened with. A tile interface
    order is a transform `FABulousTileIOPlacement` applies on top of this.
    """
    port_regexes = [
        regex
        for port in side_ports
        if (regex := port.get_port_regex(indexed=True, prefix=prefix))
    ]
    segments = [(tile.pin_order_config[side], regex) for regex in port_regexes] + [
        (PinOrderConfig(), regex) for regex in fixed_regexes
    ]
    return [config([regex]).to_dict() for config, regex in segments]


def _frame_regexes(side: Side, prefix: str) -> list[str]:
    """Return the frame-chain and clock pin regexes that cross `side`."""
    regexes: list[str] = []
    for pair in FRAME_CHAIN_PAIRS:
        if (name := pair.on(side)) is None:
            continue
        regexes.append(f"{prefix}{name}" if pair.scalar else rf"{prefix}{name}\[\d+\]")
    return regexes


def _serialize_tile_ports(
    tile: Tile,
    prefix: str = "",
    external_port_side: Side = Side.SOUTH,
) -> dict[str, list[dict]]:
    """Serialize a single tile's ports for IO pin placement."""
    side_ports = {
        Side.NORTH: tile.ports_on(Side.NORTH),
        Side.EAST: tile.ports_on(Side.EAST),
        Side.SOUTH: tile.ports_on(Side.SOUTH),
        Side.WEST: tile.ports_on(Side.WEST),
    }
    port_dict = {
        side.name: _side_segments(
            tile, side, ports, _frame_regexes(side, prefix), prefix
        )
        for side, ports in side_ports.items()
    }
    # Place BEL external ports on the specified side
    for bel in tile.bels:
        pin_regexes = [
            f"{prefix}{name}" for name in bel.externalInput + bel.externalOutput
        ]
        if pin_regexes:
            port_dict[external_port_side.name].append(
                tile.pin_order_config[external_port_side](pin_regexes).to_dict()
            )

    return port_dict


def _serialize_composite_ports(
    super_tile: Tile,
    prefix: str = "",
    external_port_sides: dict[tuple[int, int], Side] | None = None,
) -> dict[str, dict[str, list[dict]]]:
    """Serialize composite tile ports, processing only perimeter sides.

    Every perimeter face of a sub-tile is laid out like the same face of a
    leaf tile, with the sub-tile prefix on every pin.
    """
    config_payload: dict[str, dict[str, list[dict]]] = {}
    ports_around = super_tile.get_ports_around_tile()

    for coord_key, port_lists in ports_around.items():
        if not port_lists:
            continue

        x, y = coord_key.split(",")
        tile_key = f"X{x}Y{y}"
        config_payload[tile_key] = {
            Side.NORTH.name: [],
            Side.EAST.name: [],
            Side.SOUTH.name: [],
            Side.WEST.name: [],
        }

        x_int, y_int = int(x), int(y)
        tile = super_tile.tile_map[y_int][x_int]
        if tile is None:
            continue

        tile_prefix = f"Tile_{tile_key}_{prefix}"

        # Routing ports: only present for sides that actually have wires.
        routing_ports: dict[Side, list[TilePort]] = {}
        for port_list in port_lists:
            if not port_list:
                continue
            routing_ports.setdefault(port_list[0].side_of_tile, []).extend(port_list)
        perimeter_sides: set[Side] = set(routing_ports)

        # Frame-chain signals are present on every perimeter side, even when no
        # routing wires cross that side (e.g. an IO tile without WEST wires still
        # carries FrameData on its WEST edge). Derive the full perimeter set from
        # the supertile layout instead of relying on the routing-port list.
        all_perimeter_sides: set[Side] = set()
        tm = super_tile.tile_map
        if y_int == 0 or tm[y_int - 1][x_int] is None:
            all_perimeter_sides.add(Side.NORTH)
        if x_int + 1 >= len(tm[y_int]) or tm[y_int][x_int + 1] is None:
            all_perimeter_sides.add(Side.EAST)
        if y_int + 1 >= len(tm) or tm[y_int + 1][x_int] is None:
            all_perimeter_sides.add(Side.SOUTH)
        if x_int == 0 or tm[y_int][x_int - 1] is None:
            all_perimeter_sides.add(Side.WEST)

        for side in perimeter_sides | all_perimeter_sides:
            frame_regexes = (
                _frame_regexes(side, tile_prefix) if side in all_perimeter_sides else []
            )
            config_payload[tile_key][side.name] = _side_segments(
                tile,
                side,
                routing_ports.get(side, []),
                frame_regexes,
                tile_prefix,
            )

        # Add BEL external ports
        if tile.bels:
            for bel in tile.bels:
                pin_regexes = [
                    f"{prefix}{name}" for name in bel.externalInput + bel.externalOutput
                ]
                if pin_regexes:
                    if external_port_sides and (int(x), int(y)) in external_port_sides:
                        external_side = external_port_sides[(int(x), int(y))]
                    elif perimeter_sides:
                        external_side = next(
                            side
                            for side in _EXTERNAL_SIDE_FALLBACK_PRIORITY
                            if side in perimeter_sides
                        )
                    else:
                        external_side = Side.SOUTH

                    config_payload[tile_key][external_side.name].append(
                        tile.pin_order_config[external_side](pin_regexes).to_dict()
                    )

    # Supertile-level BEL external ports live on the wrapper itself (named e.g.
    # `SUPER_out_ext`, without a `Tile_X..` prefix) and are anchored at the
    # master tile. Place them on the master tile's external side.
    # NOTE: not verified end-to-end against the GDS flow.
    if super_tile.bels:
        st_pin_regexes = [
            name
            for bel in super_tile.bels
            for name in bel.externalInput + bel.externalOutput
        ]
        mx, my = super_tile.get_master_offset()
        master_key = f"X{mx}Y{my}"
        master_tile = super_tile.get_master_tile()
        if st_pin_regexes and master_key in config_payload:
            if external_port_sides and (mx, my) in external_port_sides:
                master_side = external_port_sides[(mx, my)]
            else:
                master_side = Side.SOUTH
            config_payload[master_key][master_side.name].append(
                master_tile.pin_order_config[master_side](st_pin_regexes).to_dict()
            )

    return config_payload


def generate_IO_pin_order_config(
    tile: Tile,
    outfile: Path,
    *,
    fabric: Fabric | None = None,
    prefix: str = "",
    external_port_side: Side = Side.SOUTH,
) -> None:
    """Generate IO pin order configuration YAML for a tile or super tile.

    When `fabric` is provided, external-port sides are resolved from each
    (sub)tile's placement within the fabric; otherwise `external_port_side`
    is used as the fallback for every concrete (sub)tile.

    Parameters
    ----------
    tile : Tile
        The leaf or composite tile to generate configuration for.
    outfile : Path
        Output YAML file path.
    fabric : Fabric | None
        Optional fabric used to derive border-aware external-port sides.
    prefix : str
        Prefix to add to port names.
    external_port_side : Side
        Fallback side used for BEL external ports when no fabric placement
        context applies.
    """
    if tile.is_composite:
        sides: dict[tuple[int, int], Side] = {}
        if (fabric is not None) and (positions := fabric.find_tile_positions(tile)):
            if len(positions) == 1:
                base_x, base_y = positions[0]
            else:
                base_x = min(pos[0] for pos in positions)
                base_y = min(pos[1] for pos in positions)

            for st_y, row in enumerate(tile.tile_map):
                for st_x, st_tile in enumerate(row):
                    if st_tile is None:
                        continue
                    # tile_map is top-first (st_y=0 is north); the fabric grid is
                    # bottom-first, so map the row index to its fabric offset
                    # before querying the border side.
                    fabric_y = base_y + tile.fabric_dy(st_y)
                    if border_side := fabric.determine_border_side(
                        base_x + st_x, fabric_y
                    ):
                        sides[(st_x, st_y)] = border_side
        else:
            sides = {
                (x, y): external_port_side
                for y, row in enumerate(tile.tile_map)
                for x, subtile in enumerate(row)
                if subtile is not None
            }

        payload = _serialize_composite_ports(tile, prefix, sides)
    else:
        if fabric is not None and (positions := fabric.find_tile_positions(tile)):
            x, y = positions[0]
            side = fabric.determine_border_side(x, y) or external_port_side
        else:
            side = external_port_side

        payload = {
            "X0Y0": _serialize_tile_ports(tile, prefix, side),
        }

    with outfile.open("w") as file_descriptor:
        yaml.dump(payload, file_descriptor)
