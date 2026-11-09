"""Tests for the Jinja-rendered tool scripts and their Python-side wiring.

Covers the Yosys synthesis and OpenSTA SDF templates directly (exact rendered
text) and the `synthesize_gate_level` and `write_sdf` wrappers that check their
files and feed the rendered script to the tool.
"""

from collections.abc import Callable
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


def make_files(directory: Path, names: list[str]) -> list[Path]:
    """Write one non-empty file per name and return their paths."""
    paths = [directory / name for name in names]
    for path in paths:
        path.write_text("x")
    return paths


def synthesize(
    directory: Path,
    *,
    tiehi_cell_and_port: str | None = None,
    tielo_cell_and_port: str | None = None,
    min_buf_cell_and_ports: str = "BUF A Y",
) -> None:
    """Run `YosysTool.synthesize_gate_level` on files in `directory`."""
    YosysTool.synthesize_gate_level(
        verilog_files=[directory / "rtl.v"],
        liberty_files=[directory / "a.lib"],
        top_name="TOP",
        netlist_file=directory / "out.v",
        techmap_files=[directory / "map.v"],
        tiehi_cell_and_port=tiehi_cell_and_port,
        tielo_cell_and_port=tielo_cell_and_port,
        min_buf_cell_and_ports=min_buf_cell_and_ports,
    )


def write_sdf(directory: Path, *, spef_files: list[Path] | None = None) -> None:
    """Run `OpenStaTool.write_sdf` on files in `directory`."""
    OpenStaTool.write_sdf(
        netlist_file=directory / "n.v",
        liberty_files=[directory / "a.lib"],
        top_name="TOP",
        spef_files=[] if spef_files is None else spef_files,
        sdf_file=directory / "out.sdf",
    )


@pytest.mark.parametrize(
    ("tie_cells", "min_buf"),
    [
        pytest.param((None, None), "BUF A Y", id="no-tie-cells"),
        pytest.param(("HI Y", "LO Y"), "BUF A Y", id="tie-cells"),
    ],
)
def test_synthesize_gate_level_runs_the_script_and_strips_single_bit_ranges(
    mocker: MockerFixture,
    tmp_path: Path,
    tie_cells: tuple[str | None, str | None],
    min_buf: str,
) -> None:
    rtl, lib, techmap = make_files(tmp_path, ["rtl.v", "a.lib", "map.v"])
    netlist = tmp_path / "out.v"
    run = mocker.patch.object(
        YosysTool,
        "run",
        side_effect=lambda **_: netlist.write_text("wire [0:0] a;\nwire [1:0] b;\n"),
    )

    synthesize(
        tmp_path,
        tiehi_cell_and_port=tie_cells[0],
        tielo_cell_and_port=tie_cells[1],
        min_buf_cell_and_ports=min_buf,
    )

    run.assert_called_once_with(
        args=["-C"],
        stdin_data=YosysTool.render_template(
            "yosys_synth.j2",
            liberty_files=[lib],
            verilog_files=[rtl],
            techmap_files=[techmap],
            top_name="TOP",
            flat=False,
            tiehi_cell_and_port=tie_cells[0],
            tielo_cell_and_port=tie_cells[1],
            min_buf_cell_and_ports=min_buf,
            netlist_path=netlist,
        ),
    )
    assert netlist.read_text() == "wire   a;\nwire [1:0] b;\n"


@pytest.mark.parametrize(
    "spef_names", [pytest.param([], id="no-spef"), pytest.param(["r.spef"], id="spef")]
)
def test_write_sdf_runs_the_script(
    mocker: MockerFixture, tmp_path: Path, spef_names: list[str]
) -> None:
    netlist, lib = make_files(tmp_path, ["n.v", "a.lib"])
    spef_files = make_files(tmp_path, spef_names)
    sdf = tmp_path / "out.sdf"
    run = mocker.patch.object(
        OpenStaTool, "run", side_effect=lambda **_: sdf.write_text("(DELAYFILE)")
    )

    write_sdf(tmp_path, spef_files=spef_files)

    run.assert_called_once_with(
        stdin_data=OpenStaTool.render_template(
            "opensta_sdf.j2",
            liberty_files=[lib],
            verilog_netlist=netlist,
            top_name="TOP",
            spef_files=spef_files,
            sdf_path=sdf,
        )
    )


@pytest.mark.parametrize(
    ("tool", "call", "inputs", "output", "message"),
    [
        pytest.param(
            YosysTool,
            synthesize,
            ["rtl.v", "a.lib", "map.v"],
            "out.v",
            "empty gate-level netlist",
            id="yosys",
        ),
        pytest.param(
            OpenStaTool,
            write_sdf,
            ["n.v", "a.lib"],
            "out.sdf",
            "empty SDF file",
            id="opensta",
        ),
    ],
)
def test_empty_tool_output_raises(
    mocker: MockerFixture,
    tmp_path: Path,
    tool: type[Tool],
    call: Callable[[Path], None],
    inputs: list[str],
    output: str,
    message: str,
) -> None:
    make_files(tmp_path, inputs)
    mocker.patch.object(
        tool, "run", side_effect=lambda **_: (tmp_path / output).write_text("")
    )

    with pytest.raises(RuntimeError, match=message):
        call(tmp_path)


@pytest.mark.parametrize(
    ("tool", "call", "inputs", "output"),
    [
        pytest.param(
            YosysTool, synthesize, ["rtl.v", "a.lib", "map.v"], "out.v", id="yosys"
        ),
        pytest.param(OpenStaTool, write_sdf, ["n.v", "a.lib"], "out.sdf", id="opensta"),
    ],
)
@pytest.mark.parametrize(
    ("damage", "error"),
    [
        pytest.param("missing", FileNotFoundError, id="missing-input"),
        pytest.param("empty", ValueError, id="empty-input"),
        pytest.param("stale-output", FileExistsError, id="stale-output"),
    ],
)
def test_bad_tool_files_raise_before_running(
    mocker: MockerFixture,
    tmp_path: Path,
    tool: type[Tool],
    call: Callable[[Path], None],
    inputs: list[str],
    output: str,
    damage: str,
    error: type[Exception],
) -> None:
    paths = make_files(tmp_path, inputs)
    match damage:
        case "missing":
            paths[-1].unlink()
        case "empty":
            paths[-1].write_text("")
        case "stale-output":
            (tmp_path / output).write_text("old")
    run = mocker.patch.object(tool, "run")

    with pytest.raises(error):
        call(tmp_path)
    run.assert_not_called()


@pytest.mark.parametrize(
    ("tiehi", "tielo"), [("HI Y", None), (None, "LO Y")], ids=["hi-only", "lo-only"]
)
def test_synthesize_gate_level_needs_both_tie_cells(
    mocker: MockerFixture, tmp_path: Path, tiehi: str | None, tielo: str | None
) -> None:
    make_files(tmp_path, ["rtl.v", "a.lib", "map.v"])
    run = mocker.patch.object(YosysTool, "run")

    with pytest.raises(ValueError, match="specified together"):
        synthesize(tmp_path, tiehi_cell_and_port=tiehi, tielo_cell_and_port=tielo)
    run.assert_not_called()


@pytest.mark.parametrize("tool_cls", [Tool, YosysTool, GhdlTool, OpenStaTool])
def test_tool_cannot_be_instantiated(tool_cls: type[Tool]) -> None:
    """Tool wrappers are classmethod-only singletons and reject instantiation."""
    with pytest.raises(TypeError, match="cannot be instantiated"):
        tool_cls()
