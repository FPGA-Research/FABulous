"""Global pytest configuration and fixtures for all FABulous tests."""

import os
import shutil
from pathlib import Path
from typing import Protocol

import pytest
from _pytest.logging import LogCaptureFixture
from cocotb.runner import get_runner
from loguru import logger

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import create_project, setup_logger
from FABulous.FABulous_settings import reset_context

VERILOG_SOURCE_PATH = (
    Path(__file__).parent.parent
    / "FABulous"
    / "fabric_files"
    / "FABulous_project_template_verilog"
)

VHDL_SOURCE_PATH = (
    Path(__file__).parent.parent
    / "FABulous"
    / "fabric_files"
    / "FABulous_project_template_vhdl"
)


class CocotbRunner(Protocol):
    """Callable Protocol for our cocotb runner fixture.

    The runner is called with keyword-only arguments. Protocol structural typing
    allows any compatible callable to satisfy this contract.
    """

    def __call__(
        self,
        *,
        sources: list[Path],
        hdl_top_level: str,
        test_module_path: Path,
    ) -> None:  # pragma: no cover - typing only
        ...


@pytest.fixture
def cocotb_runner(tmp_path: Path) -> CocotbRunner:
    """Factory fixture to create cocotb runners for RTL simulation."""

    def _create_runner(
        sources: list[Path], hdl_top_level: str, test_module_path: Path
    ) -> None:
        lang = set([i.suffix for i in sources])

        if len(lang) > 1:
            raise ValueError("All source files must have the same HDL language suffix")

        hdl_toplevel_lang = lang.pop()  # Get the single language suffix
        if hdl_toplevel_lang not in {".v", ".vhdl"}:
            raise ValueError(f"Unsupported HDL language: {hdl_toplevel_lang}")

        sim = {".v": "icarus", ".vhdl": "ghdl"}[hdl_toplevel_lang]
        runner = get_runner(sim)

        timescales = ("1ps", "1ps")

        # Only add testdata models if models_pack.v is not already included
        models_pack_included = any("models_pack.v" in str(source) for source in sources)
        if not models_pack_included:
            sources.insert(
                0, Path(__file__).parent / "testdata" / f"models{hdl_toplevel_lang}"
            )
        # Copy test module and models to temp directory for cocotb
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)

        # Copy this test file to the test directory so cocotb can find it
        shutil.copy(test_module_path, test_dir / test_module_path.name)

        # Build directory
        build_dir = tmp_path / "cocotb_build"

        # Configure sources based on HDL language
        if hdl_toplevel_lang == ".v":
            runner.build(
                verilog_sources=sources,
                hdl_toplevel=hdl_top_level,
                always=True,
                build_dir=build_dir,
                defines={"NOTIMESCALE": 1},
            )
        elif hdl_toplevel_lang == ".vhdl":
            # GHDL converts identifiers to lowercase for elaboration and execution
            hdl_top_level = hdl_top_level.lower()
            runner.build(
                vhdl_sources=sources,
                hdl_toplevel=hdl_top_level,
                always=True,
                build_dir=build_dir,
                defines={"NOTIMESCALE": 1},
            )

            # Copy all files from build_dir to test_dir
            for file in build_dir.iterdir():
                if file.is_file():
                    shutil.copy(file, test_dir / file.name)

        runner.test(
            hdl_toplevel=hdl_top_level,
            test_module=test_module_path.stem,
            build_dir=build_dir,
            test_dir=test_dir,
        )

    return _create_runner


def normalize(block: str) -> list[str]:
    """Normalize a block of text to perform comparison.

    Strip newlines from the very beginning and very end, then split into separate lines and strip trailing whitespace
    from each line.
    """
    assert isinstance(block, str)
    block = block.strip("\n")
    return [line.rstrip() for line in block.splitlines()]


def run_cmd(app: FABulous_CLI, cmd: str) -> None:
    """Clear stdout, stdin and stderr buffers, run the command, and return stdout and stderr"""
    app.onecmd_plus_hooks(cmd)


def normalize_and_check_for_errors(caplog_text: str) -> list[str]:
    """Normalize a block of text and check for errors."""
    log = normalize(caplog_text)
    assert not any("ERROR" in line for line in log), "Error found in log messages"
    return log


@pytest.fixture(autouse=True)
def fabulous_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setup global test environment for FABulous tests."""
    fabulous_root = str(Path(__file__).resolve().parent.parent / "FABulous")

    for i in os.environ:
        monkeypatch.delenv(i[0], raising=False)

    # Set test environment using monkeypatch for automatic cleanup
    monkeypatch.setenv("FAB_ROOT", fabulous_root)
    monkeypatch.setenv("FABULOUS_TESTING", "TRUE")
    setup_logger(0, False)

    return


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FABulous_CLI:
    """Create a FABulous CLI instance for testing with a temporary project."""
    project_dir = tmp_path / "test_project"
    monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
    create_project(project_dir)
    cli = FABulous_CLI(
        "verilog",
        force=False,
        interactive=False,
        verbose=False,
        debug=True,
    )
    cli.debug = True
    run_cmd(cli, "load_fabric")
    return cli


@pytest.fixture(autouse=True)
def cleanup_logger() -> Generator[None]:
    """Ensure logger is properly cleaned up after each test to prevent
    'logging to closed file' errors when tests exit quickly"""
    yield
    # Remove all logger handlers to prevent logging to closed files
    # This handles cleanup for both regular logging and caplog fixtures
    logger.remove()


@pytest.fixture
def caplog(caplog: LogCaptureFixture) -> LogCaptureFixture:
    """Custom caplog fixture that integrates with loguru."""
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,  # Set to 'True' if your test is spawning child processes.
    )
    return caplog
    # No need to remove specific handler - cleanup_logger removes all handlers


@pytest.fixture
def project(tmp_path: Path) -> Generator[Path]:
    project_dir = tmp_path / "test_project"
    create_project(project_dir)
    yield project_dir

    # Cleanup
    reset_context()  # Reset context after each test to avoid state leakage
