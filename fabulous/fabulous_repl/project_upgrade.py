"""Upgrade a project created before the Yosys `synth_fabulous` rework.

Yosys 0.67 stopped shipping the FABulous primitives and technology maps, which a
project now carries in `yosys/`. The upgrade copies that library into the project
and rewrites the synthesis invocation of `Test/Taskfile.yml` into the form the
current template ships and that of `Test/Makefile` into the form the last Makefile
template shipped.

TODO(3.0): remove, together with the rest of the support for Yosys <= 0.66 and
for projects created before the `yosys/` library folder existed.
"""

import filecmp
import shutil
from pathlib import Path

from loguru import logger

from fabulous.custom_exception import ProjectUpgradeError
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_files import PACKAGED_YOSYS_LIB, TEMPLATE_DIR
from fabulous.fabulous_settings import get_context

# The run-yosys variable every Taskfile since FABulous 2.0.0 declares; the
# library probe goes right after it.
_TASKFILE_ANCHORS = (
    "      CUSTOM_PRIMS:\n"
    '        sh: \'[ -f "{{.USER_DESIGN_DIR}}/custom_prims.v" ] && echo '
    '"-extra-plib {{.USER_DESIGN_DIR}}/custom_prims.v" || true\'\n',
)
# The 2.x Makefile indents the assignment with two tabs, the 1.x one with one.
_MAKEFILE_ANCHORS = (
    "ifneq ($(wildcard ${USER_DESIGN_DIR}/custom_prims.v),)\n"
    "\t\tCUSTOM_PRIMS=-extra-plib ${USER_DESIGN_DIR}/custom_prims.v\n"
    "endif\n",
    "ifneq ($(wildcard ${USER_DESIGN_DIR}/custom_prims.v),)\n"
    "\tCUSTOM_PRIMS=-extra-plib ${USER_DESIGN_DIR}/custom_prims.v\n"
    "endif\n",
)

# Every synthesis line the templates have shipped since FABulous 2.0.0b1.
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
# FABulous 2.0.0b1 to 2.0.0b4 call `yosys` by name and define no YOSYS variable.
_PRE_REWORK_YOSYS_RECIPES: dict[HDLType, tuple[str, ...]] = {
    HDLType.VERILOG: (
        '\t${YOSYS} -p "synth_fabulous -top ${TOP_WRAPPER} -json '
        '${BUILD_DIR}/${DESIGN}.json ${CUSTOM_PRIMS}" ${USER_DESIGN_VERILOG} '
        "${TOP_WRAPPER_VERILOG}",
        '\tyosys -p "synth_fabulous -top ${TOP_WRAPPER} -json '
        '${BUILD_DIR}/${DESIGN}.json ${CUSTOM_PRIMS}" ${USER_DESIGN_VERILOG} '
        "${TOP_WRAPPER_VERILOG}",
    ),
    HDLType.VHDL: (
        '\t${YOSYS} -m ghdl -p "ghdl ${USER_DESIGN_VHDL} -e ${DESIGN}; read_verilog '
        "${TOP_WRAPPER_VERILOG}; synth_fabulous -top ${TOP_WRAPPER} -json "
        '${BUILD_DIR}/${DESIGN}.json ${CUSTOM_PRIMS};"',
        '\tyosys -m ghdl -p "ghdl ${USER_DESIGN_VHDL} -e ${DESIGN}; read_verilog '
        "${TOP_WRAPPER_VERILOG}; synth_fabulous -top ${TOP_WRAPPER} -json "
        '${BUILD_DIR}/${DESIGN}.json ${CUSTOM_PRIMS};"',
    ),
}
# The probe runs ${YOSYS}, so the recipe must run the same binary.
_MAKEFILE_RENAMES = {"\tyosys ": "\t${YOSYS} "}
_MAKEFILE_YOSYS_DEF = "YOSYS?=$(or $(FAB_YOSYS_PATH),yosys)\n"
# The probe of the last Makefile template, shared by both languages. New projects
# ship no Makefile, so no template carries it any more.
_MAKEFILE_PROBE = (
    "# TODO(3.0): drop Yosys <= 0.66 support and pass the library options\n"
    "# unconditionally. Yosys before the synth_fabulous rework bundles its own\n"
    "# FABulous library, rejects these options and inserts pads only with -iopad.\n"
    "YOSYS_LIB_DIR=${FAB_PROJ_ROOT}/yosys\n"
    "SYNTH_LIB_OPTS=-extra-plib ${YOSYS_LIB_DIR}/primitives/prims.v \\\n"
    "    -cells-map ${YOSYS_LIB_DIR}/techmap/cells_map.v \\\n"
    "    -arith-map ${YOSYS_LIB_DIR}/techmap/arith_map.v \\\n"
    "    -extra-map ${YOSYS_LIB_DIR}/techmap/ff_map.v \\\n"
    "    -extra-map ${YOSYS_LIB_DIR}/techmap/latches_map.v \\\n"
    "    -extra-map ${YOSYS_LIB_DIR}/techmap/io_map.v \\\n"
    "    -extra-mlibmap ${YOSYS_LIB_DIR}/memlib/ram_regfile.txt \\\n"
    "    -extra-map ${YOSYS_LIB_DIR}/techmap/regfile_map.v \\\n"
    "    -ff \\$$_DFF_P_ 0 -ff \\$$_DLATCH_?_ x\n"
    "checked_yosys_probe=$(if $(findstring FAB_YOSYS_PROBE_FAILED,$1),"
    '$(error ${YOSYS} -p "help synth_fabulous" failed),$1)\n'
    "# Recursively expanded, so only run_yosys starts Yosys.\n"
    "SYNTH_LIB_ARGS=$(call checked_yosys_probe,$(shell \\\n"
    '    if ! help=$$(${YOSYS} -p "help synth_fabulous"); then '
    "echo FAB_YOSYS_PROBE_FAILED; \\\n"
    "    elif printf '%s\\n' \"$$help\" | grep -q -- -cells-map; then "
    "printf '%s\\n' '${SYNTH_LIB_OPTS}'; \\\n"
    '    else echo "WARNING: Yosys 0.66 and older is deprecated; support ends in '
    'FABulous 3.0." >&2; echo -iopad; fi))\n'
)


def _template_probe_block(template: Path, next_token: str) -> str:
    """Return the Yosys library probe of a template, from its TODO to its end.

    Parameters
    ----------
    template : Path
        Template Taskfile.
    next_token : str
        First token of the line that follows the probe; an empty string
        matches a blank line.

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
    ends = [
        i
        for i, line in enumerate(lines)
        if line.strip().partition(" ")[0] == next_token
    ]
    if len(starts) != 1 or not any(end > starts[0] for end in ends):
        raise ProjectUpgradeError(f"No Yosys library probe found in {template}")
    end = min(end for end in ends if end > starts[0])
    return "".join(lines[starts[0] : end])


def _upgraded_synth_file(
    path: Path,
    *,
    known_lines: tuple[str, ...],
    anchors: tuple[str, ...],
    probe: str,
    custom_prims_ref: str,
    lib_args_ref: str,
    renames: dict[str, str],
) -> str | None:
    """Return `path` with the library probe added to its synthesis invocation.

    Parameters
    ----------
    path : Path
        Taskfile or Makefile to upgrade.
    known_lines : tuple[str, ...]
        The synthesis lines a pre-rework template of the project's language
        shipped.
    anchors : tuple[str, ...]
        The known forms of the text the probe is inserted after.
    probe : str
        The Yosys library probe, inserted after the anchor.
    custom_prims_ref : str
        Reference to the custom primitives in the synthesis line.
    lib_args_ref : str
        Reference to the library options, placed before `custom_prims_ref`.
    renames : dict[str, str]
        Replacements applied to the synthesis line on top of adding
        `lib_args_ref`.

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

    matches = [i for i, line in enumerate(lines) if line in known_lines]
    if len(matches) != 1:
        expected = "\n".join(known_lines)
        raise ProjectUpgradeError(
            f"{path}: found {len(matches)} synthesis lines in a known pre-rework "
            f"form, expected exactly one of:\n{expected}"
        )
    present = [anchor for anchor in anchors if anchor in text]
    if len(present) != 1 or text.count(present[0]) != 1:
        expected = "\n".join(anchors)
        raise ProjectUpgradeError(
            f"{path}: expected exactly one occurrence of one of:\n{expected}"
        )
    new_line = lines[matches[0]].replace(
        custom_prims_ref, f"{lib_args_ref} {custom_prims_ref}"
    )
    for old, new in renames.items():
        new_line = new_line.replace(old, new)
    lines[matches[0]] = new_line
    upgraded = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return upgraded.replace(present[0], present[0] + probe)


def upgrade_to_yosys_library(project_dir: Path) -> None:
    """Upgrade a project to carry and use its own Yosys library.

    Copies the files of the packaged `yosys/` library that the project lacks,
    then adds the library options to the synthesis invocation of
    `Test/Taskfile.yml` and `Test/Makefile`, keeping the original of each
    changed file as `<file>.bak`. A Makefile that calls `yosys` by name is
    switched to `${YOSYS}`, the binary the probe runs. Every check runs before
    the first write, so a failure leaves the project untouched. Files already
    in the current form are left alone, which makes the upgrade idempotent.

    The project language comes from the current context, which must be the
    project at `project_dir`.

    Parameters
    ----------
    project_dir : Path
        Root of the FABulous project.

    Raises
    ------
    ProjectUpgradeError
        If the project language is unsupported, neither `Test/Taskfile.yml` nor
        `Test/Makefile` exists, a synthesis invocation is in an unknown form, a
        `.bak` file to be written already exists, or a file in `yosys/` differs
        from the packaged library.
    """
    lang = get_context().proj_lang
    if lang not in _PRE_REWORK_SYNTH_CMDS:
        raise ProjectUpgradeError(
            f"No FABulous project template exists for {lang}, expected one of "
            f"{sorted(_PRE_REWORK_SYNTH_CMDS)}"
        )
    template_test_dir = TEMPLATE_DIR / f"FABulous_project_template_{lang}" / "Test"
    test_dir = project_dir / "Test"

    taskfile = test_dir / "Taskfile.yml"
    makefile = test_dir / "Makefile"
    if not taskfile.is_file() and not makefile.is_file():
        raise ProjectUpgradeError(f"Neither {taskfile} nor {makefile} found")

    upgrades: dict[Path, str] = {}
    # A 1.x project has no Taskfile.
    if not taskfile.is_file():
        logger.info(f"{taskfile} not found, nothing to upgrade")
    else:
        taskfile_text = _upgraded_synth_file(
            taskfile,
            known_lines=_PRE_REWORK_SYNTH_CMDS[lang],
            anchors=_TASKFILE_ANCHORS,
            probe=_template_probe_block(
                template_test_dir / "Taskfile.yml", "RESOLVED_DESIGN_FILES:"
            ),
            custom_prims_ref="{{.CUSTOM_PRIMS}}",
            lib_args_ref="{{.SYNTH_LIB_ARGS}}",
            renames={},
        )
        if taskfile_text is None:
            logger.info(f"{taskfile} already passes the Yosys library")
        else:
            upgrades[taskfile] = taskfile_text

    if not makefile.is_file():
        logger.info(f"{makefile} not found, nothing to upgrade")
    else:
        defines_yosys = any(
            line.partition("=")[0].rstrip("?").strip() == "YOSYS"
            for line in makefile.read_text().splitlines()
        )
        makefile_text = _upgraded_synth_file(
            makefile,
            known_lines=_PRE_REWORK_YOSYS_RECIPES[lang],
            anchors=_MAKEFILE_ANCHORS,
            probe="\n"
            + ("" if defines_yosys else _MAKEFILE_YOSYS_DEF)
            + _MAKEFILE_PROBE,
            custom_prims_ref="${CUSTOM_PRIMS}",
            lib_args_ref="${SYNTH_LIB_ARGS}",
            renames=_MAKEFILE_RENAMES,
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
    copies: dict[Path, Path] = {}
    differing: list[Path] = []
    for source in sorted(PACKAGED_YOSYS_LIB.rglob("*")):
        if not source.is_file():
            continue
        target = project_lib / source.relative_to(PACKAGED_YOSYS_LIB)
        if not target.exists():
            copies[source] = target
        elif not filecmp.cmp(source, target, shallow=False):
            differing.append(target)
    if differing:
        listed = "\n".join(str(path) for path in differing)
        raise ProjectUpgradeError(
            f"These files differ from the library packaged at {PACKAGED_YOSYS_LIB}:\n"
            f"{listed}\nMove them out of {project_lib} before upgrading, then port "
            "your changes onto the copies the upgrade writes."
        )

    for source, target in copies.items():
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
