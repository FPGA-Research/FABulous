"""Order a tile's border pairs from its placement, and the order file.

An interface order is written as an ordinary pin YAML with one segment per side
naming its pins exactly, the form `FABulousTileIOPlacement` consumes, so the
same file describes a proposal, the project order and an imported neighbour.
The pair invariant is not a property of that file, so it is checked whenever an
order is read against a tile's pairs.

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
from pathlib import Path

import yaml

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.tile_interface import (
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

TILE_INTERFACE_ORDER_VARIABLE_NAME = "FABULOUS_TILE_INTERFACE_ORDER"

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


def project_interface_order_path(proj_dir: Path) -> Path:
    """Return where a project keeps the interface order shared by all its tiles."""
    return proj_dir / "Tile" / "include" / "tile_interface_order.yaml"


def interface_order_config(proj_dir: Path) -> dict[str, str]:
    """Return the tile flow override that makes a tile follow the project order.

    Parameters
    ----------
    proj_dir : Path
        The project directory.

    Returns
    -------
    dict[str, str]
        `FABULOUS_TILE_INTERFACE_ORDER` pointing at the project order, or
        nothing when no order was installed yet, so every tile hardened after
        one was installed keeps abutting it.
    """
    path = project_interface_order_path(proj_dir)
    if not path.exists():
        return {}
    return {TILE_INTERFACE_ORDER_VARIABLE_NAME: str(path)}


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
    tile_type: Tile | SuperTile,
    outfile: Path,
    order_path: Path,
    *,
    fabric: Fabric | None = None,
) -> None:
    """Write a tile's pin YAML with the project order leading each border.

    Without an order file the pin YAML is the generated one, so a project that
    never ran the interface ordering keeps the default layout.

    Parameters
    ----------
    tile_type : Tile | SuperTile
        The tile the pins belong to.
    outfile : Path
        The pin YAML to write.
    order_path : Path
        The project interface order, which need not exist.
    fabric : Fabric | None
        The fabric, which resolves the sides of external ports.
    """
    generate_IO_pin_order_config(tile_type, outfile, fabric=fabric)
    if not order_path.exists():
        return
    payload = apply_interface_order(
        yaml.safe_load(outfile.read_text()), read_interface_order(order_path)
    )
    outfile.write_text(yaml.safe_dump(payload))


def propagate_tile_interface_order(
    fabric: Fabric, tile_root: Path, order_path: Path
) -> list[Path]:
    """Rewrite every tile's pin YAML so the whole fabric abuts on one order.

    A border pair is only in the same place on both sides of an abutment when
    both tiles were hardened against the same order, and the pin YAML under
    `Tile/<name>/` is what a hardening run reads when it is given no pin
    configuration of its own.

    Parameters
    ----------
    fabric : Fabric
        The fabric whose tiles are rewritten.
    tile_root : Path
        The project's `Tile` directory.
    order_path : Path
        The project interface order.

    Returns
    -------
    list[Path]
        The pin YAML files written.

    Raises
    ------
    GDSFlowError
        If no interface order is installed, since there is then nothing to
        propagate.
    """
    if not order_path.exists():
        raise GDSFlowError(
            f"No tile interface order at {order_path}; run the placement "
            "optimisation for one tile or copy an order there first."
        )
    written: list[Path] = []
    for tile_type in fabric.get_all_unique_tiles():
        pin_file = tile_root / tile_type.name / f"{tile_type.name}_io_pin_order.yaml"
        pin_file.parent.mkdir(parents=True, exist_ok=True)
        write_ordered_pin_yaml(tile_type, pin_file, order_path, fabric=fabric)
        written.append(pin_file)
    return written


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
