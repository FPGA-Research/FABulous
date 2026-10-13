"""Yosys tool wrapper: converts Verilog into JSON and into a gate-level netlist.

Used as a singleton through classmethods (`YosysTool.convert_to_json(...)`,
`YosysTool.synthesize_to_netlist(...)`, `YosysTool.run(...)`); never instantiated.
"""

import tempfile
from pathlib import Path

from loguru import logger

from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool


class YosysTool(Tool):
    """Yosys wrapper backed by the Yosys executable.

    Converts Verilog into Yosys's JSON netlist format, and RTL into a gate-level
    netlist. Used as a singleton: call the classmethods directly, never
    instantiate.
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
    def synthesize_to_netlist(
        cls,
        verilog_files: list[Path] | Path,
        liberty_files: list[Path] | Path,
        top_name: str,
        techmap_files: list[Path] | None = None,
        tiehi_cell_and_port: str | None = None,
        tielo_cell_and_port: str | None = None,
        min_buf_cell_and_ports: str | None = None,
        flat: bool = False,
    ) -> Path:
        """Synthesize Verilog RTL into a gate-level netlist and return it.

        Parameters
        ----------
        verilog_files : list[Path] | Path
            The RTL source file(s) to synthesize.
        liberty_files : list[Path] | Path
            The Liberty file(s) for the target technology. The first one drives
            `clockgate`, `dfflibmap` and `abc`.
        top_name : str
            The top-level module to synthesize.
        techmap_files : list[Path] | None
            Techmap files applied after `synth`, or None to skip techmapping.
        tiehi_cell_and_port : str | None
            The "cell port" pair for `hilomap -hicell`, or None to skip hilomap.
            Must be given together with `tielo_cell_and_port`.
        tielo_cell_and_port : str | None
            The "cell port" pair for `hilomap -locell`, or None to skip hilomap.
        min_buf_cell_and_ports : str | None
            The "cell in out" triple for `insbuf`, or None to skip buffer insertion.
        flat : bool
            Whether to flatten the hierarchy during synthesis. Defaults to False.

        Returns
        -------
        Path
            Path to the temporary gate-level netlist.

        Raises
        ------
        RuntimeError
            If the netlist is empty after running Yosys.
        """
        netlist_path: Path = Path(tempfile.gettempdir()) / f"synth_{top_name}_tmp.v"
        verilog_list = (
            [verilog_files] if isinstance(verilog_files, Path) else list(verilog_files)
        )
        liberty_list = (
            [liberty_files] if isinstance(liberty_files, Path) else list(liberty_files)
        )

        script: str = cls.render_template(
            "yosys_synth.j2",
            liberty_files=liberty_list,
            verilog_files=verilog_list,
            techmap_files=techmap_files,
            top_name=top_name,
            flat=flat,
            tiehi_cell_and_port=tiehi_cell_and_port,
            tielo_cell_and_port=tielo_cell_and_port,
            min_buf_cell_and_ports=min_buf_cell_and_ports,
            netlist_path=netlist_path,
        )

        logger.debug(f"Generating netlist at temporary path: {netlist_path}")
        # The script opens with `yosys -import`, so it is Tcl and needs `-C`.
        cls.run(args=["-C"], stdin_data=script)

        netlist: str = netlist_path.read_text()
        if not netlist:
            netlist_path.unlink()
            raise RuntimeError(
                "Failed to generate gate-level netlist using Yosys. "
                "No content in netlist file."
            )

        # OpenSTA cannot back-annotate SDF onto single-bit vector notation.
        netlist_path.write_text(netlist.replace("[0:0]", " "))

        return netlist_path

    @classmethod
    def clean_up(cls, netlist_file: Path) -> None:
        """Delete the temporary netlist produced by `synthesize_to_netlist`.

        Parameters
        ----------
        netlist_file : Path
            The netlist returned by `synthesize_to_netlist`.
        """
        if netlist_file.exists():
            logger.debug(f"Cleaning up temporary netlist file at: {netlist_file}")
            netlist_file.unlink()
