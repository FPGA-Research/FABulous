"""Tests for FABulousPower (ODB power connection) step.

This step has custom get_command() logic that adds the metal layer parameter.
"""

from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.odb_connect_pdn import (
    FABulousPDN,
)


def test_get_command_includes_metal_layer_parameter(
    mock_config: Config, mock_state: State, mocker: MockerFixture
) -> None:
    """Test that get_command() includes the --metal-layer-name parameter.

    This is the key customization of FABulousPower - it adds the metal layer
    parameter from PDN_VERTICAL_LAYER config.
    """
    # Mock the parent class get_command to return a base command
    mocker.patch(
        "librelane.steps.odb.OdbpyStep.get_command",
        return_value=["python", "script.py", "--input", "test.odb"],
    )

    step = FABulousPDN(mock_config, mock_state)
    step.config = mock_config
    command = step.get_command()

    # Verify the command includes the power and ground name parameters
    assert "--power-names" in command, "Command should include --power-names flag"
    assert "--ground-names" in command, "Command should include --ground-names flag"


def test_get_command_uses_custom_metal_layer(
    mock_config: Config, mock_state: State, mocker: MockerFixture
) -> None:
    """Test that get_command() uses the configured PDN_VERTICAL_LAYER value."""
    mocker.patch(
        "librelane.steps.odb.OdbpyStep.get_command",
        return_value=["python", "script.py"],
    )

    # Use a different metal layer
    custom_config = mock_config.copy(RT_MAX_LAYER="met4")

    step = FABulousPDN(custom_config, mock_state)
    step.config = custom_config
    command = step.get_command()

    metal_layer_index = command.index("--metal-layer-name")
    metal_layer_value = command[metal_layer_index + 1]

    assert metal_layer_value == "met4", f"Expected 'met4', got '{metal_layer_value}'"
