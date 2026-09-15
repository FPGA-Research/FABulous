"""Design formats the FABulous GDS flow steps exchange.

Registered once here, so a reader can take a view back out of a state without
importing the step that wrote it.
"""

from librelane.state.design_format import DesignFormat

PLACEMENT_FORMAT = DesignFormat(
    id="fabulous_placement",
    extension="placement.json",
    full_name="FABulous placement geometry",
)
PLACEMENT_FORMAT.register()

CONFIG_MEM_FORMAT = DesignFormat(
    id="fabulous_config_mem",
    extension="ConfigMem.csv",
    full_name="FABulous configuration memory mapping",
)
CONFIG_MEM_FORMAT.register()

RECONNECT_FORMAT = DesignFormat(
    id="fabulous_config_mapping_reconnect",
    extension="reconnect.json",
    full_name="FABulous configuration mapping reconnections",
)
RECONNECT_FORMAT.register()

TILE_INTERFACE_ORDER_FORMAT = DesignFormat(
    id="fabulous_tile_interface_order",
    extension="interface_order.yaml",
    full_name="FABulous tile interface order",
)
TILE_INTERFACE_ORDER_FORMAT.register()
