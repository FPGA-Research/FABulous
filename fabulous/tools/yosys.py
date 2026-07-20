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
    def convert_to_json(
        cls,
        verilog_input: Path,
        json_output: Path,
        models_pack: Path | None = None,
        run_hierarchy: bool = True,
    ) -> None:
        """Convert a Verilog file to Yosys's JSON format.

        Parameters
        ----------
        verilog_input : Path
            The Verilog/SystemVerilog source to read.
        json_output : Path
            Destination path for the emitted Yosys JSON netlist.
        models_pack : Path | None
            When given, the fabric models package is read in after the source so
            the parsed netlist resolves its instantiated primitives and becomes
            self-contained for arc analysis. Defaults to None (no augmentation).
        run_hierarchy : bool
            Whether to run `hierarchy -auto-top` to prune modules unreachable
            from the chosen top. Ignored when `models_pack` is given, since the
            two-stage bind always needs hierarchy. Defaults to True.
        """
        if models_pack is not None:
            # Read and auto-top the source ALONE first: a BEL that instantiates
            # no primitives would otherwise let -auto-top pick a models_pack
            # primitive as top. The second hierarchy binds the primitives and
            # prunes unused ones.
            script = (
                f"read_verilog -sv {verilog_input}; "
                "hierarchy -auto-top; "
                f"read_verilog -sv {models_pack}; "
                "hierarchy; "
                "proc -noopt; "
                f"write_json -compat-int {json_output}"
            )
        else:
            hierarchy_step = "hierarchy -auto-top; " if run_hierarchy else ""
            script = (
                f"read_verilog -sv {verilog_input}; "
                f"{hierarchy_step}"
                "proc -noopt; "
                f"write_json -compat-int {json_output}"
            )
        cls.run(args=["-q", f"-p {script}"])
