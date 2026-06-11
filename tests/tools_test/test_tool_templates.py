"""Tests for the Jinja-rendered tool scripts and their Python-side wiring.

Covers the Yosys synthesis and OpenSTA SDF templates directly (exact rendered
text) and the `analyze` wrapper that normalizes its inputs and feeds the rendered
script to the tool.
"""

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
