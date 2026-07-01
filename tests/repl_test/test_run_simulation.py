"""Tests for the ``run_simulation`` CLI command, including ``--gl``.

The command-branch tests mock the EDA tools (``run_task`` / ``make_hex``) so
they run without iverilog or a hardened project. The source-resolution tests
exercise the gate-level helpers directly against a tmp-path project layout. The
end-to-end gate-level run lives in
``tests/fabric_gen_test/integration_test/test_designs_pattern_gl.py`` behind
``@pytest.mark.gl``.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabulous_repl import cmd_run_simulation
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from tests.conftest import run_cmd

_CMD_MODULE = "fabulous.fabulous_repl.cmd_run_simulation"


def _make_bitstream(cli: FABulousREPL) -> Path:
    """Create a dummy ``.bin`` bitstream inside the project."""
    bitstream = cli.projectDir / "sequential_16bit_en.bin"
    bitstream.write_bytes(b"\x00\x00\x00\x00")
    return bitstream


def test_run_simulation_uses_plain_task(
    cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Without ``--gl`` the plain ``run-simulation`` task is used."""
    bitstream = _make_bitstream(cli)
    mocker.patch(f"{_CMD_MODULE}.make_hex")
    collect = mocker.patch(f"{_CMD_MODULE}.collect_gl_sources")
    run_task = mocker.patch(f"{_CMD_MODULE}.run_task")

    run_cmd(cli, f"run_simulation fst {bitstream}")

    run_task.assert_called_once()
    assert run_task.call_args.args[0] == "run-simulation"
    collect.assert_not_called()


def test_gl_branch_invokes_gl_task(cli: FABulousREPL, mocker: MockerFixture) -> None:
    """``--gl`` resolves GL sources and runs the ``run-gl-simulation`` task."""
    bitstream = _make_bitstream(cli)
    mocker.patch(f"{_CMD_MODULE}.make_hex")
    mocker.patch(
        f"{_CMD_MODULE}.collect_gl_sources",
        return_value=[
            Path("/p/Fabric/macro/final_views/eFPGA.nl.v"),
            Path("/p/Tile/LUT4AB/macro/final_views/nl/LUT4AB.nl.v"),
            Path("/pdk/sg13g2_stdcell.v"),
        ],
    )
    run_task = mocker.patch(f"{_CMD_MODULE}.run_task")

    run_cmd(cli, f"run_simulation --gl fst {bitstream}")

    run_task.assert_called_once()
    assert run_task.call_args.args[0] == "run-gl-simulation"
    task_vars = run_task.call_args.kwargs["task_vars"]
    assert task_vars["WAVEFORM_TYPE"] == "fst"
    assert task_vars["DESIGN"] == "sequential_16bit_en"
    assert task_vars["GL_SOURCES"] == (
        "/p/Fabric/macro/final_views/eFPGA.nl.v "
        "/p/Tile/LUT4AB/macro/final_views/nl/LUT4AB.nl.v "
        "/pdk/sg13g2_stdcell.v"
    )


def test_gl_sim_libs_forwarded(cli: FABulousREPL, mocker: MockerFixture) -> None:
    """``--gl-sim-libs`` overrides reach ``collect_gl_sources``."""
    bitstream = _make_bitstream(cli)
    mocker.patch(f"{_CMD_MODULE}.make_hex")
    mocker.patch(f"{_CMD_MODULE}.run_task")
    collect = mocker.patch(
        f"{_CMD_MODULE}.collect_gl_sources", return_value=[Path("n.v")]
    )

    run_cmd(
        cli,
        f"run_simulation --gl fst {bitstream} --gl-sim-libs a/*.v --gl-sim-libs b.v",
    )

    assert collect.call_args.args[0] == cli.projectDir
    assert collect.call_args.args[1] == ["a/*.v", "b.v"]


def test_gl_rejects_vhdl(
    cli: FABulousREPL, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Gate-level simulation is Verilog-only; a VHDL project is rejected."""
    bitstream = _make_bitstream(cli)
    mocker.patch(f"{_CMD_MODULE}.make_hex")
    run_task = mocker.patch(f"{_CMD_MODULE}.run_task")
    collect = mocker.patch(f"{_CMD_MODULE}.collect_gl_sources")
    cli.extension = "vhdl"

    run_cmd(cli, f"run_simulation --gl fst {bitstream}")

    # cmd2 catches the raised InvalidFileType and reports it via exit_code + log.
    assert cli.exit_code != 0
    assert "Verilog-only" in caplog.text
    run_task.assert_not_called()
    collect.assert_not_called()


def _make_fabric_netlist(project: Path, name: str = "eFPGA") -> Path:
    """Create a single fabric netlist under the expected macro layout."""
    macro = project / "Fabric" / "macro" / "final_views"
    macro.mkdir(parents=True)
    netlist = macro / f"{name}.nl.v"
    netlist.write_text(f"module {name}(); endmodule\n")
    return netlist


def _make_tile_netlist(project: Path, tile: str) -> Path:
    """Create one tile netlist under the expected per-tile macro layout."""
    nl_dir = project / "Tile" / tile / "macro" / "final_views" / "nl"
    nl_dir.mkdir(parents=True)
    netlist = nl_dir / f"{tile}.nl.v"
    netlist.write_text(f"module {tile}(); endmodule\n")
    return netlist


def _make_pdk(
    pdk_root: Path,
    pdk: str = "ihp-sg13g2",
    scl: str = "sg13g2_stdcell",
) -> Path:
    """Create a minimal PDK Verilog cell-model tree, return the primary file."""
    verilog = pdk_root / pdk / "libs.ref" / scl / "verilog"
    verilog.mkdir(parents=True)
    primary = verilog / f"{scl}.v"
    primary.write_text("// cell models\n")
    (verilog / f"{scl}_udp.v").write_text("// udp models\n")
    return primary


def _patch_context(
    mocker: MockerFixture, pdk: str | None, pdk_root: Path | None
) -> None:
    """Point ``cmd_run_simulation``'s context at a stub PDK and install root."""
    ctx = mocker.Mock()
    ctx.pdk = pdk
    ctx.pdk_root = pdk_root
    mocker.patch(f"{_CMD_MODULE}.get_context", return_value=ctx)


def test_collect_gl_sources_orders_wrapper_fabric_tiles_then_libs(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Sources are behavioural wrapper, fabric netlist, tiles, then PDK models."""
    netlist = _make_fabric_netlist(tmp_path)
    tile = _make_tile_netlist(tmp_path, "LUT4AB")
    (tmp_path / "Tile" / "DSP").mkdir()  # supertile parent, no macro -> skipped
    # behavioural wrapper directly under Fabric/; eFPGA.v core must be excluded.
    (tmp_path / "Fabric" / "eFPGA_top.v").write_text("// wrapper\n")
    (tmp_path / "Fabric" / "models_pack.v").write_text("// models\n")
    (tmp_path / "Fabric" / "eFPGA.v").write_text("// behavioural core\n")
    primary = _make_pdk(tmp_path / "pdk_root")
    _patch_context(mocker, "ihp-sg13g2", tmp_path / "pdk_root")

    sources = cmd_run_simulation.collect_gl_sources(tmp_path, [])
    names = [p.name for p in sources]

    assert "eFPGA_top.v" in names
    assert "models_pack.v" in names
    assert "eFPGA.v" not in names  # behavioural core replaced by the gate netlist
    assert {netlist, tile, primary} <= set(sources)
    assert any("udp" in n for n in names)
    # behavioural wrapper precedes the gate netlist, which precedes the tiles
    assert names.index("eFPGA_top.v") < sources.index(netlist) < sources.index(tile)


def _layout_no_fabric(_project: Path) -> None:
    """No macro tree at all -> the fabric netlist is missing."""


def _layout_multiple_fabric(project: Path) -> None:
    """Two fabric netlists under the macro tree -> ambiguous."""
    _make_fabric_netlist(project, "eFPGA")
    (project / "Fabric" / "macro" / "final_views" / "other.nl.v").write_text("//")


def _layout_fabric_only(project: Path) -> None:
    """A fabric netlist but no tile netlists."""
    _make_fabric_netlist(project)


@pytest.mark.parametrize(
    ("setup", "exc", "match"),
    [
        (_layout_no_fabric, FileNotFoundError, "gen_fabric_macro"),
        (_layout_multiple_fabric, ValueError, "Multiple fabric netlists"),
        (_layout_fabric_only, FileNotFoundError, "gen_all_tile_macros"),
    ],
    ids=["missing-fabric", "multiple-fabric", "missing-tiles"],
)
def test_collect_gl_sources_invalid_layout(
    tmp_path: Path,
    setup: Callable[[Path], None],
    exc: type[Exception],
    match: str,
) -> None:
    """An incomplete or ambiguous macro layout surfaces a clear error, not a skip."""
    setup(tmp_path)
    with pytest.raises(exc, match=match):
        cmd_run_simulation.collect_gl_sources(tmp_path, [])


def test_resolve_sim_libs_override_file(tmp_path: Path) -> None:
    """A concrete override file is resolved as-is."""
    lib = tmp_path / "cells.v"
    lib.write_text("// cells\n")
    assert cmd_run_simulation.resolve_sim_libs(tmp_path, [str(lib)]) == [lib.resolve()]


def test_resolve_sim_libs_override_no_match(tmp_path: Path) -> None:
    """An override matching nothing raises rather than silently passing."""
    with pytest.raises(FileNotFoundError, match="matched no files"):
        cmd_run_simulation.resolve_sim_libs(tmp_path, [str(tmp_path / "no" / "*.v")])


@pytest.mark.parametrize(
    ("pdk", "pdk_root", "match"),
    [
        (None, None, "set FAB_PDK"),
        ("made_up_pdk", Path("/tmp/pdk"), "No default standard-cell"),
    ],
    ids=["no-pdk", "unknown-pdk"],
)
def test_resolve_sim_libs_invalid_context(
    tmp_path: Path,
    mocker: MockerFixture,
    pdk: str | None,
    pdk_root: Path | None,
    match: str,
) -> None:
    """Without usable PDK context and no overrides, resolution fails clearly."""
    _patch_context(mocker, pdk, pdk_root)
    with pytest.raises(ValueError, match=match):
        cmd_run_simulation.resolve_sim_libs(tmp_path, [])


def test_resolve_sim_libs_from_context(tmp_path: Path, mocker: MockerFixture) -> None:
    """The context's PDK + root resolve to the primary cell file plus UDPs."""
    primary = _make_pdk(tmp_path / "pdk_root")
    _patch_context(mocker, "ihp-sg13g2", tmp_path / "pdk_root")
    result = cmd_run_simulation.resolve_sim_libs(tmp_path, [])
    assert result[0] == primary
    assert any("udp" in p.name for p in result)
