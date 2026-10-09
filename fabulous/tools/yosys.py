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

    @classmethod
    def convert_netlist_to_json(
        cls, netlist: Path, json_output: Path, *, liberty: list[Path], top: str
    ) -> None:
        """Convert a gate-level netlist to Yosys's JSON format.

        `read_liberty` without `-lib` builds each standard cell as a module of
        Yosys gates from its liberty `function`, `ff` and `latch` groups, so
        every cell instance resolves to logic. A cell with an output that has no
        `function`, such as a clock gate, is left undefined, and
        `hierarchy -check` fails if the netlist instantiates one.

        Parameters
        ----------
        netlist : Path
            The gate-level Verilog netlist to read.
        json_output : Path
            Destination path for the emitted Yosys JSON netlist.
        liberty : list[Path]
            Liberty files defining every standard cell the netlist instantiates.
        top : str
            Name of the netlist's top module.
        """
        steps = [f"read_liberty -ignore_miss_func {lib}" for lib in liberty]
        steps += [
            f"read_verilog {netlist}",
            f"hierarchy -check -top {top}",
            f"write_json -compat-int {json_output}",
        ]
        cls.run(args=["-q", f"-p {'; '.join(steps)}"])
