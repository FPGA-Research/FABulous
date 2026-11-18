"""Tests for timing-model command target and output selection."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.timing_model.models import (
    TimingModelConfig,
    TimingModelMode,
    TimingModelTarget,
)
from fabulous.fabric_definition.define import PnRTool
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_settings import get_context
from tests.conftest import run_cmd


@pytest.mark.parametrize(
    ("target_option", "expected_target"),
    [
        pytest.param("", TimingModelTarget.BOTH, id="default-both"),
        pytest.param("--target pips", TimingModelTarget.PIPS, id="pips"),
        pytest.param("--target bels", TimingModelTarget.BELS, id="bels"),
    ],
)
def test_timing_command_passes_target_to_api(
    cli: FABulousREPL,
    mocker: MockerFixture,
    tmp_path: Path,
    target_option: str,
    expected_target: TimingModelTarget,
) -> None:
    """CLI target selection reaches the API without changing existing defaults."""
    resolved_config = mocker.Mock()
    resolved_config.model_dump_json.return_value = "{}"
    timing_api = mocker.patch.object(
        cli.fabulousAPI,
        "timing_model_interface",
        return_value=(
            resolved_config,
            {"pips.txt": "timed pips", "bel.v3.txt": "timed bels"},
        ),
    )

    cli.onecmd_plus_hooks(
        f"timing_model --mode structural {target_option} "
        f"--outfile {tmp_path / 'pips.txt'} --bel-outfile {tmp_path / 'bel.v3.txt'}"
    )

    timing_api.assert_called_once_with(
        mode="structural",
        debug=cli.debug,
        manual_config=None,
        tool=PnRTool.NEXTPNR,
        target=expected_target,
    )


def test_timing_command_reads_relative_paths_from_project_dir(
    cli: FABulousREPL,
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative paths name files in the project, wherever FABulous was launched."""
    proj_dir = get_context().proj_dir
    config = TimingModelConfig(
        project_dir=proj_dir,
        liberty_files=Path("cells.lib"),
        min_buf_cell_and_ports="buf A X",
        synth_executable=Path("yosys"),
        sta_executable=Path("sta"),
        mode=TimingModelMode.STRUCTURAL,
    )
    (proj_dir / ".FABulous" / "timing_config.json").write_text(config.model_dump_json())
    (proj_dir / "out").mkdir()
    resolved_config = mocker.Mock()
    resolved_config.model_dump_json.return_value = "{}"
    timing_api = mocker.patch.object(
        cli.fabulousAPI,
        "timing_model_interface",
        return_value=(
            resolved_config,
            {"pips.txt": "timed pips", "bel.v3.txt": "timed bels"},
        ),
    )
    launch_dir = tmp_path / "elsewhere"
    launch_dir.mkdir()
    monkeypatch.chdir(launch_dir)

    cli.onecmd_plus_hooks(
        "timing_model --mode structural "
        "--with-config-file .FABulous/timing_config.json "
        "--outfile out/pips.txt --bel-outfile out/bel.v3.txt"
    )

    timing_api.assert_called_once_with(
        mode="structural",
        debug=cli.debug,
        manual_config=config,
        tool=PnRTool.NEXTPNR,
        target=TimingModelTarget.BOTH,
    )
    assert (proj_dir / "out" / "pips.txt").read_text() == "timed pips"
    assert (proj_dir / "out" / "bel.v3.txt").read_text() == "timed bels"


@pytest.mark.parametrize(
    ("target", "pip_written", "bel_written"),
    [
        pytest.param("pips", True, False, id="pips"),
        pytest.param("bels", False, True, id="bels"),
        pytest.param("both", True, True, id="both"),
    ],
)
def test_timing_command_writes_only_selected_outputs(
    cli: FABulousREPL,
    mocker: MockerFixture,
    tmp_path: Path,
    target: str,
    pip_written: bool,
    bel_written: bool,
) -> None:
    """Only the targeted files are replaced, and each old copy is backed up."""
    pip_path = tmp_path / "custom-pips.txt"
    bel_path = tmp_path / "custom-bel.v3.txt"
    pip_path.write_text("untimed pips")
    bel_path.write_text("untimed bels")
    resolved_config = mocker.Mock()
    resolved_config.model_dump_json.return_value = "{}"
    mocker.patch.object(
        cli.fabulousAPI,
        "timing_model_interface",
        return_value=(
            resolved_config,
            {"pips.txt": "timed pips", "bel.v3.txt": "timed bels"},
        ),
    )

    run_cmd(
        cli,
        f"timing_model --target {target} --outfile {pip_path} --bel-outfile {bel_path}",
    )

    assert cli.exit_code == 0
    expected_pip = "timed pips" if pip_written else "untimed pips"
    expected_bel = "timed bels" if bel_written else "untimed bels"
    assert pip_path.read_text() == expected_pip
    assert bel_path.read_text() == expected_bel
    assert pip_path.with_suffix(".backup.txt").exists() is pip_written
    assert bel_path.with_suffix(".backup.txt").exists() is bel_written


def test_timing_api_forwards_target_to_backend(
    cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """The API hands the delay model and target to the selected backend."""
    manual_config = mocker.Mock()
    fabric = mocker.Mock()
    cli.fabulousAPI.fabric = fabric
    timing_interface = mocker.patch(
        "fabulous.fabulous_api.FABulousTimingModelInterface"
    )
    gen_routing_model = mocker.patch.object(
        cli.fabulousAPI, "gen_routing_model", return_value={"pips.txt": "timed"}
    )

    result = cli.fabulousAPI.timing_model_interface(
        mode="structural",
        debug=False,
        manual_config=manual_config,
        tool=PnRTool.NEXTPNR,
        target=TimingModelTarget.BELS,
    )

    assert result == (manual_config, {"pips.txt": "timed"})
    timing_interface.assert_called_once_with(config=manual_config, fabric=fabric)
    gen_routing_model.assert_called_once_with(
        tool=PnRTool.NEXTPNR,
        delay_model=timing_interface.return_value,
        target=TimingModelTarget.BELS,
    )
