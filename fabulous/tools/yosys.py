"""Yosys tool wrapper: Verilog to JSON netlists and gate-level synthesis.

Used as a singleton through classmethods (`YosysTool.convert_to_json(...)`,
`YosysTool.synthesize_gate_level(...)`, `YosysTool.run(...)`); never instantiated.
"""

from pathlib import Path

from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool, require_input_files, require_new_output_file


class YosysTool(Tool):
    """Yosys wrapper backed by the Yosys executable.

    Converts Verilog into Yosys's JSON netlist format and synthesises RTL into a
    standard-cell netlist. Used as a singleton: call the classmethods directly,
    never instantiate.
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
    def synthesize_gate_level(
        cls,
        *,
        verilog_files: list[Path],
        liberty_files: list[Path],
        top_name: str,
        netlist_file: Path,
        techmap_files: list[Path],
        tiehi_cell_and_port: str | None,
        tielo_cell_and_port: str | None,
        min_buf_cell_and_ports: str,
    ) -> None:
        """Synthesise RTL into a hierarchical netlist of the liberty cells.

        Runs the `yosys_synth.j2` script. Clock gates, flip-flops and the `abc`
        mapping use the first liberty file only.

        Parameters
        ----------
        verilog_files : list[Path]
            RTL sources.
        liberty_files : list[Path]
            Liberty files of the standard-cell library.
        top_name : str
            Top module.
        netlist_file : Path
            Gate-level Verilog netlist to write. Must not exist yet.
        techmap_files : list[Path]
            Techmap files applied after `synth`, followed by `simplemap`; empty
            for none.
        tiehi_cell_and_port : str | None
            Tie-high `"cell port"` for `hilomap`, or None for no tie cells.
        tielo_cell_and_port : str | None
            Tie-low `"cell port"` for `hilomap`, or None for no tie cells.
        min_buf_cell_and_ports : str
            Buffer `"cell in_port out_port"` for `insbuf`.

        Raises
        ------
        ValueError
            If only one of the tie-high and tie-low cells is given.
        RuntimeError
            If Yosys writes an empty netlist.
        """
        if (tiehi_cell_and_port is None) != (tielo_cell_and_port is None):
            raise ValueError(
                "Both tiehi_cell_and_port and tielo_cell_and_port must be "
                "specified together."
            )
        require_input_files([*verilog_files, *liberty_files, *techmap_files])
        require_new_output_file(netlist_file)
        script = cls.render_template(
            "yosys_synth.j2",
            liberty_files=liberty_files,
            verilog_files=verilog_files,
            techmap_files=techmap_files,
            top_name=top_name,
            flat=False,
            tiehi_cell_and_port=tiehi_cell_and_port,
            tielo_cell_and_port=tielo_cell_and_port,
            min_buf_cell_and_ports=min_buf_cell_and_ports,
            netlist_path=netlist_file,
        )
        cls.run(args=["-C"], stdin_data=script)

        netlist = netlist_file.read_text()
        if not netlist:
            raise RuntimeError(
                f"Yosys wrote an empty gate-level netlist for {top_name!r}: "
                f"{netlist_file}"
            )
        # OpenSTA's SDF back-annotation does not accept single-bit `[0:0]` ranges.
        netlist_file.write_text(netlist.replace("[0:0]", " "))
