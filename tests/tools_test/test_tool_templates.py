"""Tests for the Jinja-rendered tool scripts and their Python-side wiring.

Covers the Yosys synthesis and OpenSTA SDF templates directly (exact rendered
text) and the `synthesize`/`analyze` wrappers that normalize their inputs and
feed the rendered script to the tool.
"""

import tempfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.cell_spec import CellSpec, StdCellLibrary
from fabulous.tools.opensta import OpenStaTool
from fabulous.tools.yosys import YosysTool


def test_yosys_template_minimal() -> None:
    script = YosysTool.render_template(
        "yosys_synth.j2",
        liberty_files=[Path("/a.lib")],
        verilog_files=[Path("/b.v")],
        techmap_files=None,
        top_name="TOP",
        flat=False,
        tiehi_cell_and_port=None,
        tielo_cell_and_port=None,
        min_buf_cell_and_ports=None,
        netlist_path=Path("/n.v"),
    )
    assert script == (
        "yosys -import\n"
        "read_liberty -lib /a.lib\n"
        "read_verilog -overwrite -sv /b.v\n"
        "synth -top TOP\n"
        "renames -top TOP\n"
        "renames -wire\n"
        "clockgate -liberty /a.lib\n"
        "dfflibmap -liberty /a.lib\n"
        "setundef -zero\n"
        "splitnets\n"
        "tribuf\n"
        "abc -liberty /a.lib\n"
        "opt -purge -full\n"
        "write_verilog -noattr -noexpr /n.v\n"
    )


def test_yosys_template_full() -> None:
    script = YosysTool.render_template(
        "yosys_synth.j2",
        liberty_files=[Path("/a.lib"), Path("/a2.lib")],
        verilog_files=[Path("/b.v"), Path("/b2.v")],
        techmap_files=[Path("/tm.v")],
        top_name="TOP",
        flat=True,
        tiehi_cell_and_port="HI Y",
        tielo_cell_and_port="LO Y",
        min_buf_cell_and_ports="BUF A Y",
        netlist_path=Path("/n.v"),
    )
    assert script == (
        "yosys -import\n"
        "read_liberty -lib /a.lib\n"
        "read_liberty -lib /a2.lib\n"
        "read_verilog -overwrite -sv /b.v\n"
        "read_verilog -overwrite -sv /b2.v\n"
        "synth -flatten -top TOP\n"
        "renames -top TOP\n"
        "renames -wire\n"
        "techmap -map /tm.v\n"
        "simplemap\n"
        "clockgate -liberty /a.lib\n"
        "dfflibmap -liberty /a.lib\n"
        "setundef -zero\n"
        "splitnets\n"
        "hilomap -hicell HI Y -locell LO Y\n"
        "insbuf -buf BUF A Y\n"
        "tribuf\n"
        "abc -liberty /a.lib\n"
        "opt -purge -full\n"
        "write_verilog -noattr -noexpr /n.v\n"
    )


def test_opensta_template_minimal() -> None:
    script = OpenStaTool.render_template(
        "opensta_sdf.j2",
        liberty_files=[Path("/a.lib")],
        verilog_netlist=Path("/net.v"),
        top_name="TOP",
        spef_files=None,
        sdf_path=Path("/o.sdf"),
    )
    assert script == (
        "read_liberty /a.lib\n"
        "read_verilog /net.v\n"
        "link_design TOP\n"
        "write_sdf /o.sdf\n"
        "exit\n"
    )


def test_opensta_template_with_spef() -> None:
    script = OpenStaTool.render_template(
        "opensta_sdf.j2",
        liberty_files=[Path("/a.lib"), Path("/a2.lib")],
        verilog_netlist=Path("/net.v"),
        top_name="TOP",
        spef_files=[Path("/r.spef")],
        sdf_path=Path("/o.sdf"),
    )
    assert script == (
        "read_liberty /a.lib\n"
        "read_liberty /a2.lib\n"
        "read_verilog /net.v\n"
        "link_design TOP\n"
        "read_spef /r.spef\n"
        "write_sdf /o.sdf\n"
        "exit\n"
    )


def _library(liberty: Path) -> StdCellLibrary:
    """Build a minimal standard-cell library with one buffer cell."""
    return StdCellLibrary(
        liberty_files=[liberty],
        cells={"buffer": [CellSpec(cell="buf", input_ports=["A"], output_ports=["X"])]},
    )


def test_synthesize_gate_level_is_passthrough(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    run = mocker.patch.object(YosysTool, "run")
    gate_level = tmp_path / "gl.v"
    gate_level.write_text("module gl(); endmodule")

    result = YosysTool.synthesize(
        [gate_level], "TOP", _library(tmp_path / "x.lib"), is_gate_level=True
    )

    assert result == [gate_level]
    run.assert_not_called()


def test_synthesize_builds_script_and_strips_single_bit_vectors(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    run = mocker.patch.object(YosysTool, "run")
    lib = tmp_path / "x.lib"
    lib.write_text("lib")
    verilog = tmp_path / "d.v"
    verilog.write_text("module d(); endmodule")

    netlist = Path(tempfile.gettempdir()) / "synth_NORM_tmp.v"
    netlist.write_text("wire [0:0] w;")
    try:
        result = YosysTool.synthesize([verilog], "NORM", _library(lib))

        assert result == netlist
        run.assert_called_once()
        assert run.call_args.kwargs["stdin_data"] == YosysTool.render_template(
            "yosys_synth.j2",
            liberty_files=[lib],
            verilog_files=[verilog],
            techmap_files=[],
            top_name="NORM",
            flat=False,
            tiehi_cell_and_port=None,
            tielo_cell_and_port=None,
            min_buf_cell_and_ports="buf A X",
            netlist_path=netlist,
        )
        # The single-bit vector notation must be stripped for SDF back-annotation.
        assert netlist.read_text() == "wire   w;"
    finally:
        netlist.unlink(missing_ok=True)


def test_synthesize_empty_netlist_raises(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.object(YosysTool, "run")

    netlist = Path(tempfile.gettempdir()) / "synth_EMPTY_tmp.v"
    netlist.write_text("")

    with pytest.raises(RuntimeError, match="No content in netlist file"):
        YosysTool.synthesize([tmp_path / "d.v"], "EMPTY", _library(tmp_path / "x.lib"))
    assert not netlist.exists()


def test_synthesize_without_buffer_raises(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(YosysTool, "run")
    library = StdCellLibrary(liberty_files=[tmp_path / "x.lib"])

    with pytest.raises(ValueError, match="No buffer cell configured"):
        YosysTool.synthesize([tmp_path / "d.v"], "NOBUF", library)


def test_analyze_normalizes_inputs(mocker: MockerFixture, tmp_path: Path) -> None:
    run = mocker.patch.object(OpenStaTool, "run")
    lib = tmp_path / "x.lib"
    lib.write_text("lib")
    netlist = tmp_path / "n.v"
    netlist.write_text("module n(); endmodule")

    sdf = Path(tempfile.gettempdir()) / "sta_NORM_tmp.sdf"
    if sdf.exists():
        sdf.unlink()

    # run is mocked, so produce the SDF file analyze reads back.
    def write_sdf(*_args: object, **_kwargs: object) -> None:
        sdf.write_text("(DELAYFILE)")

    try:
        run.side_effect = write_sdf
        result = OpenStaTool.analyze(netlist, lib, "NORM")

        assert result == sdf
        assert run.call_args.kwargs["stdin_data"] == OpenStaTool.render_template(
            "opensta_sdf.j2",
            liberty_files=[lib],
            verilog_netlist=netlist,
            top_name="NORM",
            spef_files=None,
            sdf_path=sdf,
        )
    finally:
        sdf.unlink(missing_ok=True)


def test_analyze_empty_sdf_raises(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.object(OpenStaTool, "run")
    sdf = Path(tempfile.gettempdir()) / "sta_EMPTY_tmp.sdf"
    sdf.write_text("")

    with pytest.raises(RuntimeError, match="No content in SDF file"):
        OpenStaTool.analyze(tmp_path / "n.v", tmp_path / "x.lib", "EMPTY")
    assert not sdf.exists()
