"""Extract PDK placement site dimensions step.

This step extracts standard cell placement site dimensions from the PDK technology LEF
using OpenROAD's ODB API. The dimensions are written to metrics for use by flows that
need to work with site-aligned dimensions.
"""

from decimal import Decimal
from importlib import resources

from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.openroad import Floorplan
from librelane.steps.step import Step


@Step.factory.register()
class ExtractPDKInfo(Floorplan):
    """Extract placement site dimensions from PDK technology LEF.

    This step runs an ODB Python script that extracts the primary CORE
    placement site dimensions (width and height in database units) from
    the loaded technology LEF file.

    Outputs
    -------
    Metrics:
        pdk__site_width_dbu : int
            Placement site width in database units
        pdk__site_height_dbu : int
            Placement site height in database units
    """

    id = "FABulous.ExtractPDKInfo"
    name = "Extract PDK Site Dimensions"
    long_name = "Extract PDK Site Dimensions"

    inputs = [DesignFormat.NETLIST]
    outputs = []

    def get_script_path(self) -> str:
        """Return path to the ODB Python script."""
        return str(
            resources.files("fabulous.backend.gds.script")
            / "extract_site_info.tcl"
        )

    def run(self, state_in: State, **kwargs: str) -> tuple[dict, dict]:
        """Run the step and extract site dimensions into metrics."""
        views_updates, metrics_updates = super().run(state_in, **kwargs)
        # Merge new metrics into existing metrics
        metrics_updates["pdk__site_width"] = Decimal(
            metrics_updates["pdk__site_width"].strip()
        )
        metrics_updates["pdk__site_height"] = Decimal(
            metrics_updates["pdk__site_height"].strip()
        )
        return views_updates, metrics_updates
