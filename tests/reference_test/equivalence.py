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

Instances = dict[str, tuple[str, tuple[tuple[str, str], ...]]]


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
        If a file redefines a module differently, defines a mix of already
        defined and new modules, or mixes techmap rules with RTL modules.
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
        modules = json.loads((work_dir / f"source_{index:03d}.json").read_text())
        defined = modules["modules"]
        # An escaped `\$...` module name targets a yosys cell type, so such a file
        # is a techmap rule for synthesis (e.g. a PDK latch map), not fabric RTL.
        techmap = {name for name in defined if name.startswith("\\$")}
        if techmap:
            if techmap != defined.keys():
                raise ValueError(
                    f"{path} mixes techmap rules {sorted(techmap)} with RTL "
                    "modules; keep techmap rules in their own file."
                )
            continue
        for name, body in defined.items():
            if name in definitions and definitions[name][1] != body:
                raise ValueError(
                    f"{path} redefines module {name} differently from "
                    f"{definitions[name][0]}; make the copies identical."
                )
        new = defined.keys() - definitions.keys()
        if new and len(new) != len(defined):
            raise ValueError(
                f"{path} defines {sorted(new)} next to modules an earlier file "
                "already defines; split it so each module is read once."
            )
        if new:
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


def _entities(units: list[list[str]]) -> set[str]:
    """Return the entity names of a `_ghdl_analyse` listing."""
    return {unit[1] for unit in units if unit[0] == "entity"}


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
    fabric file is first analysed alone. A file that only redefines earlier
    entities is dropped once its synthesised copies match the first ones.

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
        If a file redefines an entity differently, or defines a mix of entities
        already defined by an earlier file and new ones.
    """
    pack_units = _ghdl_analyse(work_dir / "pack", [models_pack])
    pack_entities = _entities(pack_units)
    pack_modules = {
        f"{unit[3]}_B{unit[1]}" for unit in pack_units if unit[0] == "architecture"
    }

    # Entity name to the file and GHDL library of its first definition.
    first_definition: dict[str, tuple[Path, Path]] = {}
    kept: list[Path] = []
    for index, path in enumerate(_fabric_files(project, models_pack, VHDL_SUFFIXES)):
        library = work_dir / f"file_{index:03d}"
        entities = _entities(_ghdl_analyse(library, [models_pack, path]))
        entities -= pack_entities
        defined = entities & first_definition.keys()
        if defined and defined != entities:
            raise ValueError(
                f"{path} defines {sorted(entities - defined)} next to entities an "
                "earlier file already defines; split it so each entity is read once."
            )
        for entity in sorted(defined):
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
        if not defined:
            kept.append(path)
            first_definition.update({entity: (path, library) for entity in entities})
    return kept, pack_modules


def _vhdl_to_verilog(
    project: Path, models_pack: Path, work_dir: Path
) -> tuple[Path, set[str]]:
    """Synthesise the VHDL fabric of `project` into one Verilog netlist.

    Returns the netlist and the pack module names from `_vhdl_sources`.
    """
    sources, pack_modules = _vhdl_sources(project, models_pack, work_dir)
    top = _fabric_top(project, VHDL_SUFFIXES).stem.lower()
    fabric_library = work_dir / "fabric"
    _ghdl_analyse(fabric_library, [models_pack, *sources])
    fabric = _ghdl_synth(fabric_library, top, work_dir / "fabric.v")
    return fabric, pack_modules


def _hide_ghdl_nets(
    rtlil: Path, netlist: Path, modules: dict[str, Any], script: Path
) -> dict[str, Any]:
    """Make the numbered nets of a GHDL netlist private and rewrite the design.

    GHDL numbers anonymous nets across the whole design, so once the two sides
    differ the same name denotes unrelated nets and `equiv_make` would pair them.
    Hiding a name removes only a matching hint, so it can cause a false failure but
    never a false pass.

    Parameters
    ----------
    rtlil : Path
        RTLIL design, rewritten in place.
    netlist : Path
        Yosys JSON of the same design, rewritten in place.
    modules : dict[str, Any]
        The `modules` table of `netlist`.
    script : Path
        Path for the yosys script; its log goes next to it.

    Returns
    -------
    dict[str, Any]
        The `modules` table of the rewritten netlist.
    """
    hide: list[str] = []
    for module, body in modules.items():
        nets = [
            net
            for net in body["netnames"]
            if (last := net.rsplit("_", 1)[-1])[0] == "n" and last[1:].isdigit()
        ]
        # One command per module; one per net costs a full design walk each.
        if nets:
            hide.append(f"rename -hide {' '.join(f'{module}/w:{n}' for n in nets)}")
    script.write_text(
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
    YosysTool.run(args=["-q", "-l", str(script.with_suffix(".log")), str(script)])
    return json.loads(netlist.read_text())["modules"]


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
            fabric, pack_modules = _vhdl_to_verilog(project, models_pack, source_dir)
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
            # pack_modules comes from `_vhdl_to_verilog` in the read step above.
            modules = _hide_ghdl_nets(
                rtlil, netlist, modules, work_dir / f"{tag}_hide.ys"
            )
            project_modules = modules.keys() - pack_modules
    return _Design(rtlil=rtlil, modules=modules, project_modules=project_modules)


def _instances(design: _Design, module: str) -> Instances:
    """Map each project-module instance in `module` to its type and parameters."""
    return {
        name: (cell["type"], tuple(sorted(cell.get("parameters", {}).items())))
        for name, cell in design.modules[module]["cells"].items()
        if cell["type"] in design.project_modules
    }


def _prepare(rtlil: Path, module: str, children: list[str], tag: str) -> list[str]:
    """Return the yosys commands that reduce `module` to one proof side named `tag`."""
    lines = [f'read_rtlil "{rtlil}"', f"hierarchy -top {module}"]
    if children:
        lines += [
            f"setattr -mod -set keep_hierarchy 1 {' '.join(children)}",
            f"flatten {module}",
            f"blackbox * {module} %d",
            # The GHDL plugin gives internal cells public names; cut only instances.
            f"expose -evert {module}/c:* {module}/t:$* %d",
        ]
    else:
        lines.append("flatten")
    # async2sync: `sat` cannot model the config latches as `$dlatch`.
    lines += [
        "memory",
        "async2sync",
        "opt_clean",
        f"rename {module} {tag}",
        f"design -stash {tag}",
    ]
    return lines


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
    log = script.with_suffix(".log")
    script.write_text(
        "\n".join(
            [
                *_prepare(reference.rtlil, module, children, "gold"),
                *_prepare(regenerated.rtlil, module, children, "gate"),
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
            module=module,
            reason="not equivalent",
            detail=f"{errors[-1] if errors else 'yosys failed'} (log: {log})",
        )
    return None


def _prove_modules(
    gold: _Design, gate: _Design, modules: list[str], work_dir: Path
) -> list[EquivalenceFailure]:
    """Compare the instance maps of `modules` and prove each module equivalent."""
    failures: list[EquivalenceFailure] = []
    jobs: list[tuple[str, list[str]]] = []
    for module in modules:
        gold_instances = _instances(gold, module)
        gate_instances = _instances(gate, module)
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


def _elaborate_vhdl(
    project: Path, models_pack: Path, work_dir: Path, tag: str
) -> _Design:
    """Elaborate the VHDL fabric of `project` with the yosys GHDL plugin.

    Every module that is not a pack architecture counts as a project module, and a
    pack architecture elaborated with generics stays a pack module.
    """
    source_dir = work_dir / f"{tag}_sources"
    source_dir.mkdir()
    sources, pack_modules = _vhdl_sources(project, models_pack, source_dir)
    top = _fabric_top(project, VHDL_SUFFIXES).stem
    rtlil = work_dir / f"{tag}.il"
    netlist = work_dir / f"{tag}.json"
    script = work_dir / f"{tag}_parse.ys"
    script.write_text(
        "\n".join(
            [
                f"ghdl {' '.join(GHDL_FLAGS)} {models_pack} "
                f"{' '.join(map(str, sources))} -e {top}",
                "hierarchy -check",
                "proc",
                "opt_clean",
                f'write_rtlil "{rtlil}"',
                f'write_json "{netlist}"',
            ]
        )
    )
    YosysTool.run(
        args=["-m", "ghdl", "-q", "-l", str(script.with_suffix(".log")), str(script)]
    )
    modules: dict[str, Any] = json.loads(netlist.read_text())["modules"]
    project_modules = {
        name
        for name in modules
        if not any(name == p or name.startswith(f"{p}_") for p in pack_modules)
    }
    return _Design(rtlil=rtlil, modules=modules, project_modules=project_modules)


def _pair_modules(
    verilog: _Design, verilog_top: str, vhdl: _Design, vhdl_top: str
) -> tuple[dict[str, str], list[EquivalenceFailure]]:
    """Map each VHDL module reachable from `vhdl_top` to its Verilog module.

    GHDL names a module after its entity, architecture and generic values, so the
    two sides are paired by walking the hierarchy and matching instance names
    without case.

    Parameters
    ----------
    verilog : _Design
        Elaborated Verilog fabric.
    verilog_top : str
        Fabric top module of `verilog`.
    vhdl : _Design
        Elaborated VHDL fabric.
    vhdl_top : str
        Fabric top module of `vhdl`.

    Returns
    -------
    tuple[dict[str, str], list[EquivalenceFailure]]
        VHDL module name to Verilog module name, and one failure per instance that
        exists on one side only or pairs two modules already paired otherwise.
    """
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
            for name, cell in vhdl.modules[vhdl_module]["cells"].items()
            if cell["type"] in vhdl.project_modules
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
    return mapping, failures


def _fold_case(modules: dict[str, Any], rename: dict[str, str]) -> dict[str, Any]:
    """Lower-case the port, net and cell names of `modules` and apply `rename`.

    VHDL identifiers are case-insensitive and GHDL writes them in lower case, so
    both sides are folded before `equiv_make` matches names. The fold raises
    `ValueError` if two port, net or cell names of one module differ only in case.

    Parameters
    ----------
    modules : dict[str, Any]
        The `modules` table of a yosys JSON netlist.
    rename : dict[str, str]
        New names for modules, applied to definitions and cell types.

    Returns
    -------
    dict[str, Any]
        The folded `modules` table.
    """

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
    return result


def _write_design(
    modules: dict[str, Any], project_modules: set[str], path: Path
) -> _Design:
    """Write a `modules` table to `path` as yosys JSON and RTLIL."""
    netlist = path.with_suffix(".json")
    rtlil = path.with_suffix(".il")
    script = path.with_suffix(".ys")
    netlist.write_text(json.dumps({"modules": modules}))
    script.write_text(f'read_json "{netlist}"\nwrite_rtlil "{rtlil}"')
    YosysTool.run(args=["-q", "-l", str(path.with_suffix(".log")), str(script)])
    return _Design(rtlil=rtlil, modules=modules, project_modules=project_modules)


def check_vhdl_verilog_equivalence(
    verilog_project: Path,
    vhdl_project: Path,
    verilog_models_pack: Path,
    vhdl_models_pack: Path,
    work_dir: Path,
) -> list[EquivalenceFailure]:
    """Check the VHDL fabric of a project against its Verilog fabric.

    The yosys GHDL plugin elaborates the VHDL side directly, which keeps the config
    latches. Modules are paired through the hierarchy below the fabric top, so a
    module the top does not reach is not checked. Each paired module has its port
    directions and widths and its instance map compared, and yosys proves it
    equivalent with the Verilog side as gold.

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
        If no paired module is left to prove.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    verilog = _parse(
        verilog_project, verilog_models_pack, "verilog", work_dir, "verilog"
    )
    vhdl = _elaborate_vhdl(vhdl_project, vhdl_models_pack, work_dir, "vhdl")
    mapping, failures = _pair_modules(
        verilog,
        _fabric_top(verilog_project, VERILOG_SUFFIXES).stem,
        vhdl,
        _fabric_top(vhdl_project, VHDL_SUFFIXES).stem,
    )
    paired = set(mapping.values())
    gold = _write_design(
        _fold_case(verilog.modules, {}), paired, work_dir / "verilog_folded"
    )
    gate = _write_design(
        _fold_case(vhdl.modules, mapping), paired, work_dir / "vhdl_folded"
    )

    proved: list[str] = []
    for module in sorted(paired):
        gold_ports = {
            name: (port["direction"], len(port["bits"]))
            for name, port in gold.modules[module]["ports"].items()
        }
        gate_ports = {
            name: (port["direction"], len(port["bits"]))
            for name, port in gate.modules[module]["ports"].items()
        }
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
