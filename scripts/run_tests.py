#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from loguru import logger

# --- Configuration ---
# File used as the source for test durations and updated after a successful run.
DURATIONS_FALLBACK_FILE = Path(".test_durations_fallback")
# Temporary working directory for the parallel run.
TEMP_RUN_DIR = Path(".pytest_local_run")
# Name of the durations file used by pytest-split.
DURATIONS_FILE = Path(".test_durations")

# Repository root (script lives in <root>/scripts)
REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"


logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <white>{message}</white>",
)


def run_pytest_group(
    group_index: int, total_groups: int, pytest_args: list[str]
) -> tuple[int, int, str, str]:
    """
    Runs a single pytest group in a subprocess.

    Each group runs in its own isolated directory to prevent race conditions
    on the .test_durations file.

    Returns
    -------
        A tuple containing (group_index, exit_code, stdout, stderr).
    """
    group_dir = TEMP_RUN_DIR / f"group_{group_index}"
    group_dir.mkdir(parents=True, exist_ok=True)

    # Copy the initial durations file to the group's directory
    if (TEMP_RUN_DIR / DURATIONS_FILE).exists():
        shutil.copy(TEMP_RUN_DIR / DURATIONS_FILE, group_dir / DURATIONS_FILE)

    # Use absolute tests path so collection works even when cwd is isolated temp dir.
    command = [
        "uv",
        "run",
        "-m",
        "pytest",
        str(TESTS_DIR),
        "--splits",
        str(total_groups),
        "--group",
        str(group_index),
        "--store-durations",
        "--clean-durations",
        *pytest_args,
    ]

    logger.info(f"🚀 Starting Group {group_index}/{total_groups}...")
    logger.debug(f"Command: {' '.join(command)}")

    start_time = time.monotonic()
    # Run the subprocess from the group's temporary directory
    # Ensure package imports (e.g., FABulous) resolve when running outside repo root.
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    # Prepend repo root if not already present.
    if str(REPO_ROOT) not in existing_pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = (
            f"{REPO_ROOT}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else str(REPO_ROOT)
        )

    process = subprocess.run(
        command, capture_output=True, text=True, cwd=group_dir, env=env
    )
    duration = time.monotonic() - start_time

    # Handle the "no tests collected" case (exit code 5) as a success
    if process.returncode == 5:
        logger.success(
            f"✅ Group {group_index} finished in {duration:.2f}s (No tests collected)."
        )
        return group_index, 0, process.stdout, process.stderr
    if process.returncode == 0:
        logger.success(
            f"✅ Group {group_index} finished successfully in {duration:.2f}s."
        )
    else:
        logger.error(
            f"❌ Group {group_index} failed after {duration:.2f}s (exit {process.returncode})."
        )

    return group_index, process.returncode, process.stdout, process.stderr


def merge_and_update_durations(num_groups: int) -> None:
    """Merge per-group duration files and update fallback if test count increased."""
    logger.info("Merging test durations…")

    merged: dict[str, float] = {}
    for i in range(1, num_groups + 1):
        partial = TEMP_RUN_DIR / f"group_{i}" / DURATIONS_FILE
        if not partial.is_file():
            continue
        try:
            with partial.open() as f:
                data = json.load(f)
            if isinstance(data, dict):  # defensive
                merged.update(data)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not parse {partial}: {e}")

    if not merged:
        logger.warning("No new durations found; fallback not updated.")
        return

    # Normalise ordering (stable output for diffs)
    merged = dict(sorted(merged.items()))

    existing_count = 0
    if DURATIONS_FALLBACK_FILE.is_file():
        try:
            with DURATIONS_FALLBACK_FILE.open() as f:
                current = json.load(f)
            if isinstance(current, dict):
                existing_count = len(current)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "Existing fallback unreadable '{}' : {} (treating as empty).",
                DURATIONS_FALLBACK_FILE,
                e,
            )
            existing_count = 0

    new_count = len(merged)
    if new_count <= existing_count:
        logger.info(f"Skip update: new count {new_count} <= existing {existing_count}.")
        return
    try:
        with DURATIONS_FALLBACK_FILE.open("w") as f:
            json.dump(merged, f, indent=2)
        logger.success(
            f"Updated '{DURATIONS_FALLBACK_FILE}' with {new_count} durations (was {existing_count})."
        )
    except OSError as e:
        logger.error(f"Failed writing fallback '{DURATIONS_FALLBACK_FILE}' : {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run pytest in parallel locally, mimicking GitHub Actions parallel matrix.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--parallel",
        default="4",
        help="Number of parallel processes to run. \n"
        "Use an integer (e.g., 8) or 'auto' to use all available CPU cores. \n"
        "Default: 4",
    )
    # We intentionally do NOT predeclare pytest arguments. Anything unknown
    # to this wrapper will be forwarded to pytest (so users can just write
    # `scripts/run_tests.py -p 8 -k foo --runslow -vv` without an explicit `--`).
    args, forwarded = parser.parse_known_args()

    # --- 1. Determine number of processes ---
    if args.parallel.lower() == "auto":
        num_processes = os.cpu_count() or 4
    else:
        try:
            num_processes = int(args.parallel)
            if num_processes < 1:
                raise ValueError
        except ValueError:
            logger.error(
                f"Error: --parallel must be a positive integer or 'auto'. Got '{args.parallel}'",
            )
            sys.exit(1)

    logger.info(f"Starting parallel pytest run with {num_processes} processes.")

    # --- 2. Prepare environment ---
    if TEMP_RUN_DIR.exists():
        shutil.rmtree(TEMP_RUN_DIR)
    TEMP_RUN_DIR.mkdir(parents=True)

    if DURATIONS_FALLBACK_FILE.exists():
        logger.info(f"Using '{DURATIONS_FALLBACK_FILE}' for test splitting.")
        shutil.copy(DURATIONS_FALLBACK_FILE, TEMP_RUN_DIR / DURATIONS_FILE)
    else:
        logger.warning(
            f"'{DURATIONS_FALLBACK_FILE}' not found. Tests will be split evenly by default."
        )

    # --- 3. Run tests in parallel ---
    failed_groups = []
    pytest_args = forwarded  # alias for clarity

    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        futures = [
            executor.submit(run_pytest_group, i, num_processes, pytest_args)
            for i in range(1, num_processes + 1)
        ]

        for future in as_completed(futures):
            try:
                group_index, exit_code, stdout, stderr = future.result()
                if exit_code != 0:
                    failed_groups.append(
                        {"index": group_index, "stdout": stdout, "stderr": stderr}
                    )
            except Exception as e:
                logger.error(f"A worker process crashed: {e}")
                failed_groups.append(
                    {"index": "Unknown", "stdout": "", "stderr": str(e)}
                )

    # --- 4. Report results ---
    logger.info("=" * 50)
    logger.info("Run Summary")
    logger.info("=" * 50)

    if not failed_groups:
        logger.success("✅ All test groups passed!")
        # --- 5. Merge durations only on success ---
        merge_and_update_durations(num_processes)
        final_exit_code = 0
    else:
        logger.error(f"❌ {len(failed_groups)} test group(s) failed.")
        for failure in sorted(failed_groups, key=lambda x: x["index"]):
            logger.error(f"Failure in Group {failure['index']}")
            if failure["stdout"]:
                logger.warning("--- STDOUT ---")
                logger.info(f"\n{failure['stdout']}")
            if failure["stderr"]:
                logger.error("--- STDERR ---")
                logger.error(f"\n{failure['stderr']}")
            logger.info("-" * 20)
        final_exit_code = 1

    # --- 6. Cleanup ---
    if TEMP_RUN_DIR.exists():
        shutil.rmtree(TEMP_RUN_DIR)
    logger.info(f"Cleaned up temporary directory: {TEMP_RUN_DIR}")

    sys.exit(final_exit_code)


if __name__ == "__main__":
    main()
