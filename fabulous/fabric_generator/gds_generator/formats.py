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
