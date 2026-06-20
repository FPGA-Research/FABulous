"""Route routing-pattern requests to registered implementation classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    RoutingPipPattern,
    SwitchMatrixPatternApplyResult,
    SwitchMatrixPatternImplementation,
    SwitchMatrixPatternOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns import (
    lut_carry_rich,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.full import (
    FullRoutingPattern,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.none import (
    NoneRoutingPattern,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.subset import (
    SubsetRoutingPattern,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.universal import (
    UniversalRoutingPattern,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.wilton import (
    WiltonRoutingPattern,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge

PatternImplementation = type[SwitchMatrixPatternImplementation]

_PATTERN_IMPLEMENTATIONS: dict[RoutingPipPattern, PatternImplementation] = {
    RoutingPipPattern.NONE: NoneRoutingPattern,
    RoutingPipPattern.FULL: FullRoutingPattern,
    RoutingPipPattern.SUBSET: SubsetRoutingPattern,
    RoutingPipPattern.WILTON: WiltonRoutingPattern,
    RoutingPipPattern.UNIVERSAL: UniversalRoutingPattern,
    RoutingPipPattern.LUT_CARRY_RICH: (lut_carry_rich.LutCarryRichRoutingPattern),
}


def apply_registered_pattern(
    fpga_model: PnRBridge,
    options: SwitchMatrixPatternOptions,
) -> SwitchMatrixPatternApplyResult:
    """Apply the registered implementation for the selected pattern.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model exposing the FabGraph API.
    options : SwitchMatrixPatternOptions
        Normalized pattern options.

    Returns
    -------
    SwitchMatrixPatternApplyResult
        Pattern-local counts and warnings.
    """
    pattern = _PATTERN_IMPLEMENTATIONS[options.routing_pip_pattern]()
    return pattern.apply(fpga_model, options)
