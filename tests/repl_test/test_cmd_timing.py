"""Tests for the timing-model command output paths and API wiring."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.timing_model.config import TimingModelConfig, TimingModelMode
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_settings import get_context


def test_timing_command_passes_output_paths_to_api(
    cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
) -> None:
    """The CLI output paths reach the API unchanged."""
    resolved_config = mocker.Mock()
    resolved_config.model_dump_json.return_value = "{}"
    timing_api = mocker.patch.object(
        cli.fabulousAPI,
        "timing_model",
        return_value=resolved_config,
    )
    pip_path = tmp_path / "custom-pips.txt"
    bel_path = tmp_path / "custom-bel.v3.txt"

    cli.onecmd_plus_hooks(
        f"timing_model --mode structural --outfile {pip_path} --bel-outfile {bel_path}"
    )

    timing_api.assert_called_once_with(
        mode=TimingModelMode.STRUCTURAL,
        pip_file=pip_path,
        bel_file=bel_path,
        manual_config=None,
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
        mode=TimingModelMode.STRUCTURAL,
    )
    (proj_dir / ".FABulous" / "timing_config.json").write_text(config.model_dump_json())
    resolved_config = mocker.Mock()
    resolved_config.model_dump_json.return_value = "{}"
    timing_api = mocker.patch.object(
        cli.fabulousAPI,
        "timing_model",
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
        mode=TimingModelMode.STRUCTURAL,
        pip_file=proj_dir / "out" / "pips.txt",
        bel_file=proj_dir / "out" / "bel.v3.txt",
        manual_config=config,
    )


def test_timing_api_writes_characterized_timing(
    cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
) -> None:
    """The public API characterises the fabric and writes both timing files."""
    manual_config = mocker.Mock()
    fabric = mocker.Mock()
    cli.fabulousAPI.fabric = fabric
    characterize = mocker.patch("fabulous.fabulous_api.characterize")
    emit = mocker.patch("fabulous.fabulous_api.emit_nextpnr_model")
    timing_writer = mocker.patch("fabulous.fabulous_api.write_timing_files")
    pip_path = tmp_path / "pips.txt"
    bel_path = tmp_path / "bel.v3.txt"

    result = cli.fabulousAPI.timing_model(
        mode=TimingModelMode.STRUCTURAL,
        pip_file=pip_path,
        bel_file=bel_path,
        manual_config=manual_config,
    )

    assert result is manual_config
    characterize.assert_called_once_with(fabric, manual_config)
    emit.assert_called_once_with(fabric, characterize.return_value)
    timing_writer.assert_called_once_with(
        emit.return_value, pip_file=pip_path, bel_file=bel_path
    )
