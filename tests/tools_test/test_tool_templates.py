"""Tests for the Jinja-rendered tool scripts and their Python-side wiring.

Covers the Yosys synthesis and OpenSTA SDF templates directly (exact rendered
text), the `analyze` wrapper that normalizes its inputs and feeds the rendered
script to the tool, and the GHDL version gate that keeps a too-old GHDL from
silently stripping the VHDL attributes a BEL definition is carried in.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest
from packaging.version import Version
from pytest_mock import MockerFixture

from fabulous.custom_exception import UnsupportedToolVersion
from fabulous.tools.ghdl import GhdlTool
from fabulous.tools.opensta import OpenStaTool
from fabulous.tools.tool import Tool, _check_version_once
from fabulous.tools.yosys import YosysTool


def _reporting(
    mocker: MockerFixture, tool_cls: type[Tool], version_output: str
) -> None:
    """Make `tool_cls` report `version_output` as its version banner.

    Patches the subprocess call rather than `run`, so that `run` and the
    version check hanging off it stay under test.

    Parameters
    ----------
    mocker : MockerFixture
        The pytest-mock fixture used to patch the tool.
    tool_cls : type[Tool]
        The tool wrapper being faked.
    version_output : str
        The stdout the tool is pretended to write for its version arguments.
    """
    mocker.patch.object(tool_cls, "executable", return_value=Path("/tool"))
    mocker.patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout=version_output, stderr=""
        ),
    )
    _check_version_once.cache_clear()


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


@pytest.mark.parametrize(
    ("tool_cls", "version_output", "expected"),
    [
        (
            GhdlTool,
            "GHDL 6.0.0 (6.0.0.r0.ge589c698c) [Dunoon edition]\n",
            Version("6.0.0"),
        ),
        (
            GhdlTool,
            "GHDL 5.1.1 (4.1.0.r775.g91725e47f) [Dunoon edition]\n",
            Version("5.1.1"),
        ),
        (
            YosysTool,
            "Yosys 0.62 (git sha1 7326bb7d, clang++ 21.1.2 -fPIC -O3)\n",
            Version("0.62"),
        ),
        (OpenStaTool, "2.7.0\n", Version("2.7.0")),
    ],
)
def test_version_parsed(
    mocker: MockerFixture,
    tool_cls: type[Tool],
    version_output: str,
    expected: Version,
) -> None:
    """Every tool's real banner puts its version first on the first line."""
    _reporting(mocker, tool_cls, version_output)
    assert tool_cls.version() == expected


@pytest.mark.parametrize(
    "version_output",
    [
        "",
        "GHDL nightly\n",
        # The GNAT version on the second line is not GHDL's.
        "GHDL (built from a working tree)\n Compiled with GNAT Version: 13.3.0\n",
    ],
)
def test_unreadable_version_is_not_fatal(
    mocker: MockerFixture, version_output: str
) -> None:
    """A build with no version number in its banner is used, not rejected."""
    _reporting(mocker, GhdlTool, version_output)
    assert GhdlTool.version() is None
    GhdlTool.check_version()


@pytest.mark.parametrize(
    ("tool_cls", "version_output"),
    [
        (GhdlTool, "GHDL 6.0.0 (6.0.0.r0.ge589c698c) [Dunoon edition]\n"),
        (GhdlTool, "GHDL 7.1.0\n"),
        (YosysTool, "Yosys 0.62 (git sha1 7326bb7d)\n"),
        (YosysTool, "Yosys 0.66 (git sha1 7326bb7d)\n"),
        # oss-cad-suite builds Yosys from master, so a build of the ceiling
        # release carries the commits since its tag as a local segment.
        (YosysTool, "Yosys 0.66+42 (git sha1 7326bb7d)\n"),
        (OpenStaTool, "2.7.0\n"),
    ],
)
def test_supported_version_accepted(
    mocker: MockerFixture, tool_cls: type[Tool], version_output: str
) -> None:
    _reporting(mocker, tool_cls, version_output)
    tool_cls.check_version()


@pytest.mark.parametrize(
    ("tool_cls", "version_output", "expected_message"),
    [
        (GhdlTool, "GHDL 5.1.1 (4.1.0.r775.g91725e47f)\n", "6.0.0 or newer"),
        (YosysTool, "Yosys 0.67 (git sha1 7326bb7d)\n", "0.66 or older"),
        (YosysTool, "Yosys 0.67+3 (git sha1 7326bb7d)\n", "0.66 or older"),
        # A pre-release keeps its ordering: it comes before the release the
        # floor asks for, so it cannot carry what that release added.
        (GhdlTool, "GHDL 6.0.0-dev (6.0.0.r0)\n", "6.0.0 or newer"),
    ],
)
def test_unsupported_version_rejected(
    mocker: MockerFixture,
    tool_cls: type[Tool],
    version_output: str,
    expected_message: str,
) -> None:
    _reporting(mocker, tool_cls, version_output)
    with pytest.raises(UnsupportedToolVersion, match=expected_message):
        tool_cls.check_version()


def test_run_checks_version_once(mocker: MockerFixture) -> None:
    """The gate hangs off `run`, so no caller has to ask for it."""
    _reporting(mocker, GhdlTool, "GHDL 5.1.1 (4.1.0.r775.g91725e47f)\n")
    with pytest.raises(UnsupportedToolVersion, match="6.0.0 or newer"):
        GhdlTool.synthesize_to_verilog(Path("/bel.vhdl"), Path("/models_pack.vhdl"))


def test_opensta_is_asked_with_the_flag_it_has(mocker: MockerFixture) -> None:
    """`--version` is not an OpenSTA flag: it prints usage and exits 1."""
    _reporting(mocker, OpenStaTool, "2.7.0\n")
    assert OpenStaTool.version() == Version("2.7.0")
    assert subprocess.run.call_args.args[0] == ["/tool", "-version"]
