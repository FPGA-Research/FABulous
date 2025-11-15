"""Shared fixtures and mock objects for GDS flow tests."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Mock external dependencies BEFORE any test imports
sys.modules["odb"] = MagicMock()
sys.modules["openroad"] = MagicMock()


# ============================================================================
# ODB Power Test Mocks
# ============================================================================


class Recorder:
    """Records ODB operations for assertion in tests."""

    def __init__(self) -> None:
        self.created_nets: list[str] = []
        self.created_bterms: list[str] = []
        self.placement_status: list[str] = []


class FakeNet:
    """Mock ODB net object."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._sig: str | None = None
        self._special = False

    def getName(self) -> str:  # noqa: D401
        return self._name

    def setSpecial(self) -> None:  # noqa: D401
        self._special = True

    def setSigType(self, sig: str) -> None:  # noqa: D401
        self._sig = sig

    def getSigType(self) -> str | None:  # noqa: D401
        return self._sig


class FakeSWire:
    """Mock ODB special wire object."""

    @classmethod
    def create(cls, _net: FakeNet, _mode: str) -> "FakeSWire":  # noqa: D401
        return cls()


class FakeBPinPower:
    """Mock ODB boundary pin for power tests."""

    def __init__(self, rec: Recorder) -> None:
        self._rec = rec

    def setPlacementStatus(self, status: str) -> None:  # noqa: N802
        self._rec.placement_status.append(status)


class FakeBTerm:
    """Mock ODB boundary term object."""

    def __init__(self, name: str | None = None) -> None:
        self._name = name

    @classmethod
    def create(cls, _net: FakeNet, name: str) -> "FakeBTerm":  # noqa: D401
        return cls(name)

    def setIoType(self, _io: str) -> None: ...  # noqa: D401
    def setSigType(self, _sig: str | None) -> None: ...  # noqa: D401
    def setSpecial(self) -> None: ...  # noqa: D401


class FakeTech:
    """Mock ODB technology object."""

    def findLayer(self, _name: str) -> object:  # noqa: D401
        return object()


class FakeDb:
    """Mock ODB database object."""

    def __init__(self, tech: FakeTech) -> None:
        self._tech = tech

    def getTech(self) -> FakeTech:  # noqa: D401
        return self._tech


class FakeBlock:
    """Mock ODB block object."""

    def __init__(self) -> None:
        self._nets: dict[str, FakeNet] = {}

    def findNet(self, name: str) -> FakeNet | None:  # noqa: D401
        return self._nets.get(name)

    def addNet(self, net: FakeNet) -> None:
        self._nets[net.getName()] = net

    def getInsts(self) -> list:  # noqa: D401
        return []


class FakeReader:
    """Mock ODB reader object."""

    def __init__(self) -> None:
        self.block = FakeBlock()
        self.db = FakeDb(FakeTech())


def make_fake_odb(rec: Recorder) -> SimpleNamespace:
    """Create a fake ODB module with recording capabilities."""

    def dbNet_create(block: FakeBlock, name: str) -> FakeNet:
        net = FakeNet(name)
        block.addNet(net)
        rec.created_nets.append(name)
        return net

    def dbBTerm_create(_net: FakeNet, name: str) -> FakeBTerm:
        rec.created_bterms.append(name)
        return FakeBTerm.create(_net, name)

    def dbBPin_create(_bterm: FakeBTerm) -> FakeBPinPower:
        return FakeBPinPower(rec)

    # SBox and Box creation not exercised in this test (no insts present)
    def noop(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
        return None

    return SimpleNamespace(
        dbNet=SimpleNamespace(create=dbNet_create),
        dbSWire=FakeSWire,
        dbBTerm=SimpleNamespace(create=dbBTerm_create),
        dbBPin_create=dbBPin_create,
        dbSBox_create=noop,
        dbBox_create=noop,
    )


@pytest.fixture
def recorder() -> Recorder:
    """Provide a recorder for ODB operations."""
    return Recorder()


@pytest.fixture
def fake_odb_power(recorder: Recorder) -> SimpleNamespace:
    """Provide a fake ODB module for power tests."""
    return make_fake_odb(recorder)


@pytest.fixture
def fake_reader() -> FakeReader:
    """Provide a fake ODB reader."""
    return FakeReader()


# ============================================================================
# Fabric IO Place Test Mocks
# ============================================================================


class BoxRecorder:
    """Records ODB box creation calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, object, int, int, int, int]] = []

    def __call__(
        self, bpin: object, layer: object, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        self.calls.append((bpin, layer, x1, y1, x2, y2))


class FakeRect:
    """Mock ODB rectangle object."""

    def __init__(self, _x0: int, _y0: int, w: int, h: int) -> None:
        self._w = w
        self._h = h
        self._x = _x0
        self._y = _y0

    def moveTo(self, x: int, y: int) -> None:  # noqa: N802 (ODB-like API)
        self._x = x
        self._y = y

    def ll(self) -> tuple[int, int]:  # noqa: D401
        return (self._x, self._y)

    def ur(self) -> tuple[int, int]:  # noqa: D401
        return (self._x + self._w, self._y + self._h)

    def xMin(self) -> int:  # noqa: D401
        return self._x

    def yMin(self) -> int:  # noqa: D401
        return self._y

    def xMax(self) -> int:  # noqa: D401
        return self._x + self._w

    def yMax(self) -> int:  # noqa: D401
        return self._y + self._h

    def xCenter(self) -> int:  # noqa: D401
        return self._x + self._w // 2

    def yCenter(self) -> int:  # noqa: D401
        return self._y + self._h // 2


class FakeBPinIoPlace:
    """Mock ODB boundary pin for IO place tests."""

    def __init__(self) -> None:
        self.status: str | None = None

    def setPlacementStatus(self, status: str) -> None:  # noqa: N802
        self.status = status


class FakeLayer:
    """Mock ODB layer object."""

    def __init__(self, width: int = 100, area: int = 10000, spacing: int = 0) -> None:
        self._width = width
        self._area = area
        self._spacing = spacing

    def getWidth(self) -> int:  # noqa: D401
        return self._width

    def getArea(self) -> int:  # noqa: D401
        return self._area

    def getSpacing(self) -> int:  # noqa: D401
        return self._spacing


class FakeDie:
    """Mock ODB die area object."""

    def __init__(self, llx: int, lly: int, urx: int, ury: int) -> None:
        self._llx, self._lly, self._urx, self._ury = llx, lly, urx, ury

    def xMin(self) -> int:  # noqa: D401
        return self._llx

    def yMin(self) -> int:  # noqa: D401
        return self._lly

    def xMax(self) -> int:  # noqa: D401
        return self._urx

    def yMax(self) -> int:  # noqa: D401
        return self._ury


class FakeMaster:
    """Mock ODB master cell object."""

    def __init__(self, w: int, h: int) -> None:
        self._w = w
        self._h = h

    def getWidth(self) -> int:  # noqa: D401
        return self._w

    def getHeight(self) -> int:  # noqa: D401
        return self._h


class FakeMTerm:
    """Mock ODB master terminal object."""

    def __init__(self, bbox: FakeRect, master: FakeMaster) -> None:
        self._bbox = bbox
        self._master = master

    def getBBox(self) -> FakeRect:  # noqa: D401
        return self._bbox

    def getMaster(self) -> FakeMaster:  # noqa: D401
        return self._master


class FakeITerm:
    """Mock ODB instance terminal object."""

    def __init__(self, bbox: FakeRect, mterm: FakeMTerm) -> None:
        self._bbox = bbox
        self._mterm = mterm

    def getBBox(self) -> FakeRect:  # noqa: D401
        return self._bbox

    def getMTerm(self) -> FakeMTerm:  # noqa: D401
        return self._mterm


class FakeNetIoPlace:
    """Mock ODB net object for IO place tests."""

    def __init__(self, name: str, iterms: list[FakeITerm]) -> None:
        self._name = name
        self._iterms = iterms

    def getName(self) -> str:  # noqa: D401
        return self._name

    def getITerms(self) -> list[FakeITerm]:  # noqa: D401
        return self._iterms


class FakeBTermIoPlace:
    """Mock ODB boundary term for IO place tests."""

    def __init__(self, name: str, net: FakeNetIoPlace) -> None:
        self._name = name
        self._net = net
        self._bpins: list[FakeBPinIoPlace] = []

    def getName(self) -> str:  # noqa: D401
        return self._name

    def getSigType(self) -> str:  # noqa: D401
        return "SIGNAL"

    def getBPins(self) -> list[FakeBPinIoPlace]:  # noqa: D401
        return self._bpins

    def getNet(self) -> FakeNetIoPlace:  # noqa: D401
        return self._net


class FakeTechIoPlace:
    """Mock ODB technology for IO place tests."""

    def __init__(self, h_layer: FakeLayer, v_layer: FakeLayer) -> None:
        self._hl = h_layer
        self._vl = v_layer

    def findLayer(self, name: str) -> FakeLayer:  # noqa: D401
        return self._hl if name == "H" else self._vl


class FakeBlockIoPlace:
    """Mock ODB block for IO place tests."""

    def __init__(self, die: FakeDie, bterms: list[FakeBTermIoPlace]) -> None:
        self._die = die
        self._bterms = bterms

    def getDieArea(self) -> FakeDie:  # noqa: D401
        return self._die

    def getBTerms(self) -> list[FakeBTermIoPlace]:  # noqa: D401
        return self._bterms


class FakeReaderIoPlace:
    """Mock ODB reader for IO place tests."""

    def __init__(
        self, dbunits: float, tech: FakeTechIoPlace, block: FakeBlockIoPlace
    ) -> None:
        self.dbunits = dbunits
        self.tech = tech
        self.block = block


@pytest.fixture
def box_recorder() -> BoxRecorder:
    """Provide a box creation recorder."""
    return BoxRecorder()


@pytest.fixture
def fake_odb_io_place(box_recorder: BoxRecorder) -> SimpleNamespace:
    """Provide a fake ODB module for IO place tests."""

    def dbBPin_create(_bterm: object) -> FakeBPinIoPlace:
        return FakeBPinIoPlace()

    return SimpleNamespace(
        Rect=FakeRect,
        dbBPin_create=dbBPin_create,
        dbBox_create=box_recorder,
    )
