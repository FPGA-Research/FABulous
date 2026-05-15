"""SAT-based configurable circuit equivalence.

This package provides circuit builders, BLIF import, fast LUT targets, and a CEGIS
solver for finding configurations that make two circuits equivalent.
"""

from fabulous.fabric_cad.fabxplore.modules.sat_fab.cegis import Equiv, EquivOptions
from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import Circuit, Node, Signal
from fabulous.fabric_cad.fabxplore.modules.sat_fab.config import (
    ConfigKey,
    ConfigMode,
    ConfigSpec,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.functions import Func
from fabulous.fabric_cad.fabxplore.modules.sat_fab.import_blif import (
    BlifModel,
    BlifNames,
    BlifSubckt,
    SequentialMode,
    blif_names_to_init,
    parse_blif,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.input_mapping import (
    InputHandle,
    InputRoute,
    InputRouteSpec,
    InputSource,
    InputSourceKind,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.result import (
    CircuitConfig,
    EquivResult,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.truth import (
    TruthTableSpec,
    init_from_function,
)

__all__ = [
    "BlifModel",
    "BlifNames",
    "BlifSubckt",
    "Circuit",
    "CircuitConfig",
    "ConfigKey",
    "ConfigMode",
    "ConfigSpec",
    "Equiv",
    "EquivOptions",
    "EquivResult",
    "Func",
    "InputHandle",
    "InputRoute",
    "InputRouteSpec",
    "InputSource",
    "InputSourceKind",
    "Node",
    "Signal",
    "SequentialMode",
    "TruthTableSpec",
    "blif_names_to_init",
    "init_from_function",
    "parse_blif",
]
