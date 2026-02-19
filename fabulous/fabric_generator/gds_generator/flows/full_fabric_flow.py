"""Full automatic fabric flow with LP-based tile optimization.

This flow uses non-Linear Programming (NLP) to optimize tile dimensions:
1. Compiles all tiles with 3 modes (balance, min-width, min-height) in parallel
2. Formulates LP problem to minimize total fabric perimeter as area proxy
3. Solves for optimal tile dimensions with row/column grid constraints
4. Recompiles tiles with optimal dimensions in parallel
5. Stitches all tiles into final fabric
"""

import json
import shutil
import traceback
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import TYPE_CHECKING

from librelane.common.misc import get_latest_file
from librelane.config.flow import flow_common_variables
from librelane.config.variable import Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow, FlowException
from librelane.logging.logger import err, info
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.openroad import Floorplan
from librelane.steps.step import Step

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from fabulous.fabric_generator.gds_generator.steps.extract_pdk_info import (
    ExtractPDKInfo,
)
from fabulous.fabric_generator.gds_generator.steps.global_tile_opitmisation import (
    GlobalTileSizeOptimization,
)
from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode
from fabulous.fabulous_settings import init_context
from fabulous.processpool import DillProcessPoolExecutor

if TYPE_CHECKING:
    from concurrent.futures import Future

    from librelane.config.config import Config

configs = (
    Classic.config_vars
    + Floorplan.config_vars
    + flow_common_variables
    + GlobalTileSizeOptimization.config_vars
    + [
        Variable(
            "FABULOUS_NLP_ONLY",
            bool,
            description="Stop after NLP optimisation, skip recompilation and stitching",
            default=False,
        ),
        Variable(
            "FABULOUS_NLP_AREA_MARGIN",
            float,
            description="Area margin for NLP constraint (0.05 = 5% slack)",
            default=0.05,
        ),
    ]
)

WorkerResult = tuple[State | None, str | None, dict[str, float] | None]


def _extract_pin_min(flow: FABulousTileVerilogMacroFlow) -> dict[str, float]:
    """Extract pin minimum dimensions from flow config."""
    return {
        "fabulous__pin_min_width": float(flow.config["FABULOUS_PIN_MIN_WIDTH"]),
        "fabulous__pin_min_height": float(flow.config["FABULOUS_PIN_MIN_HEIGHT"]),
    }


def _run_tile_flow_worker(
    tile_type: Tile | SuperTile,
    proj_dir: Path,
    io_pin_config: Path,
    optimisation: OptMode,
    base_config_path: Path,
    override_config_path: Path,
    **custom_config_overrides: dict,
) -> WorkerResult:
    """Worker function to run a tile flow in a separate process.

    This function is called by ProcessPoolExecutor to compile tiles in parallel
    processes, avoiding GIL contention from blocking subprocess calls.

    Parameters
    ----------
    tile_type : Tile | SuperTile
        The tile to compile.
    proj_dir : Path
        The path to the project directory.
    io_pin_config : Path
        Path to the IO pin configuration YAML file.
    optimisation : OptMode
        The optimization mode for tile compilation.
    base_config_path : Path
        Base configuration file path for the flow.
    override_config_path : Path
        Override configuration file path for the flow.
    **custom_config_overrides : dict
        Any software overrides for the flow configuration.

    Returns
    -------
    WorkerResult
        (compiled_state, error_trace, pin_min) for result processing.
    """
    flow: FABulousTileVerilogMacroFlow | None = None
    try:
        from fabulous.fabulous_settings import FABulousSettings

        context: FABulousSettings = init_context(project_dir=proj_dir)
        # Reconstruct the flow in the worker process with serializable data
        flow = FABulousTileVerilogMacroFlow(
            tile_type,
            io_pin_config,
            optimisation,
            pdk=context.pdk,
            pdk_root=context.pdk_root.parent,
            base_config_path=base_config_path,
            override_config_path=override_config_path,
            **custom_config_overrides,
        )
        state: State = flow.start()
    except Exception:  # noqa: BLE001
        # Try to recover the state from disk - deferred errors (e.g. XOR
        # differences) raise after the state has already been saved.
        if flow is not None and flow.run_dir is not None:
            latest_state = get_latest_file(flow.run_dir, "state_out.json")
            if latest_state is not None:
                recovered = State.loads(Path(latest_state).read_text(encoding="utf-8"))
                return recovered, traceback.format_exc(), _extract_pin_min(flow)
        return None, traceback.format_exc(), None
    else:
        return state, None, _extract_pin_min(flow)


@Flow.factory.register()
class FABulousFabricMacroFullFlow(Flow):
    """Full automatic fabric flow with LP-optimized tile dimensions.

    This flow automatically:
    1. Compiles all tiles with 3 optimization modes to explore dimension space
    2. Solves LP problem to find optimal dimensions minimizing fabric perimeter
    3. Recompiles tiles with optimal dimensions from LP solution
    4. Stitches all tiles into final fabric with minimal area
    """

    Steps = [ExtractPDKInfo, GlobalTileSizeOptimization]

    config_vars = configs

    @staticmethod
    def _log_nlp_summary(nlp_state: State) -> None:
        """Log a summary table of NLP tile dimensions and utilization."""
        tile_areas = nlp_state.metrics.get("nlp__tile__area", {})
        stdcell_areas = nlp_state.metrics.get("nlp__tile__stdcell_area", {})
        total_area = nlp_state.metrics.get("nlp__total__area", 0)
        hdr = f"{'Tile':<20} {'Width':>10} {'Height':>10} {'Area':>12} {'Util':>8}"
        info(hdr)
        info("-" * len(hdr))
        for name, dims in tile_areas.items():
            w, h = float(dims[2]), float(dims[3])
            alloc_area = w * h
            sc = stdcell_areas.get(name, 0.0)
            util = sc / alloc_area * 100 if alloc_area > 0 else 0.0
            info(f"{name:<20} {w:>10.2f} {h:>10.2f} {alloc_area:>12.2f} {util:>7.1f}%")
        info("-" * len(hdr))
        info(f"{'Total fabric area':<20} {'':>10} {'':>10} {total_area:>12} {'':>8}")

    def _validate_project_dir(self, proj_dir: Path, fabric: Fabric) -> None:
        """Validate the project directory structure for required tile directories."""
        info("Validating project directory structure...")
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project directory not found: {proj_dir}")
        if not proj_dir.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {proj_dir}")

        tile_dir_base: Path = proj_dir / "Tile"
        if not tile_dir_base.exists():
            raise FileNotFoundError(
                f"Tile directory not found: {tile_dir_base}. "
                "Expected structure: <proj_dir>/Tile/<tile_name>/"
            )

        # Validate all tile directories exist
        # Check both regular tiles and SuperTiles from their dictionaries
        missing_tiles: list[str] = []
        found_regular_tiles: int = 0
        found_supertiles: int = 0

        # Build set of all subtile names that are part of SuperTiles
        # Subtiles don't need their own directories
        subtile_names: set[str] = set()
        for supertile in fabric.superTileDic.values():
            for subtile in supertile.tiles:
                subtile_names.add(subtile.name)

        # Validate regular tile directories
        # Skip tiles that are sub-components of SuperTiles
        for tile_name in fabric.tileDic:
            if tile_name in subtile_names:
                # This tile is part of a supertile, skip directory check
                continue
            tile_dir: Path = tile_dir_base / tile_name
            if not tile_dir.exists():
                missing_tiles.append(f"{tile_name} (regular Tile)")
            else:
                found_regular_tiles += 1

        # Validate SuperTile directories
        # Note: Supertiles should have their own directories with compiled output
        for supertile_name in fabric.superTileDic:
            supertile_dir: Path = tile_dir_base / supertile_name
            if not supertile_dir.exists():
                missing_tiles.append(f"{supertile_name} (SuperTile)")
            else:
                found_supertiles += 1

        if missing_tiles:
            raise FileNotFoundError(
                f"Missing tile directories in {tile_dir_base}:\n"
                + "\n".join(f"  - {tile}" for tile in missing_tiles)
            )

        total_types: int = found_regular_tiles + found_supertiles
        if subtile_names:
            info(
                f"✓ Project structure validated: {total_types} tile types found "
                f"({found_regular_tiles} regular tiles, {found_supertiles} supertiles, "
                f"{len(subtile_names)} subtiles within SuperTiles)"
            )
        else:
            info(
                f"✓ Project structure validated: {total_types} tile types found "
                f"({found_regular_tiles} regular tiles, {found_supertiles} supertiles)"
            )

    def _init_compile(self, fabric: Fabric, proj_dir: Path) -> None:
        """Compile all tiles for design space exploration."""
        # Optimization modes to try for each tile
        opt_modes: list[OptMode] = [
            OptMode.BALANCE,
            OptMode.FIND_MIN_HEIGHT,
            OptMode.FIND_MIN_WIDTH,
        ]

        handlers: list[tuple[Future[WorkerResult], OptMode, Tile | SuperTile]] = []
        with DillProcessPoolExecutor(max_workers=None) as executor:
            for opt_mode, tile_type in product(
                opt_modes, fabric.get_all_unique_tiles()
            ):
                io_config_path: Path = tile_type.tileDir.parent / "io_pin_order.yaml"
                generate_IO_pin_order_config(fabric, tile_type, io_config_path)
                base_config_path: Path = (
                    proj_dir / "Tile" / "include" / "gds_config.yaml"
                )
                override_config_path: Path = (
                    tile_type.tileDir.parent / "gds_config.yaml"
                )

                result: Future[WorkerResult] = executor.submit(
                    _run_tile_flow_worker,
                    tile_type,
                    proj_dir,
                    io_config_path,
                    opt_mode,
                    base_config_path,
                    override_config_path,
                    FABULOUS_IGNORE_DEFAULT_DIE_AREA=True,
                )
                handlers.append((result, opt_mode, tile_type))

        result_summary: dict[str, dict[str, object]] = {
            opt_mode.value: {} for opt_mode in opt_modes
        }
        for state_future, opt_mode, tile_type in handlers:
            tile_name: str = tile_type.name
            error: str | None = None
            error_trace: str | None = None
            state: State | None = None
            pin_min: dict[str, float] | None = None
            try:
                state, error_trace_worker, pin_min = state_future.result()
                if error_trace_worker:
                    error = "Worker execution failed"
                    error_trace = error_trace_worker
            except Exception as e:  # noqa: BLE001
                error = str(e)
                error_trace = traceback.format_exc()
            # Build metrics dict from state if available
            metrics_dict: dict[str, object] = {}
            if state is not None:
                metric_keys = (
                    "design__die__bbox",
                    "design__core__bbox",
                    "design__instance__area__stdcell",
                    "design__instance__utilization__stdcell",
                )
                metrics_dict = {k: state.metrics.get(k) for k in metric_keys}
            if pin_min is not None:
                metrics_dict |= pin_min

            # Add error info if present
            if error is not None:
                metrics_dict["error"] = error
                metrics_dict["error_traceback"] = error_trace

            info(f"opt_mode={opt_mode.value}, tile={tile_name}, metrics={metrics_dict}")
            result_summary[opt_mode.value][tile_name] = metrics_dict

        def custom_serializer(obj: object) -> float | object:
            if isinstance(obj, Decimal):
                return float(obj)
            return obj

        out_summary_path: Path = Path(self.run_dir) / "tile_optimisation_summary.json"
        out_summary_path.write_text(
            json.dumps(result_summary, indent=4, default=custom_serializer)
        )
        self.config = self.config.copy(TILE_OPT_INFO=str(out_summary_path))

    def run(self, initial_state: State, **_kwargs: dict) -> tuple[State, list[Step]]:
        """Execute the NLP-based fabric flow.

        Flow steps:
        1. Compile all tiles with optimization mode in parallel
        2. Formulate Non-linear Programming (NLP) problem to minimize total fabric area
        3. Recompile tiles with optimal dimensions in parallel
        4. Stitch all tiles into final fabric

        Parameters
        ----------
        initial_state : State
            Initial state.
        **_kwargs : dict
            Additional keyword arguments.

        Returns
        -------
        tuple[State, list[Step]]
            Final state and list of executed steps.

        Raises
        ------
        RuntimeError
            If tile compilation or NLP optimization fails.
        FlowException
            When NLP optimization step fails.
        """
        fabric: Fabric = self.config["FABULOUS_FABRIC"]
        proj_dir: Path = Path(self.config["FABULOUS_PROJ_DIR"])
        self.progress_bar.set_max_stage_count(4)

        self._validate_project_dir(proj_dir, fabric)

        # Step 1: Parallel compilation to find minimum dimensions
        info("\n=== Step 1: Finding minimum tile dimensions ===")
        self.progress_bar.start_stage("Finding Minimum Dimensions")
        if self.config.get("TILE_OPT_INFO") is None:
            self._init_compile(fabric, proj_dir)
        else:
            info(
                "Tile optimization info already present, skipping initial compilation."
            )

        self.progress_bar.start_stage("NLP Optimization")
        info("\n=== Step 2: Solving NLP optimization ===")
        # Create and run NLP optimization step
        nlp_config: Config = self.config.copy(FABULOUS_PROJ_DIR=proj_dir)

        nlp_step: GlobalTileSizeOptimization = GlobalTileSizeOptimization(
            nlp_config, id="SolveNLPOptimization", state_in=initial_state
        )
        try:
            nlp_state: State = self.start_step(nlp_step)
        except Exception as e:
            err(f"NLP optimization step failed to start/execute: {e}")
            err(traceback.format_exc())
            raise FlowException("NLP optimization step failed") from e

        self.progress_bar.end_stage()

        if self.config.get("FABULOUS_NLP_ONLY"):
            info("\n=== NLP-only mode: skipping recompilation and stitching ===")
            self._log_nlp_summary(nlp_state)
            return nlp_state, []

        # Step 3: Recompile tiles with optimal dimensions
        self.progress_bar.start_stage("Tile Recompilation")
        info("\n=== Step 3: Recompiling tiles with optimal dimensions ===")

        # Compile tiles with optimal dimensions in parallel
        handlers: list[tuple[Future[WorkerResult], Tile | SuperTile]] = []
        with DillProcessPoolExecutor(max_workers=None) as executor:
            for tile_type in fabric.get_all_unique_tiles():
                io_config_path: Path = tile_type.tileDir.parent / "io_pin_order.yaml"
                base_config_path: Path = (
                    proj_dir / "Tile" / "include" / "gds_config.yaml"
                )
                override_config_path: Path = (
                    tile_type.tileDir.parent / "gds_config.yaml"
                )

                die_area: tuple[int, int, Decimal, Decimal] = nlp_state.metrics[
                    "nlp__tile__area"
                ][tile_type.name]
                # Submit tile compilation with optimal dimensions
                result: Future[WorkerResult] = executor.submit(
                    _run_tile_flow_worker,
                    tile_type,
                    proj_dir,
                    io_config_path,
                    OptMode.NO_OPT,
                    base_config_path,
                    override_config_path,
                    DIE_AREA=die_area,
                )
                handlers.append((result, tile_type))

        # Collect results
        tile_type_states: dict[str, State] = {}
        for state_future, tile_type in handlers:
            tile_name: str = tile_type.name
            state, error_trace, _ = state_future.result()
            if state is None:
                raise RuntimeError(
                    f"Tile {tile_name} compilation failed:\n{error_trace}"
                )
            if error_trace:
                err(
                    f"Tile {tile_name} had errors but state was recovered:\n"
                    f"{error_trace}"
                )

            # Verify compilation succeeded
            if not state.get(DesignFormat.GDS) or not state.get(DesignFormat.LEF):
                err(f"Tile {tile_name} missing required outputs (GDS or LEF)")
                raise RuntimeError(
                    f"Tile {tile_name} failed final compilation with optimal dimensions"
                )

            tile_type_states[tile_name] = state
            info(f"✓ {tile_name} recompiled successfully")

        info(f"✓ All {len(tile_type_states)} tiles recompiled with optimal dimensions")

        self.progress_bar.end_stage()

        # Step 4: Create final_views symlinks for each tile so the
        # fabric stitching flow can find them at the standard path.
        for tile_name, tile_state in tile_type_states.items():
            gds_path: Path | None = tile_state.get(DesignFormat.GDS)
            if gds_path is None:
                raise RuntimeError(
                    f"Tile {tile_name} has no GDS output after recompilation"
                )

            # Walk up from the GDS path to find the run directory that
            # contains the final/ snapshot. This is robust to varying step
            # nesting depth (e.g. write-out steps inside a WhileStep wrapper).
            # Note: librelane's Path is a UserString, so we wrap with pathlib.
            final_dir: Path | None = next(
                (
                    parent / "final"
                    for parent in Path(str(gds_path)).parents
                    if (parent / "final").is_dir()
                ),
                None,
            )
            if final_dir is None:
                raise RuntimeError(
                    f"Could not locate final/ directory for tile {tile_name} "
                    f"from GDS path {gds_path}"
                )
            final_views: Path = proj_dir / "Tile" / tile_name / "macro" / "final_views"
            if final_views.is_symlink():
                final_views.unlink()
            elif final_views.is_dir():
                shutil.rmtree(final_views)
            final_views.symlink_to(final_dir)

        info(f"Created final_views symlinks for {len(tile_type_states)} tiles")

        # Generate fabric-level IO pin configuration
        fabric_io_config_path: Path = proj_dir / "Fabric" / "fabric_io_pin_order.yaml"
        fabric_io_config_path.parent.mkdir(parents=True, exist_ok=True)

        # Step 5: Run fabric stitching
        self.progress_bar.start_stage("Fabric Stitching")

        stitching_flow: FABulousFabricMacroFlow = FABulousFabricMacroFlow(
            fabric,
            fabric_verilog_paths=[proj_dir / "Fabric" / f"{fabric.name}.v"],
            tile_macro_dirs={
                k.name: (proj_dir / "Tile" / k.name / "macro" / "final_views")
                for k in fabric.get_all_unique_tiles()
            },
            base_config_path=proj_dir / "Fabric" / "gds_config.yaml",
        )

        final_state: State = stitching_flow.start()
        self.progress_bar.end_stage()

        info("\n✓ Fabric flow completed successfully!")
        return final_state, []
