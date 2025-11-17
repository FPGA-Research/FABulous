"""Full automatic fabric flow with LP-based tile optimization.

This flow uses Linear Programming to optimize tile dimensions:
1. Compiles all tiles with 3 modes (balance, min-width, min-height) in parallel
2. Formulates LP problem to minimize total fabric perimeter as area proxy
3. Solves for optimal tile dimensions with row/column grid constraints
4. Recompiles tiles with optimal dimensions in parallel
5. Stitches all tiles into final fabric
"""

import json
import multiprocessing
import traceback
from concurrent.futures import Future
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import cast

from librelane.config.flow import flow_common_variables
from librelane.config.variable import Macro, Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow
from librelane.logging.logger import err, info, warn
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.openroad import Floorplan
from librelane.steps.step import Step

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMarcoFlow,
)
from FABulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from FABulous.fabric_generator.gds_generator.helper import round_die_area
from FABulous.fabric_generator.gds_generator.steps import global_tile_opitmisation
from FABulous.fabric_generator.gds_generator.steps.fabric_macro_gen import (
    FabricMacroGen,
)
from FABulous.fabric_generator.gds_generator.steps.global_tile_opitmisation import (
    GlobalTileSizeOptimization,
)
from FABulous.fabric_generator.gds_generator.steps.tile_macro_gen import TileMarcoGen
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode
from FABulous.FABulous_settings import init_context
from FABulous.processpool import DillProcessPoolExecutor

configs = (
    Classic.config_vars
    + Floorplan.config_vars
    + flow_common_variables
    + GlobalTileSizeOptimization.config_vars
    + [
        Variable(
            "FABULOUS_PROJ_DIR",
            Path,
            description="Path to the FABulous project directory",
        ),
        Variable(
            "FABULOUS_FABRIC",
            Fabric,
            description="Fabric configuration object",
        ),
        Variable(
            "FABULOUS_TILE_SPACING",
            Decimal,
            description="Spacing between tiles in database units",
            default=Decimal(0),
        ),
        Variable(
            "FABULOUS_HALO_SPACING",
            tuple[Decimal, Decimal, Decimal, Decimal],
            description="Halo spacing around fabric [left, bottom, right, top] in DBU",
            default=(Decimal(100), Decimal(100), Decimal(100), Decimal(100)),
        ),
        Variable(
            "FABULOUS_ILP_SOLVER_TIME_LIMIT",
            int,
            description="Time limit in seconds for ILP solver",
            default=300,
        ),
    ]
)


def _run_tile_flow_worker(
    tile_type: Tile | SuperTile,
    proj_dir: Path,
    io_pin_config: Path,
    optimisation: OptMode,
    base_config_path: Path,
    override_config_path: Path,
    **custom_config_overrides: dict,
) -> tuple[State, str]:
    """Worker function to run a tile flow in a separate process.

    This function is called by ProcessPoolExecutor to compile tiles in parallel
    processes, avoiding GIL contention from blocking subprocess calls.

    Parameters
    ----------
    flow_config : dict
        Configuration dictionary for the flow (serializable copy)
    flow_name : str
        Name of the flow instance
    design_dir : str
        Design directory path for the flow

    Returns
    -------
    tuple[State, str]
        (compiled_state, design_name) for result processing
    """
    init_context(project_dir=proj_dir)
    # Reconstruct the flow in the worker process with serializable data
    flow = FABulousTileVerilogMarcoFlow(
        tile_type,
        io_pin_config,
        optimisation,
        base_config_path=base_config_path,
        override_config_path=override_config_path,
        **custom_config_overrides or {},
    )
    state = flow.start()
    design_name = tile_type.name + optimisation.value
    return state, design_name


@Flow.factory.register()
class FABulousFabricMacroFullFlow(Flow):
    """Full automatic fabric flow with LP-optimized tile dimensions.

    This flow automatically:
    1. Compiles all tiles with 3 optimization modes to explore dimension space
    2. Solves LP problem to find optimal dimensions minimizing fabric perimeter
    3. Recompiles tiles with optimal dimensions from LP solution
    4. Stitches all tiles into final fabric with minimal area
    """

    Steps = [TileMarcoGen, GlobalTileSizeOptimization, FabricMacroGen]

    config_vars = configs

    def _extract_tile_dimensions_from_state(
        self, state: State
    ) -> tuple[Decimal, Decimal]:
        """Extract final tile dimensions from compiled state.

        Parameters
        ----------
        state : State
            Compiled tile state

        Returns
        -------
        tuple[int, int]
            (width_dbu, height_dbu) of compiled tile

        Raises
        ------
        ValueError
            If tile dimensions cannot be determined
        """
        # Get DIE_AREA from metrics if available
        die_area_metric = state.metrics.get("design__die__bbox")
        if die_area_metric:
            llx, lly, urx, ury = map(Decimal, die_area_metric.split(" "))
            return urx - llx, ury - lly

        raise ValueError("Could not extract tile dimensions from state")

    def _compilation_successful(
        self, state: State, check_antenna: bool = False
    ) -> bool:
        """Check if tile compilation was successful.

        Parameters
        ----------
        state : State
            Compiled tile state

        Returns
        -------
        bool
            True if compilation succeeded without critical errors
        """
        # Check for critical errors in metrics
        critical_metrics = [
            "route__drc_errors",
        ]

        if check_antenna:
            critical_metrics.append("antenna__violating__nets")
            critical_metrics.append("antenna__violating__pins")

        for metric in critical_metrics:
            value = state.metrics.get(metric)
            if value is not None and int(value) > 0:
                warn(f"Tile compilation has {metric}={value}")
                return False

        # Check if required outputs exist
        if not state.get(DesignFormat.GDS) or not state.get(DesignFormat.LEF):
            err("Tile compilation missing required outputs (GDS or LEF)")
            return False

        return True

    def _validate_project_dir(self, proj_dir: Path, fabric: Fabric) -> None:
        # Validate project directory structure
        info("Validating project directory structure...")
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project directory not found: {proj_dir}")
        if not proj_dir.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {proj_dir}")

        tile_dir_base = proj_dir / "Tile"
        if not tile_dir_base.exists():
            raise FileNotFoundError(
                f"Tile directory not found: {tile_dir_base}. "
                "Expected structure: <proj_dir>/Tile/<tile_name>/"
            )

        # Validate all tile directories exist
        # Check both regular tiles and SuperTiles from their dictionaries
        missing_tiles: list[str] = []
        found_regular_tiles = 0
        found_supertiles = 0

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
            tile_dir = tile_dir_base / tile_name
            if not tile_dir.exists():
                missing_tiles.append(f"{tile_name} (regular tile)")
            else:
                found_regular_tiles += 1

        # Validate SuperTile directories
        # Note: SuperTiles should have their own directories with compiled output
        for supertile_name in fabric.superTileDic:
            supertile_dir = tile_dir_base / supertile_name
            if not supertile_dir.exists():
                missing_tiles.append(f"{supertile_name} (SuperTile)")
            else:
                found_supertiles += 1

        if missing_tiles:
            raise FileNotFoundError(
                f"Missing tile directories in {tile_dir_base}:\n"
                + "\n".join(f"  - {tile}" for tile in missing_tiles)
            )

        total_types = found_regular_tiles + found_supertiles
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

    def init_compile(self, fabric: Fabric, proj_dir: Path) -> None:
        # Optimization modes to try for each tile
        opt_modes = [
            OptMode.BALANCE,
            OptMode.FIND_MIN_HEIGHT,
            OptMode.FIND_MIN_WIDTH,
        ]

        handlers: list[tuple[Future[tuple[State, str]], OptMode, Tile | SuperTile]] = []
        with DillProcessPoolExecutor(max_workers=None) as executor:
            for opt_mode, tile_type in product(
                opt_modes, fabric.get_all_unique_tiles()
            ):
                # Extract serializable config (as dict to avoid Config lock issues)
                io_config_path = tile_type.tileDir.parent / "io_pin_order.yaml"
                generate_IO_pin_order_config(fabric, tile_type, io_config_path)
                base_config_path = proj_dir / "Tile" / "include" / "gds_config.yaml"
                override_config_path = tile_type.tileDir.parent / "gds_config.yaml"

                result = executor.submit(
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

        result_summary = {opt_mode.value: {} for opt_mode in opt_modes}
        for state_future, opt_mode, tile_type in handlers:
            tile_name = tile_type.name
            error = None
            error_trace = None
            state = None

            try:
                state, design_name = state_future.result()
            except Exception as e:
                error = str(e)
                error_trace = traceback.format_exc()
            # Try to save snapshot if state exists
            # Always build the metrics dict
            metrics_dict = {}
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

            result_summary[opt_mode.value][tile_type.name] = metrics_dict
            info(f"opt_mode={opt_mode.value}, tile={tile_name}, metrics={metrics_dict}")

        self.config = self.config.copy(TILE_OPT_INFO=result_summary)

        def custom_serializer(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            return obj

        (Path(self.run_dir) / "tile_optimisation_summary.json").write_text(
            json.dumps(result_summary, indent=4, default=custom_serializer)
        )

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
        """
        subflow_list: list[Flow] = []
        fabric: Fabric = self.config["FABULOUS_FABRIC"]
        proj_dir = Path(self.config["FABULOUS_PROJ_DIR"])
        self.progress_bar.set_max_stage_count(3)

        self._validate_project_dir(proj_dir, fabric)

        # Step 1: Parallel compilation to find minimum dimensions
        info("\n=== Step 1: Finding minimum tile dimensions ===")
        self.progress_bar.start_stage("Finding Minimum Dimensions")
        if self.config.get("TILE_OPT_INFO") is None:
            self.init_compile(fabric, proj_dir)
        else:
            info(
                "Tile optimization info already present, skipping initial compilation."
            )

        info("\n=== Step 2: Solving NLP optimization ===")
        self.progress_bar.start_stage("NLP Optimization")

        # Create and run NLP optimization step
        nlp_config = self.config.copy(FABULOUS_PROJ_DIR=proj_dir)

        nlp_step = GlobalTileSizeOptimization(
            nlp_config, id="SolveNLPOptimization", state_in=initial_state
        )
        try:
            nlp_state = self.start_step(nlp_step)
        except Exception as e:
            err(f"NLP optimization step failed to start/execute: {e}")
            err(traceback.format_exc())
            raise

        self.progress_bar.end_stage()

        # Extract optimal dimensions from step metrics
        optimal_widths = nlp_state.metrics["nlp_optimal_widths"]
        optimal_heights = nlp_state.metrics["nlp_optimal_heights"]
        type_to_positions = nlp_state.metrics.get("type_to_positions", {})

        info(f"Optimal tile width: {optimal_widths}")
        info(f"Optimal tile height: {optimal_heights}")

        # Step 3: Recompile tiles with optimal dimensions
        info("\n=== Step 3: Recompiling tiles with optimal dimensions ===")
        self.progress_bar.start_stage("Tile Recompilation")

        # Build list of unique tile types
        unique_tile_types_recompile: list[Tile | SuperTile] = []
        result_set = set()
        for tname in type_to_positions:
            if tname in fabric.tileDic:
                tile_obj = fabric.tileDic[tname]
                if not tile_obj.partOfSuperTile and tname not in result_set:
                    unique_tile_types_recompile.append(tile_obj)
                    result_set.add(tname)
            if tname in fabric.superTileDic:
                tile_obj = fabric.superTileDic[tname]
                if tname not in result_set:
                    unique_tile_types_recompile.append(tile_obj)
                    result_set.add(tname)

        # Compile tiles with optimal dimensions in parallel
        handlers: list[tuple[Future[tuple[State, str]], Tile | SuperTile]] = []
        with DillProcessPoolExecutor(max_workers=None) as executor:
            for tile_type in unique_tile_types_recompile:
                tile_name = tile_type.name

                # Get optimal dimensions
                optimal_width_float = optimal_widths.get(tile_name, 1)
                optimal_height_float = optimal_heights.get(tile_name, 1)

                # Round to pitch grid
                temp_config = self.config.copy(
                    DIE_AREA=[0, 0, int(optimal_width_float), int(optimal_height_float)]
                )
                rounded_config = round_die_area(temp_config)
                _, _, optimal_width, optimal_height = rounded_config["DIE_AREA"]

                info(
                    f"  {tile_name}: optimal={optimal_width_float:.1f}x"
                    f"{optimal_height_float:.1f}, "
                    f"rounded={optimal_width}x{optimal_height} DBU"
                )

                # Generate IO config
                io_config_path = tile_type.tileDir.parent / "io_pin_order.yaml"
                generate_IO_pin_order_config(fabric, tile_type, io_config_path)
                base_config_path = proj_dir / "Tile" / "include" / "gds_config.yaml"
                override_config_path = tile_type.tileDir.parent / "gds_config.yaml"

                # Submit tile compilation with optimal dimensions
                result = executor.submit(
                    _run_tile_flow_worker,
                    tile_type,
                    io_config_path,
                    OptMode.NO_OPT,
                    base_config_path,
                    override_config_path,
                    DIE_AREA=[0, 0, optimal_width, optimal_height],
                    IGNORE_ANTENNA_VIOLATIONS=True,
                    YOSYS_LOG_LEVEL="ERROR",
                    DRT_OPT_ITERS=5,
                )
                handlers.append((result, tile_type))

        # Collect results
        tile_type_states: dict[str, State] = {}
        for state_future, tile_type in handlers:
            tile_name = tile_type.name
            try:
                state, design_name = state_future.result()

                # Verify compilation succeeded
                if not state.get(DesignFormat.GDS) or not state.get(DesignFormat.LEF):
                    err(f"Tile {tile_name} missing required outputs (GDS or LEF)")
                    raise RuntimeError(
                        f"Tile {tile_name} failed final compilation with optimal dimensions"
                    )

                tile_type_states[tile_name] = state
                info(f"✓ {tile_name} recompiled successfully")

            except Exception as e:
                err(f"Recompilation of {tile_name} failed: {e}")
                err(traceback.format_exc())
                raise

        info(f"✓ All {len(tile_type_states)} tiles recompiled with optimal dimensions")

        self.progress_bar.end_stage()

        # Step 4: Collect tile macros for fabric stitching
        info("\n=== Step 4: Preparing fabric stitching ===")

        macros: dict[str, Macro] = {}
        tile_sizes: dict[str, tuple[Decimal, Decimal]] = {}

        for tile_type_name, tile_state in tile_type_states.items():
            width = Decimal(optimal_widths[tile_type_name])
            height = Decimal(optimal_heights[tile_type_name])
            tile_sizes[tile_type_name] = (width, height)

            # Get tile output files
            gds_file = tile_state.get(DesignFormat.GDS)
            lef_file = tile_state.get(DesignFormat.LEF)
            lib_files = tile_state.get(DesignFormat.LIB)

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
        fabric_io_config_path = proj_dir / "Fabric" / "fabric_io_pin_order.yaml"
        fabric_io_config_path.parent.mkdir(parents=True, exist_ok=True)

        # Step 5: Run fabric stitching
        info("\n=== Step 5: Fabric stitching ===")
        self.progress_bar.start_stage("Fabric Stitching")

        fabric_config = self.config.copy(
            FABULOUS_MACROS_SETTINGS=macros,
            FABULOUS_TILE_SIZES=tile_sizes,
            FABULOUS_TILE_SPACING=self.config["FABULOUS_TILE_SPACING"],
            FABULOUS_HALO_SPACING=self.config["FABULOUS_HALO_SPACING"],
        )

        fabric_step = FabricMacroGen(
            fabric_config, id="FabricMacroGen", state_in=initial_state
        )
        final_state = self.start_step(fabric_step)
        subflow_list.append(fabric_step)

        self.progress_bar.end_stage()

        info("\n✓ Fabric flow completed successfully!")
        return final_state, subflow_list
