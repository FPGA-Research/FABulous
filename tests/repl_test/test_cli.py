"""Test module for FABulous CLI command functionality.

This module contains tests for various CLI commands including fabric generation, tile
generation, bitstream creation, simulation execution, and GUI commands.
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList
from fabulous.fabulous_repl.cmd_macro import _resolve_directional_fix
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_repl.helper import create_project, setup_logger
from fabulous.fabulous_settings import init_context, reset_context
from tests.conftest import (
    normalize_and_check_for_errors,
    run_cmd,
)
from tests.repl_test.conftest import MOCK_COMPLETED_PROCESS, TILE, find_task_calls

SIM_CMD = "run_simulation fst ./user_design/sequential_16bit_en.bin"


def test_load_fabric(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test loading fabric from CSV file."""

    run_cmd(cli, "load_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Loading fabric" in log[0]
    assert "Complete" in log[-1]


def test_gen_config_mem(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating configuration memory."""
    run_cmd(cli, f"gen_config_mem {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating Config Memory for {TILE}" in log[0]
    assert "ConfigMem generation complete" in log[-1]


def test_gen_switch_matrix(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating switch matrix."""
    run_cmd(cli, f"gen_switch_matrix {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating switch matrix for {TILE}" in log[0]
    assert "Switch matrix generation complete" in log[-1]


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


def test_gen_tile(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating tile."""
    run_cmd(cli, f"gen_tile {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating tile {TILE}" in log[0]
    assert "Tile generation complete" in log[-1]


def test_gen_all_tile(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating all tiles."""
    run_cmd(cli, "gen_all_tile")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating all tiles" in log[0]
    assert "All tiles generation complete" in log[-1]


def test_gen_fabric(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating fabric."""
    run_cmd(cli, "gen_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating fabric " in log[0]
    assert "Fabric generation complete" in log[-1]


def test_gen_geometry(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating geometry."""
    # Test with default padding
    run_cmd(cli, "gen_geometry")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating geometry" in log[0]
    assert "geometry generation complete" in log[-2].lower()

    # Test with custom padding
    run_cmd(cli, "gen_geometry 16")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating geometry" in log[0]
    assert "can now be imported into fabulator" in log[-1].lower()


def test_gen_top_wrapper(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating top wrapper."""
    run_cmd(cli, "gen_top_wrapper")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating top wrapper" in log[0]
    assert "Top wrapper generation complete" in log[-1]


def test_run_fab(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test running FABulous fabric flow."""
    run_cmd(cli, "run_fab")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Running FABulous" in log[0]
    assert "FABulous fabric flow complete" in log[-1]


def test_run_FABulous_fabric_deprecated(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """Test the deprecated `run_FABulous_fabric` alias delegates to `run_fab`."""
    run_cmd(cli, "run_FABulous_fabric")

    assert any("deprecated" in r.message.lower() for r in caplog.records)
    assert any("run_fab" in r.message for r in caplog.records)
    log = normalize_and_check_for_errors(caplog.text)
    assert "FABulous fabric flow complete" in log[-1]


def test_gen_model_npnr(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating nextpnr model."""
    run_cmd(cli, "gen_model_npnr")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating npnr model" in log[0]
    assert "Generated npnr model" in log[-1]


def test_gen_io_pin_config(cli: FABulousREPL, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating an IO pin configuration YAML file for a tile."""
    output_file = cli.projectDir / "Tile" / TILE / f"{TILE}_io_pin_order.yaml"

    assert not output_file.exists()

    run_cmd(cli, f"gen_io_pin_config {TILE}")
    log = normalize_and_check_for_errors(caplog.text)

    assert f"Generating IO pin config for {TILE}" in log[0]
    assert "IO pin config generation complete" in log[-1]
    assert output_file.exists()


def test_gen_tile_macro_with_io_pin_config_skips_generation(
    cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
) -> None:
    """`gen_tile_macro --io-pin-config <file>` uses the user-provided pin config."""
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
    )
    gen_pin_order_spy = mocker.spy(cli.fabulousAPI, "gen_io_pin_order_config")
    gen_tile_macro_mock = mocker.patch.object(cli.fabulousAPI, "genTileMacro")

    user_pin_config = tmp_path / "custom_pin_config.yaml"
    user_pin_config.touch()

    run_cmd(cli, f"gen_tile_macro {TILE} --io-pin-config {user_pin_config}")

    gen_pin_order_spy.assert_not_called()
    gen_tile_macro_mock.assert_called_once()
    assert gen_tile_macro_mock.call_args.args[1] == user_pin_config.resolve()


def test_gen_tile_macro_without_io_pin_config_generates_for_tile(
    cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Without `--io-pin-config`, the CLI auto-generates the pin order for a tile."""
    mocker.patch(
        "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
    )
    gen_pin_order_mock = mocker.patch.object(cli.fabulousAPI, "gen_io_pin_order_config")
    gen_tile_macro_mock = mocker.patch.object(cli.fabulousAPI, "genTileMacro")

    run_cmd(cli, f"gen_tile_macro {TILE}")

    expected_pin_order = cli.projectDir / "Tile" / TILE / f"{TILE}_io_pin_order.yaml"
    gen_pin_order_mock.assert_called_once()
    assert gen_pin_order_mock.call_args.args[1] == expected_pin_order
    assert gen_tile_macro_mock.call_args.args[1] == expected_pin_order


def test_run_FABulous_bitstream_deprecated(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
) -> None:
    """Test the deprecated `run_FABulous_bitstream` delegates to compile_design."""
    mocker.patch("subprocess.run", return_value=MOCK_COMPLETED_PROCESS)
    run_cmd(cli, "run_fab")

    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")

    assert any("deprecated" in r.message.lower() for r in caplog.records)
    assert any("compile_design" in r.message for r in caplog.records)


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test running simulation via Taskfile."""
    run_cmd(cli, SIM_CMD)
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_makefile_fallback(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test simulation falls back to Makefile with deprecation warning."""
    # Remove Taskfile.yml so it falls back to Makefile
    (cli.projectDir / "Test" / "Taskfile.yml").unlink()

    caplog.clear()
    run_cmd(cli, SIM_CMD)

    assert any("deprecated" in r.message.lower() for r in caplog.records)
    assert any("Simulation finished" in r.message for r in caplog.records)


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_no_taskfile_no_makefile(
    cli: FABulousREPL,
) -> None:
    """Test simulation errors when neither Taskfile.yml nor Makefile exists."""
    # Remove both Taskfile.yml and Makefile
    test_dir = cli.projectDir / "Test"
    (test_dir / "Taskfile.yml").unlink()
    (test_dir / "Makefile").unlink(missing_ok=True)

    run_cmd(cli, SIM_CMD)
    assert cli.exit_code != 0


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_with_extra_flags(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test simulation passes extra iverilog flags to Taskfile."""
    run_cmd(cli, f'{SIM_CMD} --extra-iverilog-flag="-DSOME_DEFINE"')
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]

    task_cmds = find_task_calls()
    assert len(task_cmds) >= 1
    assert any("EXTRA_IVERILOG_FLAGS" in arg for arg in task_cmds[-1])


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_with_extra_nvc_flag(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test simulation passes --extra-nvc-flag to Taskfile as EXTRA_NVC_FLAGS."""
    run_cmd(cli, f'{SIM_CMD} --extra-nvc-flag="--ieee-warnings=error"')
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]

    task_cmds = find_task_calls()
    assert len(task_cmds) >= 1
    assert any("EXTRA_NVC_FLAGS" in arg for arg in task_cmds[-1])


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_with_simulator_flag(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test simulation passes --simulator to Taskfile as SIMULATOR."""
    for sim in ("nvc", "ghdl", "auto"):
        run_cmd(cli, f"{SIM_CMD} --simulator={sim}")
        log = normalize_and_check_for_errors(caplog.text)
        assert "Simulation finished" in log[-1]

        task_cmds = find_task_calls()
        assert len(task_cmds) >= 1
        assert any(f"SIMULATOR={sim}" in arg for arg in task_cmds[-1])


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_with_design_flag(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test simulation passes --design flag to Taskfile as DESIGN variable."""
    run_cmd(cli, f"{SIM_CMD} -d my_custom_design")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]

    task_cmds = find_task_calls()
    assert len(task_cmds) >= 1
    assert any("DESIGN=my_custom_design" in arg for arg in task_cmds[-1])


def test_run_tcl_with_tcl_command(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Test running a Tcl script with tcl command."""
    script_content = '# Dummy Tcl script\nputs "Text from tcl"'
    tcl_script_path = tmp_path / "test_script.tcl"
    with tcl_script_path.open("w") as f:
        f.write(script_content)

    run_cmd(cli, f"run_tcl {str(tcl_script_path)}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Execute TCL script {str(tcl_script_path)}" in log[0]
    assert "TCL script executed" in log[-1]


def test_run_tcl_with_fabulous_command(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Test running a Tcl script with FABulous command."""
    test_script = tmp_path / "test_script.tcl"
    test_script.write_text(
        "load_fabric\n"
        "gen_user_design_wrapper user_design/sequential_16bit_en.v "
        "user_design/top_wrapper.v\n"
    )
    run_cmd(cli, f"run_tcl {test_script}")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generated user design top wrapper" in log[-2]
    assert "TCL script executed" in log[-1]


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
            "ihp-sg13g2",
            "sg13g2.lyp",
            True,
            id="ihp_sg13g2_fresh_ciel_install",
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
    """The layer file resolves to `pdk_root/<pdk>/libs.tech/klayout/tech/<lyp>`.

    Covers both branches: ciel auto-resolution of `pdk_root` (fresh install)
    and an explicit `FAB_PDK_ROOT`
    """
    reset_context()
    for key in list(os.environ.keys()):
        if key.startswith("FAB_"):
            monkeypatch.delenv(key, raising=False)

    # tests/conftest.py patches get_ciel_home() to `tmp_path/.ciel`.
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


class TestResolveDirectionalFix:
    """`_resolve_directional_fix` maps a fix flag onto a directional mode."""

    def test_fix_height_implies_find_min_width(self) -> None:
        mode, die_area = _resolve_directional_fix(OptMode.NO_OPT, None, Decimal(245))
        assert mode == OptMode.FIND_MIN_WIDTH
        assert die_area == [0, 0, Decimal(245), Decimal(245)]

    def test_fix_width_implies_find_min_height(self) -> None:
        mode, die_area = _resolve_directional_fix(OptMode.NO_OPT, Decimal(246), None)
        assert mode == OptMode.FIND_MIN_HEIGHT
        assert die_area == [0, 0, Decimal(246), Decimal(246)]

    def test_fix_height_consistent_with_explicit_mode(self) -> None:
        mode, _ = _resolve_directional_fix(OptMode.FIND_MIN_WIDTH, None, Decimal(245))
        assert mode == OptMode.FIND_MIN_WIDTH

    def test_fix_height_conflicts_with_find_min_height(self) -> None:
        with pytest.raises(
            ValueError, match="only valid with --optimise find_min_width"
        ):
            _resolve_directional_fix(OptMode.FIND_MIN_HEIGHT, None, Decimal(245))

    def test_fix_width_conflicts_with_balance(self) -> None:
        with pytest.raises(
            ValueError, match="only valid with --optimise find_min_height"
        ):
            _resolve_directional_fix(OptMode.BALANCE, Decimal(246), None)

    def test_both_fix_flags_raise(self) -> None:
        with pytest.raises(ValueError, match="only one of"):
            _resolve_directional_fix(OptMode.NO_OPT, Decimal(246), Decimal(245))

    def test_no_fix_flags_passthrough(self) -> None:
        mode, die_area = _resolve_directional_fix(OptMode.BALANCE, None, None)
        assert mode == OptMode.BALANCE
        assert die_area is None


class TestGenTileMacroFlags:
    """End-to-end CLI wiring for the explicit size flags."""

    def _patch(self, cli: FABulousREPL, mocker: MockerFixture) -> MockerFixture:
        mocker.patch(
            "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
        )
        mocker.patch.object(cli.fabulousAPI, "gen_io_pin_order_config")
        return mocker.patch.object(cli.fabulousAPI, "genTileMacro")

    def test_fix_height_sets_mode_and_die_area(
        self, cli: FABulousREPL, mocker: MockerFixture
    ) -> None:
        gen_macro = self._patch(cli, mocker)

        run_cmd(cli, f"gen_tile_macro {TILE} --fix-height 245")

        kwargs = gen_macro.call_args.kwargs
        assert kwargs["optimisation"] == OptMode.FIND_MIN_WIDTH
        overrides = kwargs["custom_config_overrides"]
        assert overrides["DIE_AREA"] == [0, 0, Decimal(245), Decimal(245)]
        assert overrides["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_WIDTH

    def test_fix_width_sets_mode_and_die_area(
        self, cli: FABulousREPL, mocker: MockerFixture
    ) -> None:
        gen_macro = self._patch(cli, mocker)

        run_cmd(cli, f"gen_tile_macro {TILE} --fix-width 246")

        kwargs = gen_macro.call_args.kwargs
        assert kwargs["optimisation"] == OptMode.FIND_MIN_HEIGHT
        assert kwargs["custom_config_overrides"]["DIE_AREA"] == [
            0,
            0,
            Decimal(246),
            Decimal(246),
        ]

    def test_fix_height_conflicting_mode_aborts(
        self, cli: FABulousREPL, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        gen_macro = self._patch(cli, mocker)

        run_cmd(
            cli,
            f"gen_tile_macro {TILE} --optimise find_min_height --fix-height 245",
        )

        gen_macro.assert_not_called()
        assert "only valid with --optimise find_min_width" in caplog.text

    def test_override_merges_custom_yaml(
        self, cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        gen_macro = self._patch(cli, mocker)
        override = tmp_path / "ov.yaml"
        override.write_text("DIODE_ON_PORTS: both\n")

        run_cmd(cli, f"gen_tile_macro {TILE} --override {override}")

        assert (
            gen_macro.call_args.kwargs["custom_config_overrides"]["DIODE_ON_PORTS"]
            == "both"
        )


class TestRunEFPGAMacroForwarding:
    """End-to-end CLI wiring: flags forwarded to the API entrypoint."""

    def _patch(self, cli: FABulousREPL, mocker: MockerFixture) -> MockerFixture:
        mocker.patch(
            "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=True
        )
        return mocker.patch.object(cli.fabulousAPI, "full_fabric_automation")

    def test_forwards_nlp_flags(self, cli: FABulousREPL, mocker: MockerFixture) -> None:
        full_auto = self._patch(cli, mocker)

        run_cmd(cli, "run_FABulous_eFPGA_macro --nlp-only --nlp-area-margin 0.1")

        full_auto.assert_called_once()
        kwargs = full_auto.call_args.kwargs
        assert kwargs["nlp_only"] is True
        assert kwargs["nlp_area_margin"] == pytest.approx(0.1)
        assert kwargs["tile_opt_config"] is None

    def test_forwards_defaults(self, cli: FABulousREPL, mocker: MockerFixture) -> None:
        full_auto = self._patch(cli, mocker)

        run_cmd(cli, "run_FABulous_eFPGA_macro")

        kwargs = full_auto.call_args.kwargs
        assert kwargs["nlp_only"] is False
        assert kwargs["nlp_area_margin"] == pytest.approx(0.05)
        assert kwargs["tile_opt_config"] is None

    def test_forwards_tile_opt_info_as_path(
        self, cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        full_auto = self._patch(cli, mocker)
        summary = tmp_path / "tile_optimisation_summary.json"
        summary.touch()

        run_cmd(cli, f"run_FABulous_eFPGA_macro --tile-opt-info {summary}")

        tile_opt_config = full_auto.call_args.kwargs["tile_opt_config"]
        assert tile_opt_config == Path(summary)

    def test_skips_when_pdk_not_set(
        self, cli: FABulousREPL, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "fabulous.fabulous_repl.cmd_macro.is_pdk_config_set", return_value=False
        )
        full_auto = mocker.patch.object(cli.fabulousAPI, "full_fabric_automation")

        run_cmd(cli, "run_FABulous_eFPGA_macro")

        full_auto.assert_not_called()
