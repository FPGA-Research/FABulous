"""Test module for FABulous CLI command functionality.

This module contains tests for various CLI commands including fabric generation, tile
generation, bitstream creation, simulation execution, and GUI commands.
"""

import os
import subprocess
import tkinter as tk
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from pytest_mock import MockerFixture, MockType

from fabulous.custom_exception import CommandError
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList
from fabulous.fabulous_repl.cmd_macro import _resolve_directional_fix
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_repl.helper import MAX_BITBYTES, create_project, setup_logger
from fabulous.fabulous_settings import init_context, reset_context
from tests.conftest import (
    normalize_and_check_for_errors,
    run_cmd,
)
from tests.repl_test.conftest import MOCK_COMPLETED_PROCESS, TILE, find_task_calls

SIM_CMD = "run_simulation fst ./user_design/sequential_16bit_en.bin"


DEMO_TILES = [
    "DSP",
    "LUT4AB",
    "N_term_DSP",
    "N_term_RAM_IO",
    "N_term_single",
    "N_term_single2",
    "RAM_IO",
    "RegFile",
    "S_term_DSP",
    "S_term_RAM_IO",
    "S_term_single",
    "S_term_single2",
    "W_IO",
]

LUT4AB_TILE_ARTIFACTS = {
    "Tile/LUT4AB/LUT4AB.v",
    "Tile/LUT4AB/LUT4AB_ConfigMem.v",
    "Tile/LUT4AB/LUT4AB_switch_matrix.v",
}

# LUT4AB ships its ConfigMem csv in the template, so only the other tiles gain one.
ALL_TILE_ARTIFACTS = LUT4AB_TILE_ARTIFACTS | {
    "Tile/DSP/DSP.v",
    "Tile/DSP/DSP_bot/DSP_bot.v",
    "Tile/DSP/DSP_bot/DSP_bot_ConfigMem.csv",
    "Tile/DSP/DSP_bot/DSP_bot_ConfigMem.v",
    "Tile/DSP/DSP_bot/DSP_bot_switch_matrix.v",
    "Tile/DSP/DSP_top/DSP_top.v",
    "Tile/DSP/DSP_top/DSP_top_ConfigMem.csv",
    "Tile/DSP/DSP_top/DSP_top_ConfigMem.v",
    "Tile/DSP/DSP_top/DSP_top_switch_matrix.v",
    "Tile/N_term_DSP/N_term_DSP.v",
    "Tile/N_term_DSP/N_term_DSP_switch_matrix.v",
    "Tile/N_term_RAM_IO/N_term_RAM_IO.v",
    "Tile/N_term_RAM_IO/N_term_RAM_IO_switch_matrix.v",
    "Tile/N_term_single/N_term_single.v",
    "Tile/N_term_single/N_term_single_switch_matrix.v",
    "Tile/N_term_single2/N_term_single2.v",
    "Tile/N_term_single2/N_term_single2_switch_matrix.v",
    "Tile/RAM_IO/RAM_IO.v",
    "Tile/RAM_IO/RAM_IO_ConfigMem.csv",
    "Tile/RAM_IO/RAM_IO_ConfigMem.v",
    "Tile/RAM_IO/RAM_IO_switch_matrix.v",
    "Tile/RegFile/RegFile.v",
    "Tile/RegFile/RegFile_ConfigMem.csv",
    "Tile/RegFile/RegFile_ConfigMem.v",
    "Tile/RegFile/RegFile_switch_matrix.v",
    "Tile/S_term_DSP/S_term_DSP.v",
    "Tile/S_term_DSP/S_term_DSP_switch_matrix.v",
    "Tile/S_term_RAM_IO/S_term_RAM_IO.v",
    "Tile/S_term_RAM_IO/S_term_RAM_IO_switch_matrix.v",
    "Tile/S_term_single/S_term_single.v",
    "Tile/S_term_single/S_term_single_switch_matrix.v",
    "Tile/S_term_single2/S_term_single2.v",
    "Tile/S_term_single2/S_term_single2_switch_matrix.v",
    "Tile/W_IO/W_IO.v",
    "Tile/W_IO/W_IO_ConfigMem.csv",
    "Tile/W_IO/W_IO_ConfigMem.v",
    "Tile/W_IO/W_IO_switch_matrix.v",
}

NPNR_ARTIFACTS = {
    ".FABulous/bel.txt",
    ".FABulous/bel.v2.txt",
    ".FABulous/bel.v3.txt",
    ".FABulous/pips.txt",
    ".FABulous/placement_estimate.txt",
    ".FABulous/template.pcf",
}

RUN_FAB_ARTIFACTS = (
    ALL_TILE_ARTIFACTS
    | NPNR_ARTIFACTS
    | {
        ".FABulous/bitStreamSpec.bin",
        ".FABulous/bitStreamSpec.csv",
        "Fabric/eFPGA.v",
        "Fabric/eFPGA_top.v",
        "eFPGA_geometry.csv",
    }
)


def project_files(project_dir: Path) -> set[str]:
    """Return every file under `project_dir` as a posix path relative to it."""
    return {
        f.relative_to(project_dir).as_posix()
        for f in project_dir.rglob("*")
        if f.is_file()
    }


@pytest.mark.usefixtures("cli")
def test_load_fabric() -> None:
    """`load_fabric` builds the fabric and records every tile that has a directory."""
    repl = FABulousREPL(
        "verilog", force=False, interactive=False, verbose=False, debug=True
    )
    assert not repl.fabric_loaded

    run_cmd(repl, "load_fabric")

    assert repl.exit_code == 0
    assert repl.fabric_loaded
    assert sorted(repl.all_tile) == DEMO_TILES


@pytest.mark.parametrize(
    ("command", "expected_new_files"),
    [
        pytest.param(
            f"gen_config_mem {TILE}",
            {"Tile/LUT4AB/LUT4AB_ConfigMem.v"},
            id="config_mem",
        ),
        pytest.param(
            f"gen_switch_matrix {TILE}",
            {"Tile/LUT4AB/LUT4AB_switch_matrix.v"},
            id="switch_matrix",
        ),
        pytest.param(f"gen_tile {TILE}", LUT4AB_TILE_ARTIFACTS, id="tile"),
        pytest.param("gen_all_tile", ALL_TILE_ARTIFACTS, id="all_tile"),
        pytest.param(
            "gen_fabric", ALL_TILE_ARTIFACTS | {"Fabric/eFPGA.v"}, id="fabric"
        ),
        pytest.param("gen_top_wrapper", {"Fabric/eFPGA_top.v"}, id="top_wrapper"),
        pytest.param("gen_model_npnr", NPNR_ARTIFACTS, id="model_npnr"),
        pytest.param(
            "gen_bitStream_spec",
            {".FABulous/bitStreamSpec.bin", ".FABulous/bitStreamSpec.csv"},
            id="bitstream_spec",
        ),
        pytest.param("run_fab", RUN_FAB_ARTIFACTS, id="run_fab"),
        pytest.param("run_FABulous_fabric", RUN_FAB_ARTIFACTS, id="deprecated_run_fab"),
    ],
)
def test_generation_command_writes_artifacts(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
    command: str,
    expected_new_files: set[str],
) -> None:
    """Each generation command writes exactly its artifacts, all non-empty."""
    before = project_files(cli.projectDir)

    run_cmd(cli, command)

    normalize_and_check_for_errors(caplog.text)
    assert cli.exit_code == 0
    new_files = project_files(cli.projectDir) - before
    assert new_files == expected_new_files
    assert all((cli.projectDir / f).stat().st_size > 0 for f in new_files)


@pytest.mark.parametrize(
    ("padding", "expected_size"),
    [("", ("3018", "4770")), ("16", ("3562", "7202"))],
    ids=["default-8", "16"],
)
def test_gen_geometry(
    cli: FABulousREPL, padding: str, expected_size: tuple[str, str]
) -> None:
    """The padding argument sets the fabric outline written for FABulator."""
    run_cmd(cli, f"gen_geometry {padding}".strip())

    assert cli.exit_code == 0
    rows = (cli.projectDir / "eFPGA_geometry.csv").read_text().splitlines()
    width, height = expected_size
    assert rows[5:7] == [f"Width,{width}", f"Height,{height}"]


def test_switch_matrix_list_csv_conversion_preserve_order(
    cli: FABulousREPL, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """With --preserve-list-order the .list -> .csv -> .list round trip is exact.

    The intermediate CSV encodes each mux-input position, so a preserve read
    recovers the exact per-mux ordering (the bitstream depends on it) even
    though the regenerated .list text may differ from the original.
    """
    src = cli.projectDir / f"Tile/{TILE}/{TILE}_switch_matrix.list"
    csv = tmp_path / "sm.csv"
    run_cmd(cli, f"list_to_csv --preserve-list-order {src} {csv}")
    assert csv.exists()

    back = tmp_path / "sm.list"
    run_cmd(cli, f"csv_to_list --preserve-list-order {csv} {back}")
    assert back.exists()
    normalize_and_check_for_errors(caplog.text)

    # The logical switch-matrix ordering must survive the round trip.
    assert parseList(back, "source") == parseList(src, "source")


def test_switch_matrix_list_csv_conversion_default(
    cli: FABulousREPL, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Without the flag, the conversion still preserves connectivity (not order)."""
    src = cli.projectDir / f"Tile/{TILE}/{TILE}_switch_matrix.list"
    csv = tmp_path / "sm.csv"
    run_cmd(cli, f"list_to_csv {src} {csv}")
    back = tmp_path / "sm.list"
    run_cmd(cli, f"csv_to_list {csv} {back}")
    normalize_and_check_for_errors(caplog.text)

    # Same muxes and the same set of inputs per mux; only the order may differ.
    src_conns = parseList(src, "source")
    back_conns = parseList(back, "source")
    assert src_conns.keys() == back_conns.keys()
    assert all(set(back_conns[k]) == set(src_conns[k]) for k in src_conns)


def test_gen_tile_aborts_on_sub_command_failure(
    cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """A failing sub-command aborts gen_tile instead of being silently skipped.

    gen_tile dispatches gen_switch_matrix / gen_config_mem through
    onecmd_plus_hooks, which swallows exceptions and only records them in
    exit_code. The exit-code guard must turn that sub-command failure into a
    gen_tile failure so the following step is not silently skipped (AGENTS.md:
    surface failures, no fallbacks).
    """
    mocker.patch.object(
        cli.fabulousAPI, "genSwitchMatrix", side_effect=RuntimeError("boom")
    )
    gen_config_mem = mocker.patch.object(cli.fabulousAPI, "genConfigMem")

    run_cmd(cli, f"gen_tile {TILE}")

    assert cli.exit_code != 0, "gen_tile must report the failed sub-command"
    gen_config_mem.assert_not_called()


def test_gen_io_pin_config(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating an IO pin configuration YAML file for a tile."""
    output_file = cli.projectDir / "Tile" / TILE / f"{TILE}_io_pin_order.yaml"

    assert not output_file.exists()

    run_cmd(cli, f"gen_io_pin_config {TILE}")
    log = normalize_and_check_for_errors(caplog.text)

    assert f"Generating IO pin config for {TILE}" in log[0]
    assert "IO pin config generation complete" in log[-1]
    assert output_file.exists()


def test_gen_io_pin_config_unknown_tile(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """An unknown tile fails the command and writes no pin config."""
    run_cmd(cli, "gen_io_pin_config NO_SUCH_TILE")

    assert cli.exit_code == 1
    assert "Tile NO_SUCH_TILE not found in fabric definition" in caplog.text
    assert not (cli.projectDir / "Tile" / "NO_SUCH_TILE").exists()


def test_gen_macro_tile_with_io_pin_config_skips_generation(
    cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
) -> None:
    """`gen_macro tile --io-pin-config <file>` uses the user-provided pin config."""
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
    )
    gen_pin_order_spy = mocker.spy(cli.fabulousAPI, "gen_io_pin_order_config")
    gen_tile_macro_mock = mocker.patch.object(cli.fabulousAPI, "genTileMacro")

    user_pin_config = tmp_path / "custom_pin_config.yaml"
    user_pin_config.touch()

    run_cmd(cli, f"gen_macro tile {TILE} --io-pin-config {user_pin_config}")

    gen_pin_order_spy.assert_not_called()
    gen_tile_macro_mock.assert_called_once()
    assert gen_tile_macro_mock.call_args.args[1] == user_pin_config.resolve()


def test_gen_macro_tile_without_io_pin_config_generates_for_tile(
    cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Without ``--io-pin-config``, the CLI auto-generates the pin order for a tile."""
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
    )
    gen_pin_order_mock = mocker.patch.object(cli.fabulousAPI, "gen_io_pin_order_config")
    gen_tile_macro_mock = mocker.patch.object(cli.fabulousAPI, "genTileMacro")

    run_cmd(cli, f"gen_macro tile {TILE}")

    expected_pin_order = cli.projectDir / "Tile" / TILE / f"{TILE}_io_pin_order.yaml"
    gen_pin_order_mock.assert_called_once()
    assert gen_pin_order_mock.call_args.args[1] == expected_pin_order
    assert gen_tile_macro_mock.call_args.args[1] == expected_pin_order


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation(cli: FABulousREPL) -> None:
    """The bitstream becomes a hex image and the Taskfile simulation task runs on it."""
    bitstream = (cli.projectDir / "user_design" / "sequential_16bit_en.bin").resolve()

    run_cmd(cli, SIM_CMD)

    assert cli.exit_code == 0
    # the cli fixture enables debug, which run_task forwards as --verbose
    assert [call[1:] for call in find_task_calls()] == [
        [
            "run-simulation",
            "--verbose",
            "WAVEFORM_TYPE=fst",
            "DESIGN=sequential_16bit_en",
            f"BITSTREAM_BIN={bitstream}",
        ]
    ]
    hex_lines = (
        (cli.projectDir / "Test" / "build" / "sequential_16bit_en.hex")
        .read_text()
        .splitlines()
    )
    assert hex_lines[:4] == ["de", "ad", "be", "ef"]
    assert hex_lines[4:] == ["0"] * (MAX_BITBYTES - 4)


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_oversized_bitstream(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """A bitstream larger than the testbench memory fails before simulating."""
    bitstream = cli.projectDir / "user_design" / "sequential_16bit_en.bin"
    bitstream.write_bytes(bytes(MAX_BITBYTES + 1))

    run_cmd(cli, SIM_CMD)

    assert cli.exit_code == 1
    assert f"is {MAX_BITBYTES + 1} bytes" in caplog.text
    assert find_task_calls() == []
    assert not (cli.projectDir / "Test" / "build" / "sequential_16bit_en.hex").exists()


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_makefile_fallback(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without a Taskfile the deprecated Makefile target runs instead."""
    test_dir = cli.projectDir / "Test"
    (test_dir / "Taskfile.yml").unlink()

    run_cmd(cli, SIM_CMD)

    assert cli.exit_code == 0
    assert find_task_calls() == []
    run_mock = cast("MockType", subprocess.run)
    run_mock.assert_called_once_with(
        ["make", "-C", str(test_dir), "run_simulation"], check=True
    )
    assert any(
        r.levelname == "WARNING" and "Makefiles are deprecated" in r.message
        for r in caplog.records
    )


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_no_taskfile_no_makefile(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """With neither a Taskfile nor a Makefile the command fails and runs nothing."""
    test_dir = cli.projectDir / "Test"
    (test_dir / "Taskfile.yml").unlink()
    (test_dir / "Makefile").unlink(missing_ok=True)

    run_cmd(cli, SIM_CMD)

    assert cli.exit_code == 1
    cast("MockType", subprocess.run).assert_not_called()
    assert f"No Taskfile.yml or Makefile found in {test_dir}" in caplog.text


@pytest.mark.usefixtures("simulation_mock")
@pytest.mark.parametrize(
    ("flag", "task_var"),
    [
        ("--extra-iverilog-flag=-DSOME_DEFINE", "EXTRA_IVERILOG_FLAGS=-DSOME_DEFINE"),
        pytest.param(
            '--extra-iverilog-flag="-DSOME_DEFINE"',
            "EXTRA_IVERILOG_FLAGS=-DSOME_DEFINE",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    'cmd2 keeps quotes inside a `--flag="value"` token, so the '
                    "Taskfile variable carries literal quotes"
                ),
            ),
        ),
        (
            "--extra-nvc-flag=--ieee-warnings=error",
            "EXTRA_NVC_FLAGS=--ieee-warnings=error",
        ),
        ("--extra-ghdl-flag=--std=08", "EXTRA_GHDL_FLAGS=--std=08"),
        ("--simulator=iverilog", "SIMULATOR=iverilog"),
        ("--simulator=xvlog", "SIMULATOR=xvlog"),
        ("--simulator=nvc", "SIMULATOR=nvc"),
        ("--simulator=ghdl", "SIMULATOR=ghdl"),
        ("--simulator=xvhdl", "SIMULATOR=xvhdl"),
        ("--simulator=auto", "SIMULATOR=auto"),
        ("-d my_custom_design", "DESIGN=my_custom_design"),
    ],
)
def test_run_simulation_forwards_flag_as_task_var(
    cli: FABulousREPL,
    flag: str,
    task_var: str,
) -> None:
    """Each `run_simulation` flag reaches the Taskfile as its `KEY=value` variable."""
    run_cmd(cli, f"{SIM_CMD} {flag}")

    assert cli.exit_code == 0
    assert task_var in find_task_calls()[-1]


def test_run_tcl_with_tcl_command(
    cli: FABulousREPL, capfd: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """`run_tcl` evaluates the script in the embedded Tcl interpreter."""
    tcl_script_path = tmp_path / "test_script.tcl"
    tcl_script_path.write_text('# Dummy Tcl script\nputs "Text from tcl"')

    run_cmd(cli, f"run_tcl {tcl_script_path}")

    assert cli.exit_code == 0
    assert "Text from tcl\n" in capfd.readouterr().out


def test_run_tcl_with_fabulous_command(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """FABulous commands called from Tcl run with their arguments."""
    top_wrapper = cli.projectDir / "user_design" / "top_wrapper.v"
    top_wrapper.unlink()
    test_script = tmp_path / "test_script.tcl"
    test_script.write_text(
        "load_fabric\n"
        "gen_user_design_wrapper user_design/sequential_16bit_en.v "
        "user_design/top_wrapper.v\n"
    )

    run_cmd(cli, f"run_tcl {test_script}")

    normalize_and_check_for_errors(caplog.text)
    assert cli.exit_code == 0
    assert "sequential_16bit_en " in top_wrapper.read_text()


def test_run_fab_sv_extension(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test running FABulous fabric flow with .sv (SystemVerilog) extension files.

    This test verifies that .sv files are correctly handled as Verilog files throughout
    the fabric generation process, using the same code path as run_fab but
    with BEL files using .sv extension.
    """
    monkeypatch.setenv("FAB_PROJ_DIR", str(project))

    # Convert .v BEL files to .sv
    for v_file in project.rglob("*.v"):
        if "models_pack" not in v_file.name:
            sv_file = v_file.with_suffix(".sv")
            v_file.rename(sv_file)

    # Update CSV files to reference .sv instead of .v
    for csv_file in project.rglob("*.csv"):
        content = csv_file.read_text()
        content = content.replace(".v,", ".sv,")
        content = content.replace(".v\n", ".sv\n")
        csv_file.write_text(content)

    init_context(project)
    cli = FABulousREPL(
        "verilog",
        force=False,
        interactive=False,
        verbose=False,
        debug=True,
    )
    cli.debug = True
    run_cmd(cli, "load_fabric")

    # Clear caplog before running fabric flow to get clean assertions
    caplog.clear()

    # Run the fabric flow with .sv files
    run_cmd(cli, "run_fab")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Running FABulous" in log[0]
    assert "FABulous fabric flow complete" in log[-1]


def test_exit_code_reset_after_error(cli: FABulousREPL) -> None:
    """Test that exit code is reset between commands (regression test for issue #574).

    After a command fails, subsequent successful commands should not be affected by the
    stale exit code from the previous failure.
    """
    # Run a command that fails (invalid tile name)
    run_cmd(cli, "gen_config_mem INVALID_TILE_NAME")
    assert cli.exit_code != 0, "First command should fail"

    # Run a command that succeeds
    run_cmd(cli, "load_fabric")

    assert cli.exit_code == 0, "Exit code should be reset after successful command"


@pytest.mark.parametrize(
    ("pdk", "family", "lyp", "auto_resolve_pdk_root"),
    [
        pytest.param(
            "ihp-sg13g2",
            "ihp-sg13",
            "sg13g2.lyp",
            True,
            id="ihp_sg13g2_fresh_ciel_install",
        ),
        pytest.param(
            "ihp-sg13cmos5l",
            "ihp-sg13",
            "sg13cmos5l.lyp",
            True,
            id="ihp_sg13cmos5l_fresh_ciel_install",
        ),
        pytest.param(
            "sky130A",
            "sky130",
            "sky130A.lyp",
            False,
            id="sky130A_explicit_pdk_root",
        ),
        pytest.param(
            "gf180mcuD",
            "gf180mcu",
            "gf180mcu.lyp",
            True,
            id="gf180mcuD_fresh_ciel_install",
        ),
        pytest.param(
            "gf180mcuD",
            "gf180mcu",
            "gf180mcu.lyp",
            False,
            id="gf180mcuD_explicit_pdk_root",
        ),
    ],
)
def test_start_klayout_gui_layer_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    pdk: str,
    family: str,
    lyp: str,
    auto_resolve_pdk_root: bool,
) -> None:
    """The layer file resolves to ``pdk_root/<pdk>/libs.tech/klayout/tech/<lyp>``.

    Covers both branches: ciel auto-resolution of `pdk_root` (fresh install)
    and an explicit `FAB_PDK_ROOT`
    """
    reset_context()
    for key in list(os.environ.keys()):
        if key.startswith("FAB_"):
            monkeypatch.delenv(key, raising=False)

    # tests/conftest.py patches get_ciel_home() to ``tmp_path/.ciel``.
    pdk_root = tmp_path / ".ciel" / family
    expected_layer_file = pdk_root / pdk / "libs.tech" / "klayout" / "tech" / lyp
    expected_layer_file.parent.mkdir(parents=True, exist_ok=True)
    expected_layer_file.touch()

    monkeypatch.setenv("FAB_PDK", pdk)
    if not auto_resolve_pdk_root:
        monkeypatch.setenv("FAB_PDK_ROOT", str(pdk_root))

    gds_file = tmp_path / "fabric.gds"
    gds_file.touch()
    run_mock = mocker.patch("subprocess.run", return_value=MOCK_COMPLETED_PROCESS)

    project_dir = tmp_path / "proj"
    create_project(project_dir)
    init_context(project_dir)
    setup_logger(0, False)
    cli = FABulousREPL(
        "verilog", force=False, interactive=False, verbose=False, debug=True
    )
    run_cmd(cli, f"start_klayout_gui {gds_file}")

    cmd: list[str] = run_mock.call_args.args[0]
    assert "-l" in cmd, f"klayout invocation missing -l: {cmd}"
    assert Path(cmd[cmd.index("-l") + 1]) == expected_layer_file


@pytest.mark.parametrize(
    ("opt_mode", "fix_width", "fix_height", "expected_mode", "expected_die_area"),
    [
        pytest.param(
            OptMode.NO_OPT,
            None,
            Decimal(245),
            OptMode.FIND_MIN_WIDTH,
            [0, 0, Decimal(245), Decimal(245)],
            id="fix-height-implies-find-min-width",
        ),
        pytest.param(
            OptMode.NO_OPT,
            Decimal(246),
            None,
            OptMode.FIND_MIN_HEIGHT,
            [0, 0, Decimal(246), Decimal(246)],
            id="fix-width-implies-find-min-height",
        ),
        pytest.param(
            OptMode.FIND_MIN_WIDTH,
            None,
            Decimal(245),
            OptMode.FIND_MIN_WIDTH,
            [0, 0, Decimal(245), Decimal(245)],
            id="fix-height-with-matching-mode",
        ),
        pytest.param(
            OptMode.BALANCE, None, None, OptMode.BALANCE, None, id="no-fix-passthrough"
        ),
    ],
)
def test_resolve_directional_fix(
    opt_mode: OptMode,
    fix_width: Decimal | None,
    fix_height: Decimal | None,
    expected_mode: OptMode,
    expected_die_area: list[int | Decimal] | None,
) -> None:
    """A fix flag selects the directional mode and a square starting die area."""
    assert _resolve_directional_fix(opt_mode, fix_width, fix_height) == (
        expected_mode,
        expected_die_area,
    )


@pytest.mark.parametrize(
    ("opt_mode", "fix_width", "fix_height", "match"),
    [
        pytest.param(
            OptMode.FIND_MIN_HEIGHT,
            None,
            Decimal(245),
            "only valid with --optimise find_min_width",
            id="fix-height-vs-find-min-height",
        ),
        pytest.param(
            OptMode.BALANCE,
            Decimal(246),
            None,
            "only valid with --optimise find_min_height",
            id="fix-width-vs-balance",
        ),
        pytest.param(
            OptMode.NO_OPT, Decimal(246), Decimal(245), "only one of", id="both-fixes"
        ),
    ],
)
def test_resolve_directional_fix_rejects(
    opt_mode: OptMode,
    fix_width: Decimal | None,
    fix_height: Decimal | None,
    match: str,
) -> None:
    """Conflicting fix flags and modes are rejected."""
    with pytest.raises(ValueError, match=match):
        _resolve_directional_fix(opt_mode, fix_width, fix_height)


class TestGenMacroTileFlags:
    """End-to-end CLI wiring for the explicit size flags."""

    def _patch(self, cli: FABulousREPL, mocker: MockerFixture) -> MockerFixture:
        mocker.patch(
            "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
        )
        mocker.patch.object(cli.fabulousAPI, "gen_io_pin_order_config")
        return mocker.patch.object(cli.fabulousAPI, "genTileMacro")

    @pytest.mark.parametrize(
        ("flag", "expected_mode", "size"),
        [
            ("--fix-height 245", OptMode.FIND_MIN_WIDTH, Decimal(245)),
            ("--fix-width 246", OptMode.FIND_MIN_HEIGHT, Decimal(246)),
        ],
        ids=["fix-height", "fix-width"],
    )
    def test_fix_flag_sets_mode_and_die_area(
        self,
        cli: FABulousREPL,
        mocker: MockerFixture,
        flag: str,
        expected_mode: OptMode,
        size: Decimal,
    ) -> None:
        gen_macro = self._patch(cli, mocker)

        run_cmd(cli, f"gen_macro tile {TILE} {flag}")

        kwargs = gen_macro.call_args.kwargs
        assert kwargs["optimisation"] == expected_mode
        assert kwargs["custom_config_overrides"] == {
            "FABULOUS_OPT_MODE": expected_mode,
            "DIE_AREA": [0, 0, size, size],
        }

    def test_fix_height_conflicting_mode_aborts(
        self, cli: FABulousREPL, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        gen_macro = self._patch(cli, mocker)

        run_cmd(
            cli,
            f"gen_macro tile {TILE} --optimise find_min_height --fix-height 245",
        )

        gen_macro.assert_not_called()
        assert "only valid with --optimise find_min_width" in caplog.text

    def test_override_merges_custom_yaml(
        self, cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        gen_macro = self._patch(cli, mocker)
        override = tmp_path / "ov.yaml"
        override.write_text("DIODE_ON_PORTS: both\n")

        run_cmd(cli, f"gen_macro tile {TILE} --override {override}")

        assert (
            gen_macro.call_args.kwargs["custom_config_overrides"]["DIODE_ON_PORTS"]
            == "both"
        )


class TestGenMacroFullForwarding:
    """End-to-end CLI wiring: flags forwarded to the API entrypoint."""

    def _patch(self, cli: FABulousREPL, mocker: MockerFixture) -> MockerFixture:
        mocker.patch(
            "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
        )
        return mocker.patch.object(cli.fabulousAPI, "full_fabric_automation")

    @pytest.mark.parametrize(
        ("flags", "expected_kwargs"),
        [
            pytest.param(
                "",
                {"tile_opt_config": None, "nlp_only": False, "nlp_area_margin": 0.05},
                id="defaults",
            ),
            pytest.param(
                "--nlp-only --nlp-area-margin 0.1",
                {"tile_opt_config": None, "nlp_only": True, "nlp_area_margin": 0.1},
                id="nlp-flags",
            ),
            pytest.param(
                "--tile-opt-info summary.json",
                {
                    "tile_opt_config": Path("summary.json"),
                    "nlp_only": False,
                    "nlp_area_margin": 0.05,
                },
                id="tile-opt-info",
            ),
        ],
    )
    def test_forwards_flags(
        self,
        cli: FABulousREPL,
        mocker: MockerFixture,
        flags: str,
        expected_kwargs: dict[str, object],
    ) -> None:
        full_auto = self._patch(cli, mocker)

        run_cmd(cli, f"gen_macro full {flags}".strip())

        full_auto.assert_called_once()
        macro_dir = cli.projectDir / "Fabric" / "macro"
        assert full_auto.call_args.args[:2] == (cli.projectDir, macro_dir)
        assert full_auto.call_args.kwargs == {
            "base_config_path": cli.projectDir / "Fabric" / "gds_config.yaml",
            **expected_kwargs,
        }


@pytest.mark.parametrize(
    ("command", "api_method"),
    [
        (f"gen_macro tile {TILE}", "genTileMacro"),
        ("gen_macro all_tile", "genTileMacro"),
        ("gen_macro stitch", "fabric_stitching"),
        ("gen_macro full", "full_fabric_automation"),
    ],
    ids=["tile", "all_tile", "stitch", "full"],
)
def test_gen_macro_fails_without_pdk(
    cli: FABulousREPL,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    command: str,
    api_method: str,
) -> None:
    """Every `gen_macro` step fails without a PDK and hardens nothing."""
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=False
    )
    api_mock = mocker.patch.object(cli.fabulousAPI, api_method)

    run_cmd(cli, command)

    api_mock.assert_not_called()
    assert cli.exit_code == 1
    assert "PDK configuration is not set" in caplog.text


@pytest.mark.parametrize(
    ("make_dir", "error"),
    [
        (False, "does not exist"),
        (True, "not found in fabric definition"),
    ],
    ids=["no-tile-dir", "not-in-fabric"],
)
def test_gen_macro_tile_fails_on_unknown_tile(
    cli: FABulousREPL,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    make_dir: bool,
    error: str,
) -> None:
    """A tile without a directory or a fabric entry fails and hardens nothing."""
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
    )
    gen_tile_macro_mock = mocker.patch.object(cli.fabulousAPI, "genTileMacro")
    if make_dir:
        (cli.projectDir / "Tile" / "NO_SUCH_TILE").mkdir()

    run_cmd(cli, "gen_macro tile NO_SUCH_TILE")

    gen_tile_macro_mock.assert_not_called()
    assert cli.exit_code == 1
    assert error in caplog.text


class TestGenMacroAllTile:
    """`gen_macro all_tile` fans out over the fabric's tiles."""

    def _patch(self, cli: FABulousREPL, mocker: MockerFixture) -> MockerFixture:
        mocker.patch(
            "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
        )
        mocker.patch.object(cli.fabulousAPI, "gen_io_pin_order_config")
        return mocker.patch.object(cli.fabulousAPI, "genTileMacro")

    @pytest.mark.parametrize("flags", ["", "--parallel"], ids=["serial", "parallel"])
    def test_hardens_every_tile(
        self, cli: FABulousREPL, mocker: MockerFixture, flags: str
    ) -> None:
        gen_tile_macro_mock = self._patch(cli, mocker)

        run_cmd(cli, f"gen_macro all_tile {flags}".strip())

        hardened = [call.args[0].name for call in gen_tile_macro_mock.call_args_list]
        assert sorted(hardened) == DEMO_TILES

    @pytest.mark.parametrize(
        ("flags", "expected_mode", "expected_die_area"),
        [
            (
                "--fix-width 246",
                OptMode.FIND_MIN_HEIGHT,
                [0, 0, Decimal(246), Decimal(246)],
            ),
            ("--optimise", OptMode.BALANCE, None),
        ],
        ids=["fix-width", "bare-optimise"],
    )
    def test_forwards_flags_to_each_tile(
        self,
        cli: FABulousREPL,
        mocker: MockerFixture,
        flags: str,
        expected_mode: OptMode,
        expected_die_area: list[int | Decimal] | None,
    ) -> None:
        gen_tile_macro_mock = self._patch(cli, mocker)

        run_cmd(cli, f"gen_macro all_tile {flags}")

        expected_overrides = (
            None
            if expected_die_area is None
            else {"FABULOUS_OPT_MODE": expected_mode, "DIE_AREA": expected_die_area}
        )
        forwarded = [
            (call.kwargs["optimisation"], call.kwargs["custom_config_overrides"])
            for call in gen_tile_macro_mock.call_args_list
        ]
        assert forwarded == [(expected_mode, expected_overrides)] * len(DEMO_TILES)

    @pytest.mark.parametrize(
        "command",
        [
            "gen_macro all_tile --io-pin-config pins.yaml",
            f"gen_macro tile {TILE} --parallel",
            "gen_macro tile",
        ],
        ids=["io-pin-config-on-all-tile", "parallel-on-tile", "tile-name-missing"],
    )
    def test_usage_errors(
        self, cli: FABulousREPL, mocker: MockerFixture, command: str
    ) -> None:
        gen_tile_macro_mock = self._patch(cli, mocker)

        run_cmd(cli, command)

        gen_tile_macro_mock.assert_not_called()
        assert cli.exit_code != 0

    @pytest.mark.parametrize("flags", ["", "--parallel"], ids=["serial", "parallel"])
    def test_conflicting_sizing_flags_abort_before_fan_out(
        self, cli: FABulousREPL, mocker: MockerFixture, flags: str
    ) -> None:
        """A bad flag pair fails the command once, not once per tile."""
        gen_tile_macro_mock = self._patch(cli, mocker)

        run_cmd(cli, f"gen_macro all_tile --fix-width 246 --fix-height 245 {flags}")

        gen_tile_macro_mock.assert_not_called()
        assert cli.exit_code != 0


def test_gen_macro_tile_completer_offers_tile_names(cli: FABulousREPL) -> None:
    """The tile completer offers exactly the tiles `gen_macro all_tile` hardens.

    It reaches app state via _cmd from inside the subparser.
    """
    parser = cli.command_parsers.get(cli.do_gen_macro)
    subparsers = next(a for a in parser._actions if a.dest == "subcommand")  # noqa: SLF001
    tile_action = next(
        a
        for a in subparsers.choices["tile"]._actions  # noqa: SLF001
        if a.dest == "tile"
    )
    cmd_set = cli.find_commandset_for_command("gen_macro")

    names = list(tile_action.get_completer()(cmd_set))

    assert sorted(names) == DEMO_TILES


@pytest.mark.parametrize(
    ("deprecated", "arguments", "api_method", "expected_kwargs"),
    [
        (
            "gen_tile_macro",
            f"{TILE} --optimise",
            "genTileMacro",
            {"optimisation": OptMode.BALANCE},
        ),
        (
            "gen_all_tile_macros",
            "--optimise",
            "genTileMacro",
            {"optimisation": OptMode.BALANCE},
        ),
        ("gen_fabric_macro", "", "fabric_stitching", {}),
        (
            "run_FABulous_eFPGA_macro",
            "--nlp-only",
            "full_fabric_automation",
            {"nlp_only": True},
        ),
    ],
    ids=["tile", "all_tile", "stitch", "full"],
)
@pytest.mark.parametrize("through_tcl", [False, True], ids=["repl", "tcl"])
def test_deprecated_macro_commands_forward(
    cli: FABulousREPL,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    deprecated: str,
    arguments: str,
    api_method: str,
    expected_kwargs: dict[str, object],
    through_tcl: bool,
) -> None:
    """Each pre-subcommand name warns and runs its replacement with its arguments.

    The TCL bridge calls the `do_*` method with a joined string rather than a
    `Statement`, so both entry paths have to reach the replacement.
    """
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
    )
    mocker.patch.object(cli.fabulousAPI, "gen_io_pin_order_config")
    api_mock = mocker.patch.object(cli.fabulousAPI, api_method)
    # `gen_macro stitch` raises unless every tile in the fabric is hardened.
    for tile in cli.fabulousAPI.fabric.get_all_unique_tiles():
        (cli.projectDir / "Tile" / tile.name / "macro" / "final_views").mkdir(
            parents=True
        )
    command = f"{deprecated} {arguments}".strip()

    if through_tcl:
        cli.tcl.eval(command)
    else:
        run_cmd(cli, command)

    assert any("deprecated" in r.message.lower() for r in caplog.records)
    assert cli.exit_code == 0
    assert api_mock.call_args_list
    for call in api_mock.call_args_list:
        assert call.kwargs.items() >= expected_kwargs.items()


@pytest.mark.parametrize("through_tcl", [False, True], ids=["repl", "tcl"])
def test_deprecated_macro_command_propagates_failure(
    cli: FABulousREPL, mocker: MockerFixture, through_tcl: bool
) -> None:
    """A failing replacement stops a REPL script and raises in TCL."""
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
    )
    mocker.patch.object(cli.fabulousAPI, "gen_io_pin_order_config")
    mocker.patch.object(
        cli.fabulousAPI, "genTileMacro", side_effect=RuntimeError("flow failed")
    )

    if through_tcl:
        with pytest.raises(tk.TclError):
            cli.tcl.eval(f"gen_tile_macro {TILE}")
    else:
        assert cli.onecmd_plus_hooks(f"gen_tile_macro {TILE}")
    assert cli.exit_code != 0


@pytest.mark.parametrize(
    ("unhardened", "stale"),
    [(set(), set()), (set(), {"DROPPED_TILE"}), ({TILE}, set())],
    ids=["all_hardened", "stale_unused_macro", "used_tile_unhardened"],
)
def test_gen_macro_stitch_hands_over_exactly_the_fabric_tiles(
    cli: FABulousREPL,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    unhardened: set[str],
    stale: set[str],
) -> None:
    """Stitch takes the fabric's tiles, ignores stale macros and needs each hardened.

    A tile hardened once and later dropped from the fabric leaves its
    `final_views` behind under `Tile/`, which must not reach the stitching flow.
    """
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
    )
    api_mock = mocker.patch.object(cli.fabulousAPI, "fabric_stitching")
    used = {tile.name for tile in cli.fabulousAPI.fabric.get_all_unique_tiles()}
    for name in (used - unhardened) | stale:
        (cli.projectDir / "Tile" / name / "macro" / "final_views").mkdir(parents=True)

    run_cmd(cli, "gen_macro stitch")

    if unhardened:
        assert cli.exit_code != 0
        assert any(TILE in r.message for r in caplog.records if r.levelname == "ERROR")
        api_mock.assert_not_called()
    else:
        assert cli.exit_code == 0
        assert set(api_mock.call_args.args[0]) == used


CUSTOM_PRIM_BELS = [
    "Tile/LUT4AB/LUT4c_frame_config_dffesr.v",
    "Tile/LUT4AB/MUX8LUT_frame_config_mux.v",
]
HAND_WRITTEN_PRIM = "\nmodule keep_me (\n    input a\n);\nendmodule\n"


def custom_prims_file(cli: FABulousREPL) -> str:
    """Return the content of the project's custom primitives file."""
    return (cli.projectDir / "user_design" / "custom_prims.v").read_text()


@pytest.mark.parametrize("absolute", [True, False], ids=["absolute", "relative"])
def test_add_as_custom_prim_adds_blackbox_prims(
    cli: FABulousREPL, absolute: bool
) -> None:
    """Every given RTL file ends up as a blackbox module in custom_prims.v.

    Relative paths are resolved against the project directory, like the other
    REPL commands do.
    """
    paths = [str(cli.projectDir / bel) if absolute else bel for bel in CUSTOM_PRIM_BELS]
    before = custom_prims_file(cli)

    run_cmd(cli, f"add_as_custom_prim {' '.join(paths)}")

    prims = custom_prims_file(cli)
    for bel in CUSTOM_PRIM_BELS:
        module = bel.rsplit("/", 1)[-1].removesuffix(".v")
        assert f"module {module} (" not in before
        assert f"module {module} (" in prims


def test_add_as_custom_prim_is_idempotent(cli: FABulousREPL) -> None:
    """A primitive already present in the file is not appended again."""
    path = str(cli.projectDir / CUSTOM_PRIM_BELS[0])
    run_cmd(cli, f"add_as_custom_prim {path}")
    first = custom_prims_file(cli)

    run_cmd(cli, f"add_as_custom_prim {path}")
    assert custom_prims_file(cli) == first


@pytest.mark.parametrize(
    ("flag", "stale_kept"), [("", True), ("--overwrite", False)], ids=["off", "on"]
)
def test_add_as_custom_prim_overwrite(
    cli: FABulousREPL, flag: str, stale_kept: bool
) -> None:
    """Only `--overwrite` replaces a stale definition, and only that definition."""
    target, neighbour = CUSTOM_PRIM_BELS
    module = target.rsplit("/", 1)[-1].removesuffix(".v")
    neighbour_module = neighbour.rsplit("/", 1)[-1].removesuffix(".v")
    paths = [str(cli.projectDir / bel) for bel in CUSTOM_PRIM_BELS]
    run_cmd(cli, f"add_as_custom_prim {' '.join(paths)}")

    # make the already present definition differ from what the command generates
    prims_path = cli.projectDir / "user_design" / "custom_prims.v"
    prims_path.write_text(
        custom_prims_file(cli).replace(
            f"module {module} (", f"module {module} (\n    input stale_port,"
        )
        + HAND_WRITTEN_PRIM
    )

    run_cmd(cli, f"add_as_custom_prim {flag} {paths[0]}")

    prims = custom_prims_file(cli)
    assert ("stale_port" in prims) is stale_kept
    assert prims.count(f"module {module} (") == 1
    assert prims.count(f"module {neighbour_module} (") == 1
    assert HAND_WRITTEN_PRIM in prims


def test_add_as_custom_prim_overwrite_keeps_content_between_duplicates(
    cli: FABulousREPL,
) -> None:
    """Duplicate definitions are removed without taking the content between them."""
    target, neighbour = CUSTOM_PRIM_BELS
    module = target.rsplit("/", 1)[-1].removesuffix(".v")
    neighbour_module = neighbour.rsplit("/", 1)[-1].removesuffix(".v")
    paths = [str(cli.projectDir / bel) for bel in CUSTOM_PRIM_BELS]
    run_cmd(cli, f"add_as_custom_prim {' '.join(paths)}")

    # a second definition of the same module, with content to preserve in between
    prims_path = cli.projectDir / "user_design" / "custom_prims.v"
    generated = custom_prims_file(cli)
    prims_path.write_text(generated + HAND_WRITTEN_PRIM + generated)

    run_cmd(cli, f"add_as_custom_prim --overwrite {paths[0]}")

    prims = custom_prims_file(cli)
    assert prims.count(f"module {module} (") == 1
    assert prims.count(f"module {neighbour_module} (") == 2
    assert HAND_WRITTEN_PRIM in prims


def test_add_as_custom_prim_overwrite_removes_indented_definition(
    cli: FABulousREPL,
) -> None:
    """Hand-written formatting (indentation, trailing comment) is still matched."""
    target = CUSTOM_PRIM_BELS[0]
    module = target.rsplit("/", 1)[-1].removesuffix(".v")
    prims_path = cli.projectDir / "user_design" / "custom_prims.v"
    prims_path.write_text(
        f"  (* blackbox *)\n"
        f"  module {module} (\n    input stale_port\n  );\n"
        f"  endmodule // {module}\n"
    )

    run_cmd(cli, f"add_as_custom_prim --overwrite {cli.projectDir / target}")

    prims = custom_prims_file(cli)
    assert "stale_port" not in prims
    assert prims.count(f"module {module} (") == 1


def test_add_as_custom_prim_missing_file_errors(cli: FABulousREPL) -> None:
    """A non-existent RTL file is rejected before anything is written."""
    before = custom_prims_file(cli)

    with pytest.raises(CommandError, match="does_not_exist.v"):
        cli.get_command_func("add_as_custom_prim")("does_not_exist.v")

    assert custom_prims_file(cli) == before
