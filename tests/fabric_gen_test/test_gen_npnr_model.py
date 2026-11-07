"""Tests for nextpnr model generation, focusing on bel.v3 timing output."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from fabulous.fabric_cad.gen_npnr_model import (
    PLACEMENT_ESTIMATE_TEXT,
    emit_nextpnr_model,
    nextpnr_bel,
    placeholder_bel_arcs,
    placeholder_timing,
    render_arcs,
    tile_copies,
)
from fabulous.fabric_cad.timing_db import TimingDb
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.timing import (
    BelArcs,
    BelPin,
    DelayArc,
    FeatureIs,
    SwitchPip,
    ns,
)
from tests.conftest import make_empty_tile, make_fabric_from_grid


@pytest.fixture
def lut_fabric() -> Fabric:
    """Build one LUT tile without invoking an external HDL parser.

    Returns
    -------
    Fabric
        In-memory fabric containing one LUT tile and one switch-matrix connection.
    """
    bel = Bel(
        src=Path("LUT4c_frame_config_dffesr.v"),
        prefix="LA_",
        module_name="LUT4c_frame_config_dffesr",
        internal=[
            ("LA_I0", IO.INPUT),
            ("LA_I1", IO.INPUT),
            ("LA_I2", IO.INPUT),
            ("LA_I3", IO.INPUT),
            ("LA_Ci", IO.INPUT),
            ("LA_SR", IO.INPUT),
            ("LA_EN", IO.INPUT),
            ("LA_O", IO.OUTPUT),
            ("LA_Co", IO.OUTPUT),
        ],
        external=[],
        configPort=[],
        sharedPort=[("UserCLK", IO.INPUT)],
        configBit=0,
        belMap={},
        userCLK=True,
        ports_vectors={},
        carry={},
        localShared={},
    )
    tile = make_empty_tile("LUT4AB", pinOrderConfig={})
    tile.bels = [bel]
    tile.withUserCLK = True
    tile.switch_matrix = SwitchMatrix(
        matrix_file=Path(), connections={"LA_O": ["J_BEG"]}
    )
    return make_fabric_from_grid([[tile]])


def with_bel_arcs(fabric: Fabric, arcs: dict[str, BelArcs]) -> TimingDb:
    """Set placeholder timing, then `arcs` on the BELs of tile X0Y0 by name."""
    timing = placeholder_timing(fabric)
    for bel in fabric.tile[0][0].bels:
        bel.arcs = arcs[bel.instance_name]
    return timing


def test_emit_nextpnr_model_writes_timing_only_in_bel_v3(lut_fabric: Fabric) -> None:
    """The bel.v3 block mirrors bel.v2 and adds the FABULOUS_LC timing arcs."""
    model = emit_nextpnr_model(lut_fabric, placeholder_timing(lut_fabric))
    belv2, belv3 = model.bel_v2, model.bel_v3

    # The structural definition is shared between v2 and v3.
    assert "BelBegin,X0Y0,A,FABULOUS_LC,LA_" in belv2
    assert "BelBegin,X0Y0,A,FABULOUS_LC,LA_" in belv3

    # v3 carries the LC timing arcs reproducing nextpnr's defaults.
    assert "Delay,I0,O,3.0,FF=0" in belv3
    assert "Delay,Ci,Co,0.2,Ci/Co?" in belv3
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in belv3

    # Q is the cell's renamed FF output port (pack.cc renames O -> Q when the
    # FF is used) - a real cell port, so its clock-to-out arc is authored
    # here directly, same as every other BEL-internal constant.
    assert "ClkToOut,Q,CLK,1.0,FF=1" in belv3

    # Clock arrival time is per flop in v3; v2 keeps the bare command.
    assert "GlobalClk,1.0" in belv3
    assert "GlobalClk\n" in belv2
    assert "GlobalClk," not in belv2

    # v2 must not contain any timing lines.
    for keyword in ("Delay,", "SetupHold,", "ClkToOut,", "Clock,"):
        assert keyword not in belv2


def test_placeholder_timing_sets_arcs_on_every_copy_of_a_tile_type(
    lut_fabric: Fabric,
) -> None:
    """The tile type, each grid placement and each supertile member are timed."""
    lut = lut_fabric.tileDic["LUT4AB"]
    fabric = make_fabric_from_grid([[deepcopy(lut), deepcopy(lut)]])
    fabric.tileDic = {lut.name: lut}
    member = deepcopy(lut)
    fabric.superTileDic = {
        "ST": SuperTile(name="ST", tileDir=Path(), tiles=[member], tileMap=[[member]])
    }

    placeholder_timing(fabric)

    copies = list(tile_copies(fabric))
    assert len(copies) == 4
    assert len({id(tile.bels[0]) for tile in copies}) == 4
    assert all(tile.bels[0].arcs == copies[0].bels[0].arcs for tile in copies)
    assert copies[0].bels[0].arcs != BelArcs()
    assert all(
        tile.switch_matrix.pip_delays == {SwitchPip(src="J_BEG", dst="LA_O"): ns(8)}
        for tile in copies
    )


@pytest.mark.parametrize("on_super_tile", [False, True])
def test_emit_rejects_a_bel_without_arcs(
    lut_fabric: Fabric, *, on_super_tile: bool
) -> None:
    """A placed tile or supertile BEL with no arcs is an error, not a default."""
    tile = lut_fabric.tile[0][0]
    super_bel = deepcopy(tile.bels[0])
    super_bel.prefix = "ST_"
    lut_fabric.superTileDic = {
        "ST": SuperTile(
            name="ST", tileDir=Path(), tiles=[tile], tileMap=[[tile]], bels=[super_bel]
        )
    }
    timing = placeholder_timing(lut_fabric)
    untimed = (lut_fabric.superTileDic["ST"] if on_super_tile else tile).bels[0]
    untimed.arcs = None

    with pytest.raises(ValueError, match=rf"{untimed.instance_name}.*X0Y0"):
        emit_nextpnr_model(lut_fabric, timing)


@pytest.mark.parametrize("pip_delays", [None, {}], ids=["unset", "missing-pip"])
@pytest.mark.parametrize("on_super_tile", [False, True])
def test_emit_rejects_a_switch_pip_without_delay(
    lut_fabric: Fabric, *, on_super_tile: bool, pip_delays: dict | None
) -> None:
    """A placed tile or supertile switch pip with no delay is an error."""
    tile = lut_fabric.tile[0][0]
    super_tile = SuperTile(
        name="ST",
        tileDir=Path(),
        tiles=[tile],
        tileMap=[[tile]],
        switch_matrix=SwitchMatrix(matrix_file=Path(), connections={"ST_I0": ["X"]}),
    )
    lut_fabric.superTileDic = {"ST": super_tile}
    timing = placeholder_timing(lut_fabric)
    if on_super_tile:
        assert super_tile.switch_matrix is not None
        super_tile.switch_matrix = replace(
            super_tile.switch_matrix, pip_delays=pip_delays
        )
    else:
        tile.switch_matrix = replace(tile.switch_matrix, pip_delays=pip_delays)
    owner = "supertile 'ST'" if on_super_tile else "tile 'LUT4AB'"

    with pytest.raises(ValueError, match=rf"{owner} at X0Y0"):
        emit_nextpnr_model(lut_fabric, timing)


def test_unknown_bel_type_has_no_placeholder_arcs() -> None:
    """BEL types that nextpnr does not time produce no timing arcs in bel.v3."""
    kind = nextpnr_bel("IO_1_bidirectional_frame_config_pass").kind
    arcs = placeholder_bel_arcs(kind=kind, inputs=["I", "T"], outputs=["O", "Q"])

    assert render_arcs(arcs, kind=kind) == []


def test_placement_estimate_text_has_tunables_and_type_blocks() -> None:
    """The static placement_estimate.txt carries the tunables and one
    BelBegin/BelEnd estimate block per timed BEL type.

    Values reproduce nextpnr's historical hardcoded defaults, so P&R behaviour
    is unchanged. It is a fixed constant while every instance of a type shares
    the same timing; a real per-instance model would regenerate it.
    """
    text = PLACEMENT_ESTIMATE_TEXT
    assert "delayScale=3.0" in text
    assert "delayOffset=3.0" in text
    assert "delayEpsilon=0.25" in text
    assert "ripupPenalty=0.5" in text
    assert "carryPredictDelay=0.5" in text
    assert "pipDelayScale=0.05" in text

    # One estimate block per timed BEL type.
    for bel_type in (
        "FABULOUS_LC",
        "OutPass4_frame_config",
        "OutPass4_frame_config_mux",
        "InPass4_frame_config",
        "InPass4_frame_config_mux",
    ):
        assert f"BelBegin,{bel_type}\n" in text
    assert text.count("BelBegin,") == text.count("BelEnd")

    # The representative FABULOUS_LC arcs, in bel.v3 arc format.
    assert "Clock,CLK,FF=1" in text
    assert "Delay,I0,O,3.0,FF=0" in text
    assert "Delay,Ci,Co,0.2,Ci/Co?" in text
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in text
    assert "ClkToOut,Q,CLK,1.0,FF=1" in text

    # The representative IO register arcs.
    assert "SetupHold,I0,CLK,2.5,0.1\n" in text
    assert "ClkToOut,O0,CLK,2.5" in text


def test_bel_timing_unaffected_by_characterized_pip_delay(lut_fabric: Fabric) -> None:
    """bel.v3's BEL-internal timing arcs stay fixed regardless of pip delay.

    LUT/FF/carry timing is a property of the standard cell's implementation,
    physically unrelated to interconnect (pip) delay - a characterised pip
    delay must NOT change bel.v3's arc values.
    """
    timing = placeholder_timing(lut_fabric)
    tile = lut_fabric.tile[0][0]
    tile.switch_matrix = replace(
        tile.switch_matrix, pip_delays={SwitchPip(src="J_BEG", dst="LA_O"): ns(6.0)}
    )

    model = emit_nextpnr_model(lut_fabric, timing)

    assert "X0Y0,J_BEG,X0Y0,LA_O,6.0,J_BEG.LA_O" in model.pips
    assert "Delay,I0,O,3.0,FF=0" in model.bel_v3
    assert "Delay,Ci,Co,0.2,Ci/Co?" in model.bel_v3
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in model.bel_v3
    assert "ClkToOut,Q,CLK,1.0,FF=1" in model.bel_v3


def test_characterized_bel_timing_replaces_hardcoded_bel_output(
    lut_fabric: Fabric,
) -> None:
    """Characterised BEL timing replaces rather than seeds hardcoded BEL timing."""
    bel = lut_fabric.tile[0][0].bels[0]
    hardcoded_bel_v3 = emit_nextpnr_model(
        lut_fabric, placeholder_timing(lut_fabric)
    ).bel_v3

    characterized_bel_v3 = emit_nextpnr_model(
        lut_fabric, with_bel_arcs(lut_fabric, {bel.instance_name: BelArcs()})
    ).bel_v3

    assert "Delay,I0,O,3.0,FF=0" in hardcoded_bel_v3
    assert "Delay,I0,O,3.0,FF=0" not in characterized_bel_v3


def test_emit_serializes_characterized_bel_timing(lut_fabric: Fabric) -> None:
    """Characterised BEL values are written into bel.v3."""
    bel = lut_fabric.tile[0][0].bels[0]
    arcs = BelArcs(
        delays=(
            DelayArc(
                BelPin("I", 0), BelPin("O"), ns(9.75), when=(FeatureIs("FF", False),)
            ),
        )
    )

    bel_v3 = emit_nextpnr_model(
        lut_fabric, with_bel_arcs(lut_fabric, {bel.instance_name: arcs})
    ).bel_v3

    assert "Delay,I0,O,9.75,FF=0" in bel_v3


def test_emit_serializes_custom_bel_timing(lut_fabric: Fabric) -> None:
    """Custom BELs are timed without requiring a predefined template."""
    custom_bel = Bel(
        src=Path("CustomAccumulator.v"),
        prefix="ACC_",
        module_name="custom_accumulator",
        internal=[("ACC_A", IO.INPUT), ("ACC_Y", IO.OUTPUT)],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )
    lut_fabric.tile[0][0].bels.append(custom_bel)
    lut_bel = lut_fabric.tile[0][0].bels[0]
    timing = with_bel_arcs(
        lut_fabric,
        {
            lut_bel.instance_name: BelArcs(),
            custom_bel.instance_name: BelArcs(
                delays=(DelayArc(BelPin("A"), BelPin("Y"), ns(4.25)),)
            ),
        },
    )

    bel_v3 = emit_nextpnr_model(lut_fabric, timing).bel_v3

    assert "BelBegin,X0Y0,B,CustomAccumulator,ACC_" in bel_v3
    assert "Delay,A,Y,4.25" in bel_v3
