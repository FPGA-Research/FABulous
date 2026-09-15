"""Tests for FABulousTileIOPlacement and FABulousFabricIOPlacement steps."""

from pathlib import Path

import yaml
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import Side
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    write_interface_order,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    TILE_INTERFACE_ORDER_VARIABLE,
)
from fabulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)


def _segment(pins: list[str]) -> dict:
    return {
        "min_distance": None,
        "max_distance": None,
        "pins": pins,
        "sort_mode": "bus_major",
        "reverse_result": False,
    }


class TestFABulousTileIOPlacement:
    """Test suite for FABulousTileIOPlacement step."""

    def test_get_command_includes_required_parameters(
        self, mock_config: Config, mock_state: State, mocker: MockerFixture
    ) -> None:
        """Test that get_command() includes all required IO placement parameters."""
        mocker.patch(
            "librelane.steps.odb.OdbpyStep.get_command",
            return_value=["python", "script.py"],
        )

        # Add required config values for IO placement
        config = mock_config.copy(
            FABULOUS_IO_PIN_ORDER_CFG="/path/to/config.yaml",
            IO_PIN_H_LAYER="met3",
            IO_PIN_V_LAYER="met4",
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
    ) -> None:
        """Test that get_command() excludes length arguments when not configured."""
        mocker.patch(
            "librelane.steps.odb.OdbpyStep.get_command",
            return_value=["python", "script.py"],
        )

        config = mock_config.copy(
            FABULOUS_IO_PIN_ORDER_CFG="/path/to/config.yaml",
            IO_PIN_H_LAYER="met3",
            IO_PIN_V_LAYER="met4",
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

    def test_config_points_at_the_reordered_yaml_when_an_order_is_set(
        self,
        mock_config: Config,
        mock_state: State,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """An interface order leads each border of the YAML the script reads."""
        mocker.patch(
            "librelane.steps.odb.OdbpyStep.get_command",
            return_value=["python", "script.py"],
        )
        source = tmp_path / "base_io_pin_order.yaml"
        source.write_text(
            yaml.safe_dump(
                {
                    "X0Y0": {
                        "NORTH": [_segment([r"N1BEG\[\d+\]"]), _segment(["UserCLKo"])],
                        "SOUTH": [_segment([r"N1END\[\d+\]"]), _segment(["UserCLK"])],
                    }
                }
            )
        )
        order = tmp_path / "test_design.interface_order.yaml"
        write_interface_order(
            {
                Side.NORTH: ["N1BEG[1]", "N1BEG[0]"],
                Side.SOUTH: ["N1END[1]", "N1END[0]"],
            },
            order,
        )

        step = FABulousTileIOPlacement(mock_config, mock_state)
        step.config = mock_config.copy(
            FABULOUS_IO_PIN_ORDER_CFG=str(source),
            IO_PIN_H_LAYER="met3",
            IO_PIN_V_LAYER="met4",
            IO_PIN_V_THICKNESS_MULT=2.0,
            IO_PIN_H_THICKNESS_MULT=2.0,
            IO_PIN_H_EXTENSION=0.1,
            IO_PIN_V_EXTENSION=0.2,
            ERRORS_ON_UNMATCHED_IO="both",
            **{TILE_INTERFACE_ORDER_VARIABLE.name: str(order)},
        )
        step.step_dir = str(tmp_path)

        command = step.get_command()

        ordered = tmp_path / "test_design_io_pin_order.yaml"
        assert command[command.index("--config") + 1] == str(ordered)
        assert yaml.safe_load(ordered.read_text())["X0Y0"]["NORTH"] == [
            _segment([r"N1BEG\[1\]", r"N1BEG\[0\]"]),
            _segment(["UserCLKo"]),
        ]

    def test_config_stays_the_given_yaml_without_an_order(
        self, mock_config: Config, mock_state: State, mocker: MockerFixture
    ) -> None:
        """Without an order the pin configuration reaches the script untouched."""
        mocker.patch(
            "librelane.steps.odb.OdbpyStep.get_command",
            return_value=["python", "script.py"],
        )
        step = FABulousTileIOPlacement(mock_config, mock_state)
        step.config = mock_config.copy(
            FABULOUS_IO_PIN_ORDER_CFG="/path/to/config.yaml",
            IO_PIN_H_LAYER="met3",
            IO_PIN_V_LAYER="met4",
            IO_PIN_V_THICKNESS_MULT=2.0,
            IO_PIN_H_THICKNESS_MULT=2.0,
            IO_PIN_H_EXTENSION=0.1,
            IO_PIN_V_EXTENSION=0.2,
            ERRORS_ON_UNMATCHED_IO="both",
            **{TILE_INTERFACE_ORDER_VARIABLE.name: None},
        )

        command = step.get_command()

        assert command[command.index("--config") + 1] == "/path/to/config.yaml"
