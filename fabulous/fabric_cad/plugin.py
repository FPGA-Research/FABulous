"""Built-in plugin registering the nextpnr place-and-route model."""

from fabulous.fabric_cad.gen_npnr_model import generate_nextpnr_model
from fabulous.fabric_definition.define import PnRTool
from fabulous.plugins import hookimpl
from fabulous.plugins.types import PnRModelProvider


@hookimpl
def fabulous_register_pnr_models() -> list[PnRModelProvider]:
    """Register the built-in nextpnr place-and-route model backend.

    Returns
    -------
    list[PnRModelProvider]
        A provider for the nextpnr model.
    """
    return [
        PnRModelProvider(
            PnRTool.NEXTPNR, generate_nextpnr_model, True, PnRTool.NEXTPNR.value
        )
    ]
