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


class MockNet:
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


class MockSWire:
    """Mock ODB special wire object."""

    @classmethod
    def create(cls, _net: MockNet, _mode: str) -> "MockSWire":  # noqa: D401
        return cls()


class MockBPinPower:
    """Mock ODB boundary pin for power tests."""

    def __init__(self, rec: Recorder) -> None:
        self._rec = rec

    def setPlacementStatus(self, status: str) -> None:  # noqa: N802
        self._rec.placement_status.append(status)


class MockBTerm:
    """Mock ODB boundary term object."""

    def __init__(self, name: str | None = None) -> None:
        self._name = name

    @classmethod
    def create(cls, _net: MockNet, name: str) -> "MockBTerm":  # noqa: D401
        return cls(name)

    def getName(self) -> str | None:  # noqa: D401
        return self._name

    def setIoType(self, _io: str) -> None: ...  # noqa: D401
    def setSigType(self, _sig: str | None) -> None: ...  # noqa: D401
    def setSpecial(self) -> None: ...  # noqa: D401


class MockBPin:
    """Mock ODB boundary pin object."""

    def __init__(self, bterm: MockBTerm) -> None:
        self._bterm = bterm
        self._status: str | None = None

    def setPlacementStatus(self, status: str) -> None:  # noqa: N802
        self._status = status


class MockTech:
    """Mock ODB technology object."""

    def findLayer(self, _name: str) -> object:  # noqa: D401
        return object()


class MockDb:
    """Mock ODB database object."""

    def __init__(self, tech: MockTech) -> None:
        self._tech = tech

    def getTech(self) -> MockTech:  # noqa: D401
        return self._tech


class MockBlock:
    """Mock ODB block object."""

    def __init__(self) -> None:
        self._nets: dict[str, MockNet] = {}

    def findNet(self, name: str) -> MockNet | None:  # noqa: D401
        return self._nets.get(name)

    def addNet(self, net: MockNet) -> None:
        self._nets[net.getName()] = net

    def getInsts(self) -> list:  # noqa: D401
        return []


class MockReader:
    """Mock ODB reader object."""

    def __init__(self) -> None:
        self.block = MockBlock()
        self.db = MockDb(MockTech())


def make_mock_odb(rec: Recorder) -> SimpleNamespace:
    """Create a fake ODB module with recording capabilities."""

    def dbNet_create(block: MockBlock, name: str) -> MockNet:
        net = MockNet(name)
        block.addNet(net)
        rec.created_nets.append(name)
        return net

    def dbBTerm_create(_net: MockNet, name: str) -> MockBTerm:
        rec.created_bterms.append(name)
        return MockBTerm.create(_net, name)

    def dbBPin_create(_bterm: MockBTerm) -> MockBPinPower:
        return MockBPinPower(rec)

    # SBox and Box creation not exercised in this test (no insts present)
    def noop(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
        return None

    return SimpleNamespace(
        dbNet=SimpleNamespace(create=dbNet_create),
        dbSWire=MockSWire,
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
def mock_odb_power(recorder: Recorder) -> SimpleNamespace:
    """Provide a fake ODB module for power tests."""
    return make_mock_odb(recorder)


@pytest.fixture
def mock_reader() -> MockReader:
    """Provide a fake ODB reader."""
    return MockReader()


# ============================================================================
# ODB Power Geometry Test Mocks (for test_odb_power.py)
# ============================================================================


class GeometryRecorder:
    """Records ODB box creation with actual coordinates for validation."""

    def __init__(self) -> None:
        self.sboxes: list[tuple[str, int, int, int, int]] = []  # net, x1, y1, x2, y2
        self.bboxes: list[tuple[str, int, int, int, int]] = []  # bterm, x1, y1, x2, y2


class MockGeometry:
    """Mock geometry box with actual dimensions."""

    def __init__(self, xmin: int, ymin: int, xmax: int, ymax: int) -> None:
        self._xmin = xmin
        self._ymin = ymin
        self._xmax = xmax
        self._ymax = ymax

    def xMin(self) -> int:  # noqa: N802
        return self._xmin

    def yMin(self) -> int:  # noqa: N802
        return self._ymin

    def xMax(self) -> int:  # noqa: N802
        return self._xmax

    def yMax(self) -> int:  # noqa: N802
        return self._ymax


class MockMPin:
    """Mock master pin with geometry."""

    def __init__(self, geometries: list[MockGeometry]) -> None:
        self._geometries = geometries

    def getGeometry(self) -> list[MockGeometry]:  # noqa: D401
        return self._geometries


class MockMTermPower:
    """Mock master terminal with pins for power tests."""

    def __init__(self, name: str, mpins: list[MockMPin]) -> None:
        self._name = name
        self._mpins = mpins

    def getName(self) -> str:  # noqa: D401
        return self._name

    def getMPins(self) -> list[MockMPin]:  # noqa: D401
        return self._mpins


class MockMasterPower:
    """Mock master cell with power terminals."""

    def __init__(self, mterms: list[MockMTermPower]) -> None:
        self._mterms = mterms

    def getMTerms(self) -> list[MockMTermPower]:  # noqa: D401
        return self._mterms


class MockITermPower:
    """Mock instance terminal for power tests."""

    def __init__(self, mterm: MockMTermPower) -> None:
        self._mterm = mterm
        self._net: object | None = None

    def getMTerm(self) -> MockMTermPower:  # noqa: D401
        return self._mterm

    def connect(self, net: object) -> None:
        self._net = net


class MockInst:
    """Mock instance with location and terminals."""

    def __init__(
        self, name: str, location: tuple[int, int], master: MockMasterPower
    ) -> None:
        self._name = name
        self._location = location
        self._master = master
        # Create iterms based on master mterms
        self._iterms = [MockITermPower(mterm) for mterm in master.getMTerms()]

    def getName(self) -> str:  # noqa: D401
        return self._name

    def getLocation(self) -> tuple[int, int]:  # noqa: D401
        return self._location

    def getMaster(self) -> MockMasterPower:  # noqa: D401
        return self._master

    def getITerms(self) -> list[MockITermPower]:  # noqa: D401
        return self._iterms


class MockBlockPower:
    """Mock ODB block for power geometry tests."""

    def __init__(self, instances: list[MockInst]) -> None:
        self._nets: dict[str, MockNet] = {}
        self._instances = instances

    def findNet(self, name: str) -> MockNet | None:  # noqa: D401
        return self._nets.get(name)

    def getInsts(self) -> list[MockInst]:  # noqa: D401
        return self._instances

    def addNet(self, net: MockNet) -> None:
        self._nets[net.getName()] = net


class MockReaderPower:
    """Mock ODB reader for power geometry tests."""

    def __init__(self, instances: list[MockInst]) -> None:
        self.block = MockBlockPower(instances)
        self.db = MockDb(MockTech())


def make_mock_odb_power(recorder: GeometryRecorder) -> SimpleNamespace:
    """Create a fake ODB module with geometry recording capabilities for power tests."""

    def dbNet_create(block: MockBlockPower, name: str) -> MockNet:
        net = MockNet(name)
        block.addNet(net)
        return net

    def dbBTerm_create(_net: MockNet, name: str) -> MockBTerm:
        return MockBTerm.create(_net, name)

    def dbBPin_create(bterm: MockBTerm) -> MockBPin:
        return MockBPin(bterm)

    def dbSWire_create(net: MockNet, mode: str) -> SimpleNamespace:
        return SimpleNamespace(net=net, mode=mode)

    def dbSBox_create(
        wire: SimpleNamespace,
        _layer: object,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        _stripe: str,
    ) -> None:
        recorder.sboxes.append((wire.net.getName(), x1, y1, x2, y2))

    def dbBox_create(
        bpin: MockBPin, _layer: object, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        bterm_name = bpin._bterm.getName() if bpin._bterm else "unknown"
        recorder.bboxes.append((bterm_name, x1, y1, x2, y2))

    return SimpleNamespace(
        dbNet=SimpleNamespace(create=dbNet_create),
        dbSWire=SimpleNamespace(create=dbSWire_create),
        dbBTerm=SimpleNamespace(create=dbBTerm_create),
        dbBPin_create=dbBPin_create,
        dbSBox_create=dbSBox_create,
        dbBox_create=dbBox_create,
    )


@pytest.fixture
def geometry_recorder() -> GeometryRecorder:
    """Provide a geometry recorder for power tests."""
    return GeometryRecorder()


@pytest.fixture
def mock_odb_power_geom(geometry_recorder: GeometryRecorder) -> SimpleNamespace:
    """Provide a fake ODB module for power geometry tests."""
    return make_mock_odb_power(geometry_recorder)


def run_power_function(
    recorder: GeometryRecorder, reader: MockReaderPower, metal_layer: str = "metal1"
) -> None:
    """Execute the power connection logic (extracted from odb_power.py).
    
    This helper function mimics the logic from odb_power.py power() function
    and is used by tests to validate geometry transformations.
    """
    # Import odb from sys.modules (where it's been monkeypatched)
    import sys

    odb = sys.modules["odb"]

    tech = reader.db.getTech()
    metal_layer_obj = tech.findLayer(metal_layer)

    # Create nets
    for net_name, net_type in [("VPWR", "POWER"), ("VGND", "GROUND")]:
        net = reader.block.findNet(net_name)
        if net is None:
            net = odb.dbNet.create(reader.block, net_name)
            net.setSpecial()
            net.setSigType(net_type)

    vpwr_net = reader.block.findNet("VPWR")
    vgnd_net = reader.block.findNet("VGND")

    # Create wires
    vpwr_wire = odb.dbSWire.create(vpwr_net, "ROUTED")
    vgnd_wire = odb.dbSWire.create(vgnd_net, "ROUTED")

    # Create bterms
    vpwr_bterm = odb.dbBTerm.create(vpwr_net, "VPWR")
    vpwr_bterm.setIoType("INOUT")
    vpwr_bterm.setSigType(vpwr_net.getSigType())
    vpwr_bterm.setSpecial()
    vpwr_bpin = odb.dbBPin_create(vpwr_bterm)

    vgnd_bterm = odb.dbBTerm.create(vgnd_net, "VGND")
    vgnd_bterm.setIoType("INOUT")
    vgnd_bterm.setSigType(vgnd_net.getSigType())
    vgnd_bterm.setSpecial()
    vgnd_bpin = odb.dbBPin_create(vgnd_bterm)

    # Process instances
    for blk_inst in reader.block.getInsts():
        for iterm in blk_inst.getITerms():
            iterm_name = iterm.getMTerm().getName()

            if iterm_name == "VPWR":
                iterm.connect(vpwr_net)
            if iterm_name == "VGND":
                iterm.connect(vgnd_net)

        inst_master = blk_inst.getMaster()

        # Process power/ground mterms
        for master_mterm in inst_master.getMTerms():
            if master_mterm.getName() in ("VPWR", "VGND"):
                for mterm_mpins in master_mterm.getMPins():
                    for mpins_dbox in mterm_mpins.getGeometry():
                        inst_loc = blk_inst.getLocation()
                        if master_mterm.getName() == "VPWR":
                            odb.dbSBox_create(
                                vpwr_wire,
                                metal_layer_obj,
                                inst_loc[0] + mpins_dbox.xMin(),
                                inst_loc[1] + mpins_dbox.yMin(),
                                inst_loc[0] + mpins_dbox.xMax(),
                                inst_loc[1] + mpins_dbox.yMax(),
                                "STRIPE",
                            )
                            odb.dbBox_create(
                                vpwr_bpin,
                                metal_layer_obj,
                                inst_loc[0] + mpins_dbox.xMin(),
                                inst_loc[1] + mpins_dbox.yMin(),
                                inst_loc[0] + mpins_dbox.xMax(),
                                inst_loc[1] + mpins_dbox.yMax(),
                            )
                        if master_mterm.getName() == "VGND":
                            odb.dbSBox_create(
                                vgnd_wire,
                                metal_layer_obj,
                                inst_loc[0] + mpins_dbox.xMin(),
                                inst_loc[1] + mpins_dbox.yMin(),
                                inst_loc[0] + mpins_dbox.xMax(),
                                inst_loc[1] + mpins_dbox.yMax(),
                                "STRIPE",
                            )
                            odb.dbBox_create(
                                vgnd_bpin,
                                metal_layer_obj,
                                inst_loc[0] + mpins_dbox.xMin(),
                                inst_loc[1] + mpins_dbox.yMin(),
                                inst_loc[0] + mpins_dbox.xMax(),
                                inst_loc[1] + mpins_dbox.yMax(),
                            )

    vpwr_bpin.setPlacementStatus("FIRM")
    vgnd_bpin.setPlacementStatus("FIRM")


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


class MockMTerm:
    """Mock ODB master terminal object."""

    def __init__(self, bbox: MockRect, master: MockMaster) -> None:
        self._bbox = bbox
        self._master = master

    def getBBox(self) -> MockRect:  # noqa: D401
        return self._bbox

    def getMaster(self) -> MockMaster:  # noqa: D401
        return self._master


class MockITerm:
    """Mock ODB instance terminal object."""

    def __init__(self, bbox: MockRect, mterm: MockMTerm) -> None:
        self._bbox = bbox
        self._mterm = mterm

    def getBBox(self) -> MockRect:  # noqa: D401
        return self._bbox

    def getMTerm(self) -> MockMTerm:  # noqa: D401
        return self._mterm


class MockNetIoPlace:
    """Mock ODB net object for IO place tests."""

    def __init__(self, name: str, iterms: list[MockITerm]) -> None:
        self._name = name
        self._iterms = iterms

    def getName(self) -> str:  # noqa: D401
        return self._name

    def getITerms(self) -> list[MockITerm]:  # noqa: D401
        return self._iterms


class MockBTermIoPlace:
    """Mock ODB boundary term for IO place tests."""

    def __init__(self, name: str, net: MockNetIoPlace) -> None:
        self._name = name
        self._net = net
        self._bpins: list[MockBPinIoPlace] = []

    def getName(self) -> str:  # noqa: D401
        return self._name

    def getSigType(self) -> str:  # noqa: D401
        return "SIGNAL"

    def getBPins(self) -> list[MockBPinIoPlace]:  # noqa: D401
        return self._bpins

    def getNet(self) -> MockNetIoPlace:  # noqa: D401
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
def box_recorder() -> BoxRecorder:
    """Provide a box creation recorder."""
    return BoxRecorder()


@pytest.fixture
def mock_odb_io_place(
    box_recorder: BoxRecorder, pin_placement_recorder: PinPlacementRecorder
) -> SimpleNamespace:
    """Provide a fake ODB module for IO place tests.

    This fixture creates a fake ODB that records both box creation
    and pin placements for test verification.
    """

    def dbBPin_create(bterm: MockBTermIoPlace) -> MockBPinIoPlace:
        bpin = MockBPinIoPlace(bterm.getName())
        bterm._add_bpin(bpin)  # noqa: SLF001
        return bpin

    def dbBox_create(
        bpin: MockBPinIoPlace, layer: MockLayer, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        # Record for box_recorder (infrastructure tests)
        box_recorder(bpin, layer, x1, y1, x2, y2)
        # Record for pin_placement_recorder (behavior tests)
        if isinstance(bpin, MockBPinIoPlace) and bpin.bterm_name:
            layer_name = layer.getName()
            pin_placement_recorder.placements.append(
                (bpin.bterm_name, layer_name, x1, y1, x2, y2)
            )

    return SimpleNamespace(
        Rect=MockRect,
        dbBPin_create=dbBPin_create,
        dbBox_create=dbBox_create,
    )
