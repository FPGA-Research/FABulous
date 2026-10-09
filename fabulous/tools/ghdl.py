"""GHDL tool wrapper.

GHDL elaborates a VHDL design (`--synth --out=verilog`) and writes the resulting
Verilog netlist to stdout. This wrapper captures that output so the VHDL-to-Verilog
conversion no longer needs a raw subprocess call in the caller. `analyze` and
`synthesize_entity` expose the two steps separately for callers that keep a GHDL
library across calls. Used as a singleton through classmethods; never
instantiated.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool


@dataclass(frozen=True)
class GhdlUnit:
    """One design unit of a GHDL library, as `ghdl --dir` lists it.

    Attributes
    ----------
    kind : str
        Unit kind, such as `entity`, `architecture` or `package`.
    name : str
        Unit name in lower case.
    entity : str | None
        The entity an architecture or configuration belongs to, otherwise `None`.
    """

    kind: str
    name: str
    entity: str | None


class GhdlTool(Tool):
    """Wraps the GHDL executable to elaborate VHDL into a Verilog netlist."""

    COMMAND = "ghdl"

    @classmethod
    def executable(cls) -> Path | str:
        """Return the GHDL executable from the FABulous context.

        Returns
        -------
        Path | str
            The configured GHDL executable.
        """
        return get_context().ghdl_path

    @classmethod
    def synthesize_to_verilog(
        cls, vhdl_file: Path, models_pack: Path, std: str = "08"
    ) -> str:
        """Elaborate a VHDL file into Verilog and return the Verilog text.

        Parameters
        ----------
        vhdl_file : Path
            The VHDL source file to elaborate. Its stem is used as the
            top-level entity name passed to `-e`.
        models_pack : Path
            The FABulous models package GHDL needs on its analysis path.
        std : str
            The VHDL standard passed to `--std` (default "08").

        Returns
        -------
        str
            The Verilog netlist GHDL emits on stdout.
        """
        # FIXME: a fake stub package required by GHDL 1.3 -- unique per-invocation
        # to avoid collisions when multiple users run FABulous on the same machine.
        with tempfile.NamedTemporaryFile(
            suffix=".vhd", mode="w", delete=False
        ) as stub_file:
            stub_file.write("package my_package is\nend package;\n")
            stub = Path(stub_file.name)
        try:
            result = cls.run(
                args=[
                    "--synth",
                    f"--std={std}",
                    "--out=verilog",
                    str(stub),
                    str(models_pack),
                    str(vhdl_file),
                    "-e",
                    vhdl_file.stem,
                ],
            )
        finally:
            stub.unlink(missing_ok=True)
        return result.stdout

    @classmethod
    def analyze(
        cls, files: list[Path], workdir: Path, flags: tuple[str, ...] = ("--std=08",)
    ) -> list[GhdlUnit]:
        """Analyse `files` into the GHDL library at `workdir` and list its units.

        Parameters
        ----------
        files : list[Path]
            VHDL files to analyse, in order.
        workdir : Path
            Library directory, created if missing.
        flags : tuple[str, ...]
            Analysis flags such as `--std=08` and `-fsynopsys`.

        Returns
        -------
        list[GhdlUnit]
            Every unit in the library after the analysis.
        """
        workdir.mkdir(parents=True, exist_ok=True)
        common = [*flags, f"--workdir={workdir}"]
        cls.run(args=["-a", *common, *map(str, files)])
        units: list[GhdlUnit] = []
        for line in cls.run(args=["--dir", *common]).stdout.splitlines():
            words = line.split()
            # `#` lines name the library and its directory.
            if not words or words[0] == "#":
                continue
            entity = words[3] if words[2:3] == ["of"] else None
            units.append(GhdlUnit(kind=words[0], name=words[1], entity=entity))
        return units

    @classmethod
    def synthesize_entity(
        cls, entity: str, workdir: Path, flags: tuple[str, ...] = ("--std=08",)
    ) -> str:
        """Synthesise `entity` from the GHDL library at `workdir` into Verilog.

        Parameters
        ----------
        entity : str
            Top entity, already analysed into `workdir`.
        workdir : Path
            Library directory.
        flags : tuple[str, ...]
            Synthesis flags such as `--std=08` and `--latches`.

        Returns
        -------
        str
            The Verilog netlist GHDL emits on stdout.
        """
        return cls.run(
            args=["--synth", *flags, f"--workdir={workdir}", "--out=verilog", entity]
        ).stdout
