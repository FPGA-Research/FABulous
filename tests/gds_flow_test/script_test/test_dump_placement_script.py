"""Tests for dump_placement: finding the latches of a placed tile in OpenDB."""

from dataclasses import dataclass, field

import pytest

from fabulous.fabric_generator.gds_generator.script.dump_placement import dump_block

DBU = 1000


@dataclass
class Box:
    """A bounding box in database units."""

    x0: int
    y0: int
    x1: int
    y1: int

    def xMin(self) -> int:  # noqa: N802, D102
        return self.x0

    def yMin(self) -> int:  # noqa: N802, D102
        return self.y0

    def xMax(self) -> int:  # noqa: N802, D102
        return self.x1

    def yMax(self) -> int:  # noqa: N802, D102
        return self.y1


@dataclass
class Net:
    """A net and the terminals on it."""

    name: str
    sig: str = "SIGNAL"
    iterms: list["ITerm"] = field(default_factory=list)
    bterms: list["BTerm"] = field(default_factory=list)

    def getName(self) -> str:  # noqa: N802, D102
        return self.name

    def getSigType(self) -> str:  # noqa: N802, D102
        return self.sig

    def getITerms(self) -> list["ITerm"]:  # noqa: N802, D102
        return self.iterms

    def getBTerms(self) -> list["BTerm"]:  # noqa: N802, D102
        return self.bterms


@dataclass
class ITerm:
    """One instance pin, on a net."""

    inst: "Inst"
    pin: str
    io: str
    net: Net | None = None
    sig: str = "SIGNAL"

    def getInst(self) -> "Inst":  # noqa: N802, D102
        return self.inst

    def getMTerm(self) -> object:  # noqa: N802, D102
        return type("MTerm", (), {"getName": lambda _self, p=self.pin: p})()

    def getIoType(self) -> str:  # noqa: N802, D102
        return self.io

    def getSigType(self) -> str:  # noqa: N802, D102
        return self.sig

    def getNet(self) -> Net | None:  # noqa: N802, D102
        return self.net


@dataclass
class Inst:
    """A placed cell and its pins."""

    name: str
    box: Box
    placed: bool = True
    iterms: list[ITerm] = field(default_factory=list)

    def getName(self) -> str:  # noqa: N802, D102
        return self.name

    def getBBox(self) -> Box:  # noqa: N802, D102
        return self.box

    def isPlaced(self) -> bool:  # noqa: N802, D102
        return self.placed

    def getITerms(self) -> list[ITerm]:  # noqa: N802, D102
        return self.iterms


@dataclass
class BTerm:
    """A block port and its placed pin shape."""

    name: str
    io: str
    box: Box | None = None
    net: Net | None = None
    sig: str = "SIGNAL"

    def getName(self) -> str:  # noqa: N802, D102
        return self.name

    def getIoType(self) -> str:  # noqa: N802, D102
        return self.io

    def getSigType(self) -> str:  # noqa: N802, D102
        return self.sig

    def getBPins(self) -> list[object]:  # noqa: N802, D102
        if self.box is None:
            return []
        return [type("BPin", (), {"getBBox": lambda _s, b=self.box: b})()]

    def getNet(self) -> Net | None:  # noqa: N802, D102
        return self.net


@dataclass
class Block:
    """The placed block the dump reads."""

    insts: list[Inst]
    bterms: list[BTerm]
    die: Box = field(default_factory=lambda: Box(0, 0, 100 * DBU, 100 * DBU))

    def getDieArea(self) -> Box:  # noqa: N802, D102
        return self.die

    def getInsts(self) -> list[Inst]:  # noqa: N802, D102
        return self.insts

    def getBTerms(self) -> list[BTerm]:  # noqa: N802, D102
        return self.bterms

    def findInst(self, name: str) -> Inst | None:  # noqa: N802, D102
        return next((i for i in self.insts if i.name == name), None)


def _cell(name: str, x: int, y: int, pins: list[tuple[str, str]], **kw: bool) -> Inst:
    """Build a cell at (x, y) microns with the given `(pin, io)` list."""
    inst = Inst(
        name, Box((x - 1) * DBU, (y - 1) * DBU, (x + 1) * DBU, (y + 1) * DBU), **kw
    )
    inst.iterms = [ITerm(inst, pin, io) for pin, io in pins]
    return inst


def _wire(name: str, terminals: list[ITerm], ports: list[BTerm]) -> Net:
    """Join terminals and ports onto one net, both ways."""
    net = Net(name, iterms=terminals, bterms=ports)
    for terminal in terminals:
        terminal.net = net
    for port in ports:
        port.net = net
    return net


def _pin_of(inst: Inst, pin: str) -> ITerm:
    return next(t for t in inst.iterms if t.pin == pin)


def _border(bus: str, index: int, x: int, y: int, io: str) -> BTerm:
    return BTerm(
        f"{bus}[{index}]",
        io,
        Box((x - 1) * DBU, (y - 1) * DBU, (x + 1) * DBU, (y + 1) * DBU),
    )


def _grid_block() -> Block:
    """One latch on crosspoint (0, 0), reached from FrameData[0] through a buffer.

    The strobe reaches it directly, so the two paths differ and the walk has to
    cross the buffer on one of them.
    """
    latch = _cell("lat", 40, 60, [("D", "INPUT"), ("GATE", "INPUT"), ("Q", "OUTPUT")])
    buf = _cell("buf", 90, 25, [("A", "INPUT"), ("X", "OUTPUT")])
    strobe_buf = _cell("sbuf", 25, 90, [("A", "INPUT"), ("X", "OUTPUT")])

    data_in = _border("FrameData", 0, 0, 25, "INPUT")
    data_out = _border("FrameData_O", 0, 100, 25, "OUTPUT")
    strobe_in = _border("FrameStrobe", 0, 25, 0, "INPUT")
    strobe_out = _border("FrameStrobe_O", 0, 25, 100, "OUTPUT")

    _wire("d0", [_pin_of(latch, "D"), _pin_of(buf, "A")], [data_in])
    _wire("d0_o", [_pin_of(buf, "X")], [data_out])
    _wire("s0", [_pin_of(latch, "GATE"), _pin_of(strobe_buf, "A")], [strobe_in])
    _wire("s0_o", [_pin_of(strobe_buf, "X")], [strobe_out])

    return Block([latch, buf, strobe_buf], [data_in, data_out, strobe_in, strobe_out])


def test_dump_block_reports_the_die_and_both_border_pins() -> None:
    payload = dump_block(_grid_block(), dbu=DBU)

    assert payload["die"] == [0, 0, 100, 100]
    assert payload["data_y"] == {0: [25, 25]}
    assert payload["strobe_x"] == {0: [25, 25]}


def test_dump_block_finds_the_latch_through_the_buffer() -> None:
    """The latch is a leaf on both chains, so the walk crosses the feed-through."""
    payload = dump_block(_grid_block(), dbu=DBU)

    assert payload["latches"] == [
        {
            "frame": 0,
            "data_bit": 0,
            "instance": "lat",
            "x": 40,
            "y": 60,
            "data_pin": "D",
            "strobe_pin": "GATE",
        }
    ]


def _without_strobe() -> Block:
    """A cell reached from FrameData only, which is not a latch."""
    block = _grid_block()
    strobe = next(b for b in block.bterms if b.name == "FrameStrobe[0]")
    assert strobe.net is not None
    strobe.net.iterms = [t for t in strobe.net.iterms if t.inst.name != "lat"]
    return block


def _unpaired() -> Block:
    """A data chain that enters but never leaves."""
    block = _grid_block()
    block.bterms = [b for b in block.bterms if b.name != "FrameData_O[0]"]
    return block


def _unplaced_latch() -> Block:
    block = _grid_block()
    block.insts[0].placed = False
    return block


def _no_pin_shape() -> Block:
    block = _grid_block()
    next(b for b in block.bterms if b.name == "FrameData[0]").box = None
    return block


@pytest.mark.parametrize(
    ("build", "message"),
    [
        pytest.param(_without_strobe, "is reached from", id="not_a_latch"),
        pytest.param(_unpaired, "do not pair up", id="chain_does_not_span"),
        pytest.param(_unplaced_latch, "is not placed", id="unplaced"),
        pytest.param(_no_pin_shape, "has no placed pin", id="unplaced_port"),
    ],
)
def test_dump_block_rejects_a_block_that_breaks_the_crosspoint_model(
    build: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        dump_block(build(), dbu=DBU)  # type: ignore[operator]
