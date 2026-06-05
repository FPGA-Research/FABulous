"""Built-in plugin registering the FABulous hardening flows."""

from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
    FABulousFabricVHDLMacroFlow,
)
from fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow import (
    FABulousFabricOptimisationFlow,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
    FABulousTileVHDLMacroFlow,
)
from fabulous.plugins import hookimpl
from fabulous.plugins.types import GdsFlowProvider


@hookimpl
def fabulous_register_gds_flows() -> list[GdsFlowProvider]:
    """Register the built-in tile, fabric, and full-automation flows.

    These are the flows a project gets without any plugin, and the ones a
    `meta.flow` entry names when it wants a specific built-in rather than the
    one the project's HDL language would pick.

    Returns
    -------
    list[GdsFlowProvider]
        Providers for every built-in hardening flow.
    """
    return [
        GdsFlowProvider(flow)
        for flow in (
            FABulousTileVerilogMacroFlow,
            FABulousTileVHDLMacroFlow,
            FABulousFabricMacroFlow,
            FABulousFabricVHDLMacroFlow,
            FABulousFabricOptimisationFlow,
        )
    ]
