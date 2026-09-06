"""Tests for the ApplyConfigMapping step."""

import json
from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MAPPING_RECONNECT_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
)
from fabulous.fabric_generator.gds_generator.steps.apply_config_mapping import (
    ApplyConfigMapping,
)


def _report(tmp_path: Path, reconnected: int, errors: list[str]) -> Path:
    report = tmp_path / "test_design.reconnect_report.json"
    report.write_text(json.dumps({"reconnected": reconnected, "errors": errors}))
    return report


def test_skips_without_a_reconnect_list(mock_config: Config, mock_state: State) -> None:
    step = ApplyConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            CONFIG_MAPPING_RECONNECT_VARIABLE.name: None,
        }
    )

    assert step.run(mock_state) == ({}, {})


def test_skips_when_the_switch_is_off(
    mock_config: Config, mock_state: State, tmp_path: Path
) -> None:
    step = ApplyConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: False,
            CONFIG_MAPPING_RECONNECT_VARIABLE.name: str(tmp_path / "r.json"),
        }
    )

    assert step.run(mock_state) == ({}, {})


def test_command_passes_the_list_and_the_report(
    mock_config: Config, mock_state: State, mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "librelane.steps.odb.OdbpyStep.get_command",
        return_value=["openroad", "-python", "apply_config_mapping.py"],
    )
    step = ApplyConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            CONFIG_MAPPING_RECONNECT_VARIABLE.name: str(tmp_path / "r.json"),
        }
    )
    step.step_dir = str(tmp_path)

    assert step.get_command()[-4:] == [
        "--reconnect",
        str(tmp_path / "r.json"),
        "--report",
        str(tmp_path / "test_design.reconnect_report.json"),
    ]


def test_run_raises_on_reported_errors(
    mock_config: Config, mock_state: State, mocker: MockerFixture, tmp_path: Path
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> tuple[dict, dict]:
        _report(
            tmp_path,
            0,
            ["lat/D sits on net buf_out, not directly on a frame port net"],
        )
        return {}, {}

    mocker.patch(
        "fabulous.fabric_generator.gds_generator.steps."
        "apply_config_mapping.OdbpyStep.run",
        side_effect=fake_run,
    )
    step = ApplyConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            CONFIG_MAPPING_RECONNECT_VARIABLE.name: str(tmp_path / "r.json"),
        }
    )
    step.step_dir = str(tmp_path)

    with pytest.raises(GDSFlowError, match="buf_out"):
        step.run(mock_state)


def test_run_reports_the_moved_pin_count(
    mock_config: Config, mock_state: State, mocker: MockerFixture, tmp_path: Path
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> tuple[dict, dict]:
        _report(tmp_path, 3, [])
        return {}, {}

    mocker.patch(
        "fabulous.fabric_generator.gds_generator.steps."
        "apply_config_mapping.OdbpyStep.run",
        side_effect=fake_run,
    )
    step = ApplyConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            CONFIG_MAPPING_RECONNECT_VARIABLE.name: str(tmp_path / "r.json"),
        }
    )
    step.step_dir = str(tmp_path)

    views, metrics = step.run(mock_state)

    assert views == {}
    assert metrics == {"fabulous__config_mapping__reconnected_pins": 3}
