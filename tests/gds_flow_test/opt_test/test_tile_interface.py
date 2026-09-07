"""Tests for border pin pairs, their placement-driven order and the order file."""

import json
from pathlib import Path

import pytest
import yaml

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.tile_interface import (
    FRAME_CHAIN_PAIRS,
    Axis,
    BusKind,
    BusPair,
    PinPair,
)
from fabulous.fabric_generator.gds_generator.opt.placement import Placement
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    InterfaceOrder,
    apply_interface_order,
    current_offset,
    expand_bus_pairs,
    fixed_ranks,
    interface_order_config,
    order_pairs,
    pair_target,
    pins_by_side,
    project_interface_order_path,
    rank_offset,
    read_bus_pairs,
    read_interface_order,
    write_bus_pairs,
    write_interface_order,
)
from tests.conftest import make_empty_tile


def _wire(
    side: Side, source: str, destination: str, count: int, direction: Direction
) -> list[TilePort]:
    """Build the source and destination ports one tile CSV wire row yields."""
    common = {
        "wire_direction": direction,
        "source_name": source,
        "destination_name": destination,
        "wire_count": count,
        "y_offset": 1 if direction in (Direction.NORTH, Direction.SOUTH) else 0,
        "x_offset": 1 if direction in (Direction.EAST, Direction.WEST) else 0,
    }
    return [
        TilePort(source, IO.OUTPUT, count, side, **common),
        TilePort(destination, IO.INPUT, count, side.opposite, **common),
    ]


def _segment(pins: list[str]) -> dict:
    """Build one pin YAML segment holding `pins`, the rest at its defaults."""
    return {
        "min_distance": None,
        "max_distance": None,
        "pins": pins,
        "sort_mode": "bus_major",
        "reverse_result": False,
    }


@pytest.fixture
def tile() -> object:
    ports = (
        _wire(Side.NORTH, "N1BEG", "N1END", 2, Direction.NORTH)
        + _wire(Side.SOUTH, "S1BEG", "S1END", 1, Direction.SOUTH)
        + _wire(Side.EAST, "E1BEG", "E1END", 1, Direction.EAST)
        + _wire(Side.WEST, "W1BEG", "W1END", 1, Direction.WEST)
        + _wire(Side.NORTH, "NULL", "NN2END", 1, Direction.NORTH)
    )
    return make_empty_tile("T", ports=ports)


def test_bus_pairs_orient_every_wire_first_border_first(tile: object) -> None:
    assert tile.interface.pairs == [  # type: ignore[attr-defined]
        BusPair(Axis.VERTICAL, "N1BEG", "N1END"),
        BusPair(Axis.VERTICAL, "S1END", "S1BEG"),
        BusPair(Axis.HORIZONTAL, "E1BEG", "E1END"),
        BusPair(Axis.HORIZONTAL, "W1END", "W1BEG"),
        *FRAME_CHAIN_PAIRS,
    ]


def test_expand_bus_pairs_by_bit_and_bare_name() -> None:
    pairs = [
        BusPair(Axis.VERTICAL, "N1BEG", "N1END"),
        BusPair(Axis.VERTICAL, "UserCLKo", "UserCLK"),
        BusPair(Axis.HORIZONTAL, "E1BEG", "E1END"),
    ]
    pins = ["N1END[1]", "N1BEG[0]", "N1BEG[1]", "N1END[0]", "UserCLK", "UserCLKo"]

    assert expand_bus_pairs(pairs, pins) == [
        PinPair(Axis.VERTICAL, "N1BEG[0]", "N1END[0]"),
        PinPair(Axis.VERTICAL, "N1BEG[1]", "N1END[1]"),
        PinPair(Axis.VERTICAL, "UserCLKo", "UserCLK"),
    ]


def test_expand_bus_pairs_rejects_a_bit_without_its_partner() -> None:
    with pytest.raises(GDSFlowError, match="N1BEG/N1END has bits \\[0, 1\\] on one"):
        expand_bus_pairs(
            [BusPair(Axis.VERTICAL, "N1BEG", "N1END")],
            ["N1BEG[0]", "N1BEG[1]", "N1END[0]"],
        )


def test_bus_pairs_yaml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    write_bus_pairs(path, FRAME_CHAIN_PAIRS)
    assert read_bus_pairs(path) == list(FRAME_CHAIN_PAIRS)

    path.write_text("- {axis: vertical, first: a}\n")
    with pytest.raises(GDSFlowError, match="malformed bus pair"):
        read_bus_pairs(path)


def _pin(io: str, x: float, y: float) -> dict:
    return {"io": io, "x": x, "y": y}


def _inst(x: float, y: float) -> dict:
    return {"master": "cell", "x": x, "y": y}


def _net(bterms: list[str], iterms: list[tuple[str, str, str]]) -> dict:
    return {"bterms": bterms, "iterms": [list(t) for t in iterms]}


MUXES = ("mux_a", "mux_b", "mux_c", "mux_d", "mux_e")


# A 100 x 100 die. N1 bit 0 feeds two muxes at x = 60 and 80 and is driven by
# a mux at x = 70; N1 bit 1 lives at x = 10. The clock pair reaches nothing.
# E1 feeds a mux at y = 90 through a buffer. Two strobe lines are present.
PLACEMENT: dict = {
    "die": [0, 0, 100, 100],
    "instances": {
        "mux_a": _inst(60, 50),
        "mux_b": _inst(80, 50),
        "mux_c": _inst(70, 40),
        "mux_d": _inst(10, 20),
        "mux_e": _inst(50, 90),
        "buf_e": _inst(90, 50),
    },
    "pins": {
        "N1BEG[0]": _pin("OUTPUT", 30, 100),
        "N1END[0]": _pin("INPUT", 30, 0),
        "N1BEG[1]": _pin("OUTPUT", 50, 100),
        "N1END[1]": _pin("INPUT", 50, 0),
        "UserCLKo": _pin("OUTPUT", 90, 100),
        "UserCLK": _pin("INPUT", 90, 0),
        "FrameStrobe[0]": _pin("INPUT", 60, 0),
        "FrameStrobe_O[0]": _pin("OUTPUT", 60, 100),
        "FrameStrobe[1]": _pin("INPUT", 70, 0),
        "FrameStrobe_O[1]": _pin("OUTPUT", 70, 100),
        "E1BEG": _pin("OUTPUT", 100, 20),
        "E1END": _pin("INPUT", 0, 20),
    },
    "nets": {
        "N1END[0]": _net(
            ["N1END[0]"], [("mux_a", "I0", "INPUT"), ("mux_b", "I0", "INPUT")]
        ),
        "N1BEG[0]": _net(["N1BEG[0]"], [("mux_c", "X", "OUTPUT")]),
        "N1END[1]": _net(["N1END[1]"], [("mux_d", "I0", "INPUT")]),
        "N1BEG[1]": _net(["N1BEG[1]"], [("mux_d", "X", "OUTPUT")]),
        "UserCLK": _net(["UserCLK"], []),
        "UserCLKo": _net(["UserCLKo"], []),
        "FrameStrobe[0]": _net(["FrameStrobe[0]", "FrameStrobe_O[0]"], []),
        "FrameStrobe[1]": _net(["FrameStrobe[1]", "FrameStrobe_O[1]"], []),
        "E1END": _net(["E1END"], [("buf_e", "A", "INPUT")]),
        "e_mid": _net([], [("buf_e", "X", "OUTPUT"), ("mux_e", "I0", "INPUT")]),
        "E1BEG": _net(["E1BEG"], [("mux_e", "X", "OUTPUT")]),
        # Two select nets give every mux three pins, so none reads as a buffer.
        "sel0": _net([], [(m, "S0", "INPUT") for m in MUXES]),
        "sel1": _net([], [(m, "S1", "INPUT") for m in MUXES]),
    },
}

N1_0 = PinPair(Axis.VERTICAL, "N1BEG[0]", "N1END[0]")
N1_1 = PinPair(Axis.VERTICAL, "N1BEG[1]", "N1END[1]")
CLK = PinPair(Axis.VERTICAL, "UserCLKo", "UserCLK")
FS_0 = PinPair(
    Axis.VERTICAL, "FrameStrobe_O[0]", "FrameStrobe[0]", BusKind.FRAME_STROBE
)
FS_1 = PinPair(
    Axis.VERTICAL, "FrameStrobe_O[1]", "FrameStrobe[1]", BusKind.FRAME_STROBE
)
E1 = PinPair(Axis.HORIZONTAL, "E1BEG", "E1END")

FIXED: InterfaceOrder = {
    Side.NORTH: ["N1BEG[0]", "FrameStrobe_O[1]"],
    Side.SOUTH: ["N1END[0]", "FrameStrobe[1]"],
}


@pytest.fixture
def placement(tmp_path: Path) -> Placement:
    path = tmp_path / "tile.placement.json"
    path.write_text(json.dumps(PLACEMENT))
    return Placement.from_json(path)


@pytest.mark.parametrize(
    ("pair", "target"),
    [
        (N1_0, 70),
        (N1_1, 10),
        (CLK, 90),
        (FS_0, 25),
        (FS_1, 75),
        (E1, 90),
    ],
)
def test_pair_target(placement: Placement, pair: PinPair, target: float) -> None:
    assert pair_target(placement, pair) == target


def test_pair_target_rejects_a_pin_the_tile_lacks(placement: Placement) -> None:
    with pytest.raises(
        GDSFlowError, match="Pin S1BEG of pair .* is not on the placed tile"
    ):
        pair_target(placement, PinPair(Axis.VERTICAL, "S1BEG", "S1END"))


def test_order_pairs_sorts_each_axis_by_target(placement: Placement) -> None:
    order = order_pairs(placement, [N1_0, N1_1, CLK, FS_0, FS_1, E1])

    assert order == {
        Axis.VERTICAL: [N1_1, FS_0, N1_0, FS_1, CLK],
        Axis.HORIZONTAL: [E1],
    }


def test_order_pairs_leads_with_the_fixed_pairs(placement: Placement) -> None:
    order = order_pairs(placement, [N1_0, N1_1, CLK, FS_0, FS_1, E1], fixed=FIXED)

    # N1_0 and FS_1 hold ranks 0 and 1 although their targets are 70 and 75;
    # the free pairs follow at 10, 25 and 90.
    assert order == {
        Axis.VERTICAL: [N1_0, FS_1, N1_1, FS_0, CLK],
        Axis.HORIZONTAL: [E1],
    }


def test_offsets_before_and_after(placement: Placement) -> None:
    pairs = [N1_0, N1_1, CLK, FS_0, FS_1, E1]
    order = order_pairs(placement, pairs)

    # |70-30| + |10-50| + |90-90| + |25-60| + |75-70| + |90-20|
    assert current_offset(placement, pairs) == 190
    # Five vertical ranks at 10, 30, 50, 70, 90 against 10, 25, 70, 75, 90;
    # one horizontal rank at 50 against 90.
    assert rank_offset(placement, order) == 5 + 20 + 5 + 40


def test_fixed_ranks_keeps_the_rank_of_every_listed_pair() -> None:
    assert fixed_ranks([N1_0, N1_1, FS_0, FS_1], FIXED) == {N1_0: 0, FS_1: 1}


@pytest.mark.parametrize(
    ("fixed", "message"),
    [
        (
            {Side.NORTH: ["N1BEG[0]"], Side.SOUTH: []},
            "lists N1BEG\\[0\\] without its partner N1END\\[0\\]",
        ),
        (
            {
                Side.NORTH: ["N1BEG[0]", "N1BEG[1]"],
                Side.SOUTH: ["N1END[1]", "N1END[0]"],
            },
            "ranks N1BEG\\[0\\] at 0 on NORTH but N1END\\[0\\] at 1",
        ),
    ],
    ids=["missing partner", "different rank"],
)
def test_fixed_ranks_rejects_an_order_whose_borders_would_not_abut(
    fixed: InterfaceOrder, message: str
) -> None:
    with pytest.raises(GDSFlowError, match=message):
        fixed_ranks([N1_0, N1_1], fixed)


def test_pins_by_side_projects_each_pair_onto_its_two_borders() -> None:
    assert pins_by_side({Axis.VERTICAL: [N1_1, FS_0], Axis.HORIZONTAL: [E1]}) == {
        Side.NORTH: ["N1BEG[1]", "FrameStrobe_O[0]"],
        Side.SOUTH: ["N1END[1]", "FrameStrobe[0]"],
        Side.EAST: ["E1BEG"],
        Side.WEST: ["E1END"],
    }


def test_interface_order_yaml_round_trip(tmp_path: Path) -> None:
    order = pins_by_side({Axis.VERTICAL: [N1_1, FS_0], Axis.HORIZONTAL: [E1]})
    path = tmp_path / "tile_interface_order.yaml"
    write_interface_order(order, path)

    assert yaml.safe_load(path.read_text())["X0Y0"][Side.NORTH.name] == [
        _segment([r"N1BEG\[1\]", r"FrameStrobe_O\[0\]"])
    ]
    assert read_interface_order(path) == order


def test_read_interface_order_rejects_a_file_holding_more_than_one_tile(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tile_interface_order.yaml"
    payload = {
        key: {Side.NORTH.name: [_segment([r"N1BEG\[0\]"])]} for key in ("X0Y0", "X0Y1")
    }
    path.write_text(yaml.safe_dump(payload))

    with pytest.raises(GDSFlowError, match="single tile key 'X0Y0'"):
        read_interface_order(path)


def test_read_interface_order_rejects_a_pattern_in_place_of_a_pin_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tile_interface_order.yaml"
    payload = {"X0Y0": {Side.NORTH.name: [_segment([r"FrameStrobe_O\[\d+\]"])]}}
    path.write_text(yaml.safe_dump(payload))

    with pytest.raises(GDSFlowError, match="is a pattern, not an exact pin name"):
        read_interface_order(path)


def test_listed_pins_lead_each_border_and_unlisted_ports_follow() -> None:
    payload = {
        "X0Y0": {
            Side.NORTH.name: [
                _segment([r"N1BEG\[\d+\]"]),
                _segment(["S1END"]),
                _segment(["UserCLKo"]),
                _segment([r"FrameStrobe_O\[\d+\]"]),
            ]
        }
    }
    # NN4 is on no border of this tile, so it is skipped; the strobe pin
    # consumes the strobe regex and the two N1 pins consume the N1 regex.
    order: InterfaceOrder = {
        Side.NORTH: ["FrameStrobe_O[3]", "N1BEG[1]", "N1BEG[0]", "NN4BEG[0]"]
    }

    assert apply_interface_order(payload, order) == {
        "X0Y0": {
            Side.NORTH.name: [
                _segment([r"FrameStrobe_O\[3\]", r"N1BEG\[1\]", r"N1BEG\[0\]"]),
                _segment(["S1END"]),
                _segment(["UserCLKo"]),
            ]
        }
    }


def test_apply_interface_order_reorders_an_already_ordered_payload() -> None:
    payload = {
        "X0Y0": {
            Side.NORTH.name: [
                _segment([r"N1BEG\[1\]", r"N1BEG\[0\]"]),
                _segment(["S1END"]),
                _segment([r"FrameStrobe_O\[\d+\]"]),
            ]
        }
    }
    order: InterfaceOrder = {Side.NORTH: ["N1BEG[0]", "N1BEG[1]"]}

    assert apply_interface_order(payload, order) == {
        "X0Y0": {
            Side.NORTH.name: [
                _segment([r"N1BEG\[0\]", r"N1BEG\[1\]"]),
                _segment(["S1END"]),
                _segment([r"FrameStrobe_O\[\d+\]"]),
            ]
        }
    }


def test_super_tile_faces_follow_the_order_with_their_prefix() -> None:
    # A 1x2 super tile: X0Y0 on top of X0Y1, so the shared face is internal
    # and carries no pins.
    payload = {
        "X0Y0": {
            Side.NORTH.name: [
                _segment([r"Tile_X0Y0_N1BEG\[\d+\]"]),
                _segment([r"Tile_X0Y0_FrameStrobe_O\[\d+\]"]),
            ],
            Side.SOUTH.name: [],
        },
        "X0Y1": {
            Side.SOUTH.name: [
                _segment([r"Tile_X0Y1_N1END\[\d+\]"]),
                _segment([r"Tile_X0Y1_FrameStrobe\[\d+\]"]),
            ]
        },
    }
    order = pins_by_side({Axis.VERTICAL: [FS_1, N1_1, N1_0]})

    assert apply_interface_order(payload, order) == {
        "X0Y0": {
            Side.NORTH.name: [
                _segment(
                    [
                        r"Tile_X0Y0_FrameStrobe_O\[1\]",
                        r"Tile_X0Y0_N1BEG\[1\]",
                        r"Tile_X0Y0_N1BEG\[0\]",
                    ]
                )
            ],
            Side.SOUTH.name: [],
        },
        "X0Y1": {
            Side.SOUTH.name: [
                _segment(
                    [
                        r"Tile_X0Y1_FrameStrobe\[1\]",
                        r"Tile_X0Y1_N1END\[1\]",
                        r"Tile_X0Y1_N1END\[0\]",
                    ]
                )
            ]
        },
    }


@pytest.mark.parametrize("written", [True, False], ids=["written", "absent"])
def test_interface_order_config_points_at_an_installed_project_order(
    tmp_path: Path, written: bool
) -> None:
    path = project_interface_order_path(tmp_path)
    assert path == tmp_path / "Tile" / "include" / "tile_interface_order.yaml"
    if written:
        path.parent.mkdir(parents=True)
        write_interface_order({Side.NORTH: ["N1BEG[0]"]}, path)

    expected = {"FABULOUS_TILE_INTERFACE_ORDER": str(path)} if written else {}
    assert interface_order_config(tmp_path) == expected
