import os
import sys
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
    app.onecmd_plus_hooks(cmd)


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
