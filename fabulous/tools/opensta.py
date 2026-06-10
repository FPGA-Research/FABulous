"""OpenSTA tool wrapper: static timing analysis of a gate-level netlist.

Used as a singleton through classmethods (`OpenStaTool.analyze(...)`,
`OpenStaTool.run(...)`); never instantiated. Produces an SDF file for
back-annotated timing.
"""

import tempfile
from pathlib import Path

from loguru import logger

from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool


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
    def analyze(
        cls,
        verilog_netlist: Path,
        liberty_files: list[Path] | Path,
        top_name: str,
        spef_files: list[Path] | Path | None = None,
    ) -> Path:
        """Generate an SDF file from a Verilog gate-level netlist and return it.

        Parameters
        ----------
        verilog_netlist : Path
            The gate-level netlist to analyze.
        liberty_files : list[Path] | Path
            The Liberty timing model file(s) to use for analysis.
        top_name : str
            The name of the top-level design to analyze.
        spef_files : list[Path] | Path | None
            The SPEF RC extraction file(s) to use, or None.

        Returns
        -------
        Path
            Path to the temporary SDF file.

        Raises
        ------
        RuntimeError
            If the SDF file is empty after running OpenSTA.
        """
        sdf_path: Path = Path(tempfile.gettempdir()) / f"sta_{top_name}_tmp.sdf"
        liberty_list = (
            [liberty_files] if isinstance(liberty_files, Path) else list(liberty_files)
        )
        if spef_files is None:
            spef_list = None
        elif isinstance(spef_files, Path):
            spef_list = [spef_files]
        else:
            spef_list = list(spef_files)

        script: str = cls.render_template(
            "opensta_sdf.j2",
            liberty_files=liberty_list,
            verilog_netlist=verilog_netlist,
            top_name=top_name,
            spef_files=spef_list,
            sdf_path=sdf_path,
        )

        logger.debug(f"Generating SDF file at temporary path: {sdf_path}")
        cls.run(stdin_data=script)

        content: str = sdf_path.read_text()
        if not content:
            sdf_path.unlink()
            raise RuntimeError(
                "Failed to generate SDF file using OpenSTA. No content in SDF file."
            )

        return sdf_path

    @classmethod
    def clean_up(cls, sdf_file: Path) -> None:
        """Delete the temporary SDF file produced by `analyze`.

        Parameters
        ----------
        sdf_file : Path
            The SDF file returned by `analyze`.
        """
        if sdf_file.exists():
            logger.debug(f"Cleaning up temporary SDF file at: {sdf_file}")
            sdf_file.unlink()
