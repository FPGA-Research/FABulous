"""Tests for fabric_io_place - validates pin placement computation and geometry.

This test file validates the actual production code in fabric_io_place.py by:
1. Mocking the odb module with fake objects that record operations
2. Calling the real io_place() implementation
3. Verifying the recorded operations match expected pin placements

Note: The approach of extracting a helper function was considered, but would require
modifying the production code. Instead, we use conftest fixtures and call the real
Click-decorated function by invoking it through its callback.
"""

import sys

import pytest


# We need a minimal set of test-specific classes since conftest classes
# don't have all the methods needed for this specific test scenario

class PinPlacementRecorder:
    """Records pin placement boxes with coordinates and layers."""

    def __init__(self) -> None:
        self.placements: list[tuple[str, str, int, int, int, int]] = []


class FakeMaster:
    """Mock master cell."""

    def __init__(self, width: int, height: int) -> None:
        self._width = width
        self._height = height

    def getWidth(self) -> int:
        return self._width

    def getHeight(self) -> int:
        return self._height


class FakeMTerm:
    """Mock master terminal with bbox."""

    def __init__(self, bbox: "FakeRect", master: FakeMaster) -> None:
        self._bbox = bbox
        self._master = master

    def getBBox(self) -> "FakeRect":
        return self._bbox

    def getMaster(self) -> FakeMaster:
        return self._master


class FakeITerm:
    """Mock instance terminal."""

    def __init__(self, bbox: "FakeRect", mterm: FakeMTerm) -> None:
        self._bbox = bbox
        self._mterm = mterm

    def getBBox(self) -> "FakeRect":
        return self._bbox

    def getMTerm(self) -> FakeMTerm:
        return self._mterm


class FakeNet:
    """Mock net."""

    def __init__(self, name: str, iterms: list[FakeITerm]) -> None:
        self._name = name
        self._iterms = iterms

    def getName(self) -> str:
        return self._name

    def getITerms(self) -> list[FakeITerm]:
        return self._iterms


class FakeBTerm:
    """Mock boundary term."""

    def __init__(self, name: str, net: FakeNet) -> None:
        self._name = name
        self._net = net
        self._bpins: list = []

    def getName(self) -> str:
        return self._name

    def getSigType(self) -> str:
        return "SIGNAL"

    def getNet(self) -> FakeNet:
        return self._net

    def getBPins(self) -> list:
        return self._bpins

    def _add_bpin(self, bpin: object) -> None:
        self._bpins.append(bpin)


class FakeBPin:
    """Mock boundary pin."""

    def __init__(self, bterm_name: str) -> None:
        self.bterm_name = bterm_name
        self.status = None

    def setPlacementStatus(self, status: str) -> None:
        self.status = status


class FakeRect:
    """Mock rectangle - uses conftest.FakeRect interface."""

    def __init__(self, x: int, y: int, w: int, h: int) -> None:
        self._x = x
        self._y = y
        self._w = w
        self._h = h

    def moveTo(self, x: int, y: int) -> None:
        self._x = x
        self._y = y

    def ll(self) -> tuple[int, int]:
        return (self._x, self._y)

    def ur(self) -> tuple[int, int]:
        return (self._x + self._w, self._y + self._h)

    def xMin(self) -> int:
        return self._x

    def yMin(self) -> int:
        return self._y

    def xMax(self) -> int:
        return self._x + self._w

    def yMax(self) -> int:
        return self._y + self._h

    def xCenter(self) -> int:
        return self._x + self._w // 2

    def yCenter(self) -> int:
        return self._y + self._h // 2


class FakeLayer:
    """Mock layer."""

    def __init__(self, name: str, width: int, area: int) -> None:
        self.name = name
        self._width = width
        self._area = area

    def getWidth(self) -> int:
        return self._width

    def getArea(self) -> int:
        return self._area

    def getSpacing(self) -> int:
        return 0


class FakeDie:
    """Mock die area."""

    def __init__(self, llx: int, lly: int, urx: int, ury: int) -> None:
        self._llx = llx
        self._lly = lly
        self._urx = urx
        self._ury = ury

    def xMin(self) -> int:
        return self._llx

    def yMin(self) -> int:
        return self._lly

    def xMax(self) -> int:
        return self._urx

    def yMax(self) -> int:
        return self._ury


class FakeTech:
    """Mock technology."""

    def __init__(self, h_layer: FakeLayer, v_layer: FakeLayer) -> None:
        self._h_layer = h_layer
        self._v_layer = v_layer

    def findLayer(self, name: str) -> FakeLayer:
        if name == "H":
            return self._h_layer
        return self._v_layer


class FakeBlock:
    """Mock block."""

    def __init__(self, die: FakeDie, bterms: list[FakeBTerm]) -> None:
        self._die = die
        self._bterms = bterms

    def getDieArea(self) -> FakeDie:
        return self._die

    def getBTerms(self) -> list[FakeBTerm]:
        return self._bterms


class FakeReader:
    """Mock ODB reader."""

    def __init__(self, dbunits: float, tech: FakeTech, block: FakeBlock) -> None:
        self.dbunits = dbunits
        self.tech = tech
        self.block = block


@pytest.fixture
def recorder() -> PinPlacementRecorder:
    """Provide a recorder for pin placements."""
    return PinPlacementRecorder()


@pytest.fixture
def fake_odb_io_place(recorder: PinPlacementRecorder, box_recorder):
    """Provide a fake ODB module that records pin placements."""
    from types import SimpleNamespace

    def dbBPin_create(bterm: FakeBTerm) -> FakeBPin:
        bpin = FakeBPin(bterm.getName())
        bterm._add_bpin(bpin)  # noqa: SLF001
        return bpin

    def dbBox_create(
        bpin: FakeBPin, layer: FakeLayer, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        recorder.placements.append((bpin.bterm_name, layer.name, x1, y1, x2, y2))
        box_recorder(bpin, layer, x1, y1, x2, y2)

    return SimpleNamespace(
        Rect=FakeRect,
        dbBPin_create=dbBPin_create,
        dbBox_create=dbBox_create,
    )


def call_io_place(reader, **kwargs):
    """Call the real io_place function by accessing its callback.

    This helper bypasses Click's command-line parsing to directly invoke
    the implementation with our test parameters.
    """
    from FABulous.fabric_generator.gds_generator.script.fabric_io_place import (
        io_place,
    )

    # Access the actual callback function, bypassing Click decorators
    # The callback is the original function before decorators were applied
    callback = io_place.callback
    return callback(reader=reader, **kwargs)


def test_io_place_north_side_placement(
    monkeypatch: pytest.MonkeyPatch,
    recorder: PinPlacementRecorder,
    fake_odb_io_place,
    box_recorder,
) -> None:
    """Test pin placement on NORTH side - validates coordinates and layer selection."""
    monkeypatch.setitem(sys.modules, "odb", fake_odb_io_place)

    # Setup: die 0,0 to 1000,1000, dbunits=100 (1 micron = 100 units)
    h_layer = FakeLayer("H", width=50, area=10000)
    v_layer = FakeLayer("V", width=50, area=10000)
    tech = FakeTech(h_layer, v_layer)
    die = FakeDie(0, 0, 1000, 1000)

    # Create pin on NORTH side: mterm at yMax == master.height
    master = FakeMaster(100, 100)
    mterm_bbox = FakeRect(25, 100, 50, 0)  # yMax=100 = master height -> NORTH
    iterm_bbox = FakeRect(400, 400, 100, 100)  # Center at (450, 450)
    mterm = FakeMTerm(mterm_bbox, master)
    iterm = FakeITerm(iterm_bbox, mterm)
    net = FakeNet("north_pin", [iterm])
    bterm = FakeBTerm("north_pin", net)

    block = FakeBlock(die, [bterm])
    reader = FakeReader(100.0, tech, block)

    # Call actual io_place function
    call_io_place(
        reader,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=2.0,
        hor_width_mult=2.0,
        hor_length=None,
        ver_length=None,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    # Verify: should place on NORTH edge using V layer
    assert len(recorder.placements) == 1
    name, layer, x1, y1, x2, y2 = recorder.placements[0]

    assert name == "north_pin"
    assert layer == "V", "NORTH side should use vertical layer"

    # Pin should be at die yMax (NORTH edge)
    assert y2 == 1000, "Pin should extend to die yMax"

    # X should be centered on iterm center (450) minus half width
    assert x1 == 400, f"Pin X should be centered on iterm, got {x1}"


def test_io_place_east_side_placement(
    monkeypatch: pytest.MonkeyPatch,
    recorder: PinPlacementRecorder,
    fake_odb_io_place,
    box_recorder,
) -> None:
    """Test pin placement on EAST side."""
    monkeypatch.setitem(sys.modules, "odb", fake_odb_io_place)

    h_layer = FakeLayer("H", width=50, area=10000)
    v_layer = FakeLayer("V", width=50, area=10000)
    tech = FakeTech(h_layer, v_layer)
    die = FakeDie(0, 0, 1000, 1000)

    master = FakeMaster(100, 100)
    mterm_bbox = FakeRect(100, 25, 0, 50)  # xMax=100 = master width -> EAST
    iterm_bbox = FakeRect(400, 400, 100, 100)
    mterm = FakeMTerm(mterm_bbox, master)
    iterm = FakeITerm(iterm_bbox, mterm)
    net = FakeNet("east_pin", [iterm])
    bterm = FakeBTerm("east_pin", net)

    block = FakeBlock(die, [bterm])
    reader = FakeReader(100.0, tech, block)

    call_io_place(
        reader,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=2.0,
        hor_width_mult=2.0,
        hor_length=None,
        ver_length=None,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    assert len(recorder.placements) == 1
    name, layer, x1, y1, x2, y2 = recorder.placements[0]

    assert name == "east_pin"
    assert layer == "H", "EAST side should use horizontal layer"
    assert x2 == 1000, "Pin should extend to die xMax"


def test_io_place_width_calculation(
    monkeypatch: pytest.MonkeyPatch,
    recorder: PinPlacementRecorder,
    fake_odb_io_place,
    box_recorder,
) -> None:
    """Test that width is calculated correctly with multiplier."""
    monkeypatch.setitem(sys.modules, "odb", fake_odb_io_place)

    h_layer = FakeLayer("H", width=50, area=10000)
    v_layer = FakeLayer("V", width=50, area=10000)
    tech = FakeTech(h_layer, v_layer)
    die = FakeDie(0, 0, 1000, 1000)

    master = FakeMaster(100, 100)
    mterm_bbox = FakeRect(25, 100, 50, 0)
    iterm_bbox = FakeRect(400, 400, 100, 100)
    mterm = FakeMTerm(mterm_bbox, master)
    iterm = FakeITerm(iterm_bbox, mterm)
    net = FakeNet("test_pin", [iterm])
    bterm = FakeBTerm("test_pin", net)

    block = FakeBlock(die, [bterm])
    reader = FakeReader(100.0, tech, block)

    # ver_width_mult = 3.0 means width = 3.0 * 50 = 150
    call_io_place(
        reader,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=3.0,
        hor_width_mult=2.0,
        hor_length=None,
        ver_length=None,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    name, layer, x1, y1, x2, y2 = recorder.placements[0]
    width = x2 - x1
    assert width == 150, f"Expected width 150, got {width}"


def test_io_place_length_calculation_from_area(
    monkeypatch: pytest.MonkeyPatch,
    recorder: PinPlacementRecorder,
    fake_odb_io_place,
    box_recorder,
) -> None:
    """Test that length is calculated from area when not explicitly provided."""
    monkeypatch.setitem(sys.modules, "odb", fake_odb_io_place)

    h_layer = FakeLayer("H", width=50, area=10000)
    v_layer = FakeLayer("V", width=50, area=10000)
    tech = FakeTech(h_layer, v_layer)
    die = FakeDie(0, 0, 10000000, 10000000)

    master = FakeMaster(100, 100)
    mterm_bbox = FakeRect(25, 100, 50, 0)
    iterm_bbox = FakeRect(400, 400, 100, 100)
    mterm = FakeMTerm(mterm_bbox, master)
    iterm = FakeITerm(iterm_bbox, mterm)
    net = FakeNet("test_pin", [iterm])
    bterm = FakeBTerm("test_pin", net)

    block = FakeBlock(die, [bterm])
    reader = FakeReader(100.0, tech, block)

    call_io_place(
        reader,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=1.0,
        hor_width_mult=1.0,
        hor_length=None,
        ver_length=None,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    name, layer, x1, y1, x2, y2 = recorder.placements[0]
    length = y2 - y1
    # length = max(ceil(10000 * 100 * 100 / 50), 50)
    # = max(ceil(20000000), 50) = 20000000
    expected_length = 20000000
    assert length == expected_length, f"Expected length {expected_length}, got {length}"


def test_io_place_custom_length(
    monkeypatch: pytest.MonkeyPatch,
    recorder: PinPlacementRecorder,
    fake_odb_io_place,
    box_recorder,
) -> None:
    """Test that custom length overrides area calculation."""
    monkeypatch.setitem(sys.modules, "odb", fake_odb_io_place)

    h_layer = FakeLayer("H", width=50, area=10000)
    v_layer = FakeLayer("V", width=50, area=10000)
    tech = FakeTech(h_layer, v_layer)
    die = FakeDie(0, 0, 10000000, 10000000)

    master = FakeMaster(100, 100)
    mterm_bbox = FakeRect(25, 100, 50, 0)
    iterm_bbox = FakeRect(400, 400, 100, 100)
    mterm = FakeMTerm(mterm_bbox, master)
    iterm = FakeITerm(iterm_bbox, mterm)
    net = FakeNet("test_pin", [iterm])
    bterm = FakeBTerm("test_pin", net)

    block = FakeBlock(die, [bterm])
    reader = FakeReader(100.0, tech, block)

    # Custom vertical length of 5.0 microns = 500 units
    call_io_place(
        reader,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=1.0,
        hor_width_mult=1.0,
        hor_length=None,
        ver_length=5.0,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    name, layer, x1, y1, x2, y2 = recorder.placements[0]
    length = y2 - y1
    assert length == 500, f"Expected custom length 500, got {length}"


def test_io_place_clamping_to_die_boundary(
    monkeypatch: pytest.MonkeyPatch,
    recorder: PinPlacementRecorder,
    fake_odb_io_place,
    box_recorder,
) -> None:
    """Test that pins are clamped to die boundaries."""
    monkeypatch.setitem(sys.modules, "odb", fake_odb_io_place)

    h_layer = FakeLayer("H", width=50, area=10000)
    v_layer = FakeLayer("V", width=200, area=10000)
    tech = FakeTech(h_layer, v_layer)
    die = FakeDie(0, 0, 1000, 1000)

    master = FakeMaster(100, 100)
    mterm_bbox = FakeRect(25, 100, 50, 0)
    # ITerm very close to die edge - should be clamped
    iterm_bbox = FakeRect(950, 950, 40, 40)  # Center at (970, 970)
    mterm = FakeMTerm(mterm_bbox, master)
    iterm = FakeITerm(iterm_bbox, mterm)
    net = FakeNet("edge_pin", [iterm])
    bterm = FakeBTerm("edge_pin", net)

    block = FakeBlock(die, [bterm])
    reader = FakeReader(100.0, tech, block)

    call_io_place(
        reader,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=2.0,
        hor_width_mult=2.0,
        hor_length=None,
        ver_length=None,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    name, layer, x1, y1, x2, y2 = recorder.placements[0]
    # Width = 2.0 * 200 = 400
    # x = max(0, min(970 - 200, 1000 - 400)) = max(0, min(770, 600)) = 600
    assert x1 >= 0, "Pin should not extend beyond die xMin"
    assert x2 <= 1000, "Pin should not extend beyond die xMax"


def test_io_place_extension_handling(
    monkeypatch: pytest.MonkeyPatch,
    recorder: PinPlacementRecorder,
    fake_odb_io_place,
    box_recorder,
) -> None:
    """Test that extensions are added correctly."""
    monkeypatch.setitem(sys.modules, "odb", fake_odb_io_place)

    h_layer = FakeLayer("H", width=50, area=10000)
    v_layer = FakeLayer("V", width=50, area=10000)
    tech = FakeTech(h_layer, v_layer)
    die = FakeDie(0, 0, 10000, 10000)

    master = FakeMaster(100, 100)
    mterm_bbox = FakeRect(25, 100, 50, 0)
    iterm_bbox = FakeRect(400, 400, 100, 100)
    mterm = FakeMTerm(mterm_bbox, master)
    iterm = FakeITerm(iterm_bbox, mterm)
    net = FakeNet("test_pin", [iterm])
    bterm = FakeBTerm("test_pin", net)

    block = FakeBlock(die, [bterm])
    reader = FakeReader(100.0, tech, block)

    # Add 2.0 micron extension = 200 units
    call_io_place(
        reader,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=1.0,
        hor_width_mult=1.0,
        hor_length=None,
        ver_length=5.0,
        hor_extension=0.0,
        ver_extension=2.0,
        verbose=False,
    )

    name, layer, x1, y1, x2, y2 = recorder.placements[0]
    # ver_length=5.0 microns = 500 units
    # ver_extension=2.0 microns = 200 units
    # Total length = 500 + 200 = 700 units
    length = y2 - y1
    assert length == 700, f"Expected length with extension 700, got {length}"


def test_io_place_all_four_sides(
    monkeypatch: pytest.MonkeyPatch,
    recorder: PinPlacementRecorder,
    fake_odb_io_place,
    box_recorder,
) -> None:
    """Test that pins can be placed on all four sides."""
    monkeypatch.setitem(sys.modules, "odb", fake_odb_io_place)

    h_layer = FakeLayer("H", width=50, area=10000)
    v_layer = FakeLayer("V", width=50, area=10000)
    tech = FakeTech(h_layer, v_layer)
    die = FakeDie(0, 0, 1000, 1000)

    master = FakeMaster(100, 100)

    # Create pins on all four sides
    bterms = []
    for side, bbox in [
        ("north", FakeRect(25, 100, 50, 0)),  # yMax=100 -> NORTH
        ("south", FakeRect(25, 0, 50, 0)),  # yMin=0 -> SOUTH
        ("east", FakeRect(100, 25, 0, 50)),  # xMax=100 -> EAST
        ("west", FakeRect(0, 25, 0, 50)),  # xMin=0 -> WEST
    ]:
        iterm_bbox = FakeRect(400, 400, 100, 100)
        mterm = FakeMTerm(bbox, master)
        iterm = FakeITerm(iterm_bbox, mterm)
        net = FakeNet(f"{side}_pin", [iterm])
        bterm = FakeBTerm(f"{side}_pin", net)
        bterms.append(bterm)

    block = FakeBlock(die, bterms)
    reader = FakeReader(100.0, tech, block)

    call_io_place(
        reader,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=2.0,
        hor_width_mult=2.0,
        hor_length=None,
        ver_length=None,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    assert len(recorder.placements) == 4, "Should place pins on all four sides"

    # Verify each side uses correct layer
    placements_by_name = {
        name: (layer, x1, y1, x2, y2)
        for name, layer, x1, y1, x2, y2 in recorder.placements
    }

    assert placements_by_name["north_pin"][0] == "V", "North should use vertical layer"
    assert placements_by_name["south_pin"][0] == "V", "South should use vertical layer"
    assert placements_by_name["east_pin"][0] == "H", "East should use horizontal layer"
    assert placements_by_name["west_pin"][0] == "H", "West should use horizontal layer"
