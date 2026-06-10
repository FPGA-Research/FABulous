"""Yosys tool wrapper: synthesizes Verilog RTL into a gate-level netlist.

Used as a singleton through classmethods (`YosysTool.synthesize(...)`,
`YosysTool.run(...)`); never instantiated. The gate-level netlist it produces is
later analyzed by an STA tool (e.g. OpenSTA) to generate an SDF file.
"""

import tempfile
from pathlib import Path

from loguru import logger

from fabulous.fabric_definition.cell_spec import CellFunction, StdCellLibrary
from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool


class YosysTool(Tool):
    """Synthesis tool wrapper backed by Yosys.

    Converts Verilog RTL into a gate-level netlist, supporting techmapping,
    tie-high/low cell mapping, and buffer insertion. Used as a singleton: call the
    classmethods directly, never instantiate.
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
    def synthesize(
        cls,
        verilog_files: list[Path],
        top_name: str,
        library: StdCellLibrary,
        is_gate_level: bool = False,
        flat: bool = False,
    ) -> Path:
        """Synthesize Verilog RTL into a gate-level netlist and return its path.

        When `is_gate_level` is True the input is already a gate-level netlist and
        is returned unchanged without running synthesis. The liberty/techmap files
        and the buffer/tie cells all come from `library`; when a function declares
        several cells the first is used.

        Parameters
        ----------
        verilog_files : list[Path]
            The RTL Verilog file(s) to synthesize, or the gate-level netlist when
            `is_gate_level` is True.
        top_name : str
            The name of the top-level module.
        library : StdCellLibrary
            The PDK's standard-cell library: liberty/techmap files and cells.
        is_gate_level : bool
            Whether `verilog_files` is already a gate-level netlist.
        flat : bool
            Whether to flatten the hierarchy during synthesis.

        Returns
        -------
        Path
            Path to the gate-level netlist. A temporary file when synthesis runs,
            or `verilog_files` itself when `is_gate_level` is True.

        Raises
        ------
        ValueError
            If `library` declares no buffer cell (required for buffer insertion).
        RuntimeError
            If synthesis produces an empty netlist.
        """
        if is_gate_level:
            return verilog_files

        buffers = library.get(CellFunction.BUFFER)
        if not buffers:
            raise ValueError(
                "No buffer cell configured in the timing config; a buffer cell is "
                "required for synthesis."
            )
        tie_high = library.get(CellFunction.TIE_HIGH)
        tie_low = library.get(CellFunction.TIE_LOW)

        netlist_path: Path = Path(tempfile.gettempdir()) / f"synth_{top_name}_tmp.v"

        script: str = cls.render_template(
            "yosys_synth.j2",
            liberty_files=library.liberty_files,
            verilog_files=verilog_files,
            techmap_files=library.techmap_files,
            top_name=top_name,
            flat=flat,
            tiehi_cell_and_port=tie_high[0].yosys_arg if tie_high else None,
            tielo_cell_and_port=tie_low[0].yosys_arg if tie_low else None,
            min_buf_cell_and_ports=buffers[0].yosys_arg,
            netlist_path=netlist_path,
        )

        logger.debug(
            f"Generating Synthesized Verilog file at temporary path: {netlist_path}"
        )
        cls.run(args=["-C"], stdin_data=script)

        content: str = netlist_path.read_text()
        if not content:
            netlist_path.unlink()
            raise RuntimeError(
                "Failed to generate gate-level netlist using Yosys. "
                "No content in netlist file."
            )

        # Remove single-bit vector notation for OpenSTA SDF back-annotation.
        netlist_path.write_text(content.replace("[0:0]", " "))
        return netlist_path

    @classmethod
    def clean_up(cls, netlist_file: Path, is_gate_level: bool) -> None:
        """Delete the temporary synthesized netlist.

        A gate-level passthrough input is the caller's file and is left untouched.

        Parameters
        ----------
        netlist_file : Path
            The netlist returned by `synthesize`.
        is_gate_level : bool
            Whether `netlist_file` is a passthrough gate-level input.
        """
        if is_gate_level:
            return
        if netlist_file.exists():
            logger.debug(f"Cleaning up temporary netlist file at: {netlist_file}")
            netlist_file.unlink()
