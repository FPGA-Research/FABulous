"""Tests for upgrading a project created before the Yosys `synth_fabulous` rework.

TODO(3.0): remove together with `upgrade_to_yosys_library`.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture
from pytest_mock import MockerFixture

from fabulous.custom_exception import ProjectUpgradeError
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_files import PACKAGED_YOSYS_LIB, TEMPLATE_DIR
from fabulous.fabulous_repl.cmd_user_design import pre_rework_synth_compat_args
from fabulous.fabulous_repl.helper import update_project_version
from fabulous.fabulous_repl.project_upgrade import (
    _PRE_REWORK_SYNTH_CMDS,
    upgrade_to_yosys_library,
)
from tests.conftest import PRE_REWORK_TEST_FILES

LANGS = [HDLType.VERILOG, HDLType.VHDL]
SYNTH_FILES = ["Taskfile.yml", "Makefile"]


def _snapshot(project_dir: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(project_dir): path.read_bytes()
        for path in sorted(project_dir.rglob("*"))
        if path.is_file()
    }


@pytest.mark.parametrize("lang", LANGS)
def test_upgrade_matches_current_template(
    lang: HDLType, pre_rework_project_factory: Callable[..., Path]
) -> None:
    """An upgraded project carries the current library, Taskfile and Makefile."""
    project_dir = pre_rework_project_factory(lang=lang)

    assert update_project_version(project_dir)

    template_test_dir = TEMPLATE_DIR / f"FABulous_project_template_{lang}" / "Test"
    for name in SYNTH_FILES:
        upgraded = project_dir / "Test" / name
        assert upgraded.read_text() == (template_test_dir / name).read_text()
        backup = upgraded.with_name(f"{name}.bak")
        assert backup.read_text() == (PRE_REWORK_TEST_FILES / lang / name).read_text()
    for source in PACKAGED_YOSYS_LIB.rglob("*.*"):
        copied = project_dir / "yosys" / source.relative_to(PACKAGED_YOSYS_LIB)
        assert copied.read_bytes() == source.read_bytes()


@pytest.mark.parametrize("lang", LANGS)
def test_upgrade_is_idempotent(
    lang: HDLType, pre_rework_project_factory: Callable[..., Path]
) -> None:
    """A second upgrade changes nothing and writes no further backup."""
    project_dir = pre_rework_project_factory(lang=lang)
    upgrade_to_yosys_library(project_dir)
    upgraded = _snapshot(project_dir)

    upgrade_to_yosys_library(project_dir)

    assert _snapshot(project_dir) == upgraded


@pytest.mark.parametrize("name", SYNTH_FILES)
@pytest.mark.parametrize("lang", LANGS)
def test_unknown_synth_line_fails_without_changes(
    lang: HDLType, name: str, pre_rework_project_factory: Callable[..., Path]
) -> None:
    """A hand-edited synthesis line aborts the upgrade before any write."""
    project_dir = pre_rework_project_factory(lang=lang)
    edited = project_dir / "Test" / name
    edited.write_text(
        edited.read_text()
        .replace("${CUSTOM_PRIMS}", "${CUSTOM_PRIMS} -nofsm")
        .replace("{{.CUSTOM_PRIMS}}", "{{.CUSTOM_PRIMS}} -nofsm")
    )
    before = _snapshot(project_dir)

    with pytest.raises(
        ProjectUpgradeError,
        match=rf"{re.escape(str(edited))}(.|\n)*expected exactly one of",
    ):
        upgrade_to_yosys_library(project_dir)

    assert _snapshot(project_dir) == before


@pytest.mark.parametrize("name", SYNTH_FILES)
def test_existing_backup_fails_without_changes(
    name: str, pre_rework_project_factory: Callable[..., Path]
) -> None:
    """An existing `.bak` is never overwritten."""
    project_dir = pre_rework_project_factory()
    backup = project_dir / "Test" / f"{name}.bak"
    backup.write_text("user backup\n")
    before = _snapshot(project_dir)

    with pytest.raises(
        ProjectUpgradeError, match=rf"{re.escape(str(backup))} already exists"
    ):
        upgrade_to_yosys_library(project_dir)

    assert _snapshot(project_dir) == before


def test_partial_library_keeps_existing_files(
    pre_rework_project_factory: Callable[..., Path], caplog: LogCaptureFixture
) -> None:
    """Existing library files are kept, only the missing ones are copied."""
    project_dir = pre_rework_project_factory()
    kept = project_dir / "yosys" / "techmap" / "io_map.v"
    kept.parent.mkdir(parents=True)
    kept.write_text("// user io map\n")

    upgrade_to_yosys_library(project_dir)

    assert kept.read_text() == "// user io map\n"
    assert f"Kept existing {kept}" in caplog.text
    prims = project_dir / "yosys" / "primitives" / "prims.v"
    assert (
        prims.read_bytes()
        == (PACKAGED_YOSYS_LIB / "primitives" / "prims.v").read_bytes()
    )
    assert f"Copied {prims}" in caplog.text


def test_missing_makefile_is_skipped(
    pre_rework_project_factory: Callable[..., Path],
) -> None:
    """The deprecated Makefile may be absent; the Taskfile is still upgraded."""
    project_dir = pre_rework_project_factory()
    (project_dir / "Test" / "Makefile").unlink()

    upgrade_to_yosys_library(project_dir)

    assert (project_dir / "Test" / "Taskfile.yml.bak").is_file()
    assert not (project_dir / "Test" / "Makefile").exists()


def test_missing_taskfile_fails(
    pre_rework_project_factory: Callable[..., Path],
) -> None:
    """A project without a Taskfile cannot be upgraded."""
    project_dir = pre_rework_project_factory()
    taskfile = project_dir / "Test" / "Taskfile.yml"
    taskfile.unlink()

    with pytest.raises(
        ProjectUpgradeError, match=rf"{re.escape(str(taskfile))} not found"
    ):
        upgrade_to_yosys_library(project_dir)


@pytest.mark.parametrize(
    ("lang", "synth_cmd"),
    [(lang, line) for lang, lines in _PRE_REWORK_SYNTH_CMDS.items() for line in lines],
)
def test_every_known_taskfile_form_is_upgraded(
    lang: HDLType, synth_cmd: str, pre_rework_project_factory: Callable[..., Path]
) -> None:
    """Every synthesis line shipped since FABulous 2.0.0 gains the library."""
    project_dir = pre_rework_project_factory(lang=lang)
    taskfile = project_dir / "Test" / "Taskfile.yml"
    current = next(
        line for line in taskfile.read_text().splitlines() if "SYNTH_CMD:" in line
    )
    taskfile.write_text(taskfile.read_text().replace(current, synth_cmd))

    upgrade_to_yosys_library(project_dir)

    expected = synth_cmd.replace(
        "{{.CUSTOM_PRIMS}}", "{{.SYNTH_LIB_ARGS}} {{.CUSTOM_PRIMS}}"
    )
    assert expected in taskfile.read_text().splitlines()


def test_compile_injection_stops_after_upgrade(
    pre_rework_project_factory: Callable[..., Path], mocker: MockerFixture
) -> None:
    """An upgraded project gets no library injected by `compile_design`."""
    project_dir = pre_rework_project_factory()
    upgrade_to_yosys_library(project_dir)
    probe = mocker.patch("fabulous.fabulous_repl.cmd_user_design.sp.run")

    assert pre_rework_synth_compat_args(project_dir, "yosys", "-nofsm") == "-nofsm"
    probe.assert_not_called()


def test_current_project_is_left_alone(project: Path) -> None:
    """A project created from the current template needs no upgrade."""
    before = _snapshot(project)

    upgrade_to_yosys_library(project)

    assert _snapshot(project) == before
