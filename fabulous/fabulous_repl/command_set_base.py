"""Shared infrastructure for FABulous REPL command groups.

Collects the pieces every CommandSet module needs — help-display category
names, package-wide constants, and the typed CommandSet base — in one
dependency-free module so the CommandSet modules and the REPL class can import
them without creating an import cycle back into the REPL module.

`ReplCommandSet` is a thin alias over `cmd2.CommandSet` parametrised with the
REPL type, so command groups get `self._cmd` typed as `FABulousREPL` without
each module repeating the `TYPE_CHECKING` forward-reference dance. At runtime
it is plain `CommandSet`; the parametrisation exists only for type checkers.
"""

from typing import TYPE_CHECKING

from cmd2 import CommandSet

# Help-display category names, shared by the REPL class and every CommandSet so
# command grouping stays consistent.
CMD_SETUP = "Setup"
CMD_FABRIC_FLOW = "Fabric Flow"
CMD_USER_DESIGN_FLOW = "User Design Flow"
CMD_HELPER = "Helper"
CMD_OTHER = "Other"
CMD_GUI = "GUI"
CMD_SCRIPT = "Script"
CMD_TOOLS = "Tools"
CMD_TIMING_MODEL = "Timing Characterization"

# Directory holding FABulous project metadata.
META_DATA_DIR = ".FABulous"

if TYPE_CHECKING:
    from fabulous.fabulous_repl.fabulous_repl import FABulousREPL

    ReplCommandSet = CommandSet[FABulousREPL]
else:
    ReplCommandSet = CommandSet
