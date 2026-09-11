"""Tests for the Jinja-rendered tool scripts and their Python-side wiring.

Covers the Yosys synthesis and OpenSTA SDF templates directly (exact rendered
text) and the `analyze` wrapper that normalizes its inputs and feeds the rendered
script to the tool.
"""

import re
import sys
import tempfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.tools.ghdl import GhdlTool
from fabulous.tools.opensta import OpenStaTool
from fabulous.tools.tool import Tool
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


@pytest.mark.parametrize("tool_cls", [Tool, YosysTool, GhdlTool, OpenStaTool])
def test_tool_cannot_be_instantiated(tool_cls: type[Tool]) -> None:
    """Tool wrappers are classmethod-only singletons and reject instantiation."""
    with pytest.raises(TypeError, match="cannot be instantiated"):
        tool_cls()


def test_synthesize_renders_script_and_returns_netlist(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    run = mocker.patch.object(YosysTool, "run")
    lib = tmp_path / "x.lib"
    lib.write_text("lib")
    rtl = tmp_path / "r.v"
    rtl.write_text("module r(); endmodule")

    netlist = Path(tempfile.gettempdir()) / "synth_NORM_tmp.v"
    netlist.unlink(missing_ok=True)

    # run is mocked, so produce the netlist synthesize reads back.
    run.side_effect = lambda *_a, **_k: netlist.write_text("module NORM(); endmodule")

    try:
        result = YosysTool.synthesize_to_netlist(
            rtl, lib, "NORM", min_buf_cell_and_ports="BUF A Y"
        )

        assert result == netlist
        assert run.call_args.kwargs["stdin_data"] == YosysTool.render_template(
            "yosys_synth.j2",
            liberty_files=[lib],
            verilog_files=[rtl],
            techmap_files=None,
            top_name="NORM",
            flat=False,
            tiehi_cell_and_port=None,
            tielo_cell_and_port=None,
            min_buf_cell_and_ports="BUF A Y",
            netlist_path=netlist,
        )
    finally:
        netlist.unlink(missing_ok=True)


def test_synthesize_passes_tcl_flag(mocker: MockerFixture, tmp_path: Path) -> None:
    """The rendered script is Tcl (`yosys -import`), so yosys needs `-C`."""
    run = mocker.patch.object(YosysTool, "run")
    netlist = Path(tempfile.gettempdir()) / "synth_TCL_tmp.v"
    netlist.unlink(missing_ok=True)
    run.side_effect = lambda *_a, **_k: netlist.write_text("module TCL(); endmodule")

    try:
        YosysTool.synthesize_to_netlist(tmp_path / "r.v", tmp_path / "x.lib", "TCL")
        assert run.call_args.kwargs["args"] == ["-C"]
    finally:
        netlist.unlink(missing_ok=True)


def test_synthesize_strips_single_bit_vector_notation(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """OpenSTA cannot back-annotate SDF onto `[0:0]` single-bit vectors."""
    run = mocker.patch.object(YosysTool, "run")
    netlist = Path(tempfile.gettempdir()) / "synth_VEC_tmp.v"
    netlist.unlink(missing_ok=True)
    run.side_effect = lambda *_a, **_k: netlist.write_text("wire [0:0] w;")

    try:
        result = YosysTool.synthesize_to_netlist(
            tmp_path / "r.v", tmp_path / "x.lib", "VEC"
        )
        assert result.read_text() == "wire   w;"
    finally:
        netlist.unlink(missing_ok=True)


def test_synthesize_empty_netlist_raises(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.object(YosysTool, "run")
    netlist = Path(tempfile.gettempdir()) / "synth_EMPTY_tmp.v"
    netlist.write_text("")

    with pytest.raises(RuntimeError, match="No content in netlist file"):
        YosysTool.synthesize_to_netlist(tmp_path / "r.v", tmp_path / "x.lib", "EMPTY")
    assert not netlist.exists()


def test_run_reports_failing_command_for_path_executable() -> None:
    """A Path executable must reach the message, not break `str.join` building it."""

    class PythonTool(Tool):
        @classmethod
        def executable(cls) -> Path:
            return Path(sys.executable)

    with pytest.raises(RuntimeError, match=re.escape(sys.executable)):
        PythonTool.run(args=["-c", "raise SystemExit(1)"])
