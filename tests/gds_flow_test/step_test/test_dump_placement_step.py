"""Tests for the DumpPlacement step."""

from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.formats import PLACEMENT_FORMAT
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MAPPING_VARIABLE,
    TILE_INTERFACE_VARIABLE,
)
from fabulous.fabric_generator.gds_generator.steps.dump_placement import DumpPlacement


def test_skips_when_both_switches_are_off(
    mock_config: Config, mock_state: State
) -> None:
    step = DumpPlacement(mock_config, mock_state)
    step.config = mock_config.copy(
        **{CONFIG_MAPPING_VARIABLE.name: False, TILE_INTERFACE_VARIABLE.name: False}
    )

    assert step.run(mock_state) == ({}, {})


def test_command_targets_the_step_directory(
    mock_config: Config, mock_state: State, mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "librelane.steps.odb.OdbpyStep.get_command",
        return_value=["openroad", "-python", "dump_placement.py"],
    )
    step = DumpPlacement(mock_config, mock_state)
    step.config = mock_config.copy(**{CONFIG_MAPPING_VARIABLE.name: True})
    step.step_dir = str(tmp_path)

    command = step.get_command()

    assert command[-2] == "--placement-out"
    assert command[-1] == str(tmp_path / "test_design.placement.json")


@pytest.mark.parametrize(
    "switch", [CONFIG_MAPPING_VARIABLE.name, TILE_INTERFACE_VARIABLE.name]
)
def test_run_publishes_the_placement_view(
    mock_config: Config,
    mock_state: State,
    mocker: MockerFixture,
    tmp_path: Path,
    switch: str,
) -> None:
    mocker.patch(
        "fabulous.fabric_generator.gds_generator.steps.dump_placement.OdbpyStep.run",
        return_value=({}, {"design__instance__count": 3}),
    )
    step = DumpPlacement(mock_config, mock_state)
    step.config = mock_config.copy(**{switch: True})
    step.step_dir = str(tmp_path)

    views, metrics = step.run(mock_state)

    assert set(views) == {PLACEMENT_FORMAT}
    assert str(views[PLACEMENT_FORMAT]) == str(tmp_path / "test_design.placement.json")
    assert metrics == {"design__instance__count": 3}
    assert DumpPlacement.outputs == [PLACEMENT_FORMAT]
