"""Built-in plugin registering the nextpnr place-and-route model."""

from loguru import logger

from fabulous.fabric_cad import gen_npnr_model
from fabulous.fabric_cad.gen_nextpnr_model import (
    emit_nextpnr_model,
    set_placeholder_timing,
)
from fabulous.fabric_cad.timing_model.FABulous_timing_model_interface import (
    FABulousTimingModelInterface,
)
from fabulous.fabric_cad.timing_model.models import TimingModelTarget
from fabulous.fabric_definition.define import PnRTool
from fabulous.fabric_definition.fabric import Fabric
from fabulous.plugins import hookimpl
from fabulous.plugins.types import PnRModelProvider


def generate_nextpnr_model(
    fabric: Fabric,
    delay_model: FABulousTimingModelInterface | None = None,
    target: TimingModelTarget = TimingModelTarget.BOTH,
) -> dict[str, str | bytes]:
    """Build the nextpnr model of `fabric` as file name to file content.

    Without a delay model, the files come from the timing set on the fabric; a
    fabric without timing gets the placeholder timing first. With one, the
    legacy generator characterises the delays, because `timing_model` does not
    yet set its timing on the fabric.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    delay_model : FABulousTimingModelInterface | None
        Timing model interface providing real delays. Defaults to None.
    target : TimingModelTarget
        Which delays to take from `delay_model`. Ignored without one.

    Returns
    -------
    dict[str, str | bytes]
        The nextpnr file names mapped to their content.
    """
    if delay_model is not None:
        return gen_npnr_model.generate_nextpnr_model(fabric, delay_model, target)
    if fabric.has_timing:
        logger.info("Using the timing already set on the fabric.")
    else:
        set_placeholder_timing(fabric)
    return emit_nextpnr_model(fabric).files()


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
            tool=PnRTool.NEXTPNR,
            generate=generate_nextpnr_model,
            supports_timing=True,
            name=PnRTool.NEXTPNR.value,
        )
    ]
