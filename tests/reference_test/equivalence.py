"""Hierarchical RTL equivalence check for diff-mode reference projects.

Yosys proves each project module equivalent on its own, since a text diff fails on
cosmetic changes and a flattened proof of the whole fabric runs out of memory.
`expose -evert` cuts the project-module instances inside each module, whose own
proofs cover them. Models-pack cells are inlined.

`expose -evert` drops the type of each instance it cuts, so the instance types and
parameters are compared separately. Instance names must therefore match between the
reference and the regenerated project.

For the reference check, GHDL synthesises a VHDL project to Verilog first, because
the yosys GHDL plugin rejects the `ConfigFSM` reset process in the current VHDL
reference projects. GHDL drops the latch enable in that Verilog, so the VHDL config
latches are checked as plain connections. The VHDL-against-Verilog check reads
freshly generated VHDL through the plugin, which keeps the latches.
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
# --latches: the config latches and the template FSMs infer latches.
GHDL_FLAGS = ("--std=08", "-fsynopsys", "--latches")
# Generated fabric RTL lives here; Test/ and user_design/ hold user inputs.
RTL_DIRS = ("Tile", "Fabric")


@dataclass(frozen=True)
class EquivalenceFailure:
    """One module that differs between the reference and the regenerated project.

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
class _Design:
    """A project elaborated into RTLIL, its yosys JSON modules and non-pack names."""

    rtlil: Path
    modules: dict[str, Any]
    project_modules: set[str]


def _fabric_files(
    project: Path, models_pack: Path, suffixes: tuple[str, ...]
) -> list[Path]:
    """Return the fabric RTL files of `project` with `suffixes`, pack excluded."""
    return [
        path
        for directory in RTL_DIRS
        for path in sorted((project / directory).rglob("*"))
        if path.suffix in suffixes and path != models_pack
    ]


def _unique_sources(files: list[Path], work_dir: Path) -> list[Path]:
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


def _ghdl_analyse(library: Path, files: list[Path]) -> list[list[str]]:
    """Analyse `files` into a fresh GHDL library and return its unit listing.

    Each entry is one `ghdl --dir` line split into words, such as `entity my_buf`
    or `architecture from_verilog of my_buf`.
    """
    library.mkdir(parents=True)
    workdir = f"--workdir={library}"
    GhdlTool.run(args=["-a", *GHDL_FLAGS[:2], workdir, *map(str, files)])
    listing = GhdlTool.run(args=["--dir", *GHDL_FLAGS[:2], workdir]).stdout
    return [line.split() for line in listing.splitlines() if line.strip()]


def _ghdl_synth(library: Path, entity: str, output: Path) -> Path:
    """Synthesise `entity` and its sub-hierarchy from `library` into `output`."""
    result = GhdlTool.run(
        args=["--synth", *GHDL_FLAGS, f"--workdir={library}", "--out=verilog", entity]
    )
    output.write_text(result.stdout)
    return output


def _fabric_top(project: Path, suffixes: tuple[str, ...]) -> Path:
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


def _vhdl_sources(
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
    pack_units = _ghdl_analyse(work_dir / "pack", [models_pack])
    pack_entities = {unit[1] for unit in pack_units if unit[0] == "entity"}
    pack_modules = {
        f"{unit[3]}_B{unit[1]}" for unit in pack_units if unit[0] == "architecture"
    }

    # Entity name to the file and GHDL library of its first definition.
    first_definition: dict[str, tuple[Path, Path]] = {}
    kept: list[Path] = []
    for index, path in enumerate(_fabric_files(project, models_pack, VHDL_SUFFIXES)):
        library = work_dir / f"file_{index:03d}"
        units = _ghdl_analyse(library, [models_pack, path])
        entities = {unit[1] for unit in units if unit[0] == "entity"} - pack_entities
        for entity in sorted(entities & first_definition.keys()):
            first_path, first_library = first_definition[entity]
            copies = [
                _ghdl_synth(first_library, entity, library / "first.v"),
                _ghdl_synth(library, entity, library / "copy.v"),
            ]
            try:
                _unique_sources(copies, library / "compare")
            except ValueError as error:
                raise ValueError(
                    f"{path} defines entity {entity} differently from "
                    f"{first_path}; make the copies identical."
                ) from error
        if new := entities - first_definition.keys():
            kept.append(path)
            first_definition.update({entity: (path, library) for entity in new})
    return kept, pack_modules


def _parse(
    project: Path,
    models_pack: Path,
    language: Literal["verilog", "vhdl"],
    work_dir: Path,
    tag: str,
) -> _Design:
    """Elaborate `project` against its own models pack into RTLIL and yosys JSON.

    Every module the pack does not define counts as a project module.
    """
    rtlil = work_dir / f"{tag}.il"
    netlist = work_dir / f"{tag}.json"
    script = work_dir / f"{tag}_parse.ys"
    source_dir = work_dir / f"{tag}_sources"
    source_dir.mkdir()
    match language:
        case "verilog":
            sources = _unique_sources(
                [models_pack, *_fabric_files(project, models_pack, VERILOG_SUFFIXES)],
                source_dir,
            )
            reads = [f'read_verilog -sv "{path}"' for path in sources]
        case "vhdl":
            sources, pack_modules = _vhdl_sources(project, models_pack, source_dir)
            fabric_library = source_dir / "fabric"
            _ghdl_analyse(fabric_library, [models_pack, *sources])
            top = _fabric_top(project, VHDL_SUFFIXES).stem.lower()
            fabric = _ghdl_synth(fabric_library, top, source_dir / "fabric.v")
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
    YosysTool.run(args=["-q", "-l", str(work_dir / f"{tag}_parse.log"), str(script)])
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
    return _Design(rtlil=rtlil, modules=modules, project_modules=project_modules)


def _check_module(
    module: str,
    children: list[str],
    reference: _Design,
    regenerated: _Design,
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


def _prove_modules(
    gold: _Design, gate: _Design, modules: list[str], work_dir: Path
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


def check_rtl_equivalence(
    reference: Path,
    regenerated: Path,
    models_pack: Path,
    language: Literal["verilog", "vhdl"],
    work_dir: Path,
) -> list[EquivalenceFailure]:
    """Check the fabric RTL of `regenerated` against `reference` module by module.

    Each side is elaborated with only its own models pack. The module sets, the
    ports of `(* blackbox *)` stubs and the per-module instance maps are compared
    directly, and yosys proves every other module equivalent.

    Parameters
    ----------
    reference : Path
        Reference project directory.
    regenerated : Path
        Project directory holding the freshly generated RTL.
    models_pack : Path
        Models pack path relative to each project directory.
    language : Literal["verilog", "vhdl"]
        HDL of both projects. GHDL synthesises VHDL to Verilog first.
    work_dir : Path
        Directory for yosys scripts, logs and the parsed designs.

    Returns
    -------
    list[EquivalenceFailure]
        One entry per differing module; empty when the projects are equivalent.

    Raises
    ------
    ValueError
        If the reference project contains no project modules to check.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    gold = _parse(reference, reference / models_pack, language, work_dir, "gold")
    gate = _parse(regenerated, regenerated / models_pack, language, work_dir, "gate")

    failures = [
        EquivalenceFailure(module=m, reason="missing in regenerated", detail="")
        for m in sorted(gold.project_modules - gate.project_modules)
    ] + [
        EquivalenceFailure(module=m, reason="extra in regenerated", detail="")
        for m in sorted(gate.project_modules - gold.project_modules)
    ]

    proved: list[str] = []
    for module in sorted(gold.project_modules & gate.project_modules):
        if "blackbox" in gold.modules[module]["attributes"]:
            # Hard-macro stub: the interface is all there is to compare.
            if gold.modules[module]["ports"] != gate.modules[module]["ports"]:
                failures.append(
                    EquivalenceFailure(
                        module=module, reason="blackbox ports differ", detail=""
                    )
                )
            continue
        proved.append(module)

    if not proved:
        raise ValueError(f"No project modules found to check under {reference}.")
    return failures + _prove_modules(gold, gate, proved, work_dir)


def check_vhdl_verilog_equivalence(
    verilog_project: Path,
    vhdl_project: Path,
    verilog_models_pack: Path,
    vhdl_models_pack: Path,
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
    verilog = _parse(
        verilog_project, verilog_models_pack, "verilog", work_dir, "verilog"
    )

    source_dir = work_dir / "vhdl_sources"
    source_dir.mkdir()
    sources, pack_modules = _vhdl_sources(vhdl_project, vhdl_models_pack, source_dir)
    vhdl_top = _fabric_top(vhdl_project, VHDL_SUFFIXES).stem
    vhdl_netlist = work_dir / "vhdl.json"
    vhdl_script = work_dir / "vhdl_parse.ys"
    vhdl_script.write_text(
        "\n".join(
            [
                f"ghdl {' '.join(GHDL_FLAGS)} {vhdl_models_pack} "
                f"{' '.join(map(str, sources))} -e {vhdl_top}",
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
    # A pack architecture elaborated with generics gets their values appended.
    vhdl_project_modules = {
        name
        for name in vhdl_modules
        if not any(name == p or name.startswith(f"{p}_") for p in pack_modules)
    }

    verilog_top = _fabric_top(verilog_project, VERILOG_SUFFIXES).stem
    # VHDL module name to Verilog module name, and back.
    mapping = {vhdl_top: verilog_top}
    paired = {verilog_top: vhdl_top}
    failures: list[EquivalenceFailure] = []
    stack = [vhdl_top]
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
    designs: list[_Design] = []
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
        designs.append(
            _Design(rtlil=rtlil, modules=result, project_modules=set(paired))
        )
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
    return failures + _prove_modules(gold, gate, proved, work_dir)
