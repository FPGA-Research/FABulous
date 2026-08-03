"""Tests for nextpnr model generation, focusing on bel.v3 timing output."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.gen_npnr_model import (
    PLACEMENT_ESTIMATE_TEXT,
    belLines,
    genNextpnrModel,
    write_nextpnr_timing_files,
)
from fabulous.fabric_cad.timing_model.models import (
    BelDelayTiming,
    BelTiming,
    TimingModelTarget,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile


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
    tile = Tile(
        name="LUT4AB",
        ports=[],
        bels=[bel],
        tileDir=Path(),
        switch_matrix=SwitchMatrix(matrix_file=Path(), connections={"LA_O": ["J_BEG"]}),
        gen_ios=[],
        userCLK=True,
        pinOrderConfig={},
    )
    return Fabric(
        fabric_dir=Path(),
        tile=[[tile]],
        numberOfRows=1,
        numberOfColumns=1,
        tileDic={tile.name: tile},
    )


def test_gen_routing_model_returns_five_with_timing(lut_fabric: Fabric) -> None:
    """gen_routing_model emits a bel.v3 string with timing arcs alongside bel.v2.

    The bel.v3 block must mirror the bel.v2 structural lines and additionally
    carry the FABULOUS_LC timing arcs, while bel.v2 stays free of timing lines.
    """
    model = genNextpnrModel(lut_fabric)
    assert len(model) == 5

    belv2, belv3 = model[2], model[3]

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

    # v2 must not contain any timing lines.
    for keyword in ("Delay,", "SetupHold,", "ClkToOut,", "Clock,"):
        assert keyword not in belv2


def test_belLines_unknown_type_emits_no_timing_arcs() -> None:
    """BEL types that nextpnr does not time produce no timing arcs in bel.v3."""
    bel = Bel.__new__(Bel)
    bel.name = "IO_1_bidirectional_frame_config_pass"
    bel.prefix = "A_"
    bel.inputs = ["A_I", "A_T"]
    bel.outputs = ["A_O", "A_Q"]
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
    fake_model.bel_timing.assert_called_once_with(
        "LUT4AB", lut_fabric.tile[0][0].bels[0]
    )
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
    )
    lut_fabric.tile[0][0].bels.append(custom_bel)
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
    ("target", "pip_exists", "bel_exists"),
    [
        pytest.param(TimingModelTarget.PIPS, True, False, id="pips"),
        pytest.param(TimingModelTarget.BELS, False, True, id="bels"),
        pytest.param(TimingModelTarget.BOTH, True, True, id="both"),
    ],
)
def test_write_nextpnr_timing_files_writes_only_selected_outputs(
    lut_fabric: Fabric,
    mocker: MockerFixture,
    tmp_path: Path,
    target: TimingModelTarget,
    pip_exists: bool,
    bel_exists: bool,
) -> None:
    """The timing writer leaves unselected output files untouched."""
    fake_model = mocker.Mock()
    fake_model.pip_delay.return_value = 6.0
    fake_model.bel_timing.return_value = BelTiming()
    pip_path = tmp_path / "pips.txt"
    bel_path = tmp_path / "bel.v3.txt"

    write_nextpnr_timing_files(
        lut_fabric,
        pip_output_file=pip_path,
        bel_output_file=bel_path,
        delay_model=fake_model,
        target=target,
    )

    assert pip_path.exists() is pip_exists
    assert bel_path.exists() is bel_exists
