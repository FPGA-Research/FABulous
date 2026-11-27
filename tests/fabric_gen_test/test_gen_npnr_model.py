"""Tests for nextpnr model generation, focusing on bel.v3 timing output."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.gen_npnr_model import (
    PLACEMENT_ESTIMATE_TEXT,
    belLines,
    generate_nextpnr_model,
    genNextpnrModel,
)
from fabulous.fabric_cad.timing_model.models import (
    BelDelayTiming,
    BelTiming,
    TimingModelTarget,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, BelRole
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import BelPort
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from tests.conftest import make_empty_tile, make_fabric_from_grid

NEXTPNR_ARTIFACTS = (
    "pips.txt",
    "bel.txt",
    "bel.v2.txt",
    "bel.v3.txt",
    "template.pcf",
    "placement_estimate.txt",
)


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
        role=BelRole.LOGIC_CELL,
    )
    tile = make_empty_tile("LUT4AB", pinOrderConfig={})
    tile.bels = [bel]
    tile.withUserCLK = True
    tile.switch_matrix = SwitchMatrix(
        matrix_file=Path(), connections={"LA_O": ["J_BEG"]}
    )
    return make_fabric_from_grid([[tile]])


def test_generate_nextpnr_model_emits_the_full_artifact_set(lut_fabric: Fabric) -> None:
    """The nextpnr backend emits its six model files with `genNextpnrModel`'s text.

    The CLI writes these out verbatim, so a backend dropping or renaming a file
    breaks downstream nextpnr invocations.
    """
    pips, bel, bel_v2, bel_v3, constraints = genNextpnrModel(lut_fabric)

    assert generate_nextpnr_model(lut_fabric) == {
        "pips.txt": pips,
        "bel.txt": bel,
        "bel.v2.txt": bel_v2,
        "bel.v3.txt": bel_v3,
        "template.pcf": constraints,
        "placement_estimate.txt": PLACEMENT_ESTIMATE_TEXT,
    }


def test_generate_nextpnr_model_returns_bel_v3_with_timing(lut_fabric: Fabric) -> None:
    """The nextpnr model emits a bel.v3 file with timing arcs alongside bel.v2.

    The bel.v3 block must mirror the bel.v2 structural lines and additionally
    carry the FABULOUS_LC timing arcs, while bel.v2 stays free of timing lines.
    """
    model = generate_nextpnr_model(lut_fabric)

    belv2, belv3 = model["bel.v2.txt"], model["bel.v3.txt"]
    assert isinstance(belv2, str)
    assert isinstance(belv3, str)

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


def test_belLines_unknown_type_emits_no_timing_arcs() -> None:
    """BEL types that nextpnr does not time produce no timing arcs in bel.v3."""
    bel = Bel.__new__(Bel)
    bel.name = "IO_1_bidirectional_frame_config_pass"
    bel.prefix = "A_"
    bel.input_ports = [
        BelPort("I", IO.INPUT, 1, prefix="A_"),
        BelPort("T", IO.INPUT, 1, prefix="A_"),
    ]
    bel.output_ports = [
        BelPort("O", IO.OUTPUT, 1, prefix="A_"),
        BelPort("Q", IO.OUTPUT, 1, prefix="A_"),
    ]
    bel.belFeatureMap = {}
    bel.withUserCLK = False

    _, _, v3_lines, _ = belLines(bel, "A", 0, 0)

    for keyword in ("Delay,", "SetupHold,", "ClkToOut,", "Clock,"):
        assert not any(line.startswith(keyword) for line in v3_lines)


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


def test_genNextpnrModel_bel_timing_unaffected_by_real_pip_delay(
    lut_fabric: Fabric, mocker: MockerFixture
) -> None:
    """bel.v3's BEL-internal timing arcs stay fixed regardless of pip delay.

    LUT/FF/carry timing is a property of the standard cell's implementation,
    physically unrelated to interconnect (pip) delay - a supplied
    delay_model's real pip delay must NOT change bel.v3's arc values.
    """
    fake_model = mocker.Mock()
    fake_model.pip_delay.return_value = 6.0

    _, _, _, belv3, _ = genNextpnrModel(
        lut_fabric, fake_model, target=TimingModelTarget.PIPS
    )

    assert "Delay,I0,O,3.0,FF=0" in belv3
    assert "Delay,Ci,Co,0.2,Ci/Co?" in belv3
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in belv3
    assert "ClkToOut,Q,CLK,1.0,FF=1" in belv3
    fake_model.bel_timing.assert_not_called()


def test_timing_model_result_replaces_hardcoded_bel_output(
    lut_fabric: Fabric, mocker: MockerFixture
) -> None:
    """An active timing model replaces rather than seeds hardcoded BEL timing."""
    hardcoded_bel_v3 = genNextpnrModel(lut_fabric)[3]
    fake_model = mocker.Mock()
    fake_model.bel_timing.return_value = BelTiming()

    characterized_bel_v3 = genNextpnrModel(
        lut_fabric, fake_model, target=TimingModelTarget.BELS
    )[3]

    assert "Delay,I0,O,3.0,FF=0" in hardcoded_bel_v3
    assert "Delay,I0,O,3.0,FF=0" not in characterized_bel_v3
    tile = lut_fabric.tile[0][0]
    assert tile is not None
    fake_model.bel_timing.assert_called_once_with("LUT4AB", tile.bels[0])
    fake_model.pip_delay.assert_not_called()


@pytest.mark.parametrize(
    ("target", "expect_pips", "expect_bels"),
    [
        pytest.param(TimingModelTarget.PIPS, True, False, id="pips"),
        pytest.param(TimingModelTarget.BELS, False, True, id="bels"),
        pytest.param(TimingModelTarget.BOTH, True, True, id="both"),
    ],
)
def test_genNextpnrModel_computes_only_selected_timing(
    lut_fabric: Fabric,
    mocker: MockerFixture,
    target: TimingModelTarget,
    expect_pips: bool,
    expect_bels: bool,
) -> None:
    """The target controls expensive timing calls, not only file selection."""
    fake_model = mocker.Mock()
    fake_model.pip_delay.return_value = 6.0
    fake_model.bel_timing.return_value = BelTiming()

    genNextpnrModel(lut_fabric, fake_model, target=target)

    assert bool(fake_model.pip_delay.call_count) is expect_pips
    assert bool(fake_model.bel_timing.call_count) is expect_bels


def test_genNextpnrModel_serializes_timing_returned_by_model(
    lut_fabric: Fabric, mocker: MockerFixture
) -> None:
    """BEL values returned by the timing model are written into bel.v3."""
    fake_model = mocker.Mock()
    fake_model.bel_timing.return_value = BelTiming(
        arcs=(BelDelayTiming(source="I0", sink="O", delay=9.75, condition="FF=0"),)
    )

    _, _, _, bel_v3, _ = genNextpnrModel(
        lut_fabric, fake_model, target=TimingModelTarget.BELS
    )

    assert "Delay,I0,O,9.75,FF=0" in bel_v3
    fake_model.pip_delay.assert_not_called()


def test_genNextpnrModel_dispatches_custom_bels_to_timing_model(
    lut_fabric: Fabric, mocker: MockerFixture
) -> None:
    """Custom BELs are dispatched without requiring a predefined template."""
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
        role=BelRole.OTHER,
    )
    tile = lut_fabric.tile[0][0]
    assert tile is not None
    tile.bels.append(custom_bel)
    fake_model = mocker.Mock()

    def characterize(_tile_name: str, bel: Bel) -> BelTiming:
        """Return a recognizable characterized arc for the custom BEL.

        Parameters
        ----------
        _tile_name : str
            Tile type receiving the BEL.
        bel : Bel
            BEL definition sent by nextpnr model generation.

        Returns
        -------
        BelTiming
            Empty timing for the LUT or a recognizable custom timing result.
        """
        if bel is custom_bel:
            return BelTiming(arcs=(BelDelayTiming("A", "Y", 4.25),))
        return BelTiming()

    fake_model.bel_timing.side_effect = characterize

    _, _, _, bel_v3, _ = genNextpnrModel(
        lut_fabric, fake_model, target=TimingModelTarget.BELS
    )

    assert fake_model.bel_timing.call_count == 2
    assert any(
        call.args[1] is custom_bel for call in fake_model.bel_timing.call_args_list
    )
    assert "BelBegin,X0Y0,B,CustomAccumulator,ACC_" in bel_v3
    assert "Delay,A,Y,4.25" in bel_v3


@pytest.mark.parametrize(
    ("target", "expect_pips", "expect_bels"),
    [
        pytest.param(TimingModelTarget.PIPS, True, False, id="pips"),
        pytest.param(TimingModelTarget.BELS, False, True, id="bels"),
        pytest.param(TimingModelTarget.BOTH, True, True, id="both"),
    ],
)
def test_generate_nextpnr_model_forwards_target(
    lut_fabric: Fabric,
    mocker: MockerFixture,
    target: TimingModelTarget,
    expect_pips: bool,
    expect_bels: bool,
) -> None:
    """The backend entry point characterizes only the timing `target` selects."""
    fake_model = mocker.Mock()
    fake_model.pip_delay.return_value = 6.0
    fake_model.bel_timing.return_value = BelTiming()

    artifacts = generate_nextpnr_model(lut_fabric, fake_model, target)

    assert tuple(artifacts) == NEXTPNR_ARTIFACTS
    assert bool(fake_model.pip_delay.call_count) is expect_pips
    assert bool(fake_model.bel_timing.call_count) is expect_bels
