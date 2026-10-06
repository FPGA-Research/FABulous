"""Shared fixtures and mock objects for GDS flow tests."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Mock external dependencies BEFORE any test imports
sys.modules["odb"] = MagicMock()
sys.modules["openroad"] = MagicMock()
sys.modules["utl"] = MagicMock()


# ============================================================================
# Fabric IO Place Test Mocks
# ============================================================================


class MockRect:
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


class PinPlacementRecorder:
    """Records pin placement boxes with coordinates and layers."""

    def __init__(self) -> None:
        self.placements: list[tuple[str, str, int, int, int, int]] = []


class MockBPinIoPlace:
    """Mock ODB boundary pin for IO place tests."""

    def __init__(self, bterm_name: str | None = None) -> None:
        self.status: str | None = None
        self.bterm_name = bterm_name

    def setPlacementStatus(self, status: str) -> None:  # noqa: N802
        self.status = status


class MockLayer:
    """Mock ODB layer object."""

    def __init__(
        self,
        width: int = 100,
        area: int = 10000,
        spacing: int = 0,
        name: str = "UNKNOWN",
    ) -> None:
        self._width = width
        self._area = area
        self._spacing = spacing
        self._layer_name = name

    def getWidth(self) -> int:  # noqa: D401
        return self._width

    def getArea(self) -> int:  # noqa: D401
        return self._area

    def getSpacing(self) -> int:  # noqa: D401
        return self._spacing

    def getName(self) -> str:  # noqa: D401
        return self._layer_name


class MockDie:
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


class MockMaster:
    """Mock ODB master cell object."""

    def __init__(self, w: int, h: int) -> None:
        self._w = w
        self._h = h

    def getWidth(self) -> int:  # noqa: D401
        return self._w

    def getHeight(self) -> int:  # noqa: D401
        return self._h


class MockGeom:
    """Mock ODB geometry box (mPin shape)."""

    def __init__(self, layer: object, x1: int, y1: int, x2: int, y2: int) -> None:
        self._layer, self._x1, self._y1, self._x2, self._y2 = layer, x1, y1, x2, y2

    def getTechLayer(self) -> object:  # noqa: D401, N802
        return self._layer

    def xMin(self) -> int:  # noqa: D401, N802
        return self._x1

    def yMin(self) -> int:  # noqa: D401, N802
        return self._y1

    def xMax(self) -> int:  # noqa: D401, N802
        return self._x2

    def yMax(self) -> int:  # noqa: D401, N802
        return self._y2


class MockMPin:
    """Mock ODB master pin (geometry container)."""

    def __init__(self, geometry: list[MockGeom]) -> None:
        self._g = geometry

    def getGeometry(self) -> list[MockGeom]:  # noqa: D401, N802
        return self._g


class MockInst:
    """Mock ODB instance with a placement location."""

    def __init__(self, x: int = 0, y: int = 0) -> None:
        self._x, self._y = x, y

    def getLocation(self) -> tuple[int, int]:  # noqa: D401, N802
        return (self._x, self._y)


class MockMTerm:
    """Mock ODB master terminal object."""

    def __init__(
        self,
        bbox: MockRect,
        master: MockMaster,
        mpins: list[MockMPin] | None = None,
    ) -> None:
        self._bbox = bbox
        self._master = master
        self._mpins = mpins or []

    def getBBox(self) -> MockRect:  # noqa: D401
        return self._bbox

    def getMaster(self) -> MockMaster:  # noqa: D401
        return self._master

    def getMPins(self) -> list[MockMPin]:  # noqa: D401, N802
        return self._mpins


class MockITerm:
    """Mock ODB instance terminal object."""

    def __init__(
        self,
        bbox: MockRect,
        mterm: MockMTerm,
        inst: MockInst | None = None,
    ) -> None:
        self._bbox = bbox
        self._mterm = mterm
        self._inst = inst or MockInst(0, 0)

    def getBBox(self) -> MockRect:  # noqa: D401
        return self._bbox

    def getMTerm(self) -> MockMTerm:  # noqa: D401
        return self._mterm

    def getInst(self) -> MockInst:  # noqa: D401, N802
        return self._inst


class MockNetIoPlace:
    """Mock ODB net object for IO place tests."""

    def __init__(self, name: str, iterms: list[MockITerm]) -> None:
        self._name = name
        self._iterms = iterms
        self._bterms: list[MockBTermIoPlace] = []

    def getName(self) -> str:  # noqa: D401
        return self._name

    def getITerms(self) -> list[MockITerm]:  # noqa: D401
        return self._iterms

    def getBTerms(self) -> list["MockBTermIoPlace"]:  # noqa: D401, N802
        return self._bterms


class MockBTermIoPlace:
    """Mock ODB boundary term for IO place tests."""

    def __init__(
        self,
        name: str,
        net: MockNetIoPlace | None,
        sig_type: str = "SIGNAL",
    ) -> None:
        self._name = name
        self._net = net
        self._sig_type = sig_type
        self._bpins: list[MockBPinIoPlace] = []

    def getName(self) -> str:  # noqa: D401
        return self._name

    def getSigType(self) -> str:  # noqa: D401
        return self._sig_type

    def getBPins(self) -> list[MockBPinIoPlace]:  # noqa: D401
        return list(self._bpins)

    def getNet(self) -> MockNetIoPlace | None:  # noqa: D401
        return self._net

    def _add_bpin(self, bpin: MockBPinIoPlace) -> None:
        self._bpins.append(bpin)


class MockTechIoPlace:
    """Mock ODB technology for IO place tests."""

    def __init__(self, h_layer: MockLayer, v_layer: MockLayer) -> None:
        self._hl = h_layer
        self._vl = v_layer

    def findLayer(self, name: str) -> MockLayer:  # noqa: D401
        return self._hl if name == "H" else self._vl


class MockBlockIoPlace:
    """Mock ODB block for IO place tests."""

    def __init__(self, die: MockDie, bterms: list[MockBTermIoPlace]) -> None:
        self._die = die
        self._bterms = bterms

    def getDieArea(self) -> MockDie:  # noqa: D401
        return self._die

    def getBTerms(self) -> list[MockBTermIoPlace]:  # noqa: D401
        return self._bterms


class MockReaderIoPlace:
    """Mock ODB reader for IO place tests."""

    def __init__(
        self, dbunits: float, tech: MockTechIoPlace, block: MockBlockIoPlace
    ) -> None:
        self.dbunits = dbunits
        self.tech = tech
        self.block = block


@pytest.fixture
def pin_placement_recorder() -> PinPlacementRecorder:
    """Provide a pin placement recorder."""
    return PinPlacementRecorder()


@pytest.fixture
def mock_odb_io_place(pin_placement_recorder: PinPlacementRecorder) -> SimpleNamespace:
    """Provide a fake ODB module that records every pin box it is asked to create."""

    def dbBPin_create(bterm: MockBTermIoPlace) -> MockBPinIoPlace:
        bpin = MockBPinIoPlace(bterm.getName())
        bterm._add_bpin(bpin)  # noqa: SLF001
        return bpin

    def dbBox_create(
        bpin: MockBPinIoPlace,
        layer: object,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> None:
        layer_name = layer.getName() if hasattr(layer, "getName") else str(layer)
        if isinstance(bpin, MockBPinIoPlace) and bpin.bterm_name:
            pin_placement_recorder.placements.append(
                (bpin.bterm_name, layer_name, x1, y1, x2, y2)
            )

    destroyed_bterms: list[MockBTermIoPlace] = []
    destroyed_nets: list[MockNetIoPlace] = []

    class _DbBTerm:
        @staticmethod
        def destroy(b: MockBTermIoPlace) -> None:
            destroyed_bterms.append(b)

    class _DbNet:
        @staticmethod
        def destroy(n: MockNetIoPlace) -> None:
            destroyed_nets.append(n)

    return SimpleNamespace(
        Rect=MockRect,
        dbBPin_create=dbBPin_create,
        dbBox_create=dbBox_create,
        dbBTerm=_DbBTerm,
        dbNet=_DbNet,
        destroyed_bterms=destroyed_bterms,
        destroyed_nets=destroyed_nets,
    )
