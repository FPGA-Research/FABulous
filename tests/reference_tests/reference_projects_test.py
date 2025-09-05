"""Test suite for running FABulous on reference projects with difference checking.

This module tests FABulous against reference projects defined in a config file,
supporting both "run" mode (error checking) and "diff" mode (regression testing).
"""

import shutil
from pathlib import Path
from typing import Literal, NamedTuple

import pytest
import yaml
from loguru import logger

from tests.reference_tests.helpers import (
    compare_directories,
    format_file_differences_report,
    run_fabulous_commands_with_logging,
)


class ReferenceProject(NamedTuple):
    """Configuration for a reference project test."""

    name: str
    path: Path
    language: Literal["verilog", "vhdl"]
    test_mode: Literal["run", "diff"]
    description: str = ""
    expected_outputs: list[str] | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    commands: list[str] | None = None
    skip_reason: str | None = None


def load_reference_projects_config(config_path: Path) -> list[ReferenceProject]:
    """Load reference projects configuration from YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r") as f:
        config_data = yaml.safe_load(f)

    projects = []
    for project_data in config_data.get("reference_projects", []):
        if Path(project_data["path"]).is_absolute():
            path = Path(project_data["path"])
        else:
            path = config_path.parent / project_data["path"]
        try:
            project = ReferenceProject(
                name=project_data["name"],
                path=path.resolve(),
                language=project_data["language"],
                test_mode=project_data["test_mode"],
                description=project_data.get("description", ""),
                expected_outputs=project_data.get("expected_outputs"),
                include_patterns=project_data.get("include_patterns"),
                exclude_patterns=project_data.get("exclude_patterns"),
                commands=project_data.get("commands"),
                skip_reason=project_data.get("skip_reason"),
            )
            projects.append(project)
        except KeyError as e:
            logger.warning(f"Invalid project config, missing key {e}: {project_data}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to load project config: {e}")

    return projects


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate test parameters dynamically based on config."""
    if "ref_project" in metafunc.fixturenames:
        # Need to import _session_config here to avoid uninialized/circular import
        from tests.reference_tests.conftest import _session_config

        if _session_config.projects_conf is None:
            raise RuntimeError(
                "Session config not initialized. This should be set in "
                "pytest_configure."
            )

        config_path = _session_config.projects_conf

        assert config_path.exists(), f"Config file not found: {config_path}"

        projects = load_reference_projects_config(config_path)

        # Filter out skipped projects
        active_projects = [p for p in projects if p.skip_reason is None]

        assert active_projects, "No active reference projects found in config."

        metafunc.parametrize(
            "ref_project", active_projects, ids=[p.name for p in active_projects]
        )
    else:
        raise RuntimeError("No 'project' fixture found in test function.")


def test_reference_project_execution(
    ref_project: ReferenceProject,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test execution of reference projects with run or diff mode."""
    assert ref_project.path.exists(), (
        f"Reference project path does not exist: {ref_project.path}"
    )

    # Copy project to temporary location
    project_name = ref_project.path.name
    test_project_path = tmp_path / project_name
    if ref_project.path.is_dir():
        shutil.copytree(ref_project.path, test_project_path, symlinks=True)
    else:
        raise ValueError(
            f"Reference project path is not a directory: {ref_project.path}"
        )

    # Run FABulous commands
    _, execution_info = run_fabulous_commands_with_logging(
        test_project_path,
        ref_project.language,
        caplog,
        monkeypatch,
        commands=ref_project.commands,
    )

    # Always check that basic commands succeeded
    assert not execution_info["commands_failed"], (
        f"Commands failed for {ref_project.name}: {execution_info['commands_failed']}"
        f"\nErrors: {execution_info['errors']}"
    )

    # Verify expected outputs exist if specified
    if ref_project.expected_outputs:
        for expected_file in ref_project.expected_outputs:
            file_path = test_project_path / expected_file
            assert file_path.exists(), f"Expected output file missing: {expected_file}"
            assert file_path.stat().st_size > 0, (
                f"Expected output file is empty: {expected_file}"
            )

    # For "run" mode, just check for errors and expected outputs
    if ref_project.test_mode == "run":
        logger.info(f"✓ Project {ref_project.name} executed successfully in 'run' mode")

    # For "diff" mode, perform simple comparison
    if ref_project.test_mode == "diff":
        # Compare files
        # Determine file patterns based on project configuration or language
        if ref_project.include_patterns:
            logger.info("Using defined include patterns:")
            include_patterns = ref_project.include_patterns
        else:
            logger.info("Using default include patterns for:")
            include_patterns = ["*.v", "*.sv"]
            if ref_project.language != "verilog":
                include_patterns = ["*.vhd", "*.vhdl"]
            include_patterns += ["*.csv", "*.list", "*txt", "*.bin"]
        logger.info(f"  Patterns: {include_patterns}")

        cmp_diff = compare_directories(
            ref_project.path,
            test_project_path,
            include_patterns,
            exclude_patterns=ref_project.exclude_patterns,
        )

        if cmp_diff:
            # Need to import _session_config here to avoid uninialized/circular import
            from tests.reference_tests.conftest import _session_config

            diff_report = format_file_differences_report(
                cmp_diff,
                verbose=_session_config.verbose,
                current_dir=test_project_path,
                reference_dir=ref_project.path,
            )
            pytest.fail(
                f"Compare project differences in {ref_project.name}:\n{diff_report}"
            )

        logger.info(
            f"✓ Project {ref_project.name} passed regression testing in 'diff' mode"
        )

    return
