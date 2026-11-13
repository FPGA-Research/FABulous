"""Equivalence of the VHDL and Verilog fabric RTL generated from one fabric.

The yosys GHDL plugin reads the VHDL side directly, which keeps the config latches
that `ghdl --synth --out=verilog` reduces to wires.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_settings import get_context, init_context, reset_context
from fabulous.tools.yosys import YosysTool
from tests.conftest import run_cmd
from tests.equivalence import (
    GHDL_FLAGS,
    VHDL_SUFFIXES,
    Design,
    EquivalenceFailure,
    fabric_files,
    parse_project,
    prove_modules,
    vhdl_pack_prefixes,
)
from tests.fabric_gen_test.integration_test.conftest import set_multiplexer_style


def _check_vhdl_verilog_equivalence(
    verilog_project: Path,
    vhdl_project: Path,
    verilog_models_pack: Path,
    vhdl_models_pack: Path,
    top: str,
    work_dir: Path,
) -> list[EquivalenceFailure]:
    """Check the VHDL fabric of a project against its Verilog fabric.

    The yosys GHDL plugin elaborates the VHDL side directly, which keeps the config
    latches. GHDL names a module after its entity, architecture and generic values,
    so modules are paired by walking the hierarchy from the fabric top and matching
    instance names without case. A module the top does not reach is not checked.
    Each paired module has its port directions and widths and its instance map
    compared, and yosys proves it equivalent with the Verilog side as gold.

    Parameters
    ----------
    verilog_project : Path
        Project generated with Verilog output.
    vhdl_project : Path
        The same fabric generated with VHDL output.
    verilog_models_pack : Path
        Absolute Verilog models pack path.
    vhdl_models_pack : Path
        Absolute VHDL models pack path.
    top : str
        Fabric top module, `<fabric>_top`, the same in both languages.
    work_dir : Path
        Directory for yosys scripts, logs and the parsed designs.

    Returns
    -------
    list[EquivalenceFailure]
        One entry per differing module or instance; empty when the two are
        equivalent.

    Raises
    ------
    ValueError
        If two port, net or cell names of one module differ only in case, or no
        paired module is left to prove.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    verilog = parse_project(
        project=verilog_project,
        models_pack=verilog_models_pack,
        language=HDLType.VERILOG,
        top=top,
        work_dir=work_dir,
        tag="verilog",
    )

    pack_prefixes = vhdl_pack_prefixes(vhdl_models_pack, work_dir / "vhdl_pack")
    sources = fabric_files(vhdl_project, vhdl_models_pack, VHDL_SUFFIXES)
    vhdl_netlist = work_dir / "vhdl.json"
    vhdl_script = work_dir / "vhdl_parse.ys"
    vhdl_script.write_text(
        "\n".join(
            [
                f"ghdl {' '.join(GHDL_FLAGS)} {vhdl_models_pack} "
                f"{' '.join(map(str, sources))} -e {top}",
                "hierarchy -check",
                "proc",
                "opt_clean",
                f'write_json "{vhdl_netlist}"',
            ]
        )
    )
    YosysTool.run(
        args=[
            "-m",
            "ghdl",
            "-q",
            "-l",
            str(vhdl_script.with_suffix(".log")),
            str(vhdl_script),
        ]
    )
    vhdl_modules: dict[str, Any] = json.loads(vhdl_netlist.read_text())["modules"]
    vhdl_project_modules = {
        name for name in vhdl_modules if not name.startswith(pack_prefixes)
    }

    # VHDL module name to Verilog module name, and back.
    mapping = {top: top}
    paired = {top: top}
    failures: list[EquivalenceFailure] = []
    stack = [top]
    while stack:
        vhdl_module = stack.pop()
        verilog_module = mapping[vhdl_module]
        verilog_cells = {
            name.lower(): cell["type"]
            for name, cell in verilog.modules[verilog_module]["cells"].items()
            if cell["type"] in verilog.project_modules
        }
        vhdl_cells = {
            name.lower(): cell["type"]
            for name, cell in vhdl_modules[vhdl_module]["cells"].items()
            if cell["type"] in vhdl_project_modules
        }
        for name in sorted(verilog_cells.keys() ^ vhdl_cells.keys()):
            side = "VHDL" if name in verilog_cells else "Verilog"
            failures.append(
                EquivalenceFailure(
                    module=verilog_module,
                    reason=f"instance missing in {side}",
                    detail=name,
                )
            )
        for name in sorted(verilog_cells.keys() & vhdl_cells.keys()):
            vhdl_type, verilog_type = vhdl_cells[name], verilog_cells[name]
            if vhdl_type not in mapping and verilog_type not in paired:
                mapping[vhdl_type] = verilog_type
                paired[verilog_type] = vhdl_type
                stack.append(vhdl_type)
            elif mapping.get(vhdl_type) != verilog_type:
                failures.append(
                    EquivalenceFailure(
                        module=verilog_module,
                        reason="instance pairs modules paired elsewhere",
                        detail=f"{name}: Verilog {verilog_type}, VHDL {vhdl_type}",
                    )
                )

    def lower(module: str, kind: str, table: dict[str, Any]) -> dict[str, Any]:
        folded: dict[str, Any] = {}
        for name, value in table.items():
            if name.lower() in folded:
                raise ValueError(
                    f"Module {module} has two {kind} names that differ only in "
                    f"case ({name}); VHDL cannot tell them apart."
                )
            folded[name.lower()] = value
        return folded

    # VHDL identifiers are case-insensitive and GHDL writes them in lower case, so
    # both sides are lower-cased before `equiv_make` matches names.
    designs: list[Design] = []
    for tag, modules, rename in (
        ("verilog", verilog.modules, {}),
        ("vhdl", vhdl_modules, mapping),
    ):
        result: dict[str, Any] = {}
        for name, module in modules.items():
            cells: dict[str, Any] = {}
            for cell_name, cell in module["cells"].items():
                if cell["type"] in modules:
                    cell = {
                        **cell,
                        "type": rename.get(cell["type"], cell["type"]),
                        "connections": lower(name, "connection", cell["connections"]),
                    }
                    if "port_directions" in cell:
                        cell["port_directions"] = lower(
                            name, "port direction", cell["port_directions"]
                        )
                cells[cell_name] = cell
            result[rename.get(name, name)] = {
                **module,
                "ports": lower(name, "port", module["ports"]),
                "netnames": lower(name, "net", module["netnames"]),
                "cells": lower(name, "cell", cells),
            }
        netlist = work_dir / f"{tag}_folded.json"
        rtlil = work_dir / f"{tag}_folded.il"
        script = work_dir / f"{tag}_folded.ys"
        netlist.write_text(json.dumps({"modules": result}))
        script.write_text(f'read_json "{netlist}"\nwrite_rtlil "{rtlil}"')
        YosysTool.run(args=["-q", "-l", str(script.with_suffix(".log")), str(script)])
        designs.append(Design(rtlil=rtlil, modules=result, project_modules=set(paired)))
    gold, gate = designs

    proved: list[str] = []
    for module in sorted(paired):
        gold_ports, gate_ports = (
            {
                name: (port["direction"], len(port["bits"]))
                for name, port in design.modules[module]["ports"].items()
            }
            for design in (gold, gate)
        )
        if gold_ports != gate_ports:
            differing = sorted(
                name
                for name in gold_ports.keys() | gate_ports.keys()
                if gold_ports.get(name) != gate_ports.get(name)
            )
            failures.append(
                EquivalenceFailure(
                    module=module,
                    reason="port direction or width differs",
                    detail=", ".join(differing),
                )
            )
        if "blackbox" not in gold.modules[module]["attributes"]:
            proved.append(module)

    if not proved:
        raise ValueError(f"No paired modules to prove under {verilog_project}.")
    return failures + prove_modules(gold, gate, proved, work_dir)


def _generate(
    project_factory: Callable[..., Path], lang: HDLType, mux_style: str
) -> tuple[Path, Path, str]:
    """Generate the fabric RTL of a new `lang` project.

    Returns the project, its models pack and the fabric name.
    """
    project_dir = project_factory(lang=lang, name=f"{lang.value}_project")
    set_multiplexer_style(project_dir, mux_style)
    reset_context()
    init_context(project_dir)
    cli = FABulousREPL(
        lang.value, force=False, interactive=False, verbose=False, debug=True
    )
    for command in (
        "load_fabric",
        "gen_io_fabric",
        "gen_fabric",
        "gen_bitStream_spec",
        "gen_top_wrapper",
    ):
        run_cmd(cli, command)
        assert cli.exit_code == 0, f"{command} failed for the {lang.value} project"
    models_pack = get_context().models_pack
    assert models_pack is not None, f"No models pack configured for {project_dir}"
    return project_dir, models_pack, cli.fabulousAPI.fabric.name


@pytest.mark.parametrize("mux_style", ["custom", "generic"])
@pytest.mark.slow
def test_vhdl_matches_verilog(
    mux_style: str, project_factory: Callable[..., Path], tmp_path: Path
) -> None:
    """The VHDL fabric of the template project is equivalent to its Verilog one."""
    verilog_project, verilog_pack, fabric = _generate(
        project_factory, HDLType.VERILOG, mux_style
    )
    vhdl_project, vhdl_pack, _ = _generate(project_factory, HDLType.VHDL, mux_style)

    failures = _check_vhdl_verilog_equivalence(
        verilog_project=verilog_project,
        vhdl_project=vhdl_project,
        verilog_models_pack=verilog_pack,
        vhdl_models_pack=vhdl_pack,
        top=f"{fabric}_top",
        work_dir=tmp_path / "equivalence",
    )
    if failures:
        report = "\n".join(
            f"  {f.module}: {f.reason}" + (f": {f.detail}" if f.detail else "")
            for f in failures
        )
        pytest.fail(
            f"VHDL fabric is not equivalent to the Verilog fabric in "
            f"{len(failures)} places:\n{report}"
        )
