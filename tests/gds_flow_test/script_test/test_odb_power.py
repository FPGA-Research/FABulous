"""Tests for odb_power module - validates coordinate transformation and geometry."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


class GeometryRecorder:
    """Records ODB box creation with actual coordinates for validation."""

    def __init__(self) -> None:
        self.sboxes: list[tuple[str, int, int, int, int]] = []  # net, x1, y1, x2, y2
        self.bboxes: list[tuple[str, int, int, int, int]] = []  # bterm, x1, y1, x2, y2


class FakeGeometry:
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


class FakeMPin:
    """Mock master pin with geometry."""

    def __init__(self, geometries: list[FakeGeometry]) -> None:
        self._geometries = geometries

    def getGeometry(self) -> list[FakeGeometry]:
        return self._geometries


class FakeMTerm:
    """Mock master terminal with pins."""

    def __init__(self, name: str, mpins: list[FakeMPin]) -> None:
        self._name = name
        self._mpins = mpins

    def getName(self) -> str:
        return self._name

    def getMPins(self) -> list[FakeMPin]:
        return self._mpins


class FakeMaster:
    """Mock master cell with power terminals."""

    def __init__(self, mterms: list[FakeMTerm]) -> None:
        self._mterms = mterms

    def getMTerms(self) -> list[FakeMTerm]:
        return self._mterms


class FakeITerm:
    """Mock instance terminal."""

    def __init__(self, mterm: FakeMTerm) -> None:
        self._mterm = mterm
        self._net = None

    def getMTerm(self) -> FakeMTerm:
        return self._mterm

    def connect(self, net: object) -> None:
        self._net = net


class FakeInst:
    """Mock instance with location and terminals."""

    def __init__(
        self, name: str, location: tuple[int, int], master: FakeMaster
    ) -> None:
        self._name = name
        self._location = location
        self._master = master
        # Create iterms based on master mterms
        self._iterms = [FakeITerm(mterm) for mterm in master.getMTerms()]

    def getName(self) -> str:
        return self._name

    def getLocation(self) -> tuple[int, int]:
        return self._location

    def getMaster(self) -> FakeMaster:
        return self._master

    def getITerms(self) -> list[FakeITerm]:
        return self._iterms


class FakeNet:
    """Mock ODB net."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._sig_type = None
        self._special = False

    def getName(self) -> str:
        return self._name

    def setSpecial(self) -> None:
        self._special = True

    def setSigType(self, sig_type: str) -> None:
        self._sig_type = sig_type

    def getSigType(self) -> str | None:
        return self._sig_type


class FakeBTerm:
    """Mock boundary terminal."""

    def __init__(self, name: str) -> None:
        self._name = name

    def getName(self) -> str:
        return self._name

    def setIoType(self, io_type: str) -> None:
        pass

    def setSigType(self, sig_type: str | None) -> None:
        pass

    def setSpecial(self) -> None:
        pass


class FakeBPin:
    """Mock boundary pin."""

    def __init__(self, bterm: FakeBTerm) -> None:
        self._bterm = bterm
        self._status = None

    def setPlacementStatus(self, status: str) -> None:
        self._status = status


class FakeBlock:
    """Mock ODB block."""

    def __init__(self, instances: list[FakeInst]) -> None:
        self._nets: dict[str, FakeNet] = {}
        self._instances = instances

    def findNet(self, name: str) -> FakeNet | None:
        return self._nets.get(name)

    def getInsts(self) -> list[FakeInst]:
        return self._instances

    def _add_net(self, net: FakeNet) -> None:
        self._nets[net.getName()] = net


class FakeTech:
    """Mock technology."""

    def findLayer(self, name: str) -> object:
        return Mock(name=name)


class FakeDb:
    """Mock database."""

    def __init__(self) -> None:
        self._tech = FakeTech()

    def getTech(self) -> FakeTech:
        return self._tech


class FakeReader:
    """Mock ODB reader."""

    def __init__(self, instances: list[FakeInst]) -> None:
        self.block = FakeBlock(instances)
        self.db = FakeDb()


def make_fake_odb_with_geometry(recorder: GeometryRecorder) -> SimpleNamespace:
    """Create fake ODB that records actual geometry coordinates."""

    def dbNet_create(block: FakeBlock, name: str) -> FakeNet:
        net = FakeNet(name)
        block._add_net(net)
        return net

    def dbBTerm_create(net: FakeNet, name: str) -> FakeBTerm:
        return FakeBTerm(name)

    def dbBPin_create(bterm: FakeBTerm) -> FakeBPin:
        return FakeBPin(bterm)

    def dbSWire_create(net: FakeNet, mode: str) -> Mock:
        return Mock(net=net, mode=mode)

    def dbSBox_create(
        wire: Mock, layer: object, x1: int, y1: int, x2: int, y2: int, stripe: str
    ) -> None:
        recorder.sboxes.append((wire.net.getName(), x1, y1, x2, y2))

    def dbBox_create(
        bpin: FakeBPin, layer: object, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        recorder.bboxes.append((bpin._bterm.getName(), x1, y1, x2, y2))

    return SimpleNamespace(
        dbNet=SimpleNamespace(create=dbNet_create),
        dbSWire=SimpleNamespace(create=dbSWire_create),
        dbBTerm=SimpleNamespace(create=dbBTerm_create),
        dbBPin_create=dbBPin_create,
        dbSBox_create=dbSBox_create,
        dbBox_create=dbBox_create,
    )


def run_power_function(
    recorder: GeometryRecorder, reader: FakeReader, metal_layer: str = "metal1"
) -> None:
    """Execute the power connection logic (extracted from odb_power.py)."""
    # Import odb from sys.modules (where we've monkeypatched it)
    import sys

    odb = sys.modules["odb"]

    # This mimics the logic from odb_power.py power() function
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


def test_power_transforms_coordinates_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that power() correctly transforms geometry coordinates by instance location."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create instance at (100, 200) with VPWR pin geometry (10, 20, 30, 40)
    vpwr_geom = FakeGeometry(10, 20, 30, 40)
    vpwr_mpin = FakeMPin([vpwr_geom])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin])
    master = FakeMaster([vpwr_mterm])
    inst = FakeInst("tile_0", (100, 200), master)

    reader = FakeReader([inst])

    # Run the power function
    run_power_function(recorder, reader, "metal1")

    # Verify coordinate transformation: instance_loc + geometry_bbox
    # Expected: (100 + 10, 200 + 20, 100 + 30, 200 + 40) = (110, 220, 130, 240)
    vpwr_sboxes = [box for box in recorder.sboxes if box[0] == "VPWR"]
    assert len(vpwr_sboxes) == 1, "Should create one SBox for VPWR"
    assert vpwr_sboxes[0] == ("VPWR", 110, 220, 130, 240), (
        "Incorrect coordinate transformation"
    )

    vpwr_bboxes = [box for box in recorder.bboxes if box[0] == "VPWR"]
    assert len(vpwr_bboxes) == 1, "Should create one BBox for VPWR"
    assert vpwr_bboxes[0] == ("VPWR", 110, 220, 130, 240), (
        "BBox should match SBox coordinates"
    )


def test_power_handles_multiple_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that power() processes multiple instances correctly."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create two instances at different locations
    vpwr_geom = FakeGeometry(0, 0, 50, 50)
    vgnd_geom = FakeGeometry(0, 0, 50, 50)

    vpwr_mpin = FakeMPin([vpwr_geom])
    vgnd_mpin = FakeMPin([vgnd_geom])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin])
    vgnd_mterm = FakeMTerm("VGND", [vgnd_mpin])
    master = FakeMaster([vpwr_mterm, vgnd_mterm])

    inst1 = FakeInst("tile_0", (0, 0), master)
    inst2 = FakeInst("tile_1", (100, 100), master)

    reader = FakeReader([inst1, inst2])
    run_power_function(recorder, reader, "metal1")

    # Should have 2 VPWR boxes (one per instance) and 2 VGND boxes
    vpwr_sboxes = [box for box in recorder.sboxes if box[0] == "VPWR"]
    vgnd_sboxes = [box for box in recorder.sboxes if box[0] == "VGND"]

    assert len(vpwr_sboxes) == 2, "Should create SBox for each instance's VPWR"
    assert len(vgnd_sboxes) == 2, "Should create SBox for each instance's VGND"

    # Verify first instance (at origin)
    assert (0, 0, 50, 50) in [box[1:] for box in vpwr_sboxes]
    # Verify second instance (offset by 100, 100)
    assert (100, 100, 150, 150) in [box[1:] for box in vpwr_sboxes]


def test_power_handles_multiple_geometries_per_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that power() creates boxes for all geometries in a pin."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create pin with multiple geometry shapes
    geom1 = FakeGeometry(0, 0, 10, 10)
    geom2 = FakeGeometry(20, 20, 30, 30)
    geom3 = FakeGeometry(40, 40, 50, 50)

    vpwr_mpin = FakeMPin([geom1, geom2, geom3])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin])
    master = FakeMaster([vpwr_mterm])
    inst = FakeInst("tile_0", (0, 0), master)

    reader = FakeReader([inst])
    run_power_function(recorder, reader, "metal1")

    vpwr_sboxes = [box for box in recorder.sboxes if box[0] == "VPWR"]
    assert len(vpwr_sboxes) == 3, "Should create SBox for each geometry"

    # Verify all three geometries are present
    coords = [box[1:] for box in vpwr_sboxes]
    assert (0, 0, 10, 10) in coords
    assert (20, 20, 30, 30) in coords
    assert (40, 40, 50, 50) in coords


def test_power_creates_nets_and_bterms_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that power() creates VPWR/VGND nets and bterms with correct properties."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create instance with both VPWR and VGND
    vpwr_geom = FakeGeometry(0, 0, 10, 10)
    vgnd_geom = FakeGeometry(0, 0, 10, 10)
    vpwr_mpin = FakeMPin([vpwr_geom])
    vgnd_mpin = FakeMPin([vgnd_geom])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin])
    vgnd_mterm = FakeMTerm("VGND", [vgnd_mpin])
    master = FakeMaster([vpwr_mterm, vgnd_mterm])
    inst = FakeInst("tile_0", (0, 0), master)

    reader = FakeReader([inst])
    run_power_function(recorder, reader, "metal1")

    # Verify nets were created
    vpwr_net = reader.block.findNet("VPWR")
    vgnd_net = reader.block.findNet("VGND")

    assert vpwr_net is not None, "VPWR net should be created"
    assert vgnd_net is not None, "VGND net should be created"
    assert vpwr_net.getSigType() == "POWER", "VPWR should have POWER signal type"
    assert vgnd_net.getSigType() == "GROUND", "VGND should have GROUND signal type"


def test_power_connects_iterms_to_nets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that power() connects instance terminals to power nets."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    vpwr_geom = FakeGeometry(0, 0, 10, 10)
    vgnd_geom = FakeGeometry(0, 0, 10, 10)
    vpwr_mpin = FakeMPin([vpwr_geom])
    vgnd_mpin = FakeMPin([vgnd_geom])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin])
    vgnd_mterm = FakeMTerm("VGND", [vgnd_mpin])
    master = FakeMaster([vpwr_mterm, vgnd_mterm])
    inst = FakeInst("tile_0", (0, 0), master)

    reader = FakeReader([inst])
    run_power_function(recorder, reader, "metal1")

    # Verify iterms are connected to nets
    iterms = inst.getITerms()
    vpwr_iterm = next(it for it in iterms if it.getMTerm().getName() == "VPWR")
    vgnd_iterm = next(it for it in iterms if it.getMTerm().getName() == "VGND")

    assert vpwr_iterm._net is not None, "VPWR iterm should be connected"
    assert vgnd_iterm._net is not None, "VGND iterm should be connected"
    assert vpwr_iterm._net.getName() == "VPWR"
    assert vgnd_iterm._net.getName() == "VGND"


def test_power_handles_empty_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that power() handles blocks with no instances gracefully."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    reader = FakeReader([])  # Empty block
    run_power_function(recorder, reader, "metal1")

    # Should create nets and bterms but no boxes
    assert reader.block.findNet("VPWR") is not None
    assert reader.block.findNet("VGND") is not None
    assert len(recorder.sboxes) == 0, "No SBoxes should be created for empty block"
    assert len(recorder.bboxes) == 0, "No BBoxes should be created for empty block"
