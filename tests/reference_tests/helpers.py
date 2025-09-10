"""Helper functions for FABulous reference testing.

This module contains utility functions for downloading reference projects,
file comparison, and other testing helpers.
"""

import difflib
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from loguru import logger

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import setup_logger
from FABulous.FABulous_settings import init_context
from tests.conftest import normalize, run_cmd


class FileDifference(NamedTuple):
    """Represents a difference found between files."""

    file_path: str
    difference_type: str  # "missing", "extra", "modified"
    details: dict[str, Any]


def compare_files_with_diff(
    current_file: Path, reference_file: Path
) -> list[str] | None:
    """Compare two files and return unified diff if they differ.

    Returns
    -------
        None if files are identical, list of diff lines if different
    """
    try:
        with current_file.open("r", encoding="utf-8", errors="replace") as f:
            current_lines = f.readlines()
    except Exception:
        current_lines = []

    try:
        with reference_file.open("r", encoding="utf-8", errors="replace") as f:
            reference_lines = f.readlines()
    except Exception:
        reference_lines = []

    # Quick check for identical files
    if current_lines == reference_lines:
        return None

    # Generate unified diff
    diff = difflib.unified_diff(
        reference_lines,
        current_lines,
        fromfile=f"reference/{reference_file.name}",
        tofile=f"current/{current_file.name}",
        n=3,
    )

    diff_lines = list(diff)
    return diff_lines if diff_lines else None


def compare_directories(
    current_dir: Path,
    reference_dir: Path,
    file_patterns: list[str],
    exclude_patterns: list[str] | None = None,
) -> list[FileDifference]:
    """Compare files in two directories using simple pattern matching."""
    differences = []

    # Find all matching files
    current_files = set()
    reference_files = set()

    for pattern in file_patterns:
        current_files.update(current_dir.rglob(pattern))
        reference_files.update(reference_dir.rglob(pattern))

    # Filter out excluded files
    if exclude_patterns:
        excluded_current = set()
        excluded_reference = set()

        for pattern in exclude_patterns:
            excluded_current.update(current_dir.rglob(pattern))
            excluded_reference.update(reference_dir.rglob(pattern))

        current_files -= excluded_current
        reference_files -= excluded_reference

    # Create relative path mappings
    current_rel_map = {str(f.relative_to(current_dir)): f for f in current_files}

    reference_rel_map = {str(f.relative_to(reference_dir)): f for f in reference_files}

    # Compare all files
    all_rel_paths = set(current_rel_map.keys()) | set(reference_rel_map.keys())

    for rel_path in sorted(all_rel_paths):
        current_file = current_rel_map.get(rel_path)
        reference_file = reference_rel_map.get(rel_path)

        if not current_file:
            # File missing in current
            differences.append(
                FileDifference(
                    file_path=rel_path,
                    difference_type="missing",
                    details={
                        "message": "File exists in reference but missing in current"
                    },
                )
            )

        elif not reference_file:
            # Extra file in current
            differences.append(
                FileDifference(
                    file_path=rel_path,
                    difference_type="extra",
                    details={"message": "File exists in current but not in reference"},
                )
            )

        else:
            # Compare file contents
            diff_result = compare_files_with_diff(current_file, reference_file)
            if diff_result:
                differences.append(
                    FileDifference(
                        file_path=rel_path,
                        difference_type="modified",
                        details={
                            "diff": diff_result,
                            "total_diff_lines": len(diff_result),
                        },
                    )
                )

    return differences


def format_file_differences_report(
    differences: list[FileDifference],
    verbose: bool = False,
    current_dir: Path | None = None,
    reference_dir: Path | None = None,
) -> str:
    """Format file differences into a readable report with git-style diffs."""
    if not differences:
        return "No differences found."

    lines = [f"Found {len(differences)} file differences:"]
    lines.append("")

    # Group by difference type
    by_type = {}
    for diff in differences:
        diff_type = diff.difference_type
        if diff_type not in by_type:
            by_type[diff_type] = []
        by_type[diff_type].append(diff)

    # Report each type
    for diff_type, diff_list in by_type.items():
        lines.append(f"{diff_type.upper()} FILES ({len(diff_list)}):")

        # Determine how many files to show
        max_files = len(diff_list) if verbose else 5

        for diff in diff_list[:max_files]:
            lines.append(f"  {diff.file_path}")

            # Show full paths and status in verbose mode if directories are provided
            if verbose and current_dir and reference_dir:
                current_full_path = current_dir / diff.file_path
                reference_full_path = reference_dir / diff.file_path

                if diff.difference_type == "missing":
                    lines.append(f"    Reference (exists): {reference_full_path}")
                    lines.append(f"    Current (missing):   {current_full_path}")
                elif diff.difference_type == "extra":
                    lines.append(f"    Reference (missing): {reference_full_path}")
                    lines.append(f"    Current (exists):   {current_full_path}")
                else:  # modified
                    lines.append(f"    Reference: {reference_full_path}")
                    lines.append(f"    Current:   {current_full_path}")

            if diff.difference_type == "modified" and "diff" in diff.details:
                total_lines = diff.details.get("total_diff_lines", 0)
                lines.append(f"    ({total_lines} lines changed)")

                # Show the actual diff
                diff_lines = diff.details["diff"]

                # determine how many lines to show
                max_diff_lines = len(diff_lines) if verbose else 20

                for i, line in enumerate(diff_lines):
                    if not verbose and i >= max_diff_lines:
                        break
                    lines.append(f"    {line.rstrip()}")

                if not verbose and len(diff_lines) > max_diff_lines:
                    lines.append(
                        f"    ... ({len(diff_lines) - max_diff_lines} more lines)"
                    )
                lines.append("")

        if not verbose and len(diff_list) > max_files:
            lines.append(f"  ... and {len(diff_list) - max_files} more files")
        lines.append("")

    return "\n".join(lines)


def run_fabulous_commands_with_logging(
    project_path: Path,
    language: str,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    commands: list[str] | None = None,
    skip_on_fail: bool = False,
) -> tuple[FABulous_CLI, dict[str, Any]]:
    """Run standard FABulous commands using existing test patterns.

    Args:
        project_path: Path to the project directory to run commands in
        language: Language type for FABulous CLI ("verilog" or "vhdl")
        caplog: Pytest log capture fixture for collecting log output
        monkeypatch: Pytest monkeypatch fixture for environment management
        commands: Optional list of commands to run. If None, runs standard sequence
        skip_on_fail: Whether to skip remaining commands if one fails

    Returns
    -------
        Tuple of (FABulous_CLI instance, execution_info dict)

    The execution_info dict contains:
        - commands_run: List of successfully executed commands
        - commands_failed: List of commands that failed
        - commands_not_executed: List of commands skipped due to failures
        - errors: List of error messages collected from logs
        - warnings: List of warning messages collected from logs
    """
    setup_logger(0, False)

    monkeypatch.setenv("FAB_PROJ_DIR", str(project_path))
    monkeypatch.setenv("FAB_PROJ_LANG", language.upper())
    init_context(project_path)
    cli = FABulous_CLI(
        language,
        force=False,
        interactive=False,
        verbose=False,
        debug=True,
    )

    if not commands:
        # Standard FABulous command sequence
        commands = [
            "load_fabric",
            # run_FABulous_fabric commands:
            "gen_io_fabric",
            "gen_fabric",
            "gen_bitStream_spec",
            "gen_top_wrapper",
            "gen_model_npnr",
            "gen_geometry",
        ]

    execution_info = {
        "commands_run": [],
        "commands_failed": [],
        "commands_not_executed": [],
        "errors": [],
        "warnings": [],
    }

    for cmd in commands:
        fail = False
        try:
            logger.info(f"Running command: {cmd}")
            # Reuse the run_cmd function from CLI tests
            run_cmd(cli, cmd)

            # check for errors and warnings in logs
            log_lines = normalize(caplog.text)

            execution_info["warnings"] += [
                line for line in log_lines if "WARNING" in line
            ]
            if errors := [line for line in log_lines if "ERROR" in line]:
                execution_info["commands_failed"].append(cmd)
                execution_info["errors"] += errors
                fail = True

            caplog.clear()  # Clear for next command

            execution_info["commands_run"].append(cmd)

        except Exception as e:  # noqa: BLE001
            execution_info["commands_failed"].append(cmd)
            execution_info["errors"].append(f"Command '{cmd}' failed: {str(e)}")
            logger.error(f"Command '{cmd}' failed: {e}")
            fail = True

        if skip_on_fail and fail:
            # skip remaining commands on failure
            execution_info["commands_not_executed"] = commands[
                commands.index(cmd) + 1 :
            ]
            break

    return cli, execution_info
