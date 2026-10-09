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
from typing import Any, Literal

from fabulous.tools.ghdl import GhdlTool
from fabulous.tools.yosys import YosysTool

VERILOG_SUFFIXES = (".v", ".sv")
VHDL_SUFFIXES = (".vhd", ".vhdl")
GHDL_ANALYSIS_FLAGS = ("--std=08", "-fsynopsys")
# --latches: the config latches and the template FSMs infer latches.
GHDL_FLAGS = (*GHDL_ANALYSIS_FLAGS, "--latches")
# Generated fabric RTL lives here; Test/ and user_design/ hold user inputs.
RTL_DIRS = ("Tile", "Fabric")


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


def fabric_files(
    project: Path, models_pack: Path, suffixes: tuple[str, ...]
) -> list[Path]:
    """Return the fabric RTL files of `project` with `suffixes`, pack excluded."""
    return [
        path
        for directory in RTL_DIRS
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
    script = work_dir / "sources.ys"
    commands: list[str] = []
    for index, path in enumerate(files):
        commands += [
            "design -reset",
            f'read_verilog -sv "{path}"',
            "proc",
            "setattr -unset src",
            "setattr -mod -unset src",
            f'write_json "{work_dir / f"source_{index:03d}.json"}"',
        ]
    script.write_text("\n".join(commands))
    YosysTool.run(args=["-q", "-l", str(script.with_suffix(".log")), str(script)])

    definitions: dict[str, tuple[Path, Any]] = {}
    sources: list[Path] = []
    for index, path in enumerate(files):
        defined = json.loads((work_dir / f"source_{index:03d}.json").read_text())[
            "modules"
        ]
        # An escaped `\$...` module name targets a yosys cell type, so such a file
        # is a techmap rule for synthesis (e.g. a PDK latch map), not fabric RTL.
        if any(name.startswith("\\$") for name in defined):
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


def fabric_top(project: Path, suffixes: tuple[str, ...]) -> Path:
    """Return the one `Fabric/<fabric>_top` file of `project` with `suffixes`."""
    # `ghdl --find-top` cannot stand in: unused BEL entities are tops as well.
    tops = sorted(
        path for path in (project / "Fabric").glob("*_top.*") if path.suffix in suffixes
    )
    if len(tops) != 1:
        raise ValueError(
            f"Expected one fabric top file Fabric/*_top{suffixes} in {project}, "
            f"found {[top.name for top in tops]}."
        )
    return tops[0]


def vhdl_sources(
    project: Path, models_pack: Path, work_dir: Path
) -> tuple[list[Path], set[str]]:
    """Select the VHDL fabric files of `project` that GHDL reads together.

    GHDL keeps the last of several same-named entities without warning, so each
    fabric file is first analysed alone. Every redefined entity must synthesise to
    the same netlist as its first definition, and a file without a new entity is
    dropped.

    Parameters
    ----------
    project : Path
        Project directory to collect from.
    models_pack : Path
        Absolute VHDL models pack path.
    work_dir : Path
        Directory for the per-file GHDL libraries.

    Returns
    -------
    tuple[list[Path], set[str]]
        The fabric files to read, and the yosys module names
        `<entity>_B<architecture>` of the pack architectures.

    Raises
    ------
    ValueError
        If a file redefines an entity differently.
    """
    pack_units = GhdlTool.analyze(
        files=[models_pack], workdir=work_dir / "pack", flags=GHDL_ANALYSIS_FLAGS
    )
    pack_entities = {unit.name for unit in pack_units if unit.kind == "entity"}
    pack_modules = {
        f"{unit.entity}_B{unit.name}"
        for unit in pack_units
        if unit.kind == "architecture"
    }

    # Entity name to the file and GHDL library of its first definition.
    first_definition: dict[str, tuple[Path, Path]] = {}
    kept: list[Path] = []
    for index, path in enumerate(fabric_files(project, models_pack, VHDL_SUFFIXES)):
        library = work_dir / f"file_{index:03d}"
        units = GhdlTool.analyze(
            files=[models_pack, path], workdir=library, flags=GHDL_ANALYSIS_FLAGS
        )
        entities = {unit.name for unit in units if unit.kind == "entity"}
        entities -= pack_entities
        for entity in sorted(entities & first_definition.keys()):
            first_path, first_library = first_definition[entity]
            copies = [library / "first.v", library / "copy.v"]
            for copy, source in zip(copies, (first_library, library), strict=True):
                copy.write_text(
                    GhdlTool.synthesize_entity(
                        entity=entity, workdir=source, flags=GHDL_FLAGS
                    )
                )
            try:
                unique_sources(copies, library / "compare")
            except ValueError as error:
                raise ValueError(
                    f"{path} defines entity {entity} differently from "
                    f"{first_path}; make the copies identical."
                ) from error
        if new := entities - first_definition.keys():
            kept.append(path)
            first_definition.update({entity: (path, library) for entity in new})
    return kept, pack_modules


def parse_project(
    project: Path,
    models_pack: Path,
    language: Literal["verilog", "vhdl"],
    work_dir: Path,
    tag: str,
) -> Design:
    """Elaborate `project` against its own models pack into RTLIL and yosys JSON.

    Every module the pack does not define counts as a project module.
    """
    rtlil = work_dir / f"{tag}.il"
    netlist = work_dir / f"{tag}.json"
    script = work_dir / f"{tag}parse_project.ys"
    source_dir = work_dir / f"{tag}_sources"
    source_dir.mkdir()
    match language:
        case "verilog":
            sources = unique_sources(
                [models_pack, *fabric_files(project, models_pack, VERILOG_SUFFIXES)],
                source_dir,
            )
            reads = [f'read_verilog -sv "{path}"' for path in sources]
        case "vhdl":
            sources, pack_modules = vhdl_sources(project, models_pack, source_dir)
            fabric_library = source_dir / "fabric"
            GhdlTool.analyze(
                files=[models_pack, *sources],
                workdir=fabric_library,
                flags=GHDL_ANALYSIS_FLAGS,
            )
            top = fabric_top(project, VHDL_SUFFIXES).stem.lower()
            fabric = source_dir / "fabric.v"
            fabric.write_text(
                GhdlTool.synthesize_entity(
                    entity=top, workdir=fabric_library, flags=GHDL_FLAGS
                )
            )
            reads = [f'read_verilog -sv "{fabric}"']
    script.write_text(
        "\n".join(
            [
                *reads,
                "hierarchy -check",
                "proc",
                "opt_clean",
                f'write_rtlil "{rtlil}"',
                f'write_json "{netlist}"',
            ]
        )
    )
    YosysTool.run(
        args=["-q", "-l", str(work_dir / f"{tag}parse_project.log"), str(script)]
    )
    modules: dict[str, Any] = json.loads(netlist.read_text())["modules"]
    match language:
        case "verilog":
            pack_src = f"{models_pack}:"
            project_modules = {
                name
                for name, module in modules.items()
                if not module["attributes"].get("src", "").startswith(pack_src)
            }
        case "vhdl":
            # GHDL numbers anonymous nets `n<number>` and `<instance>_n<number>`
            # across the whole design, so once the two sides differ the same name
            # denotes unrelated nets and `equiv_make` would pair them. Hiding them
            # removes only a matching hint, so the worst case is a false failure.
            hide: list[str] = []
            for module, body in modules.items():
                nets = [
                    net
                    for net in body["netnames"]
                    if (last := net.rsplit("_", 1)[-1])[0] == "n" and last[1:].isdigit()
                ]
                # One command per module; one per net costs a full design walk each.
                if nets:
                    hide.append(
                        f"rename -hide {' '.join(f'{module}/w:{n}' for n in nets)}"
                    )
            hide_script = work_dir / f"{tag}_hide.ys"
            hide_script.write_text(
                "\n".join(
                    [
                        f'read_rtlil "{rtlil}"',
                        *hide,
                        "opt_clean",
                        f'write_rtlil "{rtlil}"',
                        f'write_json "{netlist}"',
                    ]
                )
            )
            YosysTool.run(
                args=[
                    "-q",
                    "-l",
                    str(hide_script.with_suffix(".log")),
                    str(hide_script),
                ]
            )
            modules = json.loads(netlist.read_text())["modules"]
            project_modules = modules.keys() - pack_modules
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
    commands: list[str] = []
    for design, tag in ((reference, "gold"), (regenerated, "gate")):
        commands += [f'read_rtlil "{design.rtlil}"', f"hierarchy -top {module}"]
        if children:
            commands += [
                f"setattr -mod -set keep_hierarchy 1 {' '.join(children)}",
                f"flatten {module}",
                f"blackbox * {module} %d",
                # The GHDL plugin gives internal cells public names; cut only
                # instances.
                f"expose -evert {module}/c:* {module}/t:$* %d",
            ]
        else:
            commands.append("flatten")
        # async2sync: `sat` cannot model the config latches as `$dlatch`.
        commands += [
            "memory",
            "async2sync",
            "opt_clean",
            f"rename {module} {tag}",
            f"design -stash {tag}",
        ]
    log = script.with_suffix(".log")
    script.write_text(
        "\n".join(
            [
                *commands,
                "design -copy-from gold -as gold gold",
                "design -copy-from gate -as gate gate",
                "equiv_make gold gate equiv",
                "hierarchy -top equiv",
                "equiv_simple",
                "equiv_induct",
                "equiv_status -assert",
            ]
        )
    )
    try:
        YosysTool.run(args=["-q", "-l", str(log), str(script)])
    except RuntimeError:
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
        # Project-module instance name to its type and parameters.
        gold_instances, gate_instances = (
            {
                name: (cell["type"], tuple(sorted(cell.get("parameters", {}).items())))
                for name, cell in design.modules[module]["cells"].items()
                if cell["type"] in design.project_modules
            }
            for design in (gold, gate)
        )
        if gold_instances != gate_instances:
            differing = sorted(
                name
                for name in gold_instances.keys() | gate_instances.keys()
                if gold_instances.get(name) != gate_instances.get(name)
            )
            failures.append(
                EquivalenceFailure(
                    module=module,
                    reason="instance type or parameters differ",
                    detail=", ".join(differing),
                )
            )
        jobs.append((module, sorted({kind for kind, _ in gold_instances.values()})))

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
