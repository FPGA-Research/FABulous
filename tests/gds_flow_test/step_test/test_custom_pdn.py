"""Tests for CustomGeneratePDN step.

This step only customizes the default PDN_CFG path. The script path and other
functionality are inherited from OpenROADStep and tested by librelane.
"""

from librelane.config.config import Config
from librelane.state.state import State

from FABulous.fabric_generator.gds_generator.steps.custom_pdn import CustomGeneratePDN


class TestCustomGeneratePDN:
    """Test suite for CustomGeneratePDN step - focuses on custom PDN config."""

    def test_pdn_cfg_default_is_custom(self) -> None:
        """Test that PDN_CFG has a custom FABulous default (not librelane default)."""
        pdn_cfg_var = next(
            var for var in CustomGeneratePDN.config_vars if var.name == "PDN_CFG"
        )
        assert pdn_cfg_var.default is not None
        assert "pdn_config.tcl" in str(pdn_cfg_var.default)
        assert "FABulous" in str(pdn_cfg_var.default)

    def test_get_script_path(self, mock_config: Config, mock_state: State) -> None:
        """Test that get_script_path returns the correct script path."""
        step = CustomGeneratePDN(mock_config, mock_state)
        script_path = step.get_script_path()
        assert "FABulous/fabric_generator/gds_generator/script/pdn.tcl" in script_path
