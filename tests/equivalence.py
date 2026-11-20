"""Hierarchical yosys equivalence checking of generated fabric RTL.

Yosys proves each project module equivalent on its own, since a text diff fails on
cosmetic changes and a flattened proof of the whole fabric runs out of memory.
`expose -evert` cuts the project-module instances inside each module, whose own
proofs cover them. Models-pack cells are inlined.

`expose -evert` drops the type of each instance it cuts, so the instance types and
parameters are compared separately. Instance names must therefore match between the
two sides.

`parse_project` reads VHDL through `ghdl --synth --out=verilog`, because the yosys
GHDL plugin rejects the `ConfigFSM` reset process in the current VHDL reference
projects. GHDL drops the latch enable in that Verilog, so this route checks the
config latches as plain connections.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from fabulous.fabric_definition.define import HDLType
from fabulous.tools.ghdl import GhdlTool
from fabulous.tools.yosys import YosysTool

VERILOG_SUFFIXES = (".v", ".sv")
VHDL_SUFFIXES = (".vhd", ".vhdl")
GHDL_ANALYSIS_FLAGS = ("--std=08", "-fsynopsys")
GHDL_FLAGS = (*GHDL_ANALYSIS_FLAGS, "--latches")
GENERATED_RTL_DIRS = ("Tile", "Fabric")
YOSYS_SCRIPT_TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


@dataclass(frozen=True)
class EquivalenceFailure:
    """One module or instance that differs between the two sides of a check.

    Attributes
    ----------
    module : str
        Yosys module name, including any `$paramod` prefix.
    reason : str
        Failure class, such as `not equivalent` or `missing in regenerated`.
    detail : str
        The last yosys error line with its log path, or the differing instance
        names.
    """

    module: str
    reason: str
    detail: str


@dataclass(frozen=True)
class Design:
    """A project elaborated into RTLIL, its yosys JSON modules and non-pack names."""

    rtlil: Path
    modules: dict[str, Any]
    project_modules: set[str]


def run_yosys_script(script: Path, template: str, **context: object) -> None:
    """Render `template` from `tests/templates` into `script` and run it in yosys.

    The yosys log lands next to `script` with a `.log` suffix. A variable missing
    from `context` raises `jinja2.UndefinedError`, and a failing yosys run raises
    `RuntimeError`.
    """
    script.write_text(YOSYS_SCRIPT_TEMPLATES.get_template(template).render(**context))
    YosysTool.run(args=["-q", "-l", str(script.with_suffix(".log")), str(script)])


def fabric_files(
    project: Path, models_pack: Path, suffixes: tuple[str, ...]
) -> list[Path]:
    """Return the fabric RTL files of `project` with `suffixes`, pack excluded."""
    return [
        path
        for directory in GENERATED_RTL_DIRS
        for path in sorted((project / directory).rglob("*"))
        if path.suffix in suffixes and path != models_pack
    ]


def unique_sources(files: list[Path], work_dir: Path) -> list[Path]:
    """Drop every file that only repeats modules an earlier file defines.

    Tile directories carry their own copies of shared BEL sources such as
    `Config_access.v`. A file is dropped when an earlier file already defines all of
    its modules identically, ignoring `src` attributes. Techmap rule files are
    dropped too.

    Parameters
    ----------
    files : list[Path]
        Verilog files in read order.
    work_dir : Path
        Directory for the per-file yosys script, log and JSON.

    Returns
    -------
    list[Path]
        Files to read, in read order.

    Raises
    ------
    ValueError
        If a file redefines a module differently.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    netlists = [
        (path, work_dir / f"source_{index:03d}.json")
        for index, path in enumerate(files)
    ]
    run_yosys_script(work_dir / "sources.ys", "unique_sources.ys.j2", sources=netlists)

    definitions: dict[str, tuple[Path, Any]] = {}
    sources: list[Path] = []
    for path, netlist in netlists:
        defined = json.loads(netlist.read_text())["modules"]
        is_techmap_rule = any(name.startswith("\\$") for name in defined)
        if is_techmap_rule:
            continue
        for name, body in defined.items():
            if name in definitions and definitions[name][1] != body:
                raise ValueError(
                    f"{path} redefines module {name} differently from "
                    f"{definitions[name][0]}; make the copies identical."
                )
        if new := defined.keys() - definitions.keys():
            sources.append(path)
            definitions.update({name: (path, defined[name]) for name in new})
    return sources


def vhdl_pack_prefixes(models_pack: Path, library: Path) -> tuple[str, ...]:
    """Return the module name prefixes GHDL gives the entities of a VHDL pack.

    GHDL names a module `<entity>_B<architecture>`, with generic values appended.
    Entity names are lower case, so `<entity>_B` matches no other entity's modules.
    """
    entities = GhdlTool.analyze(
        files=[models_pack], workdir=library, flags=GHDL_ANALYSIS_FLAGS
    )
    return tuple(f"{entity}_B" for entity in entities)


def parse_project(
    project: Path,
    models_pack: Path,
    language: HDLType,
    top: str,
    work_dir: Path,
    tag: str,
) -> Design:
    """Elaborate `project` against its own models pack into RTLIL and yosys JSON.

    Every module the pack does not define counts as a project module. `top` names
    the fabric top entity GHDL synthesises a VHDL project from. Tile directories
    carry their own copies of shared files such as `Config_access.vhdl`, and GHDL
    keeps the last copy it analyses.
    """
    rtlil = work_dir / f"{tag}.il"
    netlist = work_dir / f"{tag}.json"
    source_dir = work_dir / f"{tag}_sources"
    source_dir.mkdir()
    match language:
        case HDLType.VERILOG | HDLType.SYSTEM_VERILOG:
            sources = unique_sources(
                [models_pack, *fabric_files(project, models_pack, VERILOG_SUFFIXES)],
                source_dir,
            )
        case HDLType.VHDL:
            pack_prefixes = vhdl_pack_prefixes(models_pack, source_dir / "pack")
            fabric_library = source_dir / "fabric"
            GhdlTool.analyze(
                files=[models_pack, *fabric_files(project, models_pack, VHDL_SUFFIXES)],
                workdir=fabric_library,
                flags=GHDL_ANALYSIS_FLAGS,
            )
            fabric = source_dir / "fabric.v"
            fabric.write_text(
                GhdlTool.synthesize_entity(
                    entity=top, workdir=fabric_library, flags=GHDL_FLAGS
                )
            )
            sources = [fabric]
    run_yosys_script(
        work_dir / f"{tag}_parse.ys",
        "parse_project.ys.j2",
        sources=sources,
        rtlil=rtlil,
        netlist=netlist,
    )
    modules: dict[str, Any] = json.loads(netlist.read_text())["modules"]
    match language:
        case HDLType.VERILOG | HDLType.SYSTEM_VERILOG:
            pack_src = f"{models_pack}:"
            project_modules = {
                name
                for name, module in modules.items()
                if not module["attributes"].get("src", "").startswith(pack_src)
            }
        case HDLType.VHDL:
            ghdl_anonymous_nets: dict[str, list[str]] = {}
            for module, body in modules.items():
                nets = [
                    net
                    for net in body["netnames"]
                    if (last := net.rsplit("_", 1)[-1])[0] == "n" and last[1:].isdigit()
                ]
                if nets:
                    ghdl_anonymous_nets[module] = nets
            run_yosys_script(
                work_dir / f"{tag}_hide.ys",
                "hide_ghdl_nets.ys.j2",
                anonymous_nets=ghdl_anonymous_nets,
                rtlil=rtlil,
                netlist=netlist,
            )
            modules = json.loads(netlist.read_text())["modules"]
            project_modules = {
                name for name in modules if not name.startswith(pack_prefixes)
            }
    return Design(rtlil=rtlil, modules=modules, project_modules=project_modules)


def _check_module(
    module: str,
    children: list[str],
    reference: Design,
    regenerated: Design,
    script: Path,
) -> EquivalenceFailure | None:
    """Prove `module` equivalent, cutting at its project-module instances.

    Returns `None` when the proof holds, otherwise a failure carrying the last
    yosys error line.
    """
    try:
        run_yosys_script(
            script,
            "prove_module.ys.j2",
            module=module,
            children=children,
            sides=[("gold", reference.rtlil), ("gate", regenerated.rtlil)],
        )
    except RuntimeError:
        log = script.with_suffix(".log")
        errors = [line for line in log.read_text().splitlines() if "ERROR:" in line]
        return EquivalenceFailure(
            module=module, reason="not equivalent", detail=f"{errors[-1]} (log: {log})"
        )
    return None


def prove_modules(
    gold: Design, gate: Design, modules: list[str], work_dir: Path
) -> list[EquivalenceFailure]:
    """Compare the instance maps of `modules` and prove each module equivalent."""
    failures: list[EquivalenceFailure] = []
    jobs: list[tuple[str, list[str]]] = []
    for module in modules:
        gold_project_instances, gate_project_instances = (
            {
                name: (cell["type"], tuple(sorted(cell.get("parameters", {}).items())))
                for name, cell in design.modules[module]["cells"].items()
                if cell["type"] in design.project_modules
            }
            for design in (gold, gate)
        )
        if gold_project_instances != gate_project_instances:
            differing = sorted(
                name
                for name in gold_project_instances.keys()
                | gate_project_instances.keys()
                if gold_project_instances.get(name) != gate_project_instances.get(name)
            )
            failures.append(
                EquivalenceFailure(
                    module=module,
                    reason="instance type or parameters differ",
                    detail=", ".join(differing),
                )
            )
        jobs.append(
            (module, sorted({kind for kind, _ in gold_project_instances.values()}))
        )

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        results = pool.map(
            lambda job: _check_module(
                module=job[1][0],
                children=job[1][1],
                reference=gold,
                regenerated=gate,
                script=work_dir / f"module_{job[0]:03d}.ys",
            ),
            enumerate(jobs),
        )
        failures += [result for result in results if result is not None]
    return failures
