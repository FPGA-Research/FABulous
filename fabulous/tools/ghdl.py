"""GHDL tool wrapper.

GHDL elaborates a VHDL design (`--synth --out=verilog`) and writes the resulting
Verilog netlist to stdout. This wrapper captures that output so the VHDL-to-Verilog
conversion no longer needs a raw subprocess call in the caller. Used as a singleton
via `GhdlTool.synthesize_to_verilog(...)`; never instantiated.
"""

import tempfile
from pathlib import Path

from fabulous.fabulous_settings import get_context
from fabulous.tools.tool import Tool


class GhdlTool(Tool):
    """Wraps the GHDL executable to elaborate VHDL into a Verilog netlist."""

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
