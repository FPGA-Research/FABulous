"""Core implementation for switch-block factorization."""

from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer.core.factorizer import (  # noqa: E501
    SwitchBlockFactorizer,
)
from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer.core.models import (
    MuxReductionRule,
    SwitchBlockFactorizerOptions,
    SwitchBlockFactorizerResult,
    SwitchBlockFactorizerStats,
)

__all__ = [
    "MuxReductionRule",
    "SwitchBlockFactorizer",
    "SwitchBlockFactorizerOptions",
    "SwitchBlockFactorizerResult",
    "SwitchBlockFactorizerStats",
]
