"""Tests for fabric_io_place: halo-aware stamping of fabric-level BPins.

The placement rule is decided per BTerm from geometry alone:

- The facing side is the master edge the tile pin is flush with (generic N/S/E/W).
- The gap between that pin edge and the die edge on that side equals the halo.
- gap == 0 (pin flush with die edge): stamp the pin geometry in place.
- gap  > 0 (halo on that side): snap one BPin box onto the die edge so the
  router can connect it across the halo. This is how a multi-fanout net such
  as the clock gets a routing channel.
- gap == 0 with more than one sink: the net needs a channel that does not
  exist, so placement fails loudly instead of emitting an unroutable design.
"""

import contextlib
from types import SimpleNamespace

import pytest
from conftest import (
    MockBlockIoPlace,
    MockBPinIoPlace,
    MockBTermIoPlace,
    MockDie,
    MockGeom,
    MockInst,
    MockITerm,
    MockMaster,
    MockMPin,
    MockMTerm,
    MockNetIoPlace,
    MockReaderIoPlace,
    MockRect,
    MockTechIoPlace,
    PinPlacementRecorder,
)


@pytest.fixture
def _io_place_setup(
    mock_odb_io_place: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wire the fake ODB module into fabric_io_place for the test."""
    from fabulous.fabric_generator.gds_generator.script import fabric_io_place

    monkeypatch.setattr(fabric_io_place, "odb", mock_odb_io_place)


def _call_io_place(reader: MockReaderIoPlace, monkeypatch: pytest.MonkeyPatch) -> None:
    from librelane.scripts.odbpy.reader import OdbReader

    from fabulous.fabric_generator.gds_generator.script import fabric_io_place

    def _init(self: object, *_a: object, **_k: object) -> None:
        for attr in dir(reader):
            if attr.startswith("_"):
                continue
            with contextlib.suppress(AttributeError):
                setattr(self, attr, getattr(reader, attr))

    monkeypatch.setattr(OdbReader, "__init__", _init)
    actual = fabric_io_place.io_place.callback
    assert actual is not None
    actual(input_db="x.odb", input_lefs=[], config_path=None, reader=reader)


def _side_geom(side: str, w: int, h: int) -> tuple[int, int, int, int]:
    """Pin box (master coords) flush with the requested master edge."""
    return {
        "SOUTH": (40, 0, 60, 10),
        "NORTH": (40, h - 10, 60, h),
        "WEST": (0, 40, 10, 60),
        "EAST": (w - 10, 40, w, 60),
    }[side]


def _make_iterm(
    inst_x: int,
    inst_y: int,
    side: str,
    *,
    w: int = 100,
    h: int = 100,
    layer: str = "Metal2",
) -> MockITerm:
    """Build an ITerm whose pin sits flush against `side` of its master tile."""
    x1, y1, x2, y2 = _side_geom(side, w, h)
    geom = MockGeom(layer, x1, y1, x2, y2)
    bbox = MockRect(x1, y1, x2 - x1, y2 - y1)
    mterm = MockMTerm(bbox, MockMaster(w, h), mpins=[MockMPin([geom])])
    return MockITerm(bbox, mterm, inst=MockInst(inst_x, inst_y))


def _placements_for(recorder: PinPlacementRecorder, name: str) -> list[tuple]:
    return [p for p in recorder.placements if p[0] == name]


@pytest.mark.usefixtures("_io_place_setup")
def test_stamps_in_place_when_pin_flush_with_die_edge(
    pin_placement_recorder: PinPlacementRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gap == 0: the BPin box coincides with the tile pin (no offset)."""
    # Tile flush with the south die edge: inst_y == die.yMin, so gap == 0.
    iterm = _make_iterm(0, 0, "SOUTH")
    net = MockNetIoPlace("sig", [iterm])
    bterm = MockBTermIoPlace("sig", net)

    block = MockBlockIoPlace(MockDie(0, 0, 100, 100), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    pins = bterm.getBPins()
    assert len(pins) == 1
    assert pins[0].status == "FIRM"
    boxes = _placements_for(pin_placement_recorder, "sig")
    # Absolute pin geometry, unchanged.
    assert boxes == [("sig", "Metal2", 40, 0, 60, 10)]


@pytest.mark.usefixtures("_io_place_setup")
def test_offsets_pin_to_south_die_edge_when_halo_present(
    pin_placement_recorder: PinPlacementRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gap > 0: the BPin box snaps onto the die edge so the router can reach it."""
    # Bottom halo of 20: tile inset by 20 from the die bottom.
    iterm = _make_iterm(0, 20, "SOUTH")
    net = MockNetIoPlace("sig", [iterm])
    bterm = MockBTermIoPlace("sig", net)

    block = MockBlockIoPlace(MockDie(0, 0, 200, 150), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    boxes = _placements_for(pin_placement_recorder, "sig")
    # Pin geometry translated down by the halo so its south edge lands on y=0.
    assert boxes == [("sig", "Metal2", 40, 0, 60, 10)]


@pytest.mark.usefixtures("_io_place_setup")
def test_multifanout_places_single_edge_box_with_halo(
    pin_placement_recorder: PinPlacementRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multi-sink net with a halo gets exactly one edge box; router fans out."""
    # Two bottom-row tiles both driven by the same fabric clock, south halo 20.
    iterm_a = _make_iterm(0, 20, "SOUTH")
    iterm_b = _make_iterm(100, 20, "SOUTH")
    net = MockNetIoPlace("UserCLK", [iterm_a, iterm_b])
    bterm = MockBTermIoPlace("UserCLK", net)

    block = MockBlockIoPlace(MockDie(0, 0, 200, 150), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    boxes = _placements_for(pin_placement_recorder, "UserCLK")
    # One access box on the die edge, taken from the first sink; not one per sink.
    assert boxes == [("UserCLK", "Metal2", 40, 0, 60, 10)]


@pytest.mark.usefixtures("_io_place_setup")
def test_errors_on_multifanout_without_halo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gap == 0 with multiple sinks has no channel: fail loudly, mention the halo."""
    iterm_a = _make_iterm(0, 0, "SOUTH")
    iterm_b = _make_iterm(100, 0, "SOUTH")
    net = MockNetIoPlace("UserCLK", [iterm_a, iterm_b])
    bterm = MockBTermIoPlace("UserCLK", net)

    block = MockBlockIoPlace(MockDie(0, 0, 200, 100), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    with pytest.raises(ValueError, match="halo"):
        _call_io_place(reader, monkeypatch)


@pytest.mark.usefixtures("_io_place_setup")
@pytest.mark.parametrize(
    ("side", "inst", "die", "expected"),
    [
        ("SOUTH", (0, 20), (0, 0, 200, 150), (40, 0, 60, 10)),
        ("NORTH", (0, 0), (0, 0, 100, 120), (40, 110, 60, 120)),
        ("WEST", (20, 0), (0, 0, 120, 100), (0, 40, 10, 60)),
        ("EAST", (0, 0), (0, 0, 120, 100), (110, 40, 120, 60)),
    ],
)
def test_offsets_to_correct_die_edge_for_each_side(
    side: str,
    inst: tuple[int, int],
    die: tuple[int, int, int, int],
    expected: tuple[int, int, int, int],
    pin_placement_recorder: PinPlacementRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The offset is generic: a halo on any side snaps the pin to that die edge."""
    iterm = _make_iterm(inst[0], inst[1], side)
    net = MockNetIoPlace("sig", [iterm])
    bterm = MockBTermIoPlace("sig", net)

    block = MockBlockIoPlace(MockDie(*die), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    boxes = _placements_for(pin_placement_recorder, "sig")
    assert boxes == [("sig", "Metal2", *expected)]


@pytest.mark.usefixtures("_io_place_setup")
def test_skips_power_and_ground(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POWER/GROUND BTerms must not be touched."""
    pwr = MockBTermIoPlace("VPWR", None, sig_type="POWER")
    gnd = MockBTermIoPlace("VGND", None, sig_type="GROUND")

    block = MockBlockIoPlace(MockDie(0, 0, 100, 100), [pwr, gnd])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    assert pwr.getBPins() == []
    assert gnd.getBPins() == []


@pytest.mark.usefixtures("_io_place_setup")
def test_destroys_orphan_bterm_with_no_iterms(
    mock_odb_io_place: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A signal BTerm whose net has no ITerms is destroyed (and so is the net)."""
    net = MockNetIoPlace("orphan", [])
    bterm = MockBTermIoPlace("orphan", net)

    block = MockBlockIoPlace(MockDie(0, 0, 100, 100), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    assert bterm in mock_odb_io_place.destroyed_bterms
    assert net in mock_odb_io_place.destroyed_nets


@pytest.mark.usefixtures("_io_place_setup")
def test_leaves_existing_bpins_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a BTerm already has a BPin, io_place skips it without re-stamping."""
    iterm = _make_iterm(0, 0, "SOUTH")
    net = MockNetIoPlace("sig", [iterm])
    bterm = MockBTermIoPlace("sig", net)
    pre_existing = MockBPinIoPlace(bterm.getName())
    bterm._add_bpin(pre_existing)  # noqa: SLF001

    block = MockBlockIoPlace(MockDie(0, 0, 100, 100), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    # Still exactly one BPin, no new one was created.
    assert bterm.getBPins() == [pre_existing]
