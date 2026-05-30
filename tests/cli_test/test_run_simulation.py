"""Tests for the ``run_simulation`` CLI command, including ``--gl``.

The command-branch tests mock the EDA tools (``run_task`` / ``make_hex``) so
they run without iverilog or a hardened project. The source-resolution tests
exercise the gate-level helpers directly against a tmp-path project layout. The
end-to-end gate-level run lives in
``tests/fabric_gen_test/integration_test/test_designs_pattern_gl.py`` behind
``@pytest.mark.gl``.
"""

# cspell:words netlist netlists pnr hdl stdcell sg13g2 ihp udp pdk

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.custom_exception import InvalidFileType
from fabulous.fabulous_cli import cmd_run_simulation
from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from tests.conftest import run_cmd

_CMD_MODULE = "fabulous.fabulous_cli.cmd_run_simulation"


def _make_bitstream(cli: FABulous_CLI) -> Path:
    """Create a dummy ``.bin`` bitstream inside the project."""
    bitstream = cli.projectDir / "sequential_16bit_en.bin"
    bitstream.write_bytes(b"\x00\x00\x00\x00")
    return bitstream


# ---------------------------------------------------------------------------
# Command wiring
# ---------------------------------------------------------------------------


def test_run_simulation_uses_plain_task(
    cli: FABulous_CLI, mocker: MockerFixture
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


def test_gl_branch_invokes_gl_task(cli: FABulous_CLI, mocker: MockerFixture) -> None:
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


def test_gl_sim_libs_forwarded(cli: FABulous_CLI, mocker: MockerFixture) -> None:
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


def test_gl_rejects_vhdl(cli: FABulous_CLI, mocker: MockerFixture) -> None:
    """Gate-level simulation is Verilog-only; a VHDL project is rejected."""
    bitstream = _make_bitstream(cli)
    mocker.patch(f"{_CMD_MODULE}.make_hex")
    run_task = mocker.patch(f"{_CMD_MODULE}.run_task")
    collect = mocker.patch(f"{_CMD_MODULE}.collect_gl_sources")
    cli.extension = "vhdl"

    with pytest.raises(InvalidFileType, match="Verilog-only"):
        cli.do_run_simulation(f"fst {bitstream} --gl")

    run_task.assert_not_called()
    collect.assert_not_called()


# ---------------------------------------------------------------------------
# Gate-level source resolution
# ---------------------------------------------------------------------------


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


def _write_env(project: Path, pdk_root: Path) -> None:
    """Write a project ``.FABulous/.env`` pointing at ``pdk_root``."""
    (project / ".FABulous").mkdir()
    (project / ".FABulous" / ".env").write_text(
        f"FAB_PDK=ihp-sg13g2\nFAB_PDK_ROOT={pdk_root}\n"
    )


def test_collect_gl_sources_orders_fabric_tiles_then_libs(tmp_path: Path) -> None:
    """Sources are fabric netlist, then tile netlists, then PDK cell models."""
    netlist = _make_fabric_netlist(tmp_path)
    tile = _make_tile_netlist(tmp_path, "LUT4AB")
    (tmp_path / "Tile" / "DSP").mkdir()  # supertile parent, no macro -> skipped
    primary = _make_pdk(tmp_path / "pdk_root")
    _write_env(tmp_path, tmp_path / "pdk_root")

    sources = cmd_run_simulation.collect_gl_sources(tmp_path, [])

    assert sources[0] == netlist
    assert sources[1] == tile
    assert primary in sources
    assert any("udp" in p.name for p in sources)


def test_collect_gl_sources_missing_fabric_netlist(tmp_path: Path) -> None:
    """A missing fabric macro surfaces a clear error, not a skip."""
    with pytest.raises(FileNotFoundError, match="gen_fabric_macro"):
        cmd_run_simulation.collect_gl_sources(tmp_path, [])


def test_collect_gl_sources_multiple_fabric_netlists(tmp_path: Path) -> None:
    """More than one fabric netlist refuses to guess."""
    _make_fabric_netlist(tmp_path, "eFPGA")
    (tmp_path / "Fabric" / "macro" / "final_views" / "other.nl.v").write_text("//")
    with pytest.raises(ValueError, match="Multiple fabric netlists"):
        cmd_run_simulation.collect_gl_sources(tmp_path, [])


def test_collect_gl_sources_missing_tile_netlists(tmp_path: Path) -> None:
    """A fabric netlist without tile netlists surfaces a clear error."""
    _make_fabric_netlist(tmp_path)
    with pytest.raises(FileNotFoundError, match="gen_all_tile_macros"):
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


def test_resolve_sim_libs_missing_pdk(tmp_path: Path) -> None:
    """Without FAB_PDK and without overrides, resolution fails clearly."""
    (tmp_path / ".FABulous").mkdir()
    (tmp_path / ".FABulous" / ".env").write_text("")
    with pytest.raises(ValueError, match="set FAB_PDK"):
        cmd_run_simulation.resolve_sim_libs(tmp_path, [])


def test_resolve_sim_libs_unknown_pdk(tmp_path: Path) -> None:
    """A PDK with no known standard-cell library fails clearly."""
    (tmp_path / ".FABulous").mkdir()
    (tmp_path / ".FABulous" / ".env").write_text(
        "FAB_PDK=made_up_pdk\nFAB_PDK_ROOT=/tmp/pdk\n"
    )
    with pytest.raises(ValueError, match="No default standard-cell"):
        cmd_run_simulation.resolve_sim_libs(tmp_path, [])


def test_resolve_sim_libs_from_env(tmp_path: Path) -> None:
    """FAB_PDK + FAB_PDK_ROOT resolve to the primary cell file plus UDPs."""
    primary = _make_pdk(tmp_path / "pdk_root")
    _write_env(tmp_path, tmp_path / "pdk_root")
    result = cmd_run_simulation.resolve_sim_libs(tmp_path, [])
    assert result[0] == primary
    assert any("udp" in p.name for p in result)
