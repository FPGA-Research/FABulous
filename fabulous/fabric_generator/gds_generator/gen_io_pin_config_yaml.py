"""Generate IO pin order configuration files for FABulous tiles and fabrics."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

import yaml

from fabulous.fabric_definition.define import PinSortMode, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile


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


def _serialize_tile_ports(
    tile: Tile, prefix: str = "", external_port_side: Side = Side.SOUTH
) -> dict[str, list[dict]]:
    """Serialize a single tile's ports for IO pin placement."""
    port_dict = {
        Side.NORTH.name: [],
        Side.EAST.name: [],
        Side.SOUTH.name: [],
        Side.WEST.name: [],
    }

    for port in tile.getNorthSidePorts():
        if regex := port.getPortRegex(indexed=True, prefix=prefix):
            port_dict[Side.NORTH.name].append(
                tile.pinOrderConfig[Side.NORTH]([regex]).to_dict()
            )
    port_dict[Side.NORTH.name].append(PinOrderConfig()([f"{prefix}UserCLKo"]).to_dict())
    port_dict[Side.NORTH.name].append(
        PinOrderConfig()([rf"{prefix}FrameStrobe_O\[\d+\]"]).to_dict()
    )

    for port in tile.getEastSidePorts():
        if regex := port.getPortRegex(indexed=True, prefix=prefix):
            port_dict[Side.EAST.name].append(
                tile.pinOrderConfig[Side.EAST]([regex]).to_dict()
            )
    port_dict[Side.EAST.name].append(
        PinOrderConfig()([rf"{prefix}FrameData_O\[\d+\]"]).to_dict()
    )

    for port in tile.getSouthSidePorts():
        if regex := port.getPortRegex(indexed=True, prefix=prefix):
            port_dict[Side.SOUTH.name].append(
                tile.pinOrderConfig[Side.SOUTH]([regex]).to_dict()
            )
    port_dict[Side.SOUTH.name].append(PinOrderConfig()([f"{prefix}UserCLK"]).to_dict())
    port_dict[Side.SOUTH.name].append(
        PinOrderConfig()([rf"{prefix}FrameStrobe\[\d+\]"]).to_dict()
    )

    for port in tile.getWestSidePorts():
        if regex := port.getPortRegex(indexed=True, prefix=prefix):
            port_dict[Side.WEST.name].append(
                tile.pinOrderConfig[Side.WEST]([regex]).to_dict()
            )
    port_dict[Side.WEST.name].append(
        PinOrderConfig()([rf"{prefix}FrameData\[\d+\]"]).to_dict()
    )

    # Place BEL external ports on the specified side
    for bel in tile.bels:
        pin_regexes = [
            f"{prefix}{name}" for name in bel.externalInput + bel.externalOutput
        ]
        if pin_regexes:
            port_dict[external_port_side.name].append(
                tile.pinOrderConfig[external_port_side](pin_regexes).to_dict()
            )

    return port_dict


def _serialize_supertile_ports(
    super_tile: SuperTile,
    prefix: str = "",
    external_port_sides: dict[tuple[int, int], Side] | None = None,
) -> dict[str, dict[str, list[dict]]]:
    """Serialize SuperTile ports, processing only perimeter sides."""
    config_payload: dict[str, dict[str, list[dict]]] = {}
    ports_around = super_tile.getPortsAroundTile()

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

        tile = super_tile.tileMap[int(y)][int(x)]
        if tile is None:
            continue

        tile_prefix = f"Tile_{tile_key}_{prefix}"
        perimeter_sides = set()
        for port_list in port_lists:
            if not port_list:
                continue

            side = port_list[0].sideOfTile
            perimeter_sides.add(side)

            for port in port_list:
                if regex := port.getPortRegex(indexed=True, prefix=tile_prefix):
                    config_payload[tile_key][side.name].append(
                        tile.pinOrderConfig[side]([regex]).to_dict()
                    )

            # Add frame signals based on side
            if side == Side.NORTH:
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([f"{tile_prefix}UserCLKo"]).to_dict()
                )
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([rf"{tile_prefix}FrameStrobe_O\[\d+\]"]).to_dict()
                )
            elif side == Side.EAST:
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([rf"{tile_prefix}FrameData_O\[\d+\]"]).to_dict()
                )
            elif side == Side.SOUTH:
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([f"{tile_prefix}UserCLK"]).to_dict()
                )
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([rf"{tile_prefix}FrameStrobe\[\d+\]"]).to_dict()
                )
            elif side == Side.WEST:
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([rf"{tile_prefix}FrameData\[\d+\]"]).to_dict()
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
                        external_side = next(iter(perimeter_sides))
                    else:
                        external_side = Side.SOUTH

                    config_payload[tile_key][external_side.name].append(
                        tile.pinOrderConfig[external_side](pin_regexes).to_dict()
                    )

    return config_payload


def generate_IO_pin_order_config(
    tile_or_super_tile: Tile | SuperTile,
    outfile: Path,
    *,
    fabric: Fabric | None = None,
    prefix: str = "",
    external_port_side: Side = Side.SOUTH,
) -> None:
    """Generate IO pin order configuration YAML for a tile or super tile.

    When ``fabric`` is provided, external-port sides are resolved from each
    (sub)tile's placement within the fabric; otherwise ``external_port_side``
    is used as the fallback for every concrete (sub)tile.

    Parameters
    ----------
    tile_or_super_tile : Tile | SuperTile
        The tile or super tile to generate configuration for.
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
    if isinstance(tile_or_super_tile, SuperTile):
        sides = _resolve_supertile_external_port_sides(
            tile_or_super_tile, fabric, external_port_side
        )
        payload = _serialize_supertile_ports(tile_or_super_tile, prefix, sides)
    else:
        side = _resolve_tile_external_port_side(
            tile_or_super_tile, fabric, external_port_side
        )
        payload = {
            "X0Y0": _serialize_tile_ports(tile_or_super_tile, prefix, side),
        }

    with outfile.open("w") as file_descriptor:
        yaml.dump(payload, file_descriptor)


def _resolve_tile_external_port_side(
    tile: Tile,
    fabric: Fabric | None,
    default_side: Side,
) -> Side:
    """Resolve a tile's external side from fabric placement when possible."""
    if fabric is None:
        return default_side
    positions = fabric.find_tile_positions(tile)
    if not positions:
        return default_side
    x, y = positions[0]
    return fabric.determine_border_side(x, y) or default_side


def _resolve_supertile_external_port_sides(
    super_tile: SuperTile,
    fabric: Fabric | None,
    default_side: Side,
) -> dict[tuple[int, int], Side]:
    """Resolve SuperTile external sides from fabric placement when possible.

    Without a fabric, every concrete subtile maps to ``default_side``. With a
    fabric, only subtiles that land on a fabric border get an entry; interior
    subtiles are omitted so the serializer's perimeter-side heuristic applies.
    """
    if fabric is None:
        return {
            (x, y): default_side
            for y, row in enumerate(super_tile.tileMap)
            for x, subtile in enumerate(row)
            if subtile is not None
        }

    sides: dict[tuple[int, int], Side] = {}
    positions = fabric.find_tile_positions(super_tile)
    if not positions:
        return sides

    if len(positions) == 1:
        base_x, base_y = positions[0]
    else:
        base_x = min(pos[0] for pos in positions)
        base_y = min(pos[1] for pos in positions)

    for st_y, row in enumerate(super_tile.tileMap):
        for st_x, st_tile in enumerate(row):
            if st_tile is None:
                continue
            if border_side := fabric.determine_border_side(
                base_x + st_x, base_y + st_y
            ):
                sides[(st_x, st_y)] = border_side

    return sides
