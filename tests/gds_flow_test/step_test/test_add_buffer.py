"""Tests for AddBuffers step.

This step has custom run() logic that selects between RSZ_CORNERS and STA_CORNERS.
"""

from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers


class TestAddBuffers:
    """Test suite for AddBuffers step - focuses on corner selection logic."""

    def test_run_with_rsz_corners(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test run method uses RSZ_CORNERS when available."""
        mock_config = mock_config.copy(RSZ_CORNERS=["typical", "fast"])

        mock_run = mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.add_buffer.OpenROADStep.run",
            return_value=({}, {}),
        )

        step = AddBuffers(mock_config, mock_state)
        step.step_dir = "/tmp/test"
        step.config = mock_config

        mocker.patch.object(step, "extract_env", return_value=({}, {}))
        step.run(mock_state)

        # Verify corners parameter uses RSZ_CORNERS
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["corners"] == ["typical", "fast"]

    def test_run_fallback_to_sta_corners(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test run method falls back to STA_CORNERS when RSZ_CORNERS is None."""
        mock_config = mock_config.copy(RSZ_CORNERS=None)
        mock_config = mock_config.copy(STA_CORNERS=["typical"])

        mock_run = mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.add_buffer.OpenROADStep.run",
            return_value=({}, {}),
        )

        step = AddBuffers(mock_config, mock_state)
        step.step_dir = "/tmp/test"
        step.config = mock_config

        mocker.patch.object(step, "extract_env", return_value=({}, {}))
        step.run(mock_state)

        # Verify corners parameter falls back to STA_CORNERS
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["corners"] == ["typical"]
