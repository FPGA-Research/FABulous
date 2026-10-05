"""Tests for AddBuffers step.

This step has custom run() logic that selects between RSZ_CORNERS and STA_CORNERS.
"""

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers


@pytest.mark.parametrize(
    ("rsz_corners", "expected_corners"),
    [
        pytest.param(["typical", "fast"], ["typical", "fast"], id="rsz-corners"),
        pytest.param(None, ["typical"], id="falls-back-to-sta-corners"),
    ],
)
def test_run_selects_corners(
    mocker: MockerFixture,
    mock_config: Config,
    mock_state: State,
    rsz_corners: list[str] | None,
    expected_corners: list[str],
) -> None:
    """RSZ_CORNERS drives the resizer corners; STA_CORNERS stands in when unset."""
    config = mock_config.copy(RSZ_CORNERS=rsz_corners, STA_CORNERS=["typical"])
    mock_run = mocker.patch(
        "fabulous.fabric_generator.gds_generator.steps.add_buffer.OpenROADStep.run",
        return_value=({}, {}),
    )

    step = AddBuffers(config, mock_state)
    step.config = config
    mocker.patch.object(step, "extract_env", return_value=({}, {}))
    step.run(mock_state)

    assert mock_run.call_args.kwargs["corners"] == expected_corners
