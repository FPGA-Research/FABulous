"""Yosys equivalence of regenerated reference-project RTL.

A project opts in with `rtl_equivalence: true` in the reference projects config.
`reference_projects_test.py` then leaves its RTL out of the text diff, and this
module proves the regenerated RTL equivalent to the reference instead.
"""

import shutil
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_settings import get_context
from tests.equivalence import EquivalenceFailure, parse_project, prove_modules
from tests.reference_test.helpers import generate_project
from tests.reference_test.reference_projects_test import (
    ReferenceProject,
    load_reference_projects_config,
)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrise over the active projects that set `rtl_equivalence`."""
    # Imported here: conftest sets the config path in `pytest_configure`.
    from tests.reference_test.conftest import _session_config

    assert _session_config.projects_conf is not None
    projects = [
        project
        for project in load_reference_projects_config(_session_config.projects_conf)
        if project.rtl_equivalence and project.skip_reason is None
    ]
    metafunc.parametrize("ref_project", projects, ids=[p.name for p in projects])


def _check_rtl_equivalence(
    reference: Path,
    regenerated: Path,
    models_pack: Path,
    language: HDLType,
    top: str,
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
    language : HDLType
        HDL of both projects. GHDL synthesises VHDL to Verilog first.
    top : str
        Fabric top module, `<fabric>_top`.
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
    gold, gate = (
        parse_project(
            project=project,
            models_pack=project / models_pack,
            language=language,
            top=top,
            work_dir=work_dir,
            tag=tag,
        )
        for project, tag in ((reference, "gold"), (regenerated, "gate"))
    )

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
    return failures + prove_modules(gold, gate, proved, work_dir)


def test_rtl_equivalence(
    ref_project: ReferenceProject,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regenerated fabric RTL of `ref_project` is equivalent to the reference."""
    regenerated = tmp_path / ref_project.path.name
    shutil.copytree(ref_project.path, regenerated, symlinks=True)
    fabric = generate_project(
        regenerated,
        ref_project.language,
        caplog,
        monkeypatch,
        pre_fab_commands=ref_project.pre_fab_commands,
        fab_commands=ref_project.fab_commands,
    )

    models_pack = get_context().models_pack
    assert models_pack is not None, f"No models pack configured for {ref_project.name}"
    failures = _check_rtl_equivalence(
        reference=ref_project.path,
        regenerated=regenerated,
        models_pack=models_pack.relative_to(regenerated),
        language=ref_project.language,
        top=f"{fabric}_top",
        work_dir=tmp_path / "equivalence",
    )
    if failures:
        report = "\n".join(
            f"  {f.module}: {f.reason}" + (f": {f.detail}" if f.detail else "")
            for f in failures
        )
        pytest.fail(
            f"RTL of {ref_project.name} is not equivalent to the reference in "
            f"{len(failures)} modules:\n{report}"
        )
