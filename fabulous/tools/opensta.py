"""OpenSTA tool wrapper: static timing analysis of a gate-level netlist.

Used as a singleton through classmethods (`OpenStaTool.write_sdf(...)`,
`OpenStaTool.run(...)`); never instantiated. Produces an SDF file for
back-annotated timing.
"""

from pathlib import Path

from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool, require_input_files, require_new_output_file


class OpenStaTool(Tool):
    """Static timing analysis wrapper backed by OpenSTA.

    Runs timing analysis on a synthesized netlist and writes an SDF file. Used as a
    singleton: call the classmethods directly, never instantiate.
    """

    @classmethod
    def executable(cls) -> Path | str:
        """Return the OpenSTA executable from the FABulous context.

        Returns
        -------
        Path | str
            The configured OpenSTA executable.
        """
        return get_context().opensta_path

    @classmethod
    def write_sdf(
        cls,
        *,
        netlist_file: Path,
        liberty_files: list[Path],
        top_name: str,
        spef_files: list[Path],
        sdf_file: Path,
    ) -> None:
        """Write the SDF timing of a gate-level netlist.

        Parameters
        ----------
        netlist_file : Path
            Gate-level Verilog netlist.
        liberty_files : list[Path]
            Liberty files of the cells in the netlist.
        top_name : str
            Top module.
        spef_files : list[Path]
            SPEF parasitics to annotate; empty for none.
        sdf_file : Path
            SDF file to write. Must not exist yet.

        Raises
        ------
        RuntimeError
            If OpenSTA writes an empty SDF file.
        """
        require_input_files([netlist_file, *liberty_files, *spef_files])
        require_new_output_file(sdf_file)
        script = cls.render_template(
            "opensta_sdf.j2",
            liberty_files=liberty_files,
            verilog_netlist=netlist_file,
            top_name=top_name,
            spef_files=spef_files,
            sdf_path=sdf_file,
        )
        cls.run(stdin_data=script)

        if not sdf_file.read_text():
            raise RuntimeError(
                f"OpenSTA wrote an empty SDF file for {top_name!r}: {sdf_file}"
            )
