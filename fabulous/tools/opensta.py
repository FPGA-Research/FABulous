"""OpenSTA tool wrapper: static timing analysis of a gate-level netlist.

Used as a singleton through classmethods (`OpenStaTool.write_sdf(...)`,
`OpenStaTool.run(...)`); never instantiated. Produces an SDF file for
back-annotated timing.
"""

import re
from pathlib import Path

from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool, require_input_files, require_new_output_file

_UNANNOTATED = re.compile(r"Found (\d+) unannotated drivers\.")
_PARTIALLY_ANNOTATED = re.compile(r"Found (\d+) partially unannotated drivers\.")
_INTERCONNECT_SOURCE = re.compile(r"\(INTERCONNECT\s+(\S+)\s")
# Drivers named in an error message; the rest are counted.
_NAMED_DRIVERS = 5


def _missing_parasitics(report: str) -> tuple[list[str], list[str]] | None:
    """Return the drivers `report_parasitic_annotation -report_unannotated` lists.

    OpenSTA prints each count line, then one driver per line indented by one
    space; a partially annotated driver is followed by its unannotated loads,
    indented by two.

    Parameters
    ----------
    report : str
        OpenSTA output that holds the report.

    Returns
    -------
    tuple[list[str], list[str]] | None
        The unannotated and the partially annotated drivers, or `None` if the
        output holds no complete report.
    """
    unannotated: list[str] | None = None
    partial: list[str] | None = None
    current: list[str] | None = None
    for line in report.splitlines():
        if _UNANNOTATED.fullmatch(line):
            unannotated = current = []
        elif _PARTIALLY_ANNOTATED.fullmatch(line):
            partial = current = []
        elif current is not None and line.startswith(" ") and line[1:2] != " ":
            current.append(line[1:])
        elif not line.startswith(" "):
            current = None
    if unannotated is None or partial is None:
        return None
    return unannotated, partial


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
            If OpenSTA writes an empty SDF file, or a driver with loads did not
            get its parasitics from `spef_files`. OpenSTA skips SPEF nets it
            cannot find in the netlist, so a name mismatch would otherwise leave
            the wire delays at zero.
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
        result = cls.run(stdin_data=script)

        sdf = sdf_file.read_text()
        if not sdf:
            raise RuntimeError(
                f"OpenSTA wrote an empty SDF file for {top_name!r}: {sdf_file}"
            )
        if not spef_files:
            return
        missing = _missing_parasitics(result.stdout)
        if missing is None:
            raise RuntimeError(
                f"OpenSTA printed no parasitic annotation report for {top_name!r}."
            )
        unannotated, partial = missing
        # A driver without loads, such as an unused input port, has no wire.
        sources = set(_INTERCONNECT_SOURCE.findall(sdf))
        unannotated = [driver for driver in unannotated if driver in sources]
        spef = ", ".join(str(spef_file) for spef_file in spef_files)
        if unannotated:
            raise RuntimeError(
                f"{len(unannotated)} driver(s) with loads got no parasitics from "
                f"{spef}: {', '.join(unannotated[:_NAMED_DRIVERS])}. The SPEF net "
                f"names do not match the netlist {netlist_file}."
            )
        if partial:
            raise RuntimeError(
                f"{len(partial)} driver(s) got no parasitics from {spef} for some "
                f"of its loads: {', '.join(partial[:_NAMED_DRIVERS])}. The SPEF "
                f"pin names do not match the netlist {netlist_file}."
            )
