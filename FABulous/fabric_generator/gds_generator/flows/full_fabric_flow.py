"""Full automatic fabric flow with LP-based tile optimization.

This flow uses Linear Programming to optimize tile dimensions:
1. Compiles all tiles with 3 modes (balance, min-width, min-height) in parallel
2. Formulates LP problem to minimize total fabric perimeter as area proxy
3. Solves for optimal tile dimensions with row/column grid constraints
4. Recompiles tiles with optimal dimensions in parallel
5. Stitches all tiles into final fabric
"""

import json
import traceback
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import TYPE_CHECKING

from librelane.config.flow import flow_common_variables
from librelane.config.variable import Macro
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow, FlowException
from librelane.logging.logger import err, info
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.openroad import Floorplan
from librelane.steps.step import Step

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)
from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMarcoFlow,
)
from FABulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from FABulous.fabric_generator.gds_generator.steps.extract_pdk_info import (
    ExtractPDKInfo,
)
from FABulous.fabric_generator.gds_generator.steps.global_tile_opitmisation import (
    GlobalTileSizeOptimization,
)
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode
from FABulous.FABulous_settings import init_context
from FABulous.processpool import DillProcessPoolExecutor

if TYPE_CHECKING:
    from concurrent.futures import Future

    from librelane.config.config import Config

configs = (
    Classic.config_vars
    + Floorplan.config_vars
    + flow_common_variables
    + GlobalTileSizeOptimization.config_vars
)


def _run_tile_flow_worker(
    tile_type: Tile | SuperTile,
    proj_dir: Path,
    io_pin_config: Path,
    optimisation: OptMode,
    base_config_path: Path,
    override_config_path: Path,
    **custom_config_overrides: dict,
) -> tuple[State | None, str | None]:
    """Worker function to run a tile flow in a separate process.

    This function is called by ProcessPoolExecutor to compile tiles in parallel
    processes, avoiding GIL contention from blocking subprocess calls.

    Parameters
    ----------
    tile_type : Tile | SuperTile
        The tile to compile
    proj_dir : Path
        The path to the project directory
    io_pin_config : Path
        Path to the IO pin configuration YAML file
    optimisation : OptMode
        The optimization mode for tile compilation
    base_config_path : Path
        Base configuration file path for the flow
    override_config_path : Path
        Override configuration file path for the flow
    **custom_config_overrides : dict
        Any software overrides for the flow configuration

    Returns
    -------
    tuple[State | None, str | None]
        (compiled_state, error_trace) for result processing
    """
    try:
        from FABulous.FABulous_settings import FABulousSettings

        context: FABulousSettings = init_context(project_dir=proj_dir)
        # Reconstruct the flow in the worker process with serializable data
        flow: FABulousTileVerilogMarcoFlow = FABulousTileVerilogMarcoFlow(
            tile_type,
            io_pin_config,
            optimisation,
            pdk=context.pdk,
            pdk_root=context.pdk_root.parent,
            base_config_path=base_config_path,
            override_config_path=override_config_path,
            **custom_config_overrides or {},
        )
        state: State = flow.start()
    except Exception:  # noqa: BLE001
        return None, traceback.format_exc()
    else:
        return state, None


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

        # Build set of all sub-tile names that are part of SuperTiles
        # Sub-tiles don't need their own directories
        subtile_names: set[str] = set()
        for supertile in fabric.superTileDic.values():
            for subtile in supertile.tiles:
                subtile_names.add(subtile.name)

        # Validate regular tile directories
        # Skip tiles that are sub-components of SuperTiles
        for tile_name in fabric.tileDic:
            if tile_name in subtile_names:
                # This tile is part of a SuperTile, skip directory check
                continue
            tile_dir: Path = tile_dir_base / tile_name
            if not tile_dir.exists():
                missing_tiles.append(f"{tile_name} (regular tile)")
            else:
                found_regular_tiles += 1

        # Validate SuperTile directories
        # Note: SuperTiles should have their own directories with compiled output
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
                f"({found_regular_tiles} regular tiles, {found_supertiles} SuperTiles, "
                f"{len(subtile_names)} sub-tiles within SuperTiles)"
            )
        else:
            info(
                f"✓ Project structure validated: {total_types} tile types found "
                f"({found_regular_tiles} regular tiles, {found_supertiles} SuperTiles)"
            )

    def _init_compile(self, fabric: Fabric, proj_dir: Path) -> None:
        """Compile all tiles for design space exploration."""
        # Optimization modes to try for each tile
        opt_modes: list[OptMode] = [
            OptMode.BALANCE,
            OptMode.FIND_MIN_HEIGHT,
            OptMode.FIND_MIN_WIDTH,
        ]

        handlers: list[
            tuple[Future[tuple[State | None, str | None]], OptMode, Tile | SuperTile]
        ] = []
        with DillProcessPoolExecutor(max_workers=None) as executor:
            for opt_mode, tile_type in product(
                opt_modes, fabric.get_all_unique_tiles()
            ):
                # Extract serializable config (as dict to avoid Config lock issues)
                io_config_path: Path = tile_type.tileDir.parent / "io_pin_order.yaml"
                generate_IO_pin_order_config(fabric, tile_type, io_config_path)
                base_config_path: Path = (
                    proj_dir / "Tile" / "include" / "gds_config.yaml"
                )
                override_config_path: Path = (
                    tile_type.tileDir.parent / "gds_config.yaml"
                )

                result: Future[tuple[State | None, str | None]] = executor.submit(
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

            try:
                state, error_trace_worker = state_future.result()
                if error_trace_worker:
                    error = "Worker execution failed"
                    error_trace = error_trace_worker
            except Exception as e:  # noqa: BLE001
                error = str(e)
                error_trace = traceback.format_exc()
            # Try to save snapshot if state exists
            # Always build the metrics dict
            metrics_dict: dict[str, object] = {}
            if state is not None:
                metrics_dict = {
                    k: state.metrics.get(k)
                    for k in [
                        "design__die__bbox",
                        "design__core__bbox",
                        "design__instance__area__stdcell",
                        "design__instance__utilization__stdcell",
                    ]
                }

            # Add error info if present
            if error is not None:
                metrics_dict["error"] = error
                metrics_dict["error_traceback"] = error_trace

            info(f"opt_mode={opt_mode.value}, tile={tile_name}, metrics={metrics_dict}")

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
        2. Formulate NLP problem to minimize total fabric area
        3. Solve for optimal tile dimensions with row/column grid constraints
        4. Recompile tiles with optimal dimensions in parallel
        5. Stitch all tiles into final fabric

        Parameters
        ----------
        initial_state : State
            Initial state
        **_kwargs : dict
            Additional keyword arguments

        Returns
        -------
        tuple[State, list[Step]]
            Final state and list of executed steps

        Raises
        ------
        RuntimeError
            If tile compilation or NLP optimization fails
        FlowException
            When NLP optimization step fails
        """
        fabric: Fabric = self.config["FABULOUS_FABRIC"]
        proj_dir: Path = Path(self.config["FABULOUS_PROJ_DIR"])
        self.progress_bar.set_max_stage_count(3)

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

        # Step 3: Recompile tiles with optimal dimensions
        self.progress_bar.start_stage("Tile Recompilation")
        info("\n=== Step 3: Recompiling tiles with optimal dimensions ===")

        # Compile tiles with optimal dimensions in parallel
        handlers: list[
            tuple[Future[tuple[State | None, str | None]], Tile | SuperTile]
        ] = []
        with DillProcessPoolExecutor(max_workers=None) as executor:
            for tile_type in fabric.get_all_unique_tiles():
                io_config_path: Path = (
                    tile_type.tileDir.parent / f"{tile_type.name}_io_pin_order.yaml"
                )
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
                result: Future[tuple[State | None, str | None]] = executor.submit(
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
            state: State | None
            error_trace: str | None
            state, error_trace = state_future.result()
            if error_trace or state is None:
                raise RuntimeError(
                    f"Tile {tile_name} compilation failed:\n{error_trace}"
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

        # Step 4: Collect tile macros for fabric stitching
        macros: dict[str, Macro] = {}
        tile_sizes: dict[str, tuple[Decimal, Decimal]] = {}

        for tile_type_name, tile_state in tile_type_states.items():
            width: Decimal = Decimal(
                tile_type_states[tile_type_name]
                .metrics["design__die__bbox"]
                .split(" ")[2]
            )
            height: Decimal = Decimal(
                tile_type_states[tile_type_name]
                .metrics["design__die__bbox"]
                .split(" ")[3]
            )
            tile_sizes[tile_type_name] = (width, height)

            # Get tile output files
            gds_file: Path | None = tile_state.get(DesignFormat.GDS)
            lef_file: Path | None = tile_state.get(DesignFormat.LEF)
            lib_files: (
                dict[str, list[Path]] | list[Path] | Path | None
            ) = tile_state.get(DesignFormat.LIB)

            # Build lib dict
            lib_dict: dict[str, list[Path]] = {}
            if lib_files:
                if isinstance(lib_files, dict):
                    for corner, paths in lib_files.items():
                        lib_dict[corner] = [Path(str(p)) for p in paths]
                elif isinstance(lib_files, list):
                    lib_dict["default"] = [Path(str(p)) for p in lib_files]
                else:
                    lib_dict["default"] = [Path(str(lib_files))]

            macros[tile_type_name] = Macro(
                gds=[Path(str(gds_file))] if gds_file else [],
                lef=[Path(str(lef_file))] if lef_file else [],
                lib=lib_dict,
                instances={},
            )

        info(f"Collected {len(macros)} tile macros")

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
