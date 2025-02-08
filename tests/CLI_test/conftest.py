import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture
from cmd2.utils import StdSim
from loguru import logger

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import create_project, setup_logger


def normalize(block: str):
    """Normalize a block of text to perform comparison.

    Strip newlines from the very beginning and very end  Then split into separate lines and strip trailing whitespace
    from each line.
    """
    assert isinstance(block, str)
    block = block.strip("\n")
    return [line.rstrip() for line in block.splitlines()]


def run_cmd(app, cmd):
    """Clear out and err StdSim buffers, run the command, and return out and err"""
    saved_sysout = sys.stdout
    sys.stdout = app.stdout

    # This will be used to capture app.stdout and sys.stdout
    copy_cmd_stdout = StdSim(app.stdout)

    # This will be used to capture sys.stderr
    copy_stderr = StdSim(sys.stderr)

    try:
        app.stdout = copy_cmd_stdout
        with redirect_stdout(copy_cmd_stdout):
            with redirect_stderr(copy_stderr):
                app.onecmd_plus_hooks(cmd)
    finally:
        app.stdout = copy_cmd_stdout.inner_stream
        sys.stdout = saved_sysout
    out = copy_cmd_stdout.getvalue()
    err = copy_stderr.getvalue()
    return normalize(out), normalize(err)


TILE = "LUT4AB"
SUPER_TILE = "DSP"

os.environ["FAB_ROOT"] = str(Path(__file__).resolve().parent.parent.parent / "FABulous")


@pytest.fixture
def cli(tmp_path):
    projectDir = tmp_path / "test_project"
    fabulousRoot = str(Path(__file__).resolve().parent.parent.parent / "FABulous")
    os.environ["FAB_ROOT"] = fabulousRoot
    create_project(projectDir)
    setup_logger(0)
    cli = FABulous_CLI(writerType="verilog", projectDir=projectDir, enteringDir=tmp_path)
    run_cmd(cli, "load_fabric")
    return cli


@pytest.fixture
def caplog(caplog: LogCaptureFixture):
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,  # Set to 'True' if your test is spawning child processes.
    )
    yield caplog
    logger.remove(handler_id)
