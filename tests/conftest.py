"""Global pytest configuration and fixtures for all FABulous tests."""

import os
import shutil
from collections.abc import Generator
from pathlib import Path
from typing import Protocol

import pytest
from _pytest.logging import LogCaptureFixture
from cocotb_tools.runner import get_runner
from loguru import logger

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import create_project, setup_logger
from FABulous.FABulous_settings import init_context, reset_context

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
        """Build and run a cocotb simulation.

        Inject correct model pack file for each language (verilog: models_pack.v,
        vhdl: model_pack.vhdl) if not already supplied, replacing the previous
        reference to a non-existent tests/testdata directory.
        """
        if not sources:
            raise ValueError("No HDL sources provided")

        lang = {p.suffix for p in sources}
        if len(lang) > 1:
            raise ValueError("All source files must have the same HDL language suffix")
        hdl_toplevel_lang = lang.pop()
        if hdl_toplevel_lang not in {".v", ".sv", ".vhdl", ".vhd"}:
            raise ValueError(f"Unsupported HDL language: {hdl_toplevel_lang}")

        sim = {".v": "icarus", ".sv": "icarus", ".vhdl": "ghdl", ".vhd": "ghdl"}[
            hdl_toplevel_lang
        ]

        # No graceful skip: allow missing simulator to raise error for visibility

        # Ensure model pack file is present for primitives if not explicitly provided
        if hdl_toplevel_lang == ".v":
            model_pack_path = VERILOG_SOURCE_PATH / "Fabric" / "models_pack.v"
        else:  # .vhdl or .vhd
            model_pack_path = VHDL_SOURCE_PATH / "Fabric" / "model_pack.vhdl"

        # Only add if not already one of the provided sources (compare resolved paths)
        resolved_sources = {p.resolve() for p in sources}
        if (
            model_pack_path.exists()
            and model_pack_path.resolve() not in resolved_sources
        ):
            # Prepend so dependencies are available early
            sources.insert(0, model_pack_path)

        # Avoid errors when reading 'X'/'Z' by telling cocotb how to resolve them
        # Options: ZEROS, ONES, RANDOM, VALUE_ERROR. Pick ZEROS for deterministic tests.
        os.environ.setdefault("COCOTB_RESOLVE_X", "ZEROS")

        runner = get_runner(sim)

        # Copy test module to temp directory for cocotb
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)

        # Copy this test file to the test directory so cocotb can find it
        shutil.copy(test_module_path, test_dir / test_module_path.name)

        # Build directory
        build_dir = tmp_path / "cocotb_build"

        # Configure sources based on HDL language
        # GHDL flags for VHDL-2008 and IEEE extensions
        ghdl_flags: list[str] = []

        if hdl_toplevel_lang == ".v":
            runner.build(
                sources=sources,
                hdl_toplevel=hdl_top_level,
                always=True,
                build_dir=build_dir,
                defines={"NOTIMESCALE": 1},
                timescale=("1ns", "1ps"),  # Set simulation time unit/precision
            )
        else:  # .vhdl or .vhd
            # GHDL converts identifiers to lowercase for elaboration and execution
            hdl_top_level = hdl_top_level.lower()
            ghdl_flags = ["--std=08", "--ieee=synopsys"]
            runner.build(
                sources=sources,
                hdl_toplevel=hdl_top_level,
                always=True,
                build_dir=build_dir,
                defines={"NOTIMESCALE": 1},
                build_args=ghdl_flags,  # VHDL-2008 & IEEE extensions
                timescale=("1ns", "1ps"),
            )

            # GHDL mcode backend requires running from the build directory.
            # Copy the test module to build_dir and run tests from there.
            shutil.copy(test_module_path, build_dir / test_module_path.name)
            test_dir = build_dir

        # GHDL mcode backend requires --std and --ieee flags during run as well,
        # otherwise it cannot find entities compiled with those options.
        test_args = ghdl_flags if sim == "ghdl" else []

        runner.test(
            hdl_toplevel=hdl_top_level,
            test_module=test_module_path.stem,
            build_dir=build_dir,
            test_dir=test_dir,
            test_args=test_args,
        )

    return _create_runner


def pytest_addoption(parser: pytest.Parser) -> None:  # type: ignore[name-defined]
    """Add command line option to include slow tests explicitly.

    Usage: pytest --runslow
    Without this flag, tests marked with @pytest.mark.slow are skipped via addopts filter.
    """
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run tests marked as slow (overrides default '-m not slow')",
    )


def pytest_configure(config: pytest.Config) -> None:  # type: ignore[name-defined]
    # If --runslow is given, remove the '-m not slow' filter so slow tests run.
    if (
        config.getoption("runslow")
        and getattr(config.option, "markexpr", None) == "not slow"
    ):
        config.option.markexpr = ""


def normalize(block: str) -> list[str]:
    """Normalize a block of text to perform comparison.

    Strip newlines from the very beginning and very end, then split into
    separate lines and strip trailing whitespace from each line.
    """
    assert isinstance(block, str)
    block = block.strip("\n")
    return [line.rstrip() for line in block.splitlines()]


def run_cmd(app: FABulous_CLI, cmd: str) -> None:
    """Run a command in the given FABulous_CLI instance."""
    app.onecmd_plus_hooks(cmd)


def normalize_and_check_for_errors(caplog_text: str) -> list[str]:
    """Normalize a block of text and check for errors."""
    log = normalize(caplog_text)
    assert not any("ERROR" in line for line in log), "Error found in log messages"
    return log


@pytest.fixture(autouse=True)
def fabulous_test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Set up global test environment for FABulous tests."""
    fabulous_root = str(Path(__file__).resolve().parent.parent / "FABulous")

    for i in os.environ:
        monkeypatch.delenv(i[0], raising=False)

    # Set test environment using monkeypatch for automatic cleanup
    monkeypatch.setenv("FAB_ROOT", fabulous_root)
    monkeypatch.setenv("FABULOUS_TESTING", "TRUE")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda _: tmp_path)
    (tmp_path / ".ciel" / "ihp-sg13g2").mkdir(parents=True, exist_ok=True)
    setup_logger(0, False)

    return


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FABulous_CLI:
    """Create a FABulous CLI instance for testing with a temporary project."""
    project_dir = tmp_path / "test_project"
    monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
    create_project(project_dir)
    init_context(project_dir)
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
    """Ensure logger is properly cleaned up.

    Run after each test to prevent 'logging to closed file' errors when tests exit
    quickly.
    """
    yield
    # Remove all logger handlers to prevent logging to closed files
    # This handles cleanup for both regular logging and caplog fixtures
    logger.remove()


@pytest.fixture
def caplog(caplog: LogCaptureFixture) -> LogCaptureFixture:
    """Caplog fixture that integrates with loguru."""
    logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,  # Set to 'True' if your test is spawning child processes.
    )
    return caplog
    # No need to remove specific handler - cleanup_logger removes all handlers


@pytest.fixture
def project(tmp_path: Path) -> Generator[Path, None, None]:
    project_dir = tmp_path / "test_project"
    create_project(project_dir)
    yield project_dir

    # Cleanup
    reset_context()  # Reset context after each test to avoid state leakage
