#!/usr/bin/env python3
"""Reformat VHDL with the pinned GHDL Docker image.

Every invocation analyses all project VHDL into a shared work library inside a
tempdir so cross-file entity references (``entity work.cus_mux21`` etc.)
resolve; then ``ghdl --format`` reprints each file passed on the command line
and rewrites it if the output differs. Exits non-zero so pre-commit reports the
reformat.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

GHDL_IMAGE = "ghdl/ghdl:6.0.0-mcode-ubuntu-24.04"
VHDL_STD = "08"
PROJECT_ROOTS = ("fabulous", "tests")


def discover_vhdl(repo_root: Path) -> list[Path]:
    """Return every ``.vhd`` / ``.vhdl`` source under the project roots."""
    found: list[Path] = []
    for root in PROJECT_ROOTS:
        found.extend((repo_root / root).rglob("*.vhd"))
        found.extend((repo_root / root).rglob("*.vhdl"))
    return sorted(set(found))


def docker_run(
    repo_root: Path, workdir: Path, argv: list[str]
) -> subprocess.CompletedProcess:
    """Run a GHDL command inside the pinned image with the repo + workdir mounted."""
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{repo_root}:/work",
            "-v",
            f"{workdir}:/ghdlwork",
            "-w",
            "/work",
            GHDL_IMAGE,
            *argv,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def analyse_project(repo_root: Path, workdir: Path, files: list[Path]) -> None:
    """Analyse every project VHDL file into the shared work library.

    Two passes so out-of-order dependencies resolve on the second sweep. Only
    the last pass's stderr is surfaced so users see errors located at the
    right file rather than transient first-pass noise.
    """
    rel = [str(p.relative_to(repo_root)) for p in files]
    base = ["ghdl", "-a", "--workdir=/ghdlwork", f"--std={VHDL_STD}"]
    last = None
    for _ in range(2):
        last = docker_run(repo_root, workdir, base + rel)
    if last is not None and last.returncode != 0:
        sys.stderr.write(last.stderr)
        raise SystemExit("ghdl -a failed during project analysis")


def reprint(repo_root: Path, workdir: Path, path: Path) -> str:
    """Return the ``ghdl --format`` reprint of ``path`` using the shared workdir."""
    rel = str(path.relative_to(repo_root))
    result = docker_run(
        repo_root,
        workdir,
        ["ghdl", "--format", "--workdir=/ghdlwork", f"--std={VHDL_STD}", rel],
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(f"ghdl --format failed for {rel}")
    return result.stdout


def main() -> int:
    """Reformat every VHDL target passed on argv; return 1 if any file changed."""
    targets = [Path(p).resolve() for p in sys.argv[1:]]
    if not targets:
        return 0
    repo_root = Path.cwd().resolve()
    project_files = discover_vhdl(repo_root)
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        analyse_project(repo_root, workdir, project_files)
        changed = 0
        for path in targets:
            formatted = reprint(repo_root, workdir, path)
            if formatted != path.read_text():
                path.write_text(formatted)
                sys.stderr.write(f"reformatted {path.relative_to(repo_root)}\n")
                changed += 1
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
