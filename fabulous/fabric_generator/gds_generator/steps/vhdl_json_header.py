"""Custom JSON-header step that reads VHDL through the GHDL Yosys plugin."""

from importlib import resources

from librelane.steps import pyosys as pyYosys
from librelane.steps.pyosys import JsonHeader, PyosysStep, verilog_rtl_cfg_vars
from librelane.steps.step import Step

# Reuse the exact `VHDL_FILES` / `GHDL_ARGUMENTS` Variable objects declared by
# `Yosys.VHDLSynthesis` so the shared config keys have identical definitions across
# both VHDL steps in a flow.
_vhdl_synth_vars = [
    v
    for v in pyYosys.VHDLSynthesis.config_vars
    if v.name in {"VHDL_FILES", "GHDL_ARGUMENTS"}
]


@Step.factory.register()
class FABulousVHDLJsonHeader(JsonHeader):
    """Generate the JSON header for a VHDL design using GHDL.

    Mirrors `Yosys.JsonHeader` but reads the design through the GHDL frontend
    instead of `read_verilog`, so VHDL tiles still produce the `JSON_HEADER`
    view consumed by `Odb.SetPowerConnections` and `Odb.WriteVerilogHeader`.
    """

    id = "FABulous.VHDLJsonHeader"
    name = "Generate JSON Header (VHDL)"
    long_name = "Generate JSON Header (VHDL)"

    # Drop the required `VERILOG_FILES` variable (a VHDL config never sets it) while
    # keeping the optional Verilog header variables the inherited command/script touch.
    config_vars = (
        PyosysStep.config_vars
        + [v for v in verilog_rtl_cfg_vars if v.name != "VERILOG_FILES"]
        + _vhdl_synth_vars
    )

    def get_script_path(self) -> str:
        """Return the path to the VHDL JSON-header Yosys script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "vhdl_json_header.py"
        )
