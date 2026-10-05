"""Tests for FABulousPDN (ODB power connection) step.

This step has custom get_command() logic that passes every supply net name.
"""

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.odb_connect_pdn import (
    FABulousPDN,
)


@pytest.mark.parametrize(
    ("overrides", "supply_args"),
    [
        pytest.param(
            {},
            ["--power-names", "VDD", "--ground-names", "VSS"],
            id="config-nets",
        ),
        pytest.param(
            # The tile macros expose exactly the PDK power/ground pins, so on PDKs
            # where those are VDD/VSS (gf180mcuD, ihp-sg13g2) a hardcoded VPWR/VGND
            # fallback would leave the fabric power pins disconnected.
            {"VDD_NETS": None, "GND_NETS": None, "VDD_PIN": "VPIN", "GND_PIN": "GPIN"},
            ["--power-names", "VPIN", "--ground-names", "GPIN"],
            id="falls-back-to-pdk-pins",
        ),
        pytest.param(
            {"VDD_NETS": ["VDD1", "VDD2"], "GND_NETS": ["GND1", "GND2"]},
            [
                "--power-names",
                "VDD1",
                "--power-names",
                "VDD2",
                "--ground-names",
                "GND1",
                "--ground-names",
                "GND2",
            ],
            id="multiple-nets",
        ),
    ],
)
def test_get_command_passes_supply_nets(
    mock_config: Config,
    mock_state: State,
    mocker: MockerFixture,
    overrides: dict,
    supply_args: list[str],
) -> None:
    """Each power net then each ground net is appended behind its own flag."""
    base_command = ["python", "script.py", "--input", "test.odb"]
    mocker.patch("librelane.steps.odb.OdbpyStep.get_command", return_value=base_command)
    config = mock_config.copy(**overrides)

    step = FABulousPDN(config, mock_state)
    step.config = config

    assert step.get_command() == base_command + supply_args
