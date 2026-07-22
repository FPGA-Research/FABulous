"""Tests for the folded RoutingModelGenerator.

Covers the no-timing path (placeholder delays, folding the old gen_npnr_model) and
the per-fabric pip-delay caching (folding the old FABulousTimingModelInterface).
"""

from pathlib import Path

import pytest
import pytest_mock

from fabulous.fabric_definition.cell_spec import CellSpec, StdCellLibrary
from fabulous.fabric_definition.define import IO
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.routing_model.generator import (
    PLACEHOLDER_PIP_DELAY,
    PLACEMENT_ESTIMATE_TEXT,
    RoutingModelGenerator,
    bel_lines,
)
from fabulous.routing_model.tile_timing_model import TimingModelMode
from tests.conftest import make_muladd_bel

TIMING_KEYWORDS = ("Delay,", "SetupHold,", "ClkToOut,", "Clock,")


def _library(liberty: list[Path]) -> StdCellLibrary:
    """Build a standard-cell library with the given liberty files and a buffer."""
    return StdCellLibrary(
        liberty_files=liberty,
        cells={"buffer": [CellSpec(cell="buf", input_ports=["A"], output_ports=["X"])]},
    )


def _pip_data_lines(pips: str) -> list[str]:
    """Return only the pip data lines (skip blank and ``#`` comment lines)."""
    return [
        line
        for line in pips.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_generate_without_timing_uses_placeholder_delays(cli: FABulousREPL) -> None:
    """Without a timing config every pip carries the placeholder delay."""
    fabric = cli.fabulousAPI.fabric

    pips, bel, belv2, belv3, constraints = RoutingModelGenerator(fabric).generate()

    assert isinstance(pips, str)
    assert isinstance(bel, str)
    assert isinstance(belv2, str)
    assert isinstance(belv3, str)
    assert isinstance(constraints, str)

    data_lines = _pip_data_lines(pips)
    assert data_lines, "expected at least one pip in the demo fabric"

    # Pip line format: srcTile,srcWire,dstTile,dstWire,delay,name
    delays = {line.split(",")[4] for line in data_lines}
    assert delays == {str(PLACEHOLDER_PIP_DELAY)}


def test_pip_delay_with_timing_delegates_and_caches(
    cli: FABulousREPL, mocker: pytest_mock.MockerFixture
) -> None:
    """With a timing config, pip delays come from per-tile engines and are cached."""
    fabric = cli.fabulousAPI.fabric

    calls: list[tuple[str, str, str]] = []

    class FakeTileTimingModel:
        def __init__(self, *, tile_name: str, **_kwargs: object) -> None:
            self.tile_name = tile_name

        def pip_delay(self, src_pip: str, dst_pip: str) -> float:
            calls.append((self.tile_name, src_pip, dst_pip))
            return 1.5

    mocker.patch(
        "fabulous.routing_model.generator.FABulousTileTimingModel",
        FakeTileTimingModel,
    )
    # Timing is enabled, so the generator checks the PDK and loads the
    # standard-cell library before building the (faked) per-tile models.
    mocker.patch(
        "fabulous.routing_model.generator.get_context",
        return_value=mocker.Mock(
            pdk="sky130A", pdk_root=Path("/pdks"), proj_dir=Path("/proj")
        ),
    )
    mocker.patch(
        "fabulous.routing_model.generator.StdCellLibrary.load",
        return_value=_library([Path("/cells.lib")]),
    )

    gen = RoutingModelGenerator(
        fabric,
        mode=TimingModelMode.PHYSICAL,
        verilog_files=[Path("/does/not/matter/top.v")],
    )
    tile_name = next(iter(fabric.tileDic))

    first = gen._pip_delay(tile_name, "LB_O", "JN2BEG3")  # noqa: SLF001
    second = gen._pip_delay(tile_name, "LB_O", "JN2BEG3")  # noqa: SLF001

    assert first == 1.5
    assert second == 1.5
    # Delegated once; the second identical lookup is served from the cache.
    assert calls == [(tile_name, "LB_O", "JN2BEG3")]


def test_timing_requires_verilog_files(cli: FABulousREPL) -> None:
    """Enabling timing without Verilog sources is rejected up front."""
    fabric = cli.fabulousAPI.fabric

    with pytest.raises(ValueError, match="verilog_files is required"):
        RoutingModelGenerator(fabric, mode=TimingModelMode.PHYSICAL)


def test_timing_requires_pdk(
    cli: FABulousREPL, mocker: pytest_mock.MockerFixture
) -> None:
    """Enabling timing with no PDK set is rejected up front."""
    fabric = cli.fabulousAPI.fabric

    mocker.patch(
        "fabulous.routing_model.generator.get_context",
        return_value=mocker.Mock(pdk=None),
    )

    with pytest.raises(ValueError, match="FAB_PDK is not set"):
        RoutingModelGenerator(
            fabric,
            mode=TimingModelMode.PHYSICAL,
            verilog_files=[Path("/does/not/matter/top.v")],
        )


def test_timing_requires_configured_liberty(
    cli: FABulousREPL, mocker: pytest_mock.MockerFixture
) -> None:
    """Enabling timing with no liberty configured for the PDK is rejected up front."""
    fabric = cli.fabulousAPI.fabric

    mocker.patch(
        "fabulous.routing_model.generator.get_context",
        return_value=mocker.Mock(
            pdk="sky130A", pdk_root=Path("/pdks"), proj_dir=Path("/proj")
        ),
    )
    mocker.patch(
        "fabulous.routing_model.generator.StdCellLibrary.load",
        return_value=_library([]),
    )

    with pytest.raises(ValueError, match="No liberty files configured"):
        RoutingModelGenerator(
            fabric,
            mode=TimingModelMode.PHYSICAL,
            verilog_files=[Path("/does/not/matter/top.v")],
        )


def test_generate_emits_bel_v3_with_timing_arcs(cli: FABulousREPL) -> None:
    """bel.v3 mirrors bel.v2's structure and adds the FABULOUS_LC timing arcs.

    The structural definition is shared between the two, so bel.v2 must stay
    free of timing lines while bel.v3 carries the arcs.
    """
    _, _, belv2, belv3, _ = RoutingModelGenerator(cli.fabulousAPI.fabric).generate()

    # The structural definition is shared between v2 and v3.
    assert "BelBegin,X1Y1,A,FABULOUS_LC,LA_" in belv2
    assert "BelBegin,X1Y1,A,FABULOUS_LC,LA_" in belv3

    # v3 carries the LC timing arcs reproducing nextpnr's defaults.
    assert "Delay,I0,O,3.0,FF=0" in belv3
    assert "Delay,Ci,Co,0.2,Ci/Co?" in belv3
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in belv3

    # Q is the cell's renamed FF output port (pack.cc renames O -> Q when the
    # FF is used) - a real cell port, so its clock-to-out arc is authored here
    # directly, same as every other BEL-internal constant.
    assert "ClkToOut,Q,CLK,1.0,FF=1" in belv3

    for keyword in TIMING_KEYWORDS:
        assert keyword not in belv2


def test_bel_lines_unknown_type_emits_no_timing_arcs() -> None:
    """BEL types that nextpnr does not time produce no timing arcs in bel.v3."""
    bel = make_muladd_bel(
        [("I", IO.INPUT), ("T", IO.INPUT), ("O", IO.OUTPUT), ("Q", IO.OUTPUT)],
        prefix="A_",
    )
    bel.name = "IO_1_bidirectional_frame_config_pass"

    _, _, v3_lines, _ = bel_lines(bel, "A", 0, 0)

    for keyword in TIMING_KEYWORDS:
        assert not any(line.startswith(keyword) for line in v3_lines)


def test_bel_lines_io_type_gets_set_io_constraint() -> None:
    """A BEL whose ports are fabric pins gets exactly one `set_io` line."""
    bel = make_muladd_bel([("I", IO.INPUT)], prefix="A_")
    bel.name = "IO_1_bidirectional_frame_config_pass"

    *_, constrain_lines = bel_lines(bel, "A", 2, 3)

    assert constrain_lines == ["set_io Tile_X2Y3_A Tile_X2Y3.A"]


def test_bel_lines_non_io_type_gets_no_constraint() -> None:
    """A BEL that is not a fabric-pin type contributes no `set_io` line."""
    bel = make_muladd_bel([("A0", IO.INPUT), ("Q0", IO.OUTPUT)])

    *_, constrain_lines = bel_lines(bel, "A", 0, 0)

    assert constrain_lines == []


def test_placement_estimate_text_has_tunables_and_lc_block() -> None:
    """The static placement_estimate.txt carries the tunables and one LC block.

    Values reproduce nextpnr's historical hardcoded defaults, so P&R behaviour
    is unchanged. It is a fixed constant while every LC instance shares the same
    timing; a real per-instance model would regenerate it.
    """
    assert "delayScale=3.0" in PLACEMENT_ESTIMATE_TEXT
    assert "delayOffset=3.0" in PLACEMENT_ESTIMATE_TEXT
    assert "delayEpsilon=0.25" in PLACEMENT_ESTIMATE_TEXT
    assert "ripupPenalty=0.5" in PLACEMENT_ESTIMATE_TEXT
    assert "carryPredictDelay=0.5" in PLACEMENT_ESTIMATE_TEXT

    # The representative FABULOUS_LC arcs, in bel.v3 arc format.
    assert "Clock,CLK,FF=1" in PLACEMENT_ESTIMATE_TEXT
    assert "Delay,I0,O,3.0,FF=0" in PLACEMENT_ESTIMATE_TEXT
    assert "Delay,Ci,Co,0.2,Ci/Co?" in PLACEMENT_ESTIMATE_TEXT
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in PLACEMENT_ESTIMATE_TEXT
    assert "ClkToOut,Q,CLK,1.0,FF=1" in PLACEMENT_ESTIMATE_TEXT


def test_bel_timing_unaffected_by_real_pip_delay(
    cli: FABulousREPL, mocker: pytest_mock.MockerFixture
) -> None:
    """bel.v3's BEL-internal timing arcs stay fixed regardless of pip delay.

    LUT/FF/carry timing is a property of the standard cell's implementation,
    physically unrelated to interconnect (pip) delay, so an extracted pip delay
    must NOT change bel.v3's arc values.
    """
    mocker.patch.object(RoutingModelGenerator, "_pip_delay", return_value=6.0)

    pips, _, _, belv3, _ = RoutingModelGenerator(cli.fabulousAPI.fabric).generate()

    # The mocked pip delay really did reach the pip lines.
    assert {line.split(",")[4] for line in _pip_data_lines(pips)} == {"6.0"}

    assert "Delay,I0,O,3.0,FF=0" in belv3
    assert "Delay,Ci,Co,0.2,Ci/Co?" in belv3
    assert "SetupHold,I0,CLK,2.5,0.1,FF=1" in belv3
    assert "ClkToOut,Q,CLK,1.0,FF=1" in belv3
