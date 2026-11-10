"""Tests for nextpnr model generation, its timing output and its files."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from fabulous.fabric_cad.gen_nextpnr_model import (
    CLOCK_DELAY,
    DUMMY_PIP_DELAY,
    NextpnrModel,
    emit_nextpnr_model,
    placeholder_bel_arcs,
    placement_estimate,
    render_arcs,
    set_placeholder_timing,
    write_nextpnr_model,
    write_timing_files,
)
from fabulous.fabric_definition.bel import Bel, bel_role
from fabulous.fabric_definition.define import IO, BelRole, Direction
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import BelPort
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.timing import (
    BelArcs,
    DelayArc,
    FeatureIs,
    SwitchPip,
    WirePip,
    ns,
)
from fabulous.fabric_definition.wire import Wire
from fabulous.fabulous_api import FABulous_API
from tests.conftest import make_fabric_from_grid


def with_bel_arcs(fabric: Fabric, arcs: list[BelArcs]) -> Fabric:
    """Set placeholder timing, then `arcs` on the BELs of tile X0Y0 in order."""
    set_placeholder_timing(fabric)
    for bel, bel_arcs in zip(fabric.tile[0][0].bels, arcs, strict=True):
        bel.arcs = bel_arcs
    return fabric


def test_emit_nextpnr_model_writes_timing_only_in_bel_v3(lut_fabric: Fabric) -> None:
    """The bel.v3 block mirrors bel.v2 and adds the FABULOUS_LC timing arcs."""
    set_placeholder_timing(lut_fabric)
    model = emit_nextpnr_model(lut_fabric)
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


def test_placeholder_timing_times_every_copy_of_a_tile_type(
    lut_fabric: Fabric,
) -> None:
    """The tile type, each grid placement and each supertile member are timed."""
    lut = lut_fabric.tileDic["LUT4AB"]
    fabric = make_fabric_from_grid([[deepcopy(lut), deepcopy(lut)]])
    fabric.tileDic = {lut.name: lut}
    fabric.tile[0][1].wireList = [Wire(Direction.JUMP, "A0", 0, 0, "B0", "", "")]
    member = deepcopy(lut)
    fabric.superTileDic = {
        "ST": SuperTile(name="ST", tileDir=Path(), tiles=[member], tileMap=[[member]])
    }

    set_placeholder_timing(fabric)

    copies = list(fabric.tile_copies())
    assert len(copies) == 4
    assert len({id(tile.bels[0]) for tile in copies}) == 4
    assert all(tile.bels[0].arcs == copies[0].bels[0].arcs for tile in copies)
    assert copies[0].bels[0].arcs != BelArcs()
    assert all(
        tile.switch_matrix.pip_delays == {SwitchPip(src="J_BEG", dst="LA_O"): ns(8)}
        for tile in copies
    )
    assert [wire.delay for wire in fabric.tile[0][1].wireList] == [DUMMY_PIP_DELAY]
    assert fabric.clock_arrival == CLOCK_DELAY


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
    set_placeholder_timing(lut_fabric)
    untimed = (lut_fabric.superTileDic["ST"] if on_super_tile else tile).bels[0]
    untimed.arcs = None

    with pytest.raises(ValueError, match=rf"{untimed.prefix}{untimed.name} at X0Y0"):
        emit_nextpnr_model(lut_fabric)


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
    set_placeholder_timing(lut_fabric)
    if on_super_tile:
        assert super_tile.switch_matrix is not None
        super_tile.switch_matrix = replace(
            super_tile.switch_matrix, pip_delays=pip_delays
        )
    else:
        tile.switch_matrix = replace(tile.switch_matrix, pip_delays=pip_delays)
    owner = "supertile 'ST'" if on_super_tile else "tile 'LUT4AB'"

    with pytest.raises(ValueError, match=rf"{owner} at X0Y0"):
        emit_nextpnr_model(lut_fabric)


def test_emit_rejects_a_wire_without_delay(lut_fabric: Fabric) -> None:
    """A placed wire with no delay is an error."""
    tile = lut_fabric.tile[0][0]
    tile.wireList = [Wire(Direction.JUMP, "A0", 0, 0, "B0", "", "")]
    set_placeholder_timing(lut_fabric)
    tile.wireList = [replace(wire, delay=None) for wire in tile.wireList]

    with pytest.raises(ValueError, match=r"Wire A0-X0Y0>B0 of the tile at X0Y0"):
        emit_nextpnr_model(lut_fabric)


def test_emit_rejects_a_clocked_fabric_without_clock_arrival(
    lut_fabric: Fabric,
) -> None:
    """A fabric with a clocked BEL needs a clock arrival."""
    set_placeholder_timing(lut_fabric)
    lut_fabric.clock_arrival = None

    with pytest.raises(ValueError, match="no clock arrival"):
        emit_nextpnr_model(lut_fabric)


def test_unknown_bel_type_has_no_placeholder_arcs() -> None:
    """BEL types that nextpnr does not time produce no timing arcs in bel.v3."""
    role = bel_role("IO_1_bidirectional_frame_config_pass")
    arcs = placeholder_bel_arcs(
        role=role,
        inputs=[BelPort("I", IO.INPUT, 1), BelPort("T", IO.INPUT, 1)],
        outputs=[BelPort("O", IO.OUTPUT, 1), BelPort("Q", IO.OUTPUT, 1)],
    )

    assert role is BelRole.OTHER
    assert render_arcs(arcs, logic_cell=False) == []


def test_placement_estimate_text_has_tunables_and_type_blocks() -> None:
    """The static placement_estimate.txt carries the tunables and one
    BelBegin/BelEnd estimate block per timed BEL type.

    Values reproduce nextpnr's historical hardcoded defaults, so P&R behaviour
    is unchanged. It is a fixed constant while every instance of a type shares
    the same timing; a real per-instance model would regenerate it.
    """
    text = placement_estimate()
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


def test_emit_serializes_characterized_pip_delays(lut_fabric: Fabric) -> None:
    """Characterised switch and wire delays are written into pips.txt."""
    tile = lut_fabric.tile[0][0]
    tile.wireList = [Wire(Direction.JUMP, "A0", 0, 0, "B0", "", "")]
    lut_fabric.set_timing(
        tile_arcs={"LUT4AB": [BelArcs()]},
        tile_pip_delays={
            "LUT4AB": {
                SwitchPip(src="J_BEG", dst="LA_O"): ns(6.0),
                WirePip("A0", "B0"): ns(0.25),
            }
        },
        super_tile_arcs={},
        super_tile_pip_delays={},
        clock_arrival=CLOCK_DELAY,
    )

    pips = emit_nextpnr_model(lut_fabric).pips

    assert pips.splitlines() == [
        "#Tile-internal pips on tile X0Y0:",
        "X0Y0,J_BEG,X0Y0,LA_O,6.0,J_BEG.LA_O",
        "#Tile-external pips on tile X0Y0:",
        "X0Y0,A0,X0Y0,B0,0.25,A0.B0",
    ]


def test_characterized_bel_timing_replaces_hardcoded_bel_output(
    lut_fabric: Fabric,
) -> None:
    """Characterised BEL timing replaces rather than seeds hardcoded BEL timing."""
    set_placeholder_timing(lut_fabric)
    hardcoded_bel_v3 = emit_nextpnr_model(lut_fabric).bel_v3

    characterized_bel_v3 = emit_nextpnr_model(
        with_bel_arcs(lut_fabric, [BelArcs()])
    ).bel_v3

    assert "Delay,I0,O,3.0,FF=0" in hardcoded_bel_v3
    assert "Delay,I0,O,3.0,FF=0" not in characterized_bel_v3


def test_emit_serializes_characterized_bel_timing(lut_fabric: Fabric) -> None:
    """Characterised BEL values are written into bel.v3."""
    bel = lut_fabric.tile[0][0].bels[0]
    arcs = BelArcs(
        delays=(
            DelayArc(
                bel.input_ports[0],
                bel.output_ports[0],
                ns(9.75),
                when=(FeatureIs("FF", False),),
            ),
        )
    )

    bel_v3 = emit_nextpnr_model(with_bel_arcs(lut_fabric, [arcs])).bel_v3

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
    with_bel_arcs(
        lut_fabric,
        [
            BelArcs(),
            BelArcs(
                delays=(
                    DelayArc(
                        custom_bel.input_ports[0], custom_bel.output_ports[0], ns(4.25)
                    ),
                )
            ),
        ],
    )

    bel_v3 = emit_nextpnr_model(lut_fabric).bel_v3

    assert "BelBegin,X0Y0,B,CustomAccumulator,ACC_" in bel_v3
    assert "Delay,A,Y,4.25" in bel_v3


PLACEHOLDER_PIPS = """\
#Tile-internal pips on tile X0Y0:
X0Y0,J_BEG,X0Y0,LA_O,8,J_BEG.LA_O
#Tile-external pips on tile X0Y0:"""

PLACEHOLDER_BEL_V1 = """\
# BEL descriptions: top left corner Tile_X0Y0, bottom right Tile_X1Y1
#Tile_X0Y0
X0Y0,X0,Y0,A,FABULOUS_LC,LA_I0,LA_I1,LA_I2,LA_I3,LA_Ci,LA_SR,LA_EN,LA_O,LA_Co"""

PLACEHOLDER_BEL_V2 = """\
# BEL descriptions: top left corner Tile_X0Y0, bottom right Tile_X1Y1
#Tile_X0Y0
BelBegin,X0Y0,A,FABULOUS_LC,LA_
I,I0,X0Y0.LA_I0
I,I1,X0Y0.LA_I1
I,I2,X0Y0.LA_I2
I,I3,X0Y0.LA_I3
I,Ci,X0Y0.LA_Ci
I,SR,X0Y0.LA_SR
I,EN,X0Y0.LA_EN
O,O,X0Y0.LA_O
O,Co,X0Y0.LA_Co
GlobalClk
BelEnd"""

PLACEHOLDER_BEL_V3 = """\
# BEL descriptions: top left corner Tile_X0Y0, bottom right Tile_X1Y1
#Tile_X0Y0
BelBegin,X0Y0,A,FABULOUS_LC,LA_
I,I0,X0Y0.LA_I0
I,I1,X0Y0.LA_I1
I,I2,X0Y0.LA_I2
I,I3,X0Y0.LA_I3
I,Ci,X0Y0.LA_Ci
I,SR,X0Y0.LA_SR
I,EN,X0Y0.LA_EN
O,O,X0Y0.LA_O
O,Co,X0Y0.LA_Co
Clock,CLK,FF=1
Delay,I0,O,3.0,FF=0
Delay,I1,O,3.0,FF=0
Delay,I2,O,3.0,FF=0
Delay,I3,O,3.0,FF=0
Delay,Ci,O,3.0,FF=0&I0MUX=1
Delay,Ci,Co,0.2,Ci/Co?
Delay,I1,Co,1.0,Ci/Co?
Delay,I2,Co,1.0,Ci/Co?
SetupHold,I0,CLK,2.5,0.1,FF=1
SetupHold,I1,CLK,2.5,0.1,FF=1
SetupHold,I2,CLK,2.5,0.1,FF=1
SetupHold,I3,CLK,2.5,0.1,FF=1
SetupHold,Ci,CLK,2.5,0.1,FF=1&I0MUX=1
ClkToOut,Q,CLK,1.0,FF=1
GlobalClk,1.0
BelEnd"""


def test_placeholder_model_text(lut_fabric: Fabric) -> None:
    """The placeholder files are pinned byte for byte, with no final newline."""
    set_placeholder_timing(lut_fabric)

    model = emit_nextpnr_model(lut_fabric)

    assert model.pips == PLACEHOLDER_PIPS
    assert model.bel_v1 == PLACEHOLDER_BEL_V1
    assert model.bel_v2 == PLACEHOLDER_BEL_V2
    assert model.bel_v3 == PLACEHOLDER_BEL_V3
    # The LUT tile has no pinned IO BEL.
    assert model.pcf == ""


MODEL = NextpnrModel(
    pips="pips",
    bel_v1="bel v1",
    bel_v2="bel v2",
    bel_v3="bel v3",
    pcf="pcf",
    placement_estimate="placement estimate",
)


def read_files(directory: Path) -> dict[str, str]:
    """Return the text of every file of `directory` by file name."""
    return {path.name: path.read_text() for path in directory.iterdir()}


def test_write_nextpnr_model_writes_each_text_to_its_file(out: Path) -> None:
    """All six files are written, each under the name nextpnr reads it by."""
    write_nextpnr_model(MODEL, out)

    assert read_files(out) == {
        "pips.txt": "pips",
        "bel.txt": "bel v1",
        "bel.v2.txt": "bel v2",
        "bel.v3.txt": "bel v3",
        "template.pcf": "pcf",
        "placement_estimate.txt": "placement estimate",
    }


def test_write_timing_files_rejects_one_path_for_both_files(out: Path) -> None:
    """One destination for both files would lose the pip delays."""
    path = out / "timing.txt"
    path.write_text("previous")

    with pytest.raises(ValueError, match="output paths must be different"):
        write_timing_files(MODEL, pip_file=path, bel_file=path)

    assert read_files(out) == {"timing.txt": "previous"}


@pytest.mark.parametrize(
    ("existing", "expected"),
    [
        pytest.param({}, {}, id="nothing-to-back-up"),
        pytest.param(
            {"pips.txt": "old pips"}, {"pips.backup.txt": "old pips"}, id="pips"
        ),
        pytest.param(
            {"bel.v3.txt": "old bels", "pips.backup.txt": "older pips"},
            {"bel.v3.backup.txt": "old bels", "pips.backup.txt": "older pips"},
            id="bels",
        ),
        pytest.param(
            {"pips.txt": "old pips", "pips.backup.txt": "older pips"},
            {"pips.backup.txt": "old pips"},
            id="backup-replaced",
        ),
    ],
)
def test_write_timing_files_backs_up_existing_files(
    out: Path, existing: dict[str, str], expected: dict[str, str]
) -> None:
    """An existing destination is kept as `<name>.backup.txt` beside the new file."""
    for name, text in existing.items():
        (out / name).write_text(text)

    write_timing_files(MODEL, pip_file=out / "pips.txt", bel_file=out / "bel.v3.txt")

    assert read_files(out) == {
        "pips.txt": "pips",
        "bel.v3.txt": "bel v3",
        **expected,
    }


def test_gen_routing_model_sets_placeholders_on_an_untimed_fabric(
    api: FABulous_API,
) -> None:
    """A fabric that was never characterised gets the placeholder timing."""
    assert not api.fabric.has_timing

    model = api.gen_routing_model()

    assert api.fabric.has_timing
    assert model.pips == PLACEHOLDER_PIPS
    assert model.bel_v3 == PLACEHOLDER_BEL_V3


def test_gen_routing_model_keeps_characterised_timing(api: FABulous_API) -> None:
    """Timing already on the fabric is emitted, not reset to the placeholders."""
    bel = api.fabric.tileDic["LUT4AB"].bels[0]
    api.fabric.set_timing(
        tile_arcs={
            "LUT4AB": [
                BelArcs(
                    delays=(
                        DelayArc(bel.input_ports[0], bel.output_ports[0], ns(9.75)),
                    )
                )
            ]
        },
        tile_pip_delays={"LUT4AB": {SwitchPip(src="J_BEG", dst="LA_O"): ns(6.5)}},
        super_tile_arcs={},
        super_tile_pip_delays={},
        clock_arrival=ns(0.75),
    )

    model = api.gen_routing_model()

    assert "X0Y0,J_BEG,X0Y0,LA_O,6.5,J_BEG.LA_O" in model.pips
    assert "Delay,I0,O,9.75\n" in model.bel_v3
    assert "GlobalClk,0.75\n" in model.bel_v3
    assert "Delay,I0,O,3.0" not in model.bel_v3
    assert f",{DUMMY_PIP_DELAY}," not in model.pips
