"""Helper functions for FABulous reference testing.

This module contains utility functions for downloading reference projects,
file comparison, and other testing helpers.
"""

import difflib
import shutil
import subprocess
from pathlib import Path
from typing import Any, NamedTuple

from loguru import logger


def download_reference_projects(repo_url: str, target_dir: Path, branch: str = "main") -> bool:
    """Download reference projects from GitHub repository.

    Args:
        repo_url: GitHub repository URL (e.g., "https://github.com/user/repo.git")
        target_dir: Local directory to clone/download to
        branch: Git branch to checkout (default: "main")

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Downloading reference projects from {repo_url}")

        if target_dir.exists():
            # If directory exists, try to update it
            if (target_dir / ".git").exists():
                logger.info("Updating existing repository...")
                result = subprocess.run(
                    ["git", "pull", "origin", branch],
                    cwd=target_dir,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    logger.warning(f"Git pull failed: {result.stderr}")
                    logger.info("Attempting fresh clone...")
                    shutil.rmtree(target_dir)
                else:
                    logger.info("✓ Repository updated successfully")
                    return True
            else:
                logger.error(f"Target directory {target_dir} exists but is not a git repository.",
                             " Please remove or specify a different directory.")
                return False

        if not target_dir.exists():
            # Fresh clone
            logger.info("Cloning repository...")
            target_dir.parent.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                ["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(target_dir)],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                logger.error(f"Failed to clone repository: {result.stderr}")
                return False

            logger.info("✓ Repository cloned successfully")
            return True

    except subprocess.TimeoutExpired:
        logger.error("Git operation timed out")
        return False
    except FileNotFoundError:
        logger.error("Git command not found. Please install git.")
        return False
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to download reference projects: {e}")
        return False

    return True


class FileDifference(NamedTuple):
    """Represents a difference found between files."""

    file_path: str
    difference_type: str  # "missing", "extra", "modified"
    details: dict[str, Any]


def compare_files_with_diff(
    current_file: Path,
    reference_file: Path
) -> list[str] | None:
    """Compare two files and return unified diff if they differ.

    Returns:
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
        n=3
    )

    diff_lines = list(diff)
    return diff_lines if diff_lines else None


def compare_directories(
    current_dir: Path,
    reference_dir: Path,
    file_patterns: list[str],
    exclude_patterns: list[str] | None = None
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
    current_rel_map = {
        str(f.relative_to(current_dir)): f
        for f in current_files
    }

    reference_rel_map = {
        str(f.relative_to(reference_dir)): f
        for f in reference_files
    }

    # Compare all files
    all_rel_paths = set(current_rel_map.keys()) | set(reference_rel_map.keys())

    for rel_path in sorted(all_rel_paths):
        current_file = current_rel_map.get(rel_path)
        reference_file = reference_rel_map.get(rel_path)

        if not current_file:
            # File missing in current
            differences.append(FileDifference(
                file_path=rel_path,
                difference_type="missing",
                details={"message": "File exists in reference but missing in current"}
            ))

        elif not reference_file:
            # Extra file in current
            differences.append(FileDifference(
                file_path=rel_path,
                difference_type="extra",
                details={"message": "File exists in current but not in reference"}
            ))

        else:
            # Compare file contents
            diff_result = compare_files_with_diff(current_file, reference_file)
            if diff_result:
                differences.append(FileDifference(
                    file_path=rel_path,
                    difference_type="modified",
                    details={
                        "diff": diff_result,
                        "total_diff_lines": len(diff_result)
                    }
                ))

    return differences


def format_file_differences_report(differences: list[FileDifference], verbose: bool = False, current_dir: Path | None = None, reference_dir: Path | None = None) -> str:
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
                    lines.append(f"    ... ({len(diff_lines) - max_diff_lines} more lines)")
                lines.append("")

        if not verbose and len(diff_list) > max_files:
            lines.append(f"  ... and {len(diff_list) - max_files} more files")
        lines.append("")

    return "\n".join(lines)

