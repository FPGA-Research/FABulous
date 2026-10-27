"""Generate IO pin order configuration files for FABulous tiles and fabrics."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

import yaml
from loguru import logger

from fabulous.custom_exception import StaleIOPinConfigError
from fabulous.fabric_definition.define import PinSortMode, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile

# The hash of the body as generated tells a user edit (body no longer matches)
# apart from a fabric change (fresh body no longer matches). It is stored as the
# first top-level key, which cannot clash with the `X<x>Y<y>` tile keys.
GENERATED_HASH_KEY = "fabulous_generated_sha256"


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
    tile: Tile,
    prefix: str = "",
    external_port_side: Side = Side.SOUTH,
    user_clk_side: Side = Side.SOUTH,
) -> dict[str, list[dict]]:
    """Serialize a single tile's ports for IO pin placement."""
    port_dict = {
        Side.NORTH.name: [],
        Side.EAST.name: [],
        Side.SOUTH.name: [],
        Side.WEST.name: [],
    }
    # UserCLK enters on user_clk_side and UserCLKo leaves on the opposite side.
    clk_pins = {
        user_clk_side.name: PinOrderConfig()([f"{prefix}UserCLK"]).to_dict(),
        user_clk_side.opposite.name: PinOrderConfig()([f"{prefix}UserCLKo"]).to_dict(),
    }

    for port in tile.getNorthSidePorts():
        if regex := port.get_port_regex(indexed=True, prefix=prefix):
            port_dict[Side.NORTH.name].append(
                tile.pinOrderConfig[Side.NORTH]([regex]).to_dict()
            )
    if pin := clk_pins.get(Side.NORTH.name):
        port_dict[Side.NORTH.name].append(pin)
    port_dict[Side.NORTH.name].append(
        PinOrderConfig()([rf"{prefix}FrameStrobe_O\[\d+\]"]).to_dict()
    )

    for port in tile.getEastSidePorts():
        if regex := port.get_port_regex(indexed=True, prefix=prefix):
            port_dict[Side.EAST.name].append(
                tile.pinOrderConfig[Side.EAST]([regex]).to_dict()
            )
    if pin := clk_pins.get(Side.EAST.name):
        port_dict[Side.EAST.name].append(pin)
    port_dict[Side.EAST.name].append(
        PinOrderConfig()([rf"{prefix}FrameData_O\[\d+\]"]).to_dict()
    )

    for port in tile.getSouthSidePorts():
        if regex := port.get_port_regex(indexed=True, prefix=prefix):
            port_dict[Side.SOUTH.name].append(
                tile.pinOrderConfig[Side.SOUTH]([regex]).to_dict()
            )
    if pin := clk_pins.get(Side.SOUTH.name):
        port_dict[Side.SOUTH.name].append(pin)
    port_dict[Side.SOUTH.name].append(
        PinOrderConfig()([rf"{prefix}FrameStrobe\[\d+\]"]).to_dict()
    )

    for port in tile.getWestSidePorts():
        if regex := port.get_port_regex(indexed=True, prefix=prefix):
            port_dict[Side.WEST.name].append(
                tile.pinOrderConfig[Side.WEST]([regex]).to_dict()
            )
    if pin := clk_pins.get(Side.WEST.name):
        port_dict[Side.WEST.name].append(pin)
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
    user_clk_side: Side = Side.SOUTH,
) -> dict[str, dict[str, list[dict]]]:
    """Serialize SuperTile ports, processing only perimeter sides."""
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
        tile = super_tile.tileMap[y_int][x_int]
        if tile is None:
            continue

        tile_prefix = f"Tile_{tile_key}_{prefix}"

        # Routing ports: only present for sides that actually have wires.
        perimeter_sides: set[Side] = set()
        for port_list in port_lists:
            if not port_list:
                continue
            side = port_list[0].side_of_tile
            perimeter_sides.add(side)
            for port in port_list:
                if regex := port.get_port_regex(indexed=True, prefix=tile_prefix):
                    config_payload[tile_key][side.name].append(
                        tile.pinOrderConfig[side]([regex]).to_dict()
                    )

        # Frame-chain signals are present on every perimeter side, even when no
        # routing wires cross that side (e.g. an IO tile without WEST wires still
        # carries FrameData on its WEST edge). Derive the full perimeter set from
        # the supertile layout instead of relying on the routing-port list.
        all_perimeter_sides: set[Side] = set()
        tm = super_tile.tileMap
        if y_int == 0 or tm[y_int - 1][x_int] is None:
            all_perimeter_sides.add(Side.NORTH)
        if x_int + 1 >= len(tm[y_int]) or tm[y_int][x_int + 1] is None:
            all_perimeter_sides.add(Side.EAST)
        if y_int + 1 >= len(tm) or tm[y_int + 1][x_int] is None:
            all_perimeter_sides.add(Side.SOUTH)
        if x_int == 0 or tm[y_int][x_int - 1] is None:
            all_perimeter_sides.add(Side.WEST)

        for side in all_perimeter_sides:
            if side == user_clk_side:
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([f"{tile_prefix}UserCLK"]).to_dict()
                )
            elif side == user_clk_side.opposite:
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([f"{tile_prefix}UserCLKo"]).to_dict()
                )
            if side == Side.NORTH:
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([rf"{tile_prefix}FrameStrobe_O\[\d+\]"]).to_dict()
                )
            elif side == Side.EAST:
                config_payload[tile_key][side.name].append(
                    PinOrderConfig()([rf"{tile_prefix}FrameData_O\[\d+\]"]).to_dict()
                )
            elif side == Side.SOUTH:
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
                        # Side is a StrEnum, so set order follows the hash seed.
                        external_side = next(
                            side for side in Side if side in perimeter_sides
                        )
                    else:
                        external_side = Side.SOUTH

                    config_payload[tile_key][external_side.name].append(
                        tile.pinOrderConfig[external_side](pin_regexes).to_dict()
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
        mx, my = super_tile.get_master_tile_coords()
        master_key = f"X{mx}Y{my}"
        master_tile = super_tile.tileMap[my][mx]
        if st_pin_regexes and master_tile is not None and master_key in config_payload:
            if external_port_sides and (mx, my) in external_port_sides:
                master_side = external_port_sides[(mx, my)]
            else:
                master_side = Side.SOUTH
            config_payload[master_key][master_side.name].append(
                master_tile.pinOrderConfig[master_side](st_pin_regexes).to_dict()
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

    When `fabric` is provided, external-port sides are resolved from each
    (sub)tile's placement within the fabric; otherwise `external_port_side`
    is used as the fallback for every concrete (sub)tile.

    The first line of the file is the `GENERATED_HASH_KEY` entry holding the
    hash of the generated body below it. An existing `outfile` is overwritten
    only when its body still matches that hash, or already matches the fresh
    body. A body the user edited is kept while the fresh body matches the
    recorded hash. A file without the key, such as a hand-written one or one
    from an older FABulous, keeps its body and gains the key with the fresh
    hash, so it counts as edited against the current fabric.

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

    Raises
    ------
    StaleIOPinConfigError
        If `outfile` holds user edits and the fabric has changed since it was
        generated.
    ValueError
        If `outfile` has no `GENERATED_HASH_KEY` and prepending it does not
        yield the same mapping plus that key, as with a leading `---` marker.
    """
    user_clk_side = fabric.userCLKSide if fabric is not None else Side.SOUTH
    if isinstance(tile_or_super_tile, SuperTile):
        sides: dict[tuple[int, int], Side] = {}
        if (fabric is not None) and (
            positions := fabric.find_tile_positions(tile_or_super_tile)
        ):
            if len(positions) == 1:
                base_x, base_y = positions[0]
            else:
                base_x = min(pos[0] for pos in positions)
                base_y = min(pos[1] for pos in positions)

            for st_y, row in enumerate(tile_or_super_tile.tileMap):
                for st_x, st_tile in enumerate(row):
                    if st_tile is None:
                        continue
                    if border_side := fabric.determine_border_side(
                        base_x + st_x, base_y + st_y
                    ):
                        sides[(st_x, st_y)] = border_side
        else:
            sides = {
                (x, y): external_port_side
                for y, row in enumerate(tile_or_super_tile.tileMap)
                for x, subtile in enumerate(row)
                if subtile is not None
            }

        payload = _serialize_supertile_ports(
            tile_or_super_tile, prefix, sides, user_clk_side
        )
    else:
        if fabric is not None and (
            positions := fabric.find_tile_positions(tile_or_super_tile)
        ):
            x, y = positions[0]
            side = fabric.determine_border_side(x, y) or external_port_side
        else:
            side = external_port_side

        payload = {
            "X0Y0": _serialize_tile_ports(
                tile_or_super_tile, prefix, side, user_clk_side
            ),
        }

    body = yaml.dump(payload)
    fresh_hash = hashlib.sha256(body.encode()).hexdigest()
    if outfile.exists():
        existing = outfile.read_text()
        existing_config = yaml.safe_load(existing)
        if not (
            isinstance(existing_config, dict) and GENERATED_HASH_KEY in existing_config
        ):
            stamped = yaml.dump({GENERATED_HASH_KEY: fresh_hash}) + existing
            unstampable = (
                f"Cannot add `{GENERATED_HASH_KEY}` to {outfile}: the file must "
                "be a single block mapping. Remove any `---` marker, or move the "
                "file aside to regenerate it."
            )
            try:
                stamped_config = yaml.safe_load(stamped)
            except yaml.YAMLError as e:
                raise ValueError(unstampable) from e
            if stamped_config != {
                GENERATED_HASH_KEY: fresh_hash,
                **(existing_config or {}),
            }:
                raise ValueError(unstampable)
            outfile.write_text(stamped)
            logger.info(
                f"Added `{GENERATED_HASH_KEY}` to {outfile}; its content is kept "
                "as a user edit of the current fabric"
            )
            return
        recorded_hash = existing_config[GENERATED_HASH_KEY]
        existing_body = existing.removeprefix(
            yaml.dump({GENERATED_HASH_KEY: recorded_hash})
        )
        existing_hash = hashlib.sha256(existing_body.encode()).hexdigest()
        if existing_hash not in (recorded_hash, fresh_hash):
            if fresh_hash != recorded_hash:
                raise StaleIOPinConfigError(
                    f"{outfile} has user edits but the fabric changed since it "
                    "was generated. Move it aside, rerun to regenerate it, then "
                    "reapply the edits to the new file."
                )
            logger.info(f"Keeping user-edited {outfile}")
            return

    outfile.write_text(yaml.dump({GENERATED_HASH_KEY: fresh_hash}) + body)
