"""Yosys tool wrapper: converts Verilog into Yosys's JSON netlist format.

Used as a singleton through classmethods (`YosysTool.convert_to_json(...)`,
`YosysTool.run(...)`); never instantiated.
"""

from pathlib import Path

from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool


class YosysTool(Tool):
    """Yosys wrapper backed by the Yosys executable.

    Converts Verilog into Yosys's JSON netlist format. Used as a singleton: call
    the classmethods directly, never instantiate.
    """

    @classmethod
    def executable(cls) -> Path | str:
        """Return the Yosys executable from the FABulous context.

        Returns
        -------
        Path | str
            The configured Yosys executable.
        """
        return get_context().yosys_path

    @classmethod
    def convert_to_json(cls, verilog_input: Path, json_output: Path) -> None:
        """Convert a Verilog file to Yosys's JSON format."""
        cls.run(
            args=[
                "-q",
                (
                    "-p "
                    f"read_verilog -sv {verilog_input}; "
                    "hierarchy -auto-top; "
                    "proc -noopt; "
                    f"write_json -compat-int {json_output}"
                ),
            ]
        )
