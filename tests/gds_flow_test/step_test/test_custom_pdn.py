"""Tests for CustomGeneratePDN step.

This step only customizes the default PDN_CFG path. The script path and other
functionality are inherited from OpenROADStep and tested by librelane.
"""

from fabulous.fabric_generator.gds_generator.steps.custom_pdn import CustomGeneratePDN


class TestCustomGeneratePDN:
    """Test suite for CustomGeneratePDN step - focuses on custom PDN config."""

    def test_pdn_cfg_default_is_custom(self) -> None:
        """Test that PDN_CFG has a custom FABulous default (not librelane default).

        This validates the key customization of this step - it overrides the default
        PDN_CFG path to point to FABulous's custom pdn_config.tcl file.
        """
        pdn_cfg_var = next(
            var for var in CustomGeneratePDN.config_vars if var.name == "PDN_CFG"
        )
        assert pdn_cfg_var.default is not None, "PDN_CFG must have a default value"
        assert "pdn_config.tcl" in str(pdn_cfg_var.default), (
            "Default should point to pdn_config.tcl"
        )
        assert "FABulous" in str(pdn_cfg_var.default), (
            "Default should be in FABulous package"
        )
