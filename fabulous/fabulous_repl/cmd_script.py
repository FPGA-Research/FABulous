"""Script-execution commands for the FABulous REPL.

Run TCL scripts through the embedded interpreter. Grouped as a CommandSet so it
can be registered and, in future, managed independently of the core REPL.

Note: ``run_script`` stays on the REPL class rather than living here, because it
overrides cmd2's built-in ``run_script`` (which cmd2 also calls internally) and
cmd2 forbids a CommandSet from replacing an existing command attribute.
"""

from pathlib import Path
from typing import Annotated

from cmd2 import with_annotated, with_category
from cmd2.annotated import Argument
from loguru import logger

from fabulous.fabulous_repl.command_set_base import CMD_SCRIPT, ReplCommandSet


class ScriptCommandSet(ReplCommandSet):
    """Commands that execute TCL scripts from the REPL."""

    @with_category(CMD_SCRIPT)
    @with_annotated
    def do_run_tcl(
        self,
        file: Annotated[Path, Argument(help_text="Path to the target file")],
    ) -> None:
        """Execute TCL script relative to the project directory.

        Specified by <tcl_scripts>. Use the 'tk' module to create TCL commands.

        Also logs usage errors and file not found errors.
        """
        repl = self._cmd
        if not file.exists():
            raise FileNotFoundError(
                f"Cannot find {file} file, please check the path and try again."
            )

        if repl.force:
            logger.warning(
                "TCL script does not work with force mode, TCL will stop on first error"
            )

        logger.info(f"Execute TCL script {file}")

        with file.open() as f:
            script = f.read()
        repl.tcl.eval(script)

        logger.info("TCL script executed")
