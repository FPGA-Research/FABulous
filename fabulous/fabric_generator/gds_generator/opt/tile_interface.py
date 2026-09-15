"""Order a tile's border pairs from its placement, and from the tiles it abuts.

An interface order is written as an ordinary pin YAML with one segment per side
naming its pins exactly, the form `FABulousTileIOPlacement` consumes, so the
same file describes a proposal, the pin YAML a tile is hardened from and an
order imported from elsewhere. The pair invariant is not a property of that
file, so it is checked whenever an order is read against a tile's pairs.

An order belongs to a whole row or column rather than to one tile, since a
`PinPair` is one wire crossing the tile and ordering a border orders its
opposite. A tile next to an already ordered one therefore has that axis fixed,
which `abutments` and `translate_order` work out from the fabric grid and the
wire model rather than from pin names.

A routing pair's target coordinate is the median of the leaf cells on the
logical nets of its two pins, which is the L1-optimal position for the trunk of
that net and reduces to the nearest primitive when the net has one sink. A frame
pair's target is its uniform spread position, because frame lines are pure
feed-throughs whose latches the configuration mapping moves onto them, and
deriving their target from the current placement would put every frame line at
the tile centre.
"""

import re
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import IO, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.tile_interface import (
    FRAME_CHAIN_PAIRS,
    SIDE_INPUT_CONNECTIONS,
    Axis,
    BusKind,
    BusPair,
    PinPair,
)
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    PinOrderConfig,
    generate_IO_pin_order_config,
)
from fabulous.fabric_generator.gds_generator.opt.placement import (
    INDEXED_PIN,
    Placement,
)

SINGLE_TILE_KEY = "X0Y0"

InterfaceOrder = dict[Side, list[str]]
"""The ordered pin names of each border."""


def write_bus_pairs(path: Path, pairs: Iterable[BusPair]) -> None:
    """Write bus pairs as `{axis, first, second, kind, scalar}` entries."""
    payload = [
        {
            "axis": pair.axis.value,
            "first": pair.first,
            "second": pair.second,
            "kind": pair.kind.value,
            "scalar": pair.scalar,
        }
        for pair in pairs
    ]
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def read_bus_pairs(path: Path) -> list[BusPair]:
    """Read bus pairs written by `write_bus_pairs`.

    Parameters
    ----------
    path : Path
        The YAML file.

    Returns
    -------
    list[BusPair]
        The pairs in file order.

    Raises
    ------
    GDSFlowError
        If an entry lacks one of `axis`, `first` or `second`.
    """
    pairs = []
    for entry in yaml.safe_load(path.read_text()):
        try:
            pairs.append(
                BusPair(
                    Axis(entry["axis"]),
                    entry["first"],
                    entry["second"],
                    BusKind(entry["kind"]),
                    bool(entry["scalar"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GDSFlowError(f"{path}: malformed bus pair {entry!r}") from exc
    return pairs


def expand_bus_pairs(
    pairs: Iterable[BusPair], pin_names: Iterable[str]
) -> list[PinPair]:
    """Turn bus pairs into pin pairs using the pins a placed tile has.

    A bus present as `bus[k]` pins pairs bit by bit; a bus present as a bare
    pin pairs as one. Bits present on one border only are an error, since the
    fabric could not abut them.

    Parameters
    ----------
    pairs : Iterable[BusPair]
        Bus pairs of the tile.
    pin_names : Iterable[str]
        Every border pin of the placed tile.

    Returns
    -------
    list[PinPair]
        Pin pairs in bus order, bits ascending.

    Raises
    ------
    GDSFlowError
        If a bus has a bit on one border without its partner on the other.
    """
    bits: dict[str, set[int | None]] = {}
    for name in pin_names:
        if match := INDEXED_PIN.match(name):
            bits.setdefault(match["bus"], set()).add(int(match["index"]))
        else:
            bits.setdefault(name, set()).add(None)

    expanded: list[PinPair] = []
    for pair in pairs:
        first_bits = bits.get(pair.first, set())
        second_bits = bits.get(pair.second, set())
        if first_bits != second_bits:
            raise GDSFlowError(
                f"Bus pair {pair.first}/{pair.second} has bits "
                f"{sorted(first_bits, key=str)} on one border and "
                f"{sorted(second_bits, key=str)} on the other"
            )
        for bit in sorted(first_bits, key=lambda b: -1 if b is None else b):
            suffix = "" if bit is None else f"[{bit}]"
            expanded.append(
                PinPair(pair.axis, pair.first + suffix, pair.second + suffix, pair.kind)
            )
    return expanded


def pins_by_side(ordered: Mapping[Axis, Iterable[PinPair]]) -> InterfaceOrder:
    """Project ordered pairs onto the four borders.

    Parameters
    ----------
    ordered : Mapping[Axis, Iterable[PinPair]]
        The pairs of each axis in rank order.

    Returns
    -------
    InterfaceOrder
        Pin names per border, the first member of each pair on the axis's
        first border and the second member on its second border.
    """
    order: InterfaceOrder = {side: [] for side in Axis.VERTICAL.sides}
    order.update({side: [] for side in Axis.HORIZONTAL.sides})
    for axis, pairs in ordered.items():
        first_side, second_side = axis.sides
        for pair in pairs:
            order[first_side].append(pair.first)
            order[second_side].append(pair.second)
    return order


def write_interface_order(order: InterfaceOrder, path: Path) -> None:
    """Write an order as a single-tile pin YAML, one exact-name segment per side.

    The names are regex-escaped because the placer reads segment entries as
    patterns, so the file is valid input to `FABulousTileIOPlacement` on its
    own as well as through `FABULOUS_TILE_INTERFACE_ORDER`.
    """
    sides = {
        side.name: [PinOrderConfig(pins=[re.escape(name) for name in names]).to_dict()]
        for side, names in order.items()
        if names
    }
    path.write_text(yaml.safe_dump({SINGLE_TILE_KEY: sides}, sort_keys=False))


def read_interface_order(path: Path) -> InterfaceOrder:
    """Read an order from a single-tile pin YAML naming its pins exactly.

    Parameters
    ----------
    path : Path
        A pin YAML with the one tile key `X0Y0`.

    Returns
    -------
    InterfaceOrder
        Pin names per border, every segment of a side concatenated in order.

    Raises
    ------
    GDSFlowError
        If the file holds more than the one tile, or if a segment entry is a
        pattern rather than an exact escaped pin name, since a pattern has no
        rank to keep.
    """
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict) or set(payload) != {SINGLE_TILE_KEY}:
        raise GDSFlowError(
            f"{path}: an interface order is a pin YAML with the single tile key "
            f"{SINGLE_TILE_KEY!r}, found {sorted(payload) if payload else payload!r}"
        )
    order: InterfaceOrder = {}
    for side_name, segments in (payload[SINGLE_TILE_KEY] or {}).items():
        names: list[str] = []
        for segment in segments or []:
            for pattern in segment["pins"]:
                name = str(pattern).replace("\\", "")
                if re.escape(name) != pattern:
                    raise GDSFlowError(
                        f"{path}: {pattern!r} on {side_name} is a pattern, not an "
                        "exact pin name; an interface order names every pin"
                    )
                names.append(name)
        order[Side[side_name]] = names
    return order


def apply_interface_order(
    payload: dict[str, dict[str, list[dict]]], order: InterfaceOrder
) -> dict[str, dict[str, list[dict]]]:
    """Lead each border of every tile in a pin YAML with the ordered pins.

    Each listed pin takes the first pattern on its border that matches it, and
    that pattern leaves the segment it came from, so an already ordered payload
    is valid input: its old leading segment loses the pins listed again and
    keeps the rest. Segments emptied this way disappear, the others keep their
    place after the new leading segment, which carries the config of the
    border's first segment. Exact names survive in order because the placer
    matches a segment's patterns in list order and sorts only within one
    pattern's matches. A sub-tile of a super tile prefixes its pins with
    `Tile_<key>_`, so a listed name is tried bare and with that prefix. A
    pattern leaves its segment whole, so an order that lists only some bits
    of a bus leaves the other bits in no segment; the placer then stops on
    them as design pins missing from its configuration. Orders this module
    writes list every bit, since `expand_bus_pairs` pairs buses bit by bit.

    Parameters
    ----------
    payload : dict[str, dict[str, list[dict]]]
        Segment dicts per `Side.name` per tile key, as
        `generate_IO_pin_order_config` writes them.
    order : InterfaceOrder
        The order to apply.

    Returns
    -------
    dict[str, dict[str, list[dict]]]
        The reordered payload.
    """
    result: dict[str, dict[str, list[dict]]] = {}
    for tile_key, sides in payload.items():
        result[tile_key] = {}
        for side_name, segments in sides.items():
            patterns = [pattern for segment in segments for pattern in segment["pins"]]
            listed: list[str] = []
            matched: set[str] = set()
            for name in order.get(Side[side_name], []):
                for full in (name, f"Tile_{tile_key}_{name}"):
                    if match := next(
                        (p for p in patterns if re.fullmatch(p, full)), None
                    ):
                        listed.append(re.escape(full))
                        matched.add(match)
                        break
            ordered: list[dict] = []
            if listed:
                ordered.append({**segments[0], "pins": listed})
            for segment in segments:
                kept = [p for p in segment["pins"] if p not in matched]
                if kept:
                    ordered.append({**segment, "pins": kept})
            result[tile_key][side_name] = ordered
    return result


def write_ordered_pin_yaml(
    tile_type: Tile,
    outfile: Path,
    order: InterfaceOrder | None,
    *,
    fabric: Fabric | None = None,
) -> None:
    """Write a tile's pin YAML with `order` leading each border.

    Without an order the pin YAML is the generated one, so a tile nothing has
    ordered keeps the default layout.

    Parameters
    ----------
    tile_type : Tile
        The tile the pins belong to.
    outfile : Path
        The pin YAML to write.
    order : InterfaceOrder | None
        The ranks to lead each border with, in the tile's own pin names.
    fabric : Fabric | None
        The fabric, which resolves the sides of external ports.
    """
    generate_IO_pin_order_config(tile_type, outfile, fabric=fabric)
    if order is None:
        return
    payload = apply_interface_order(yaml.safe_load(outfile.read_text()), order)
    outfile.write_text(yaml.safe_dump(payload))


def _frame_target(pair: PinPair, placement: Placement) -> float | None:
    """Return the uniform spread coordinate of a frame pair, or None for others."""
    if pair.kind not in (BusKind.FRAME_STROBE, BusKind.FRAME_DATA):
        return None
    match = INDEXED_PIN.match(pair.second)
    if match is None:
        raise GDSFlowError(f"Frame pin {pair.second} is not indexed as bus[k]")
    count = sum(1 for p in placement.pins if p.startswith(f"{match['bus']}["))
    fraction = (int(match["index"]) + 0.5) / count
    if pair.kind is BusKind.FRAME_STROBE:
        return placement.die[0] + fraction * placement.width
    return placement.die[1] + fraction * placement.height


def _along(axis: Axis, x: float, y: float) -> float:
    """Return the coordinate that runs along the borders of `axis`."""
    return x if axis is Axis.VERTICAL else y


def pair_target(placement: Placement, pair: PinPair) -> float:
    """Return the coordinate along the border a pair should sit at.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    pair : PinPair
        The pair, both of whose pins must exist on the tile.

    Returns
    -------
    float
        The x coordinate for a vertical-axis pair, the y coordinate for a
        horizontal-axis pair, in microns. A pair whose nets reach no leaf
        cell keeps the mean coordinate of its two pins.

    Raises
    ------
    GDSFlowError
        If either pin is not on the placed tile.
    """
    if (target := _frame_target(pair, placement)) is not None:
        return target
    coordinates: list[float] = []
    for name in (pair.first, pair.second):
        if name not in placement.pins:
            raise GDSFlowError(f"Pin {name} of pair {pair} is not on the placed tile")
        coordinates.extend(
            _along(pair.axis, leaf.x, leaf.y)
            for leaf in placement.leaves(placement.net_of_port(name).name)
        )
    if coordinates:
        return statistics.median(coordinates)
    return statistics.mean(
        _along(pair.axis, placement.pins[name].x, placement.pins[name].y)
        for name in (pair.first, pair.second)
    )


def fixed_ranks(pairs: Iterable[PinPair], fixed: InterfaceOrder) -> dict[PinPair, int]:
    """Return the rank each pair holds in a fixed order, checking the pair invariant.

    Parameters
    ----------
    pairs : Iterable[PinPair]
        The pin pairs of the tile.
    fixed : InterfaceOrder
        An order the tile must keep, normally the project order.

    Returns
    -------
    dict[PinPair, int]
        The rank of every pair both of whose pins the order lists.

    Raises
    ------
    GDSFlowError
        If an order lists one pin of a pair without the other, or lists the two
        at different ranks, since either way the two borders would not abut.
    """
    ranks: dict[PinPair, int] = {}
    for pair in pairs:
        first_side, second_side = pair.axis.sides
        first = fixed.get(first_side, [])
        second = fixed.get(second_side, [])
        in_first = pair.first in first
        in_second = pair.second in second
        if in_first != in_second:
            raise GDSFlowError(
                f"The fixed order lists {pair.first if in_first else pair.second} "
                f"without its partner {pair.second if in_first else pair.first}"
            )
        if in_first:
            rank_first = first.index(pair.first)
            rank_second = second.index(pair.second)
            if rank_first != rank_second:
                raise GDSFlowError(
                    f"The fixed order ranks {pair.first} at {rank_first} on "
                    f"{first_side.name} but {pair.second} at {rank_second} on "
                    f"{second_side.name}; the two borders would not abut"
                )
            ranks[pair] = rank_first
    return ranks


_SIDE_OF_OFFSET = {
    (0, 1): Side.NORTH,
    (0, -1): Side.SOUTH,
    (1, 0): Side.EAST,
    (-1, 0): Side.WEST,
}
"""The border a tile turns towards the grid cell at each offset."""


@dataclass(frozen=True)
class Abutment:
    """A border a tile shares with a reference tile, and the buses crossing it.

    `bus_of_reference` is keyed by the reference's bus because an order is read
    in the reference's names and has to come out in the tile's.
    """

    side: Side
    bus_of_reference: dict[str, str]


def _bus_correspondence(
    tile: Tile, reference: Tile, offset: tuple[int, int]
) -> dict[str, str]:
    """Map the reference's buses on a shared border onto the tile's own.

    Routing buses meet in declaration order along each direction that crosses
    the border, which is what `SIDE_INPUT_CONNECTIONS` indexes. The chains meet
    by their pair, since every tile names those alike. A wire terminated with
    `NULL` on one end contributes no port on that end, so it drops out of both
    lists together and the order of the rest still lines up.

    Parameters
    ----------
    tile : Tile
        The tile whose names the correspondence ends in.
    reference : Tile
        The tile at `offset`, whose names it starts from.
    offset : tuple[int, int]
        The grid step from the tile to the reference.

    Returns
    -------
    dict[str, str]
        The tile bus each reference bus meets.

    Raises
    ------
    GDSFlowError
        If the two carry a different number of wires along a direction that
        crosses the border, or two wires of different width, since a fabric
        could not then abut them.
    """
    correspondence: dict[str, str] = {}
    for direction, dx, dy in SIDE_INPUT_CONNECTIONS:
        if (dx, dy) == offset:
            near = tile.ports_along(direction, IO.INPUT)
            far = reference.ports_along(direction, IO.OUTPUT)
        elif (dx, dy) == (-offset[0], -offset[1]):
            near = tile.ports_along(direction, IO.OUTPUT)
            far = reference.ports_along(direction, IO.INPUT)
        else:
            continue
        if len(near) != len(far):
            raise GDSFlowError(
                f"{tile.name} carries {len(near)} {direction.value} wires across "
                f"the border where {reference.name} carries {len(far)}; the two "
                "do not abut"
            )
        for own, other in zip(near, far, strict=True):
            if own.width != other.width:
                raise GDSFlowError(
                    f"{tile.name}.{own.name} is {own.width} wires wide and "
                    f"{reference.name}.{other.name} is {other.width}; the two "
                    "do not abut"
                )
            correspondence[other.name] = own.name

    side = _SIDE_OF_OFFSET[offset]
    for pair in FRAME_CHAIN_PAIRS:
        first_side, second_side = pair.axis.sides
        if side is first_side:
            correspondence[pair.second] = pair.first
        elif side is second_side:
            correspondence[pair.first] = pair.second
    return correspondence


def abutments(fabric: Fabric, tile: Tile, reference: Tile) -> list[Abutment]:
    """Return the borders on which the tile meets the reference in the fabric.

    Parameters
    ----------
    fabric : Fabric
        The fabric whose grid places the two.
    tile : Tile
        The tile being ordered.
    reference : Tile
        The tile whose order it has to follow.

    Returns
    -------
    list[Abutment]
        One entry per shared border, north, south, east then west. Empty when
        the two never touch, which is what a caller searching for references
        asks about and what a caller given one has to reject.

    Raises
    ------
    GDSFlowError
        If either tile is absent from the grid.
    """
    here = fabric.find_tile_positions(tile)
    there = fabric.find_tile_positions(reference)
    if not here or not there:
        raise GDSFlowError(
            f"{tile.name if not here else reference.name} is not placed anywhere "
            "in the fabric grid"
        )
    cells = set(there)
    return [
        Abutment(side, _bus_correspondence(tile, reference, offset))
        for offset, side in _SIDE_OF_OFFSET.items()
        if any((x + offset[0], y + offset[1]) in cells for x, y in here)
    ]


def translate_order(
    tile: Tile, abutment: Abutment, reference_order: InterfaceOrder
) -> InterfaceOrder:
    """Rewrite a reference tile's order into the pins of the tile abutting it.

    The opposite border comes back with the shared one, because the two pins of
    a pair are one wire and holding either at a rank holds the other. A wire
    terminated inside the tile has no pin on the opposite border, so a border
    carrying one of those is translated on its own and the opposite border of
    that axis is left free rather than ranked out of step.

    Parameters
    ----------
    tile : Tile
        The tile being ordered.
    abutment : Abutment
        The border it shares with the reference.
    reference_order : InterfaceOrder
        The reference's order, in the reference's own pin names.

    Returns
    -------
    InterfaceOrder
        The tile's pins in rank order, on the shared border and, where every
        wire of it is paired, on the border opposite.

    Raises
    ------
    GDSFlowError
        If the reference ranks nothing on the shared border, or ranks a pin
        that does not cross it, since neither leaves an order to follow.
    """
    facing = abutment.side.opposite
    ranked = reference_order.get(facing, [])
    if not ranked:
        raise GDSFlowError(
            f"The reference ranks no pin on its {facing.name} border, the one it "
            f"shares with {tile.name}; order the reference first"
        )
    pair_of_bus = {
        bus: pair for pair in tile.pairs for bus in (pair.first, pair.second)
    }
    near: list[str] = []
    far: list[str] = []
    for name in ranked:
        match = INDEXED_PIN.match(name)
        bus = match["bus"] if match else name
        suffix = f"[{match['index']}]" if match else ""
        if (own := abutment.bus_of_reference.get(bus)) is None:
            raise GDSFlowError(
                f"The reference's {name} does not cross its {facing.name} border, "
                f"so it ranks no pin of {tile.name}"
            )
        near.append(own + suffix)
        if (pair := pair_of_bus.get(own)) is not None:
            partner = pair.second if pair.first == own else pair.first
            far.append(partner + suffix)
    if len(far) != len(near):
        return {abutment.side: near}
    return {abutment.side: near, abutment.side.opposite: far}


def merge_orders(orders: Iterable[InterfaceOrder]) -> InterfaceOrder:
    """Combine the orders several references fix, one border at a time.

    Parameters
    ----------
    orders : Iterable[InterfaceOrder]
        Orders already in the pin names of the tile being ordered.

    Returns
    -------
    InterfaceOrder
        Every border any of them ranks.

    Raises
    ------
    GDSFlowError
        If two rank one border differently. A border belongs to a whole row or
        column of the fabric, so two references disagreeing on it means the two
        cannot both be abutted and the sweep order has to be settled by hand.
    """
    merged: InterfaceOrder = {}
    for order in orders:
        for side, names in order.items():
            if merged.setdefault(side, names) != names:
                raise GDSFlowError(
                    f"Two references rank the {side.name} border differently; "
                    "harden them against one another before using both"
                )
    return merged


def read_pin_yaml_order(path: Path) -> InterfaceOrder:
    """Read the ranks a pin YAML fixes, the exact names leading each border.

    `apply_interface_order` writes the ordered pins as one leading segment and
    leaves what it did not order, the BEL external pins among them, in the
    segments behind it. Those hold no rank, since the placer sorts a pattern's
    own matches, so a border is read up to its first pattern.

    Parameters
    ----------
    path : Path
        A pin YAML, normally a tile's own `<tile>_io_pin_order.yaml`.

    Returns
    -------
    InterfaceOrder
        The exact pin names leading each border, in file order.

    Raises
    ------
    GDSFlowError
        If the file holds more than the one tile, since a composite's borders
        are not reordered.
    """
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict) or set(payload) != {SINGLE_TILE_KEY}:
        raise GDSFlowError(
            f"{path}: an order is read from a pin YAML with the single tile key "
            f"{SINGLE_TILE_KEY!r}, found {sorted(payload) if payload else payload!r}"
        )
    order: InterfaceOrder = {}
    for side_name, segments in (payload[SINGLE_TILE_KEY] or {}).items():
        names: list[str] = []
        for pattern in (p for segment in segments or [] for p in segment["pins"]):
            name = str(pattern).replace("\\", "")
            if re.escape(name) != pattern:
                break
            names.append(name)
        order[Side[side_name]] = names
    return order


def tile_pin_yaml(tile_root: Path, tile_name: str) -> Path:
    """Return where a project keeps the pin YAML a tile is hardened from."""
    return tile_root / tile_name / f"{tile_name}_io_pin_order.yaml"


def ordered_neighbours(fabric: Fabric, tile: Tile, tile_root: Path) -> list[Tile]:
    """Return the tiles abutting `tile` whose pin YAML ranks their shared border.

    A neighbour that has never been ordered ranks nothing and is left out, so
    discovery reports what is actually settled rather than everything adjacent.

    Parameters
    ----------
    fabric : Fabric
        The fabric whose grid places the tiles.
    tile : Tile
        The tile being ordered.
    tile_root : Path
        The project's `Tile` directory.

    Returns
    -------
    list[Tile]
        The neighbours, in the fabric's own tile order.
    """
    found: list[Tile] = []
    for neighbour in fabric.get_all_unique_tiles():
        if neighbour.name == tile.name or neighbour.is_composite:
            continue
        pin_yaml = tile_pin_yaml(tile_root, neighbour.name)
        if not pin_yaml.is_file():
            continue
        shared = abutments(fabric, tile, neighbour)
        order = read_pin_yaml_order(pin_yaml)
        if any(order.get(one.side.opposite) for one in shared):
            found.append(neighbour)
    return found


def fixed_order_from_references(
    fabric: Fabric,
    tile: Tile,
    tile_root: Path,
    names: Iterable[str],
) -> InterfaceOrder | None:
    """Return the ranks the named references fix, in the tile's own pin names.

    A name that is a tile of the fabric is translated across every border the
    two share. Anything else is the path of a pin YAML already written in this
    tile's own names, which is how an order is carried between projects.

    Parameters
    ----------
    fabric : Fabric
        The fabric whose grid places the tiles.
    tile : Tile
        The tile being ordered.
    tile_root : Path
        The project's `Tile` directory.
    names : Iterable[str]
        Reference tile names or pin YAML paths.

    Returns
    -------
    InterfaceOrder | None
        Every border the references between them rank, or None when none were
        given.

    Raises
    ------
    GDSFlowError
        If a reference tile never touches the tile, or ranks nothing on a
        border they share, or a reference path is neither a tile nor a file,
        since a reference that fixes nothing is a mistake worth stopping on.
    """
    orders: list[InterfaceOrder] = []
    for name in names:
        reference = fabric.tileDic.get(name) or fabric.unusedTileDic.get(name)
        if reference is None:
            path = Path(name)
            if not path.is_file():
                raise GDSFlowError(
                    f"{name} is neither a tile of the fabric nor a pin YAML on disk"
                )
            orders.append(read_pin_yaml_order(path))
            continue
        shared = abutments(fabric, tile, reference)
        if not shared:
            raise GDSFlowError(
                f"{tile.name} never touches {reference.name} in the fabric grid, "
                f"so {reference.name} fixes none of its borders"
            )
        order = read_pin_yaml_order(tile_pin_yaml(tile_root, reference.name))
        orders.extend(translate_order(tile, one, order) for one in shared)
    return merge_orders(orders) if orders else None


def order_pairs(
    placement: Placement,
    pairs: Iterable[PinPair],
    fixed: InterfaceOrder | None = None,
) -> dict[Axis, list[PinPair]]:
    """Order the pairs of each axis, fixed pairs first, then free pairs by target.

    Fixed pairs keep their relative order and take the leading ranks. Free pairs
    follow in ascending target order, ties in input order. Rank-based spreading
    means an appended pair shifts every pin on that axis, so abutting tiles
    must carry the same pair set on a shared axis, which the even spread of the
    default layout already required.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    pairs : Iterable[PinPair]
        The pin pairs to order.
    fixed : InterfaceOrder | None
        An order whose pairs hold their rank. Defaults to None, every pair free.

    Returns
    -------
    dict[Axis, list[PinPair]]
        The pairs of each axis in rank order.
    """
    pairs = list(pairs)
    ranks = fixed_ranks(pairs, fixed) if fixed is not None else {}
    ordered: dict[Axis, list[PinPair]] = {axis: [] for axis in Axis}
    for axis in Axis:
        on_axis = [pair for pair in pairs if pair.axis is axis]
        held = sorted((p for p in on_axis if p in ranks), key=lambda p: ranks[p])
        free = sorted(
            (p for p in on_axis if p not in ranks),
            key=lambda p: pair_target(placement, p),
        )
        ordered[axis] = held + free
    return ordered


def rank_offset(placement: Placement, ordered: Mapping[Axis, list[PinPair]]) -> float:
    """Sum over pairs of the distance from target to the evenly spread rank position.

    This is what a border laid out by rank costs against the targets, and is
    reported next to the same sum for the current pin positions.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    ordered : Mapping[Axis, list[PinPair]]
        The pairs of each axis in rank order.

    Returns
    -------
    float
        Summed offset in microns.
    """
    total = 0.0
    for axis, pairs in ordered.items():
        if not pairs:
            continue
        origin = placement.die[0] if axis is Axis.VERTICAL else placement.die[1]
        length = placement.width if axis is Axis.VERTICAL else placement.height
        for rank, pair in enumerate(pairs):
            spread = origin + (rank + 0.5) / len(pairs) * length
            total += abs(pair_target(placement, pair) - spread)
    return total


def current_offset(placement: Placement, pairs: Iterable[PinPair]) -> float:
    """Sum over pairs of the distance from target to the first pin's position.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    pairs : Iterable[PinPair]
        The pairs to evaluate.

    Returns
    -------
    float
        Summed offset in microns.
    """
    total = 0.0
    for pair in pairs:
        pin = placement.pins[pair.first]
        total += abs(pair_target(placement, pair) - _along(pair.axis, pin.x, pin.y))
    return total
