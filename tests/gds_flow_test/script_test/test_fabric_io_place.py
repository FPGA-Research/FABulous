"""Tests for fabric_io_place: stamps BPin geometry from connected ITerms."""

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
    fn = fabric_io_place.io_place
    actual = fn.callback if hasattr(fn, "callback") else fn
    actual(input_db="x.odb", input_lefs=[], config_path=None, reader=reader)


def _make_iterm(inst_x: int, inst_y: int, geoms: list[MockGeom]) -> MockITerm:
    master = MockMaster(100, 100)
    bbox = MockRect(0, 0, 0, 0)
    mterm = MockMTerm(bbox, master, mpins=[MockMPin(geoms)])
    return MockITerm(bbox, mterm, inst=MockInst(inst_x, inst_y))


@pytest.mark.usefixtures("_io_place_setup")
def test_stamps_bpin_geometry_from_iterm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BPin gets one box per mPin geometry, shifted by the instance location."""
    geom = MockGeom("Metal2", 10, 20, 30, 40)
    iterm = _make_iterm(1000, 2000, [geom])
    net = MockNetIoPlace("sig", [iterm])
    bterm = MockBTermIoPlace("sig", net)

    block = MockBlockIoPlace(MockDie(0, 0, 1000, 1000), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    pins = bterm.getBPins()
    assert len(pins) == 1
    pin = pins[0]
    assert pin.status == "FIRM"
    assert pin.bterm_name == "sig"


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
    geom = MockGeom("Metal2", 0, 0, 10, 10)
    iterm = _make_iterm(0, 0, [geom])
    net = MockNetIoPlace("sig", [iterm])
    bterm = MockBTermIoPlace("sig", net)
    pre_existing = MockBPinIoPlace(bterm.getName())
    bterm._add_bpin(pre_existing)  # noqa: SLF001

    block = MockBlockIoPlace(MockDie(0, 0, 100, 100), [bterm])
    reader = MockReaderIoPlace(100.0, MockTechIoPlace(None, None), block)

    _call_io_place(reader, monkeypatch)

    # Still exactly one BPin, no new one was created.
    assert bterm.getBPins() == [pre_existing]
