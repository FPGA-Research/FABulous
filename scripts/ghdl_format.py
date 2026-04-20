#!/usr/bin/env python3
"""Reformat VHDL with GHDL.

Prefers a system-installed ``ghdl`` binary on ``PATH``; otherwise falls back
to the pinned GHDL Docker image.

Every invocation analyses all project VHDL into a shared work library inside a
tempdir so cross-file entity references (``entity work.cus_mux21`` etc.)
resolve; then ``ghdl --format`` reprints each file passed on the command line
and rewrites it if the output differs. Exits non-zero so pre-commit reports the
reformat.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

GHDL_IMAGE = "ghdl/ghdl:6.0.0-mcode-ubuntu-24.04"
VHDL_STD = "08"
PROJECT_ROOTS = ("fabulous", "tests")
DOCKER_REPO_MOUNT = "/work"
DOCKER_WORKDIR_MOUNT = "/ghdlwork"


def discover_vhdl(repo_root: Path) -> list[Path]:
    """Return every ``.vhd`` / ``.vhdl`` source under the project roots."""
    found: list[Path] = []
    for root in PROJECT_ROOTS:
        found.extend((repo_root / root).rglob("*.vhd"))
        found.extend((repo_root / root).rglob("*.vhdl"))
    return sorted(set(found))


class GhdlRunner:
    """Run ghdl natively when available, else via the pinned Docker image."""

    def __init__(self, repo_root: Path, workdir: Path) -> None:
        self.repo_root = repo_root
        self.workdir = workdir
        self.native = shutil.which("ghdl")

    @property
    def workdir_flag(self) -> str:
        path = str(self.workdir) if self.native else DOCKER_WORKDIR_MOUNT
        return f"--workdir={path}"

    def run(self, args: list[str]) -> subprocess.CompletedProcess:
        """Invoke ghdl with ``args`` and return the completed process."""
        if self.native:
            cmd = [self.native, *args]
        else:
            cmd = [
                "docker",
                "run",
                "--rm",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-v",
                f"{self.repo_root}:{DOCKER_REPO_MOUNT}",
                "-v",
                f"{self.workdir}:{DOCKER_WORKDIR_MOUNT}",
                "-w",
                DOCKER_REPO_MOUNT,
                GHDL_IMAGE,
                "ghdl",
                *args,
            ]
        return subprocess.run(
            cmd,
            cwd=self.repo_root if self.native else None,
            capture_output=True,
            text=True,
            check=False,
        )


def analyse_project(runner: GhdlRunner, files: list[Path]) -> None:
    """Analyse every project VHDL file into the shared work library.

    Two passes so out-of-order dependencies resolve on the second sweep. Only
    the last pass's stderr is surfaced so users see errors located at the
    right file rather than transient first-pass noise.
    """
    rel = [str(p.relative_to(runner.repo_root)) for p in files]
    base = ["-a", runner.workdir_flag, f"--std={VHDL_STD}"]
    last = None
    for _ in range(2):
        last = runner.run(base + rel)
    if last is not None and last.returncode != 0:
        sys.stderr.write(last.stderr)
        raise SystemExit("ghdl -a failed during project analysis")


def reprint(runner: GhdlRunner, path: Path) -> str:
    """Return the ``ghdl --format`` reprint of ``path`` using the shared workdir."""
    rel = str(path.relative_to(runner.repo_root))
    result = runner.run(
        ["--format", runner.workdir_flag, f"--std={VHDL_STD}", rel],
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
        runner = GhdlRunner(repo_root, Path(tmp))
        analyse_project(runner, project_files)
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            formatted_texts = list(pool.map(lambda p: reprint(runner, p), targets))
        changed = 0
        for path, formatted in zip(targets, formatted_texts, strict=True):
            if formatted != path.read_text():
                path.write_text(formatted)
                sys.stderr.write(f"reformatted {path.relative_to(repo_root)}\n")
                changed += 1
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
