"""Generate a JSON header for a VHDL design using the GHDL Yosys plugin.

Adapted from LibreLane's `scripts/pyosys/json_header.py`. The only difference is
that the design is read through the GHDL frontend (`plugin -i ghdl` followed by the
`ghdl` pass) instead of `read_verilog`, so VHDL tiles still produce the
`JSON_HEADER` view consumed by `Odb.SetPowerConnections` and
`Odb.WriteVerilogHeader`.
"""

import json
from pathlib import Path

import click
from ys_common import ys


@click.command()
@click.option("--output", type=click.Path(exists=False, dir_okay=False), required=True)
@click.option(
    "--config-in", type=click.Path(exists=True, dir_okay=False), required=True
)
@click.option("--extra-in", type=click.Path(exists=True, dir_okay=False), required=True)
def vhdl_json_header(output: str, config_in: str, extra_in: str) -> None:
    """Emit a flattened JSON header for a VHDL top-level entity read through GHDL."""
    config = json.loads(Path(config_in).read_text())
    extra = json.loads(Path(extra_in).read_text())

    blackbox_models = extra["blackbox_models"]

    includes = config["VERILOG_INCLUDE_DIRS"] or []
    defines = (
        (config["VERILOG_DEFINES"] or [])
        + [
            f"PDK_{config['PDK'].replace('-', '_')}",
            f"SCL_{config['STD_CELL_LIBRARY']}",
            "__librelane__",
            "__pnr__",
        ]
        + (
            []
            if config.get("VERILOG_POWER_DEFINE") is None
            else [config.get("VERILOG_POWER_DEFINE")]
        )
    )

    d = ys.Design()
    d.add_blackbox_models(
        blackbox_models,
        includes=includes,
        defines=defines,
    )
    d.run_pass("plugin", "-i", "ghdl")
    ghdl_arguments = config.get("GHDL_ARGUMENTS") or []
    d.run_pass(
        "ghdl", *ghdl_arguments, *config["VHDL_FILES"], "-e", config["DESIGN_NAME"]
    )
    d.run_pass(
        "hierarchy",
        "-check",
        "-top",
        config["DESIGN_NAME"],
        "-nokeep_prints",
        "-nokeep_asserts",
    )
    d.run_pass("rename", "-top", config["DESIGN_NAME"])
    d.run_pass("proc")
    d.run_pass("flatten")
    d.run_pass("opt_clean", "-purge")
    d.run_pass("json", "-o", output)


if __name__ == "__main__":
    vhdl_json_header()
