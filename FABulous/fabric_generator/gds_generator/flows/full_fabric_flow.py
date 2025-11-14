"""Full automatic fabric flow with LP-based tile optimization.

This flow uses Linear Programming to optimize tile dimensions:
1. Compiles all tiles with 3 modes (balance, min-width, min-height) in parallel
2. Formulates LP problem to minimize total fabric perimeter as area proxy
3. Solves for optimal tile dimensions with row/column grid constraints
4. Recompiles tiles with optimal dimensions in parallel
5. Stitches all tiles into final fabric
"""

import contextlib
import json
import multiprocessing
import traceback
from concurrent.futures import Future, ProcessPoolExecutor
from decimal import Decimal
from pathlib import Path
from typing import cast

import dill
import yaml
from librelane.config.flow import flow_common_variables
from librelane.config.variable import Macro, Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow, FlowError
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
from FABulous.fabric_generator.gds_generator.steps.fabric_macro_gen import (
    FabricMacroGen,
)
from FABulous.fabric_generator.gds_generator.steps.global_tile_opitmisation import (
    GlobalTileSizeOptimization,
)
from FABulous.fabric_generator.gds_generator.steps.tile_macro_gen import TileMarcoGen
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode
from FABulous.FABulous_settings import get_context, init_context

configs = (
    Classic.config_vars
    + Floorplan.config_vars
    + flow_common_variables
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


def _init_worker() -> None:
    """Initialize worker process to use dill for pickling."""
    from multiprocessing.reduction import ForkingPickler

    # Override ForkingPickler with dill
    ForkingPickler.dumps = dill.dumps
    ForkingPickler.loads = dill.loads


def _run_tile_flow_worker(
    tile_type: Tile,
    io_pin_config: Path,
    optimisation: OptMode,
    base_config_path: Path,
    override_config_path: Path,
    **custom_config_overrides,
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
    from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
        FABulousTileVerilogMarcoFlow,
    )

    init_context()
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


class DillProcessPoolExecutor(ProcessPoolExecutor):
    """ProcessPoolExecutor that uses dill for serialization.

    This executor patches both the main process and worker processes to use dill instead
    of pickle, allowing serialization of thread locks and other complex objects that
    standard pickle cannot handle.
    """

    def __init__(self, *args, **kwargs):
        # Patch the main process to use dill BEFORE calling parent init
        from multiprocessing.reduction import ForkingPickler

        ForkingPickler.dumps = dill.dumps
        ForkingPickler.loads = dill.loads
        super().__init__(*args, **kwargs)


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

    def _get_compile_tile_flow(
        self,
        tile_type: Tile | SuperTile,
        fabric: Fabric,
        proj_dir: Path,
        opt_mode: OptMode,
        die_area: list | None = None,
        io_min_width: Decimal | None = None,
        io_min_height: Decimal | None = None,
        extra_config: dict | None = None,
    ) -> Flow:
        """Create a TileMarcoGen step for compiling a tile.

        This function centralizes tile compilation step creation to maximize code reuse.

        Parameters
        ----------
        tile_type : Tile | SuperTile
            Tile to compile
        fabric : Fabric
            Fabric configuration
        proj_dir : Path
            Project directory
        initial_state : State
            Initial state for the step
        step_id : str
            Unique ID for the step
        tile_optimization : bool
            Whether to enable tile optimization
        opt_mode : OptMode | None
            Optimization mode (if tile_optimization=True)
        die_area : list | None
            Override DIE_AREA constraint [llx, lly, urx, ury]
        io_min_width : Decimal | None
            Minimum width constraint from IO pins
        io_min_height : Decimal | None
            Minimum height constraint from IO pins
        extra_config : dict | None
            Additional configuration overrides

        Returns
        -------
        Step
            TileMarcoGen step ready to be executed
        """
        tile_dir = proj_dir / "Tile" / tile_type.name
        tile_name = tile_type.name

        # Generate IO pin configuration
        out_file = tile_dir / "io_pin_order.yaml"
        generate_IO_pin_order_config(fabric, tile_type, out_file)

        # Build file list
        file_list = [str(f) for f in tile_dir.glob("**/*.v") if "macro" not in f.parts]
        if models_pack := get_context().models_pack:
            file_list.append(str(models_pack.resolve()))

        # Load base config
        tile_config_overrides = {}
        if (proj_dir / "Tile" / "include" / "gds_config.yaml").exists():
            tile_config_overrides.update(
                yaml.safe_load(
                    (proj_dir / "Tile" / "include" / "gds_config.yaml").read_text(
                        encoding="utf-8"
                    )
                )
            )

        gds_config_file = tile_dir / "gds_config.yaml"
        if gds_config_file.exists():
            tile_config_overrides.update(
                yaml.safe_load(gds_config_file.read_text(encoding="utf-8"))
            )

        # Apply die area override if provided
        if die_area is not None:
            tile_config_overrides["DIE_AREA"] = die_area

        # Determine logical dimensions
        if isinstance(tile_type, SuperTile):
            logical_width = tile_type.max_width
            logical_height = tile_type.max_height
        else:
            logical_width = 1
            logical_height = 1

        # Build tile configuration
        tile_config_dict = {
            "DESIGN_NAME": tile_name,
            "FABULOUS_IO_PIN_ORDER_CFG": out_file,
            "FABULOUS_TILE_DIR": str(tile_dir),
            "VERILOG_FILES": file_list,
            "FABULOUS_TILE_LOGICAL_WIDTH": logical_width,
            "FABULOUS_TILE_LOGICAL_HEIGHT": logical_height,
            "FABULOUS_OPT_MODE": opt_mode,
            "FABULOUS_FABRIC": fabric,
            "FABULOUS_PROJ_DIR": str(proj_dir),
        }

        # Add IO constraints if provided
        if io_min_width is not None:
            tile_config_dict["FABULOUS_IO_MIN_WIDTH"] = io_min_width
        if io_min_height is not None:
            tile_config_dict["FABULOUS_IO_MIN_HEIGHT"] = io_min_height

        # Add run directory override if provided

        # Add extra config if provided
        if extra_config:
            tile_config_dict.update(extra_config)

        # Add tile-specific overrides
        tile_config_dict.update(tile_config_overrides)
        design_dir = tile_dir / "macro" / opt_mode.value
        design_dir.mkdir(parents=True, exist_ok=True)
        # full librelane config resolve
        # Create and return the step
        return FABulousTileVerilogMarcoFlow(
            tile_config_dict,
            name=tile_name,
            design_dir=str(design_dir),
            pdk=get_context().pdk,
            pdk_root=str(get_context().pdk_root.resolve().parent),
        )

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

        # Compute IO-based minimum dimensions upfront
        # This ensures TileOptimisation starts from IO-aware bounds
        info("\n=== Computing IO pin density constraints ===")

        # Step 1: Parallel compilation to find minimum dimensions
        info("\n=== Step 1: Finding minimum tile dimensions ===")
        self.progress_bar.start_stage("Finding Minimum Dimensions")

        # Optimization modes to try for each tile
        opt_modes = [
            OptMode.BALANCE,
        ]

        # Create compilation steps for all tiles with all optimization modes
        min_dim_flow_steps: list[tuple[Flow, Tile | SuperTile]] = []
        for tile_type in fabric.get_all_unique_tiles():
            out_file = tile_type.tileDir.parent / "io_pin_order.yaml"
            generate_IO_pin_order_config(fabric, tile_type, out_file)
            for opt_mode in opt_modes:
                flow = FABulousTileVerilogMarcoFlow(
                    tile_type,
                    out_file,
                    opt_mode,
                    base_config_path=proj_dir / "Tile" / "include" / "gds_config.yaml",
                    override_config_path=tile_type.tileDir.parent / "gds_config.yaml",
                    FABULOUS_IGNORE_DEFAULT_DIE_AREA=True,
                )
                min_dim_flow_steps.append((flow, tile_type))

        # TODO: Makeing this working with async setps again once librelane is fixed
        handlers: list[
            tuple[Future[tuple[State, str]], Flow, dict, Tile | SuperTile]
        ] = []
        mp_context = multiprocessing.get_context("spawn")
        with DillProcessPoolExecutor(
            max_workers=None,
            mp_context=mp_context,
            initializer=_init_worker,
        ) as executor:
            for subflow, tile_type in min_dim_flow_steps:
                # Extract serializable config (as dict to avoid Config lock issues)
                flow_config_dict = dict(subflow.config)
                io_pin_config = Path(flow_config_dict["FABULOUS_IO_PIN_ORDER_CFG"])
                opt_mode = flow_config_dict["FABULOUS_OPT_MODE"]
                base_config_path = proj_dir / "Tile" / "include" / "gds_config.yaml"
                override_config_path = tile_type.tileDir.parent / "gds_config.yaml"

                result = executor.submit(
                    _run_tile_flow_worker,
                    tile_type,
                    io_pin_config,
                    opt_mode,
                    base_config_path,
                    override_config_path,
                    FABULOUS_IGNORE_DEFAULT_DIE_AREA=True,
                )
                handlers.append((result, subflow, flow_config_dict, tile_type))

        result_summary = {}
        for state_future, subflow, flow_config_dict, tile_type in handlers:
            try:
                state, design_name = state_future.result()
                state.save_snapshot(
                    str(Path(cast("str", subflow.run_dir)) / "final_views")
                )
                result_summary[design_name] = {
                    k: state.metrics.get(k)
                    for k in [
                        "FABULOUS_OPT_MODE",
                        "design__die__bbox",
                        "design__core__bbox",
                        "design__instance__area__stdcell",
                        "design__instance__utilization__stdcell",
                        "antenna__violating__nets",
                        "antenna__violating__pins",
                    ]
                }
                subflow_list.append(subflow)

                tile_name = design_name
                opt_mode = flow_config_dict["FABULOUS_OPT_MODE"]

                initial_state.metrics[f"{tile_name}_opt_mode_{opt_mode}"] = (
                    state.metrics
                )

                if not self._compilation_successful(state):
                    warn(
                        f"Tile {tile_name} with {opt_mode} mode failed compilation, "
                        "skipping"
                    )
                else:
                    info(
                        f"{tile_name} ({opt_mode}): bounding box "
                        f"{state.metrics['design__die__bbox']}"
                    )
            except Exception as e:
                err(f"Error processing tile result: {e}")
                err(traceback.format_exc())
                result_summary[f"error_{flow_config_dict.get('DESIGN_NAME', 'unknown')}"] = {
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }

            # Write summary after each iteration for debugging
            (Path(self.design_dir) / "tile_optimisation_summary.json").write_text(
                json.dumps(result_summary, indent=2), encoding="utf-8"
            )
        # Step 2: Formulate and solve NLP problem
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
        subflow_list.append(nlp_step)

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

        final_steps: list[Step] = []

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
            extra_config = {
                "IGNORE_ANTENNA_VIOLATIONS": True,
                "YOSYS_LOG_LEVEL": "ERROR",
                "DRT_OPT_ITERS": 5,
            }
            # Create compilation step using helper with optimal dimensions
            tile_flow = self._get_compile_tile_flow(
                tile_type=tile_type,
                fabric=fabric,
                proj_dir=proj_dir,
                opt_mode=OptMode.NO_OPT,
                extra_config=extra_config,
            )

        # Start all final compilation steps and collect results
        tile_type_states: dict[str, State] = {}
        for tile_step in final_steps:
            try:
                state = self.start_step(tile_step)
                tile_name = tile_step.config["DESIGN_NAME"]

                # Verify compilation succeeded
                if not state.get(DesignFormat.GDS) or not state.get(DesignFormat.LEF):
                    err(f"Tile {tile_name} missing required outputs (GDS or LEF)")
                    raise RuntimeError(
                        f"Tile {tile_name} failed final compilation with optimal dimensions"
                    )

                tile_type_states[tile_name] = state
                info(f"✓ {tile_name} recompiled successfully")

            except Exception as e:
                err(f"Recompilation failed: {e}")
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
