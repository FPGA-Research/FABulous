#!/usr/bin/env python3
"""Script to run NLP tile optimization from a summary JSON file.

This script takes a tile optimization summary JSON (as produced by Step 1 of
 FABulousFabricMacroFullFlow) and a project directory, then runs the NLP
optimization step to compute optimal tile dimensions.

Usage:
    python scripts/run_tile_optimization.py --summary summary.json --project-dir /path/to/project

Output:
    Prints optimization results including optimal widths, heights, and total fabric area.
    Also saves results to optimization_results.json in the current directory.
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from loguru import logger

# Add FABulous to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from librelane.state.state import State

from FABulous.fabric_definition.Fabric import Fabric
import FABulous.fabric_generator.parser.parse_csv as fileParser
from FABulous.fabric_generator.gds_generator.steps.global_tile_opitmisation import (
    GlobalTileSizeOptimization,
)


def load_summary_json(summary_path: Path) -> dict:
    """Load tile optimization summary JSON.
    
    Accepts the format produced by the flow:
    {opt_mode: {tile_name: {metrics}}}
    
    Parameters
    ----------
    summary_path : Path
        Path to the summary JSON file
        
    Returns
    -------
    dict
        Parsed summary dictionary
    """
    if not summary_path.exists():
        raise FileNotFoundError(f"Summary file not found: {summary_path}")
    
    with open(summary_path) as f:
        return json.load(f)


def load_fabric(project_dir: Path) -> Fabric:
    """Load Fabric configuration from project directory.

    Parameters
    ----------
    project_dir : Path
        Path to the FABulous project directory

    Returns
    -------
    Fabric
        Loaded fabric object

    Raises
    ------
    FileNotFoundError
        If fabric file doesn't exist
    """
    # Resolve to absolute path
    project_dir = project_dir.resolve()

    fabric_file = project_dir / "Fabric" / "fabric.csv"
    if not fabric_file.exists():
        # Try project root as fallback
        fabric_file = project_dir / "fabric.csv"

    if not fabric_file.exists():
        raise FileNotFoundError(
            f"Fabric file not found. Tried:\n"
            f"  - {project_dir / 'Fabric' / 'fabric.csv'}\n"
            f"  - {project_dir / 'fabric.csv'}"
        )

    return fileParser.parseFabricCSV(fabric_file)


def create_initial_state(summary: dict) -> State:
    """Create initial state with tile metrics from summary.

    Parameters
    ----------
    summary : dict
        Tile optimization summary dictionary

    Returns
    -------
    State
        Initial state with metrics populated
    """
    state = State(metrics=summary.copy())

    return state


def run_optimization(
    summary_path: Path, project_dir: Path, time_limit: int = 300
) -> dict:
    """Run NLP tile optimization.

    Parameters
    ----------
    summary_path : Path
        Path to tile optimization summary JSON
    project_dir : Path
        Path to FABulous project directory
    time_limit : int, optional
        Time limit in seconds for optimization solver (default: 300)

    Returns
    -------
    dict
        Optimization results with optimal dimensions

    Raises
    ------
    RuntimeError
        If optimization fails
    """
    logger.info(f"\n{'=' * 70}")
    logger.info("FABulous NLP Tile Optimization")
    logger.info(f"{'=' * 70}\n")

    # Load inputs
    logger.info(f"Loading summary from: {summary_path}")
    summary = load_summary_json(summary_path)

    logger.info(f"\nLoading fabric from: {project_dir}")

    # Convert to absolute path before changing directory
    project_dir_abs = project_dir.resolve()

    # Change to project directory and initialize context for fabric loading
    import os

    original_dir = Path.cwd()
    try:
        os.chdir(project_dir_abs)
        from FABulous.FABulous_settings import init_context

        init_context()

        fabric = load_fabric(project_dir_abs)
        logger.info(f"  Fabric size: {fabric.numberOfRows}x{fabric.numberOfColumns}")
    finally:
        os.chdir(original_dir)

    # Create initial state
    initial_state = create_initial_state(summary)

    # Run optimization step
    logger.info(f"\n{'=' * 70}")
    logger.info("Running NLP Optimization")
    logger.info(f"{'=' * 70}\n")

    # Create a minimal step instance bypassing full Config validation
    # The optimization doesn't actually need PDK, only fabric structure
    from types import SimpleNamespace

    # Create a simple config object with just what we need
    simple_config = {
        "FABULOUS_PROJ_DIR": project_dir_abs,
        "FABULOUS_FABRIC": fabric,
        "FABULOUS_ILP_SOLVER_TIME_LIMIT": time_limit,
    }

    # Create step with minimal config
    optimization_step = GlobalTileSizeOptimization.__new__(GlobalTileSizeOptimization)
    optimization_step.config = simple_config
    optimization_step.state_in = initial_state
    optimization_step.id = "NLPOptimization"

    try:
        views_updates, metrics_updates = optimization_step.run(initial_state)
    except Exception as e:
        logger.info(f"\n❌ Optimization failed: {e}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"NLP optimization failed: {e}") from e

    # Extract results
    results = {
        "optimal_widths": metrics_updates.get("nlp_optimal_widths", {}),
        "optimal_heights": metrics_updates.get("nlp_optimal_heights", {}),
        "total_area": metrics_updates.get("nlp_total_area", 0),
        "row_heights": metrics_updates.get("nlp_row_heights", []),
        "col_widths": metrics_updates.get("nlp_col_widths", []),
        "solver_status": metrics_updates.get("nlp_solver_status", "Unknown"),
        "type_to_positions": metrics_updates.get("type_to_positions", {}),
    }

    return results


def print_info_results(results: dict) -> None:
    """Print optimization results in a formatted way.

    Parameters
    ----------
    results : dict
        Optimization results dictionary
    """
    logger.info(f"\n{'=' * 70}")
    logger.info("Optimization Results")
    logger.info(f"{'=' * 70}\n")

    logger.info(f"Solver Status: {results['solver_status']}")
    logger.info(f"Total Fabric Area: {results['total_area']:,} DBU²")
    logger.info(f"\nRow Heights: {results['row_heights']}")
    logger.info(f"Column Widths: {results['col_widths']}")

    logger.info("\n--- Optimal Tile Dimensions ---")
    widths = results["optimal_widths"]
    heights = results["optimal_heights"]

    # Find max tile name length for formatting
    max_name_len = max(len(name) for name in widths.keys()) if widths else 10

    logger.info(
        f"{'Tile Name':<{max_name_len}}  {'Width (DBU)':>12}  {'Height (DBU)':>12}  {'Area (DBU²)':>15}"
    )
    logger.info("-" * (max_name_len + 47))

    for tile_name in sorted(widths.keys()):
        width = widths[tile_name]
        height = heights[tile_name]
        area = width * height
        logger.info(
            f"{tile_name:<{max_name_len}}  {width:>12,}  {height:>12,}  {area:>15,}"
        )

    logger.info(f"\n{'=' * 70}")


def save_results(results: dict, output_path: Path) -> None:
    """Save results to JSON file.

    Parameters
    ----------
    results : dict
        Optimization results
    output_path : Path
        Output file path
    """

    # Convert any non-serializable types
    def convert(obj):
        if isinstance(obj, (Decimal, int)):
            return int(obj)
        if isinstance(obj, float):
            return float(obj)
        return obj

    serializable_results = json.loads(json.dumps(results, default=convert))

    with open(output_path, "w") as f:
        json.dump(serializable_results, f, indent=2)

    logger.info(f"\n✓ Results saved to: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run NLP tile optimization from a summary JSON file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  %(prog)s --summary tile_optimisation_summary.json --project-dir /path/to/fab_project
  
  %(prog)s -s summary.json -p ./my_fabric --output results.json --time-limit 600
        """,
    )

    parser.add_argument(
        "-s",
        "--summary",
        type=Path,
        required=True,
        help="Path to tile optimization summary JSON file",
    )
    parser.add_argument(
        "-p",
        "--project-dir",
        type=Path,
        required=True,
        help="Path to FABulous project directory (containing Fabric/fabric.csv)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("optimization_results.json"),
        help="Output JSON file for results (default: optimization_results.json)",
    )
    parser.add_argument(
        "-t",
        "--time-limit",
        type=int,
        default=300,
        help="Time limit in seconds for NLP solver (default: 300)",
    )

    args = parser.parse_args()

    try:
        # Validate inputs
        if not args.project_dir.exists():
            logger.info(
                f"❌ Error: Project directory does not exist: {args.project_dir}"
            )
            return 1

        if not args.project_dir.is_dir():
            logger.info(
                f"❌ Error: Project path is not a directory: {args.project_dir}"
            )
            return 1

        # Run optimization
        results = run_optimization(args.summary, args.project_dir, args.time_limit)

        # Display results
        print_info_results(results)

        # Save results
        save_results(results, args.output)

        logger.info("\n✓ Optimization completed successfully!")
        return 0

    except KeyboardInterrupt:
        logger.info("\n\n⚠ Interrupted by user")
        return 130
    except Exception as e:
        logger.info(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
