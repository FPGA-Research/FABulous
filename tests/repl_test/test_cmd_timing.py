"""Tests for timing-model command target and output selection."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.timing_model.models import (
    TimingModelConfig,
    TimingModelMode,
    TimingModelTarget,
)
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_settings import get_context


@pytest.mark.parametrize(
    ("target_option", "expected_target"),
    [
        pytest.param("", TimingModelTarget.BOTH, id="default-both"),
        pytest.param("--target pips", TimingModelTarget.PIPS, id="pips"),
        pytest.param("--target bels", TimingModelTarget.BELS, id="bels"),
    ],
)
def test_timing_command_passes_target_and_output_paths_to_api(
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
        return_value=resolved_config,
    )
    pip_path = tmp_path / "custom-pips.txt"
    bel_path = tmp_path / "custom-bel.v3.txt"

    cli.onecmd_plus_hooks(
        f"timing_model --mode structural {target_option} "
        f"--outfile {pip_path} --bel-outfile {bel_path}"
    )

    timing_api.assert_called_once_with(
        mode="structural",
        output_file=pip_path,
        debug=cli.debug,
        manual_config=None,
        target=expected_target,
        bel_output_file=bel_path,
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
    resolved_config = mocker.Mock()
    resolved_config.model_dump_json.return_value = "{}"
    timing_api = mocker.patch.object(
        cli.fabulousAPI,
        "timing_model_interface",
        return_value=resolved_config,
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
        output_file=proj_dir / "out" / "pips.txt",
        debug=cli.debug,
        manual_config=config,
        target=TimingModelTarget.BOTH,
        bel_output_file=proj_dir / "out" / "bel.v3.txt",
    )


def test_timing_api_passes_target_to_nextpnr_writer(
    cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
) -> None:
    """The public API keeps its existing call shape and forwards output selection."""
    manual_config = mocker.Mock()
    fabric = mocker.Mock()
    cli.fabulousAPI.fabric = fabric
    timing_interface = mocker.patch(
        "fabulous.fabulous_api.FABulousTimingModelInterface"
    )
    timing_writer = mocker.patch(
        "fabulous.fabulous_api.model_gen_npnr.write_nextpnr_timing_files"
    )
    pip_path = tmp_path / "pips.txt"
    bel_path = tmp_path / "bel.v3.txt"

    result = cli.fabulousAPI.timing_model_interface(
        mode="structural",
        output_file=pip_path,
        debug=False,
        manual_config=manual_config,
        target=TimingModelTarget.BELS,
        bel_output_file=bel_path,
    )

    assert result is manual_config
    timing_interface.assert_called_once_with(config=manual_config, fabric=fabric)
    timing_writer.assert_called_once_with(
        fabric=fabric,
        pip_output_file=pip_path,
        bel_output_file=bel_path,
        delay_model=timing_interface.return_value,
        target=TimingModelTarget.BELS,
    )
