"""Tests for FABulousTileIOPlacement and FABulousFabricIOPlacement steps."""

from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from FABulous.fabric_generator.gds_generator.steps.fabric_IO_placement import (
    FABulousFabricIOPlacement,
)
from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)


class TestFABulousTileIOPlacement:
    """Test suite for FABulousTileIOPlacement step."""

    def test_get_command_includes_required_parameters(
        self, mock_config: Config, mock_state: State, mocker: MockerFixture
    ):
        """Test that get_command() includes all required IO placement parameters."""
        mocker.patch(
            "librelane.steps.odb.OdbpyStep.get_command",
            return_value=["python", "script.py"],
        )

        # Add required config values for IO placement
        config = mock_config.copy(
            FABULOUS_IO_PIN_ORDER_CFG="/path/to/config.yaml",
            FP_IO_HLAYER="met3",
            FP_IO_VLAYER="met4",
            IO_PIN_V_THICKNESS_MULT=2.0,
            IO_PIN_H_THICKNESS_MULT=2.0,
            IO_PIN_H_EXTENSION=0.1,
            IO_PIN_V_EXTENSION=0.2,
            ERRORS_ON_UNMATCHED_IO="both",
            IO_PIN_V_LENGTH=5.0,
            IO_PIN_H_LENGTH=3.0,
        )

        step = FABulousTileIOPlacement(config, mock_state)
        step.config = config
        command = step.get_command()

        # Verify required parameters are present
        assert "--config" in command
        assert "/path/to/config.yaml" in command

        assert "--hor-layer" in command
        hor_layer_idx = command.index("--hor-layer")
        assert command[hor_layer_idx + 1] == "met3"

        assert "--ver-layer" in command
        ver_layer_idx = command.index("--ver-layer")
        assert command[ver_layer_idx + 1] == "met4"

        assert "--unmatched-error" in command
        unmatched_idx = command.index("--unmatched-error")
        assert command[unmatched_idx + 1] == "both"

        # Verify optional length arguments are present when set
        assert "--ver-length" in command
        ver_length_idx = command.index("--ver-length")
        assert command[ver_length_idx + 1] == 5.0

        assert "--hor-length" in command
        hor_length_idx = command.index("--hor-length")
        assert command[hor_length_idx + 1] == 3.0

    def test_get_command_excludes_length_args_when_none(
        self, mock_config: Config, mock_state: State, mocker: MockerFixture
    ):
        """Test that get_command() excludes length arguments when not configured."""
        mocker.patch(
            "librelane.steps.odb.OdbpyStep.get_command",
            return_value=["python", "script.py"],
        )

        config = mock_config.copy(
            FABULOUS_IO_PIN_ORDER_CFG="/path/to/config.yaml",
            FP_IO_HLAYER="met3",
            FP_IO_VLAYER="met4",
            IO_PIN_V_THICKNESS_MULT=2.0,
            IO_PIN_H_THICKNESS_MULT=2.0,
            IO_PIN_H_EXTENSION=0.1,
            IO_PIN_V_EXTENSION=0.2,
            IO_PIN_V_LENGTH=None,
            IO_PIN_H_LENGTH=None,
            ERRORS_ON_UNMATCHED_IO="both",
        )

        step = FABulousTileIOPlacement(config, mock_state)
        step.config = config
        command = step.get_command()

        # Verify optional length arguments are NOT present when None
        assert "--ver-length" not in command
        assert "--hor-length" not in command
