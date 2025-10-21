"""Full automatic fabric flow with ILP-based tile optimization.

This flow uses Integer Linear Programming to optimize tile dimensions:
1. Compiles all tiles in parallel to find minimum dimensions
2. Formulates ILP problem to minimize total fabric area
3. Solves for optimal tile dimensions with row/column constraints
4. Recompiles tiles with optimal dimensions in parallel
5. Stitches all tiles into final fabric
"""

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from librelane.config.flow import flow_common_variables
from librelane.config.variable import Macro, Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow
from librelane.logging.logger import err, info, warn
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.openroad import Floorplan
from librelane.steps.step import Step
from pulp import (
    PULP_CBC_CMD,
    LpMinimize,
    LpProblem,
    LpStatus,
    LpVariable,
    lpSum,
)

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from FABulous.fabric_generator.gds_generator.steps.fabric_macro_gen import (
    FabricMacroGen,
)
from FABulous.fabric_generator.gds_generator.steps.tile_macro_gen import TileMarcoGen
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode
from FABulous.FABulous_settings import get_context

if TYPE_CHECKING:
    from concurrent.futures import Future

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


@Flow.factory.register()
class FABulousFabricMacroFullFlow(Flow):
    """Full automatic fabric flow with progressive tile compilation.

    This flow automatically:
    1. Extracts PDK site dimensions
    2. Finds most frequent tile and compiles it first
    3. Progressively compiles all tiles with row/column constraints
    4. Relaxes constraints when tiles fail to compile
    5. Stitches all tiles into final fabric
    """

    Steps = [TileMarcoGen, FabricMacroGen]

    config_vars = configs

    def _get_unique_tile_and_supertile_types(
        self, fabric: Fabric
    ) -> list[Tile | SuperTile]:
        """Get list of unique tile and SuperTile types used in the fabric.

        Parameters
        ----------
        fabric : Fabric
            Fabric object

        Returns
        -------
        list[Tile | SuperTile]
            Combined list of regular tiles and SuperTiles from fabric dictionaries
        """
        result: list[Tile | SuperTile] = []

        # Add all regular tiles from tileDic
        result.extend([i for i in fabric.tileDic.values() if not i.partOfSuperTile])

        # Add all SuperTiles from superTileDic
        result.extend(fabric.superTileDic.values())

        return result

    def _compile_tile(
        self,
        tile: Tile | SuperTile,
        tile_dir: Path,
        initial_state: State,
        opt_mode: OptMode = OptMode.BALANCED,
        die_area: tuple[int, int, int, int] | None = None,
        opt_relax: bool = False,
    ) -> tuple[State, Step]:
        """Compile a single tile with TileMarcoGen.

        Parameters
        ----------
        tile : Tile | SuperTile
            Tile to compile
        tile_dir : Path
            Path to tile directory
        initial_state : State
            Initial state for compilation
        opt_mode : OptMode
            Optimization mode to use. If None, defaults to BALANCED
        die_area : tuple[int, int, int, int] | None
            Die area constraint (llx, lly, urx, ury).
            If None, uses tile's gds_config.yaml
        opt_relax : bool
            If True, optimization increases dimensions (relaxation mode).
            If False, optimization reduces dimensions (minimization mode).

        Returns
        -------
        tuple[State, Step]
            (output_state, step_instance)
        """
        fabric: Fabric = self.config["FABULOUS_FABRIC"]

        # Generate IO pin configuration
        out_file = tile_dir / "io_pin_order.yaml"
        generate_IO_pin_order_config(fabric, tile, out_file)

        # Build file list for tile compilation
        file_list = [str(f) for f in tile_dir.glob("**/*.v") if "macro" not in f.parts]

        # Add models_pack from context if available
        if models_pack := get_context().models_pack:
            file_list.append(str(models_pack.resolve()))

        # Load base config from tile's gds_config.yaml if it exists
        tile_config_overrides = {}
        gds_config_file = tile_dir / "gds_config.yaml"
        if gds_config_file.exists():
            tile_config_overrides.update(
                yaml.safe_load(gds_config_file.read_text(encoding="utf-8"))
            )

        # Set die area constraint if provided
        if die_area is not None:
            tile_config_overrides["DIE_AREA"] = list(die_area)

        # Determine logical dimensions based on tile type
        if isinstance(tile, SuperTile):
            logical_width = tile.maxWidth()
            logical_height = tile.maxHeight()
        else:
            logical_width = 1
            logical_height = 1

        # Create tile-specific configuration
        tile_config = self.config.copy(
            DESIGN_NAME=tile.name,
            IO_PIN_ORDER_CFG=out_file,
            FABULOUS_TILE_DIR=str(tile_dir),
            VERILOG_FILES=file_list,
            FABULOUS_TILE_LOGICAL_WIDTH=logical_width,
            FABULOUS_TILE_LOGICAL_HEIGHT=logical_height,
            TILE_OPTIMISATION=True,  # Enable optimization
            FABULOUS_OPT_MODE=opt_mode,  # Set optimization mode
            FABULOUS_OPT_RELAX=opt_relax,  # Set relaxation mode
            **tile_config_overrides,
        )

        # Create and run step
        tile_step = TileMarcoGen(
            tile_config,
            id=f"TileMarcoGen_{tile.name}",
            state_in=initial_state,
            _no_filter_conf=True,
        )
        state_out = self.start_step(tile_step)

        return state_out, tile_step

    def _extract_tile_dimensions_from_state(self, state: State) -> tuple[int, int]:
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
            llx, lly, urx, ury = die_area_metric
            return int(urx - llx), int(ury - lly)

        raise ValueError("Could not extract tile dimensions from state")

    def _compilation_successful(self, state: State) -> bool:
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
            "antenna__violating__nets",
            "antenna__violating__pins",
        ]

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

    def _solve_ilp_optimization(
        self,
        num_rows: int,
        num_cols: int,
        row_to_types: dict[int, set[str]],
        col_to_types: dict[int, set[str]],
        type_to_positions: dict[str, list[tuple[int, int]]],
        min_tile_widths: dict[str, int],
        min_tile_heights: dict[str, int],
        fabric: Fabric,
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Solve ILP problem to find optimal tile dimensions.

        The ILP formulation minimizes total fabric area subject to:
        - All tiles in the same row have the same height
        - All tiles in the same column have the same width
        - Each tile's dimensions >= its minimum dimensions
        - SuperTiles match surrounding tile dimensions

        Parameters
        ----------
        num_rows : int
            Number of rows in fabric
        num_cols : int
            Number of columns in fabric
        row_to_types : dict[int, set[str]]
            Map of row index to tile types in that row
        col_to_types : dict[int, set[str]]
            Map of column index to tile types in that column
        type_to_positions : dict[str, list[tuple[int, int]]]
            Map of tile type to positions it appears at
        min_tile_widths : dict[str, int]
            Minimum width for each tile type (from compilation)
        min_tile_heights : dict[str, int]
            Minimum height for each tile type (from compilation)
        fabric : Fabric
            Fabric object

        Returns
        -------
        tuple[dict[str, int], dict[str, int]]
            (optimal_widths, optimal_heights) for each tile type

        Raises
        ------
        RuntimeError
            If ILP problem formulation fails
        """
        info("Formulating ILP problem...")

        # Create the problem
        prob = LpProblem("Fabric_Tile_Optimization", LpMinimize)

        # Decision variables: row heights and column widths
        row_heights = {}
        for r in range(num_rows):
            if r in row_to_types and row_to_types[r]:
                # Get minimum height needed for this row
                min_height = max(min_tile_heights.get(t, 0) for t in row_to_types[r])
                row_heights[r] = LpVariable(
                    f"row_height_{r}", lowBound=min_height, cat="Integer"
                )

        col_widths = {}
        for c in range(num_cols):
            if c in col_to_types and col_to_types[c]:
                # Get minimum width needed for this column
                min_width = max(min_tile_widths.get(t, 0) for t in col_to_types[c])
                col_widths[c] = LpVariable(
                    f"col_width_{c}", lowBound=min_width, cat="Integer"
                )

        # This is a linear objective that correlates with area minimization
        # Direct area minimization (width * height) would require bilinear programming
        total_width = lpSum([col_widths[c] for c in col_widths])
        total_height = lpSum([row_heights[r] for r in row_heights])
        prob += total_width + total_height, "Minimize_Fabric_Perimeter"

        # Constraints: Each tile type must fit in its row/column dimensions
        for tile_type, positions in type_to_positions.items():
            min_w = min_tile_widths[tile_type]
            min_h = min_tile_heights[tile_type]

            # Check if this is a SuperTile
            is_supertile = tile_type in fabric.superTileDic
            if is_supertile:
                supertile = fabric.superTileDic[tile_type]
                logical_width = supertile.maxWidth()
                logical_height = supertile.maxHeight()
            else:
                logical_width = 1
                logical_height = 1

            # For each position this tile appears at
            for row, col in positions:
                if logical_width == 1 and logical_height == 1:
                    # Regular tile: single cell constraint
                    if row in row_heights:
                        prob += (
                            row_heights[row] >= min_h,
                            f"tile_{tile_type}_at_{row}_{col}_height",
                        )
                    if col in col_widths:
                        prob += (
                            col_widths[col] >= min_w,
                            f"tile_{tile_type}_at_{row}_{col}_width",
                        )
                else:
                    # SuperTile: spanning constraint
                    # SuperTile width = sum of column widths it spans
                    # SuperTile height = sum of row heights it spans

                    # Width constraint: sum of spanned columns
                    spanned_cols = [
                        col_widths[c]
                        for c in range(col, col + logical_width)
                        if c in col_widths
                    ]
                    if spanned_cols:
                        prob += (
                            lpSum(spanned_cols) >= min_w,
                            f"supertile_{tile_type}_at_{row}_{col}_width",
                        )

                    # Height constraint: sum of spanned rows
                    spanned_rows = [
                        row_heights[r]
                        for r in range(row, row + logical_height)
                        if r in row_heights
                    ]
                    if spanned_rows:
                        prob += (
                            lpSum(spanned_rows) >= min_h,
                            f"supertile_{tile_type}_at_{row}_{col}_height",
                        )

        # Solve the problem
        time_limit = self.config.get("FABULOUS_ILP_SOLVER_TIME_LIMIT", 300)
        info(f"Solving ILP with time limit of {time_limit}s...")

        solver = PULP_CBC_CMD(msg=1, timeLimit=time_limit)
        prob.solve(solver)

        status = LpStatus[prob.status]
        info(f"ILP solver status: {status}")

        if status not in ["Optimal", "Feasible"]:
            raise RuntimeError(f"ILP solver failed with status: {status}")

        # Warn if solution is not optimal
        if status == "Feasible":
            warn(
                "ILP solver returned a feasible but potentially suboptimal solution. "
                "Consider increasing FABULOUS_ILP_SOLVER_TIME_LIMIT for better results."
            )

        # Extract optimal dimensions for each tile type
        optimal_widths: dict[str, int] = {}
        optimal_heights: dict[str, int] = {}

        for tile_type, positions in type_to_positions.items():
            # Get the row/col this tile appears in (use first position)
            row, col = positions[0]

            # Check if this is a SuperTile
            is_supertile = tile_type in fabric.superTileDic
            if is_supertile:
                supertile = fabric.superTileDic[tile_type]
                logical_width = supertile.maxWidth()
                logical_height = supertile.maxHeight()
            else:
                logical_width = 1
                logical_height = 1

            if logical_width == 1 and logical_height == 1:
                # Regular tile: single cell dimension
                if col in col_widths:
                    optimal_widths[tile_type] = int(col_widths[col].varValue)
                else:
                    optimal_widths[tile_type] = min_tile_widths[tile_type]

                if row in row_heights:
                    optimal_heights[tile_type] = int(row_heights[row].varValue)
                else:
                    optimal_heights[tile_type] = min_tile_heights[tile_type]
            else:
                # SuperTile: sum of spanned cells
                width = sum(
                    int(col_widths[c].varValue)
                    for c in range(col, col + logical_width)
                    if c in col_widths
                )
                height = sum(
                    int(row_heights[r].varValue)
                    for r in range(row, row + logical_height)
                    if r in row_heights
                )

                optimal_widths[tile_type] = (
                    width if width > 0 else min_tile_widths[tile_type]
                )
                optimal_heights[tile_type] = (
                    height if height > 0 else min_tile_heights[tile_type]
                )

        # Report results
        total_area = sum(
            optimal_widths[t] * optimal_heights[t] * len(positions)
            for t, positions in type_to_positions.items()
        )
        info("ILP optimization complete:")
        info(f"  Total fabric area: {total_area}")
        row_heights_list = [row_heights[r].varValue for r in sorted(row_heights.keys())]
        col_widths_list = [col_widths[c].varValue for c in sorted(col_widths.keys())]
        info(f"  Optimal row heights: {row_heights_list}")
        info(f"  Optimal col widths: {col_widths_list}")

        return optimal_widths, optimal_heights

    def run(self, initial_state: State, **_kwargs: dict) -> tuple[State, list[Step]]:
        """Execute the ILP-based fabric flow.

        Flow steps:
        1. Compile all tiles in parallel to find minimum dimensions
        2. Formulate ILP problem to minimize total fabric area
        3. Solve for optimal tile dimensions with row/column constraints
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
            If tile compilation or ILP optimization fails
        """
        step_list: list[Step] = []
        fabric: Fabric = self.config["FABULOUS_FABRIC"]
        proj_dir = Path(self.config["FABULOUS_PROJ_DIR"])
        self.progress_bar.set_max_stage_count(4)

        self._validate_project_dir(proj_dir, fabric)

        # Step 1: Parallel compilation to find minimum dimensions
        info("\n=== Step 1: Finding minimum tile dimensions ===")
        self.progress_bar.start_stage("Finding Minimum Dimensions")

        unique_tile_types = self._get_unique_tile_and_supertile_types(fabric)
        total_runs = len(unique_tile_types) * 3  # 3 optimization modes per tile
        info(
            f"Compiling {len(unique_tile_types)} unique tile types "
            f"with 3 optimization modes each ({total_runs} total runs)..."
        )

        # Optimization modes to try for each tile
        opt_modes = [OptMode.AGGRESSIVE, OptMode.FIX_HEIGHT, OptMode.FIX_WIDTH]

        # Create compilation steps for all tiles with all optimization modes
        min_dim_steps: list[Step] = []
        for tile_type in unique_tile_types:
            tile_dir = proj_dir / "Tile" / tile_type.name

            # Generate IO pin configuration
            out_file = tile_dir / "io_pin_order.yaml"
            generate_IO_pin_order_config(fabric, tile_type, out_file)

            # Build file list
            file_list = [
                str(f) for f in tile_dir.glob("**/*.v") if "macro" not in f.parts
            ]
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

            # Determine logical dimensions
            if isinstance(tile_type, SuperTile):
                logical_width = tile_type.maxWidth()
                logical_height = tile_type.maxHeight()
            else:
                logical_width = 1
                logical_height = 1

            # Create one compilation step for each optimization mode
            for opt_mode in opt_modes:
                step_id = f"TileMarcoGen_MinDim_{tile_type.name}_{opt_mode.value}"
                tile_config = self.config.copy(
                    DESIGN_NAME=tile_type.name,
                    FABULOUS_IO_PIN_ORDER_CFG=out_file,
                    FABULOUS_TILE_DIR=str(tile_dir),
                    VERILOG_FILES=file_list,
                    FABULOUS_TILE_LOGICAL_WIDTH=logical_width,
                    FABULOUS_TILE_LOGICAL_HEIGHT=logical_height,
                    TILE_OPTIMISATION=True,
                    FABULOUS_OPT_MODE=opt_mode,
                    FABULOUS_OPT_RELAX=False,
                    IGNORE_ANTENNA_VIOLATIONS=True,
                    RUN_DIR_OVERWRITE=str(
                        Path(self.design_dir)
                        / "runs"
                        / f"TileMarcoGen_MinDim_{tile_type.name}_{opt_mode.value}"
                    ),
                    YOSYS_LOG_LEVEL="ERROR",
                    **tile_config_overrides,
                )
                # Create step with unique ID for each mode
                tile_step = TileMarcoGen(
                    tile_config,
                    id=step_id,
                    state_in=initial_state,
                    _no_filter_conf=True,
                )
                min_dim_steps.append(tile_step)
        # Start all compilation steps asynchronously
        async_handles: list[tuple[Future[State], Step]] = []
        for step in min_dim_steps:
            # handle = self.start_step(step)
            # handle = self.start_step_async(step)
            handle = None
            async_handles.append((handle, step))
        # Wait for all compilations and collect results
        # Store multiple dimension options per tile
        tile_dimension_options: dict[str, list[tuple[int, int, str]]] = {}

        for handle, step in async_handles:
            state = self.start_step(step)
            step_list.append(step)

            tile_name = step.config["DESIGN_NAME"]
            opt_mode = step.config["FABULOUS_OPT_MODE"]

            if not self._compilation_successful(state):
                warn(
                    f"Tile {tile_name} with {opt_mode} mode failed compilation, "
                    "skipping"
                )
                continue

            width, height = self._extract_tile_dimensions_from_state(state)

            # Store this dimension option
            if tile_name not in tile_dimension_options:
                tile_dimension_options[tile_name] = []
            tile_dimension_options[tile_name].append((width, height, opt_mode))

            info(f"  {tile_name} ({opt_mode}): width={width}, height={height} DBU")

        # Collect minimum dimensions for each tile from optimization results
        min_tile_widths: dict[str, int] = {}
        min_tile_heights: dict[str, int] = {}
        min_tile_areas: dict[str, int] = {}

        for tile_name, options in tile_dimension_options.items():
            if not options:
                raise RuntimeError(f"Tile {tile_name} failed all optimization modes")

            # Find the result with minimum area (most aggressive optimization)
            min_area_result = min(options, key=lambda x: x[0] * x[1])
            min_area_width, min_area_height, min_area_mode = min_area_result
            min_area = min_area_width * min_area_height

            # Find absolute minimum width across all modes
            min_width_result = min(options, key=lambda x: x[0])
            abs_min_width = min_width_result[0]

            # Find absolute minimum height across all modes
            min_height_result = min(options, key=lambda x: x[1])
            abs_min_height = min_height_result[1]

            # Use the minimum area result as the baseline dimensions
            # The ILP will only increase from these dimensions, never decrease
            min_tile_widths[tile_name] = min_area_width
            min_tile_heights[tile_name] = min_area_height
            min_tile_areas[tile_name] = min_area

            # Log the results with analysis
            if abs_min_width < min_area_width or abs_min_height < min_area_height:
                info(
                    f"  {tile_name}: base={min_area_width}×{min_area_height} "
                    f"(area={min_area}, from {min_area_mode}), "
                    f"abs_min_w={abs_min_width}, abs_min_h={abs_min_height}"
                )
            else:
                info(
                    f"  {tile_name}: min={min_area_width}×{min_area_height} "
                    f"(area={min_area}, from {min_area_mode})"
                )

        self.progress_bar.end_stage()
        info(
            f"✓ Found minimum dimensions for {len(unique_tile_types)} tile types "
            f"({total_runs} optimization runs completed)"
        )

        # Step 2: Build fabric structure maps
        info("\n=== Step 2: Analyzing fabric structure ===")

        # Map: row_index -> set of tile type names in that row
        row_to_types: dict[int, set[str]] = {}
        # Map: col_index -> set of tile type names in that column
        col_to_types: dict[int, set[str]] = {}
        # Map: tile type name -> list of (row, col) positions
        type_to_positions: dict[str, list[tuple[int, int]]] = {}

        num_rows = len(fabric.tile)
        num_cols = len(fabric.tile[0]) if num_rows > 0 else 0

        for r in range(num_rows):
            for c in range(num_cols):
                tile = fabric.tile[r][c]
                if tile is None:
                    continue

                tname = tile.name
                row_to_types.setdefault(r, set()).add(tname)
                col_to_types.setdefault(c, set()).add(tname)
                type_to_positions.setdefault(tname, []).append((r, c))

        info(f"  Fabric grid: {num_rows} rows x {num_cols} columns")
        info(f"  Unique tile types: {len(type_to_positions)}")

        # Step 3: Formulate and solve ILP problem
        info("\n=== Step 3: Solving ILP optimization ===")
        optimal_widths, optimal_heights = self._solve_ilp_optimization(
            num_rows,
            num_cols,
            row_to_types,
            col_to_types,
            type_to_positions,
            min_tile_widths,
            min_tile_heights,
            fabric,
        )

        info(f"Number of rows: {num_rows}, Number of columns: {num_cols}")
        info(f"Row to types mapping:{row_to_types}")
        info(f"Column to types mapping:{col_to_types}")
        info(f"Tile type to positions mapping:{type_to_positions}")
        info(f"Minimum tile widths: {min_tile_widths}")
        info(f"Minimum tile heights: {min_tile_heights}")
        info(f"Optimal tile width: {optimal_widths}")
        info(f"Optimal tile height: {optimal_heights}")

        # Step 4: Recompile tiles with optimal dimensions
        info("\n=== Step 4: Recompiling tiles with optimal dimensions ===")
        self.progress_bar.start_stage("Recompiling with Optimal Dimensions")

        final_steps: list[Step] = []
        final_async_handles = []

        for tile_type in unique_tile_types:
            tile_dir = proj_dir / "Tile" / tile_type.name
            tile_name = tile_type.name

            # Get optimal dimensions for this tile
            optimal_width = optimal_widths[tile_name]
            optimal_height = optimal_heights[tile_name]

            info(f"  {tile_name}: optimal={optimal_width}x{optimal_height} DBU")

            # Generate IO pin configuration (reuse from Step 1)
            out_file = tile_dir / "io_pin_order.yaml"

            # Build file list (reuse from Step 1)
            file_list = [
                str(f) for f in tile_dir.glob("**/*.v") if "macro" not in f.parts
            ]
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

            # Override DIE_AREA with optimal dimensions
            tile_config_overrides["DIE_AREA"] = [0, 0, optimal_width, optimal_height]

            # Determine logical dimensions
            if isinstance(tile_type, SuperTile):
                logical_width = tile_type.maxWidth()
                logical_height = tile_type.maxHeight()
            else:
                logical_width = 1
                logical_height = 1

            # Create tile config for final compilation
            tile_config = self.config.copy(
                DESIGN_NAME=tile_name,
                IO_PIN_ORDER_CFG=out_file,
                FABULOUS_TILE_DIR=str(tile_dir),
                VERILOG_FILES=file_list,
                FABULOUS_TILE_LOGICAL_WIDTH=logical_width,
                FABULOUS_TILE_LOGICAL_HEIGHT=logical_height,
                TILE_OPTIMISATION=False,  # Use exact dimensions, no optimization
                **tile_config_overrides,
            )

            # Create step
            tile_step = TileMarcoGen(
                tile_config,
                id=f"TileMarcoGen_Final_{tile_name}",
                state_in=initial_state,
                _no_filter_conf=True,
            )
            final_steps.append(tile_step)

        # Start all final compilation steps asynchronously
        for step in final_steps:
            handle = self.start_step_async(step)
            final_async_handles.append((handle, step))

        # Wait for all final compilations and collect results
        tile_type_states: dict[str, State] = {}

        for handle, step in final_async_handles:
            state = self.await_step(handle)
            step_list.append(step)

            tile_name = step.config["DESIGN_NAME"]
            if not self._compilation_successful(state):
                raise RuntimeError(
                    f"Tile {tile_name} failed final compilation with optimal dimensions"
                )

            tile_type_states[tile_name] = state

        self.progress_bar.end_stage()
        info(f"✓ All {len(unique_tile_types)} tiles recompiled with optimal dimensions")

        # Step 5: Collect tile macros for fabric stitching
        info("\n=== Step 5: Preparing fabric stitching ===")

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

        # Step 6: Run fabric stitching
        info("\n=== Step 6: Fabric stitching ===")
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
        step_list.append(fabric_step)

        self.progress_bar.end_stage()

        info("\n✓ Fabric flow completed successfully!")
        info(f"  Total tiles: {len(unique_tile_types)}")
        info("  Fabric area optimized using ILP")

        return final_state, step_list
