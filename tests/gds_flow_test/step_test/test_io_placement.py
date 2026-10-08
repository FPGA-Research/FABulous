"""Tests for the FABulousTileIOPlacement step."""

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)

_BASE_COMMAND = [
    "python",
    "script.py",
    "--config",
    "/path/to/config.yaml",
    "--hor-layer",
    "met3",
    "--ver-layer",
    "met4",
    "--hor-width-mult",
    "2.0",
    "--ver-width-mult",
    "3.0",
    "--hor-extension",
    "0.1",
    "--ver-extension",
    "0.2",
    "--unmatched-error",
    "both",
]


class TestFABulousTileIOPlacement:
    """Test suite for FABulousTileIOPlacement step."""

    @pytest.mark.parametrize(
        ("v_length", "h_length", "length_args"),
        [
            pytest.param(
                5.0, 3.0, ["--ver-length", 5.0, "--hor-length", 3.0], id="both-set"
            ),
            pytest.param(5.0, None, ["--ver-length", 5.0], id="ver-only"),
            pytest.param(None, None, [], id="unset"),
        ],
    )
    def test_get_command(
        self,
        mock_config: Config,
        mock_state: State,
        mocker: MockerFixture,
        v_length: float | None,
        h_length: float | None,
        length_args: list[str | float],
    ) -> None:
        """The command maps each config value to its flag; lengths only when set."""
        mocker.patch(
            "librelane.steps.odb.OdbpyStep.get_command",
            return_value=["python", "script.py"],
        )
        config = mock_config.copy(
            FABULOUS_IO_PIN_ORDER_CFG="/path/to/config.yaml",
            IO_PIN_H_LAYER="met3",
            IO_PIN_V_LAYER="met4",
            IO_PIN_V_THICKNESS_MULT=3.0,
            IO_PIN_H_THICKNESS_MULT=2.0,
            IO_PIN_H_EXTENSION=0.1,
            IO_PIN_V_EXTENSION=0.2,
            ERRORS_ON_UNMATCHED_IO="both",
            IO_PIN_V_LENGTH=v_length,
            IO_PIN_H_LENGTH=h_length,
        )

        step = FABulousTileIOPlacement(config, mock_state)
        step.config = config

        assert step.get_command() == _BASE_COMMAND + length_args

    def test_get_command_requires_pin_order_config(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Without a pin order file there is nothing to place, so it fails loudly."""
        config = mock_config.copy(FABULOUS_IO_PIN_ORDER_CFG=None)
        step = FABulousTileIOPlacement(config, mock_state)
        step.config = config

        with pytest.raises(ValueError, match="FABULOUS_IO_PIN_ORDER_CFG must be set"):
            step.get_command()
