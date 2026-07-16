"""Tests for nextpnr model generation, focusing on bel.v3 timing output."""

from pytest_mock import MockerFixture

from fabulous.fabric_cad.gen_npnr_model import (
    PLACEMENT_ESTIMATE_TEXT,
    belLines,
    genNextpnrModel,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI


def test_gen_routing_model_returns_five_with_timing(cli: FABulous_CLI) -> None:
    """gen_routing_model emits a bel.v3 string with timing arcs alongside bel.v2.

    The bel.v3 block must mirror the bel.v2 structural lines and additionally
    carry the FABULOUS_LC timing arcs, while bel.v2 stays free of timing lines.
    """
    model = cli.fabulousAPI.gen_routing_model()
    assert len(model) == 5

    belv2, belv3 = model[2], model[3]

    # The structural definition is shared between v2 and v3.
    assert "BelBegin,X1Y1,A,FABULOUS_LC,LA_" in belv2
    assert "BelBegin,X1Y1,A,FABULOUS_LC,LA_" in belv3

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


def test_placement_estimate_text_has_tunables_and_lc_block() -> None:
    """The static placement_estimate.txt carries the tunables and one LC block.

    Values reproduce nextpnr's historical hardcoded defaults, so P&R behaviour
    is unchanged. It is a fixed constant while every LC instance shares the
    same timing; a real per-instance model would regenerate it.
    """
    text = PLACEMENT_ESTIMATE_TEXT
    assert "delayScale=3.0" in text
    assert "delayOffset=3.0" in text
    assert "delayEpsilon=0.25" in text
    assert "ripupPenalty=0.5" in text
    assert "carryPredictDelay=0.5" in text

    # The representative FABULOUS_LC arcs, in bel.v3 arc format.
    assert "Clock,CLK,FF=1" in text
    assert "Delay,I0,O,3.0,FF=0" in text
    assert "Delay,Ci,Co,0.2,Ci/Co?" in text
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in text
    assert "ClkToOut,Q,CLK,1.0,FF=1" in text


def test_genNextpnrModel_bel_timing_unaffected_by_real_pip_delay(
    cli: FABulous_CLI, mocker: MockerFixture
) -> None:
    """bel.v3's BEL-internal timing arcs stay fixed regardless of pip delay.

    LUT/FF/carry timing is a property of the standard cell's implementation,
    physically unrelated to interconnect (pip) delay - a supplied
    delay_model's real pip delay must NOT change bel.v3's arc values.
    """
    fake_model = mocker.Mock()
    fake_model.pip_delay.return_value = 6.0

    _, _, _, belv3, _ = genNextpnrModel(cli.fabulousAPI.fabric, fake_model)

    assert "Delay,I0,O,3.0,FF=0" in belv3
    assert "Delay,Ci,Co,0.2,Ci/Co?" in belv3
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in belv3
    assert "ClkToOut,Q,CLK,1.0,FF=1" in belv3
