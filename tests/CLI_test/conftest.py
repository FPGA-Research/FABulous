import os
from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture
from loguru import logger

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import create_project, setup_logger


def normalize(block: str):
    """Normalize a block of text to perform comparison.

    Strip newlines from the very beginning and very end, then split into separate lines and strip trailing whitespace
    from each line.
    """
    assert isinstance(block, str)
    block = block.strip("\n")
    return [line.rstrip() for line in block.splitlines()]


def run_cmd(app, cmd):
    """Clear stdout, stdin and stderr buffers, run the command, and return stdout and stderr"""
    app.onecmd_plus_hooks(cmd)


def normalize_and_check_for_errors(caplog_text: str):
    """Normalize a block of text and check for errors."""
    log = normalize(caplog_text)
    assert not any("ERROR" in line for line in log), "Error found in log messages"
    return log


TILE = "LUT4AB"

os.environ["FAB_ROOT"] = str(Path(__file__).resolve().parent.parent.parent / "FABulous")


@pytest.fixture
def cli(tmp_path):
    projectDir = tmp_path / "test_project"
    fabulousRoot = str(Path(__file__).resolve().parent.parent.parent / "FABulous")
    os.environ["FAB_ROOT"] = fabulousRoot
    os.environ["FAB_PROJ_DIR"] = str(projectDir)
    create_project(projectDir)
    setup_logger(0, False)
    cli = FABulous_CLI(
        writerType="verilog", projectDir=projectDir, enteringDir=tmp_path
    )
    cli.debug = True
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
