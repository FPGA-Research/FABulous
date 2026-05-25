"""Subprocess wrapper for FABulous nextpnr invocations.

The command wrapper owns only command construction and execution. Keeping it separate
from router orchestration makes it easy to extend nextpnr invocation with future options
such as pre-route scripts, router selection, or alternate report formats without
changing PCF generation or path resolution.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import TextIO

from fabulous.fabric_cad.fabxplore.modules.fabric_router.nextpnr.models import (
    NextpnrCommandResult,
)


class NextpnrCommand:
    """Build and run a FABulous nextpnr command.

    Parameters
    ----------
    executable : Path | str
        nextpnr executable path or command name.
    fab_root : Path | str
        FABulous project root exposed to nextpnr through ``FAB_ROOT``.
    cwd : Path | str | None
        Optional subprocess working directory.
    """

    def __init__(
        self,
        executable: Path | str,
        fab_root: Path | str,
        cwd: Path | str | None = None,
    ) -> None:
        self.executable = executable
        self.fab_root = Path(fab_root)
        self.cwd = Path(cwd) if cwd is not None else None

    def build_command(
        self,
        json_path: Path,
        pcf_path: Path,
        fasm_path: Path,
        report_path: Path,
        extra_args: tuple[str, ...] = (),
    ) -> list[str]:
        """Build the nextpnr command-line argument list.

        Parameters
        ----------
        json_path : Path
            Yosys JSON netlist path.
        pcf_path : Path
            Concrete PCF path.
        fasm_path : Path
            FASM output path.
        report_path : Path
            nextpnr JSON report path.
        extra_args : tuple[str, ...]
            Extra arguments appended to the command.

        Returns
        -------
        list[str]
            Command suitable for ``subprocess.run``.
        """
        return [
            str(self.executable),
            "--uarch",
            "fabulous",
            "--json",
            str(json_path),
            "-o",
            f"pcf={pcf_path}",
            "-o",
            f"fasm={fasm_path}",
            "--report",
            str(report_path),
            *extra_args,
        ]

    def run(
        self,
        json_path: Path,
        pcf_path: Path,
        fasm_path: Path,
        report_path: Path,
        extra_args: tuple[str, ...] = (),
        live_output: bool = False,
    ) -> NextpnrCommandResult:
        """Run nextpnr and capture its output.

        Parameters
        ----------
        json_path : Path
            Yosys JSON netlist path.
        pcf_path : Path
            Concrete PCF path.
        fasm_path : Path
            FASM output path.
        report_path : Path
            nextpnr JSON report path.
        extra_args : tuple[str, ...]
            Extra arguments appended to the command.
        live_output : bool
            If ``True``, mirror nextpnr stdout/stderr to the terminal while
            still capturing both streams.

        Returns
        -------
        NextpnrCommandResult
            Captured subprocess command, return code, and output streams.
        """
        command = self.build_command(
            json_path=json_path,
            pcf_path=pcf_path,
            fasm_path=fasm_path,
            report_path=report_path,
            extra_args=extra_args,
        )
        env = os.environ.copy()
        env["FAB_ROOT"] = str(self.fab_root)
        if live_output:
            return _run_with_live_output(
                command=command,
                cwd=self.cwd,
                env=env,
            )

        completed = subprocess.run(
            command,
            check=False,
            cwd=self.cwd,
            env=env,
            capture_output=True,
            text=True,
        )
        return NextpnrCommandResult(
            command=tuple(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _run_with_live_output(
    command: list[str],
    cwd: Path | None,
    env: dict[str, str],
) -> NextpnrCommandResult:
    """Run a process while teeing stdout and stderr to terminal streams.

    Parameters
    ----------
    command : list[str]
        Command argument list.
    cwd : Path | None
        Optional process working directory.
    env : dict[str, str]
        Process environment.

    Returns
    -------
    NextpnrCommandResult
        Captured process result.
    """
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    stdout_thread = threading.Thread(
        target=_read_stream,
        args=(process.stdout, sys.stdout, stdout_chunks),
    )
    stderr_thread = threading.Thread(
        target=_read_stream,
        args=(process.stderr, sys.stderr, stderr_chunks),
    )
    stdout_thread.start()
    stderr_thread.start()
    returncode = process.wait()
    stdout_thread.join()
    stderr_thread.join()

    return NextpnrCommandResult(
        command=tuple(command),
        returncode=returncode,
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
    )


def _read_stream(
    stream: TextIO | None,
    sink: TextIO,
    chunks: list[str],
) -> None:
    """Read one subprocess stream, mirror it, and capture all chunks.

    Parameters
    ----------
    stream : TextIO | None
        Process stream to read.
    sink : TextIO
        Terminal stream to mirror to.
    chunks : list[str]
        Mutable chunk collection used for the captured result.
    """
    if stream is None:
        return
    for chunk in stream:
        chunks.append(chunk)
        sink.write(chunk)
        sink.flush()
