"""Upgrade a project created before the Yosys `synth_fabulous` rework.

Yosys 0.67 stopped shipping the FABulous primitives and technology maps, which a
project now carries in `yosys/`. The upgrade copies that library into the project
and rewrites the synthesis invocation of `Test/Taskfile.yml` and `Test/Makefile`
into the form the current templates ship.

TODO(3.0): remove, together with the rest of the support for Yosys <= 0.66 and
for projects created before the `yosys/` library folder existed.
"""

import shutil
from pathlib import Path

from dotenv import get_key
from loguru import logger

from fabulous.custom_exception import ProjectUpgradeError
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_files import PACKAGED_YOSYS_LIB, TEMPLATE_DIR

# The run-yosys variable every Taskfile since FABulous 2.0.0 declares; the
# library probe goes right after it.
_TASKFILE_ANCHOR = (
    "      CUSTOM_PRIMS:\n"
    '        sh: \'[ -f "{{.USER_DESIGN_DIR}}/custom_prims.v" ] && echo '
    '"-extra-plib {{.USER_DESIGN_DIR}}/custom_prims.v" || true\'\n'
)
_MAKEFILE_ANCHOR = (
    "ifneq ($(wildcard ${USER_DESIGN_DIR}/custom_prims.v),)\n"
    "\t\tCUSTOM_PRIMS=-extra-plib ${USER_DESIGN_DIR}/custom_prims.v\n"
    "endif\n"
)

# Every synthesis line the templates have shipped since FABulous 2.0.0.
_PRE_REWORK_SYNTH_CMDS: dict[HDLType, tuple[str, ...]] = {
    HDLType.VERILOG: (
        "          SYNTH_CMD: 'synth_fabulous -top {{.TOP_WRAPPER}} -json "
        "{{.RESOLVED_JSON_FILE}} {{.CUSTOM_PRIMS}} "
        '{{.SYNTH_EXTRA_ARGS | default ""}}\'',
        '          SYNTH_CMD: "synth_fabulous -top {{.TOP_WRAPPER}} -json '
        "{{.RESOLVED_JSON_FILE}} {{.CUSTOM_PRIMS}} "
        '{{.SYNTH_EXTRA_ARGS | default \\"\\"}}"',
        '          SYNTH_CMD: "synth_fabulous -top {{.TOP_WRAPPER}} -json '
        '{{.BUILD_DIR}}/{{.DESIGN}}.json {{.CUSTOM_PRIMS}}"',
    ),
    HDLType.VHDL: (
        '          SYNTH_CMD: "ghdl {{.RESOLVED_DESIGN_FILES}} -e {{.DESIGN}}; '
        "read_verilog {{.RESOLVED_TOP_WRAPPER_FILE}}; synth_fabulous -top "
        "{{.TOP_WRAPPER}} -json {{.RESOLVED_JSON_FILE}} {{.CUSTOM_PRIMS}} "
        '{{.SYNTH_EXTRA_ARGS | default \\"\\"}};"',
        '          SYNTH_CMD: "ghdl {{.USER_DESIGN_DIR}}/{{.DESIGN}}.vhdl -e '
        "{{.DESIGN}}; read_verilog {{.USER_DESIGN_DIR}}/{{.TOP_WRAPPER}}.v; "
        "synth_fabulous -top {{.TOP_WRAPPER}} -json {{.BUILD_DIR}}/{{.DESIGN}}.json "
        '{{.CUSTOM_PRIMS}};"',
    ),
}
_PRE_REWORK_YOSYS_RECIPES: dict[HDLType, tuple[str, ...]] = {
    HDLType.VERILOG: (
        '\t${YOSYS} -p "synth_fabulous -top ${TOP_WRAPPER} -json '
        '${BUILD_DIR}/${DESIGN}.json ${CUSTOM_PRIMS}" ${USER_DESIGN_VERILOG} '
        "${TOP_WRAPPER_VERILOG}",
    ),
    HDLType.VHDL: (
        '\t${YOSYS} -m ghdl -p "ghdl ${USER_DESIGN_VHDL} -e ${DESIGN}; read_verilog '
        "${TOP_WRAPPER_VERILOG}; synth_fabulous -top ${TOP_WRAPPER} -json "
        '${BUILD_DIR}/${DESIGN}.json ${CUSTOM_PRIMS};"',
    ),
}


def _template_probe_block(template: Path, closing_line: str) -> str:
    """Return the Yosys library probe of a template, from its TODO to its closing.

    Parameters
    ----------
    template : Path
        Template Taskfile or Makefile.
    closing_line : str
        Stripped line that ends the probe conditional.

    Returns
    -------
    str
        The probe lines, newline-terminated.

    Raises
    ------
    ProjectUpgradeError
        If the template carries no probe.
    """
    lines = template.read_text().splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if "TODO(3.0): drop Yosys" in line]
    ends = [i for i, line in enumerate(lines) if line.strip() == closing_line]
    if len(starts) != 1 or not any(end > starts[0] for end in ends):
        raise ProjectUpgradeError(f"No Yosys library probe found in {template}")
    end = min(end for end in ends if end > starts[0])
    return "".join(lines[starts[0] : end + 1])


def _upgraded_synth_file(
    path: Path,
    *,
    known_lines: tuple[str, ...],
    anchor: str,
    probe: str,
    custom_prims_ref: str,
    lib_args_ref: str,
) -> str | None:
    """Return `path` with the library probe added to its synthesis invocation.

    Parameters
    ----------
    path : Path
        Taskfile or Makefile to upgrade.
    known_lines : tuple[str, ...]
        The synthesis lines a pre-rework template of the project's language
        shipped.
    anchor : str
        Text the probe is inserted after.
    probe : str
        The probe of the current template.
    custom_prims_ref : str
        Reference to the custom primitives in the synthesis line.
    lib_args_ref : str
        Reference to the library options, placed before `custom_prims_ref`.

    Returns
    -------
    str | None
        The upgraded text, or `None` if `path` is already upgraded.

    Raises
    ------
    ProjectUpgradeError
        If the synthesis line or the anchor is not in a known pre-rework form.
    """
    text = path.read_text()
    lines = text.splitlines()
    if any(lib_args_ref in line and custom_prims_ref in line for line in lines):
        return None

    matches = [line for line in lines if line in known_lines]
    if len(matches) != 1:
        expected = "\n".join(known_lines)
        raise ProjectUpgradeError(
            f"{path}: found {len(matches)} synthesis lines in a known pre-rework "
            f"form, expected exactly one of:\n{expected}"
        )
    if text.count(anchor) != 1:
        raise ProjectUpgradeError(
            f"{path}: expected exactly one occurrence of:\n{anchor}"
        )
    old_line = matches[0]
    new_line = old_line.replace(custom_prims_ref, f"{lib_args_ref} {custom_prims_ref}")
    return text.replace(anchor, anchor + probe).replace(old_line, new_line)


def upgrade_to_yosys_library(project_dir: Path) -> None:
    """Upgrade a project to carry and use its own Yosys library.

    Copies the files of the packaged `yosys/` library that the project lacks,
    then adds the library options to the synthesis invocation of
    `Test/Taskfile.yml` and `Test/Makefile`, keeping the original of each
    changed file as `<file>.bak`. Every check runs before the first write, so
    a failure leaves the project untouched. Files already in the current form
    are left alone, which makes the upgrade idempotent.

    Parameters
    ----------
    project_dir : Path
        Root of the FABulous project.

    Raises
    ------
    ProjectUpgradeError
        If the project language is unsupported, `Test/Taskfile.yml` is missing,
        a synthesis invocation is in an unknown form, or a `.bak` file to be
        written already exists.
    """
    env_file = project_dir / ".FABulous" / ".env"
    lang_value = get_key(env_file, "FAB_PROJ_LANG")
    languages = {lang.value: lang for lang in _PRE_REWORK_SYNTH_CMDS}
    if lang_value not in languages:
        raise ProjectUpgradeError(
            f"{env_file}: FAB_PROJ_LANG is {lang_value!r}, expected one of "
            f"{sorted(languages)}"
        )
    lang = languages[lang_value]
    template_test_dir = TEMPLATE_DIR / f"FABulous_project_template_{lang}" / "Test"
    test_dir = project_dir / "Test"

    taskfile = test_dir / "Taskfile.yml"
    if not taskfile.is_file():
        raise ProjectUpgradeError(f"{taskfile} not found")
    upgrades: dict[Path, str] = {}
    taskfile_text = _upgraded_synth_file(
        taskfile,
        known_lines=_PRE_REWORK_SYNTH_CMDS[lang],
        anchor=_TASKFILE_ANCHOR,
        probe=_template_probe_block(template_test_dir / "Taskfile.yml", "fi"),
        custom_prims_ref="{{.CUSTOM_PRIMS}}",
        lib_args_ref="{{.SYNTH_LIB_ARGS}}",
    )
    if taskfile_text is None:
        logger.info(f"{taskfile} already passes the Yosys library")
    else:
        upgrades[taskfile] = taskfile_text

    makefile = test_dir / "Makefile"
    if not makefile.is_file():
        logger.info(f"{makefile} not found, nothing to upgrade")
    else:
        makefile_text = _upgraded_synth_file(
            makefile,
            known_lines=_PRE_REWORK_YOSYS_RECIPES[lang],
            anchor=_MAKEFILE_ANCHOR,
            probe="\n" + _template_probe_block(template_test_dir / "Makefile", "endif"),
            custom_prims_ref="${CUSTOM_PRIMS}",
            lib_args_ref="${SYNTH_LIB_ARGS}",
        )
        if makefile_text is None:
            logger.info(f"{makefile} already passes the Yosys library")
        else:
            upgrades[makefile] = makefile_text

    for path in upgrades:
        backup = path.with_name(f"{path.name}.bak")
        if backup.exists():
            raise ProjectUpgradeError(
                f"{backup} already exists; move it away before upgrading {path}"
            )

    project_lib = project_dir / "yosys"
    for source in sorted(PACKAGED_YOSYS_LIB.rglob("*")):
        if not source.is_file():
            continue
        target = project_lib / source.relative_to(PACKAGED_YOSYS_LIB)
        if target.exists():
            logger.info(f"Kept existing {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        logger.info(f"Copied {target}")

    for path, text in upgrades.items():
        backup = path.with_name(f"{path.name}.bak")
        shutil.copy2(path, backup)
        path.write_text(text)
        logger.info(
            f"Added the Yosys library to the synthesis invocation of {path}; "
            f"the original is kept as {backup}"
        )
