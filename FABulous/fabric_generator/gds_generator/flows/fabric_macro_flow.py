"""Stitching flow to assemble FABulous tile macros into a complete fabric."""

from decimal import Decimal
from pathlib import Path

from librelane.config.variable import Instance, Macro, Orientation, Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow
from librelane.logging.logger import err, info
from librelane.state.state import State
from librelane.steps.step import Step

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.gds_generator.helper import get_pitch
from FABulous.fabric_generator.gds_generator.steps.IO_placement import (
    FABulousIOPlacement,
)
from FABulous.fabric_generator.gds_generator.steps.odb_connect_power import (
    FABulousPower,
)

# Add namedtuple for tile sizes


subs = {
    # Disable STA
    "OpenROAD.STAPrePNR*": None,
    "OpenROAD.STAMidPNR*": None,
    "OpenROAD.STAPostPNR*": None,
    # Custom PDN generation script
    "OpenROAD.GeneratePDN": FABulousPower,
    # Replace IO placement with FABulous fabric-level IO placement
    "OpenROAD.IOPlacement": None,
    "Odb.CustomIOPlacement": FABulousIOPlacement,
    # Script to manually place single IOs (for additional pins if needed)
    # "+OpenROAD.GlobalPlacementSkipIO": FABulousManualIOPlacement,
}

configs = Classic.config_vars + [
    Variable(
        "FABULOUS_FABRIC",
        Fabric,
        "The fabric configuration object.",
    ),
    Variable(
        "FABULOUS_MACROS_SETTINGS",
        dict[str, Macro],
        "A dictionary mapping tile names to their macro views (GDS, LEF, NL, SPEF).",
    ),
    Variable(
        "FABULOUS_TILE_SIZES",
        dict[str, tuple[Decimal, Decimal]],
        "A dictionary mapping tile names to their sizes (width, height).",
    ),
    Variable(
        "FABULOUS_TILE_SPACING",
        Decimal,
        "The spacing between tiles.",
    ),
    Variable(
        "FABULOUS_HALO_SPACING",
        tuple[Decimal, Decimal, Decimal, Decimal],
        "The spacing around the fabric. [left, bottom, right, top]",
        units="µm",
        default=(100, 100, 100, 100),
    ),
    Variable(
        "FABULOUS_SPEF_CORNERS",
        list[str],
        "The SPEF corners to use for the tile macros.",
        default=["nom"],
    ),
]


@Flow.factory.register()
class FABulousFabricMacroFlow(Classic):
    """Flow for stitching together individual tile macros into a complete fabric.

    This flow handles the placement and interconnection of pre-generated tile macros
    to create the final fabric layout, including power distribution and IO placement.
    """

    Substitutions = subs
    config_vars = configs

    def _compute_row_and_column_sizes(
        self, fabric: Fabric, tile_sizes: dict[str, tuple[Decimal, Decimal]]
    ) -> tuple[list[Decimal], list[Decimal]]:
        """Compute row heights and column widths in a single pass.

        Parameters
        ----------
        fabric : Fabric
            The fabric object with tile grid and dimensions.
        tile_sizes : dict[str, TileSize]
            Mapping from tile name to (width, height).

        Returns
        -------
        tuple[list[Decimal], list[Decimal]]
            Row heights (len = numberOfRows) and column widths (len = numberOfColumns).
        """
        rows = fabric.numberOfRows
        cols = fabric.numberOfColumns

        row_heights_map: dict[int, Decimal] = {}
        col_widths_map: dict[int, Decimal] = {}

        # Single pass through the grid; capture the first non-null in each row/col
        for y in range(rows):
            for x in range(cols):
                t = fabric.tile[y][x]
                if t is None:
                    continue
                if y not in row_heights_map:
                    row_heights_map[y] = tile_sizes[t.name][1]
                if x not in col_widths_map:
                    col_widths_map[x] = tile_sizes[t.name][0]

        # Build ordered lists and validate completeness
        row_heights: list[Decimal] = []
        for y in range(rows):
            h = row_heights_map.get(y)
            if h is None:
                err(f"Missing height for row {y} (no non-null tiles)")
                h = Decimal(0)
            row_heights.append(h)

        column_widths: list[Decimal] = []
        for x in range(cols):
            w = col_widths_map.get(x)
            if w is None:
                err(f"Missing width for column {x} (no non-null tiles)")
                w = Decimal(0)
            column_widths.append(w)

        return row_heights, column_widths

    def _compute_die_area(
        self,
        row_heights: list[Decimal],
        column_widths: list[Decimal],
        halo_spacing: tuple[Decimal, Decimal, Decimal, Decimal],
        tile_spacing: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Compute overall fabric width and height from per-row/column sizes.

        Returns
        -------
        tuple[Decimal, Decimal]
            (fabric_width, fabric_height)
        """
        cols = len(column_widths)
        rows = len(row_heights)

        (halo_left, halo_bottom, halo_right, halo_top) = halo_spacing

        fabric_width = (
            halo_left
            + halo_right
            + sum(column_widths)
            + (tile_spacing * (cols - 1) if cols > 0 else Decimal(0))
        )
        fabric_height = (
            halo_bottom
            + halo_top
            + sum(row_heights)
            + (tile_spacing * (rows - 1) if rows > 0 else Decimal(0))
        )

        return fabric_width, fabric_height

    def _validate_no_macro_overlaps(
        self,
        macros: dict[str, Macro],
        tile_sizes: dict[str, tuple[Decimal, Decimal]],
    ) -> bool:
        """Validate that no macros overlap in their placed positions.

        Parameters
        ----------
        macros : dict[str, Macro]
            Dictionary mapping tile names to their macro configurations with instances.
        tile_sizes : dict[str, tuple[Decimal, Decimal]]
            Dictionary mapping tile names to their sizes (width, height).

        Returns
        -------
        bool
            True if no overlaps detected, False otherwise.

        Raises
        ------
        ValueError
            If overlapping macros are detected.
        """
        # Collect all placed rectangles: (x1, y1, x2, y2, instance_name, tile_name)
        rectangles: list[tuple[Decimal, Decimal, Decimal, Decimal, str, str]] = []

        for tile_name, macro in macros.items():
            if tile_name not in tile_sizes:
                err(f"Tile {tile_name} not found in tile_sizes")
                continue

            width, height = tile_sizes[tile_name]

            for instance_name, instance in macro.instances.items():
                if instance.location is None:
                    err(f"Instance {instance_name} has no location set")
                    continue

                x1, y1 = instance.location
                x2 = x1 + width
                y2 = y1 + height
                rectangles.append((x1, y1, x2, y2, instance_name, tile_name))

        # Check for overlaps between all pairs of rectangles
        overlaps_found = False
        for i in range(len(rectangles)):
            x1_a, y1_a, x2_a, y2_a, name_a, tile_a = rectangles[i]

            for j in range(i + 1, len(rectangles)):
                x1_b, y1_b, x2_b, y2_b, name_b, tile_b = rectangles[j]

                # Check if rectangles overlap
                # Two rectangles overlap if they intersect in both X and Y dimensions
                x_overlap = not (x2_a <= x1_b or x2_b <= x1_a)
                y_overlap = not (y2_a <= y1_b or y2_b <= y1_a)

                if x_overlap and y_overlap:
                    overlaps_found = True
                    err(
                        f"Macro overlap detected between:\n"
                        f"  {name_a} ({tile_a}): ({x1_a}, {y1_a}) to ({x2_a}, {y2_a})\n"
                        f"  {name_b} ({tile_b}): ({x1_b}, {y1_b}) to ({x2_b}, {y2_b})"
                    )

        if overlaps_found:
            raise ValueError(
                "Macro placement validation failed: overlapping macros detected"
            )

        info("Macro overlap validation passed: no overlaps detected")
        return True

    def _validate_tile_sizes(
        self,
        tile_sizes: dict[str, tuple[Decimal, Decimal]],
        pitch_x: Decimal,
        pitch_y: Decimal,
    ) -> bool:
        """Validate that all tile sizes are aligned to the routing pitch grid.

        This checks that each tile's width is a multiple of min_pitch_x and
        each tile's height is a multiple of min_pitch_y.

        Parameters
        ----------
        tile_sizes : dict[str, tuple[Decimal, Decimal]]
            Dictionary mapping tile names to their sizes (width, height).
        min_pitch_x : Decimal
            Minimum pitch for horizontal (X) direction.
        min_pitch_y : Decimal
            Minimum pitch for vertical (Y) direction.

        Returns
        -------
        bool
            True if all tiles are aligned.

        Raises
        ------
        ValueError
            If any tile dimensions are not aligned to the pitch grid.
        """
        tile_size_errors: list[str] = []
        for tile_name, (width, height) in tile_sizes.items():
            width_dec = Decimal(str(width))
            height_dec = Decimal(str(height))

            width_remainder = str(round(width_dec / pitch_x, 2))[-2:]
            height_remainder = str(round(height_dec / pitch_y, 2))[-2:]

            if width_remainder != "00":
                tile_size_errors.append(
                    f"{tile_name}: width {width_dec} not aligned to {pitch_x} "
                    f"(remainder: {width_remainder})"
                )
            if height_remainder != "00":
                tile_size_errors.append(
                    f"{tile_name}: height {height_dec} not aligned to {pitch_y} "
                    f"(remainder: {height_remainder})"
                )

        if tile_size_errors:
            err("Tile sizes are not aligned to pitch grid:")
            for error in tile_size_errors:
                err(f"  {error}")
            raise ValueError(
                "Tile size validation failed: tiles must be regenerated with "
                "fixed round_die_area to ensure pitch alignment"
            )

        info("Tile size validation passed: all tiles aligned to pitch grid")
        return True

    def run(self, initial_state: State, **kwargs: dict) -> tuple[State, list[Step]]:
        """Execute the fabric stitching flow.

        Args
        ----
        initial_state : State
            Initial state for the flow
        **kwargs : dict
            Additional keyword arguments

        Returns
        -------
        tuple[State, list[Step]]
            Tuple of final state and list of executed steps
        """
        fabric: Fabric = self.config["FABULOUS_FABRIC"]

        # Get macro configurations from config
        macros: dict[str, Macro] = self.config["FABULOUS_MACROS_SETTINGS"]
        tile_sizes: dict[str, tuple[Decimal, Decimal]] = self.config[
            "FABULOUS_TILE_SIZES"
        ]

        # Tile Placement
        tile_spacing: Decimal = self.config["FABULOUS_TILE_SPACING"]
        halo_spacing: tuple[Decimal, Decimal, Decimal, Decimal] = self.config[
            "FABULOUS_HALO_SPACING"
        ]

        # Get min_pitch_x/min_pitch_y from FP_TRACKS_INFO via helper.get_min_pitch
        pitch_x, pitch_y = get_pitch(self.config)

        # Round up halo_left and halo_bottom to ensure placement origins are aligned
        def round_up_to_pitch(val: Decimal, pitch: Decimal) -> Decimal:
            if pitch == 0:
                return val
            remainder = val % pitch
            increment = Decimal(1) if remainder > 0 else Decimal(0)
            return (val // pitch + increment) * pitch

        halo_left, halo_bottom, halo_right, halo_top = halo_spacing
        halo_left = round_up_to_pitch(halo_left, pitch_x)
        halo_bottom = round_up_to_pitch(halo_bottom, pitch_y)

        info(
            f"Rounded placement origin halo: left={halo_left}, bottom={halo_bottom} "
            f"(min_pitch_x={pitch_x}, min_pitch_y={pitch_y})"
        )

        # Validate that all tile sizes are pitch-aligned
        info("Validating tile sizes are aligned to pitch grid...")
        self._validate_tile_sizes(tile_sizes, pitch_x, pitch_y)

        # Use rounded left/bottom and original right/top for initial calculation
        halo_spacing = (halo_left, halo_bottom, halo_right, halo_top)

        # Compute per-row and per-column sizes once, then derive DIE_AREA
        row_heights, column_widths = self._compute_row_and_column_sizes(
            fabric, tile_sizes
        )
        info(f"row_heights: {row_heights}")
        if len(row_heights) != fabric.numberOfRows:
            err(f"Expected {fabric.numberOfRows} row heights, got {len(row_heights)}")

        info(f"column_widths: {column_widths}")
        if len(column_widths) != fabric.numberOfColumns:
            err(
                f"Expected {fabric.numberOfColumns} column widths, got "
                f"{len(column_widths)}"
            )

        # Calculate fabric dimensions with rounded left/bottom halo
        fabric_width, fabric_height = self._compute_die_area(
            row_heights,
            column_widths,
            halo_spacing,
            tile_spacing,
        )
        info(f"Computed FABRIC_WIDTH (before rounding): {fabric_width}")
        info(f"Computed FABRIC_HEIGHT (before rounding): {fabric_height}")

        # Round the total fabric dimensions UP to the next pitch multiple
        fabric_width_rounded = round_up_to_pitch(fabric_width, pitch_x)
        fabric_height_rounded = round_up_to_pitch(fabric_height, pitch_y)

        # Calculate the adjustment needed and distribute it to the halo
        # Add the extra space to the right and top halo (keeps origin at 0,0)
        width_adjustment = fabric_width_rounded - fabric_width
        height_adjustment = fabric_height_rounded - fabric_height

        halo_right = halo_right + width_adjustment
        halo_top = halo_top + height_adjustment
        halo_spacing = (halo_left, halo_bottom, halo_right, halo_top)

        info(
            f"Adjusted halo_spacing to: {halo_spacing} "
            f"(width adj: {width_adjustment}, height adj: {height_adjustment})"
        )
        info(f"Final FABRIC_WIDTH: {fabric_width_rounded}")
        info(f"Final FABRIC_HEIGHT: {fabric_height_rounded}")

        self.config = self.config.copy(
            DIE_AREA=[0, 0, fabric_width_rounded, fabric_height_rounded]
        )

        # Place macros
        cur_y = 0
        for y, row in enumerate(reversed(fabric.tile)):
            cur_x = 0
            flipped_y = fabric.numberOfRows - 1 - y

            for x, tile in enumerate(row):
                tile_name = tile.name if tile is not None else None
                prefix = f"Tile_X{x}Y{flipped_y}_"

                for supertile_name, supertile in fabric.superTileDic.items():
                    subtiles = [tile.name for tile in supertile.tiles]

                    # Get the anchor of the supertile (bottom left)
                    anchor = supertile.tileMap[-1][0]

                    if tile_name in subtiles:
                        if tile_name == anchor.name:
                            tile_name = supertile_name

                            # While the physical anchor is at the bottom left,
                            # the anchor in FABulous is at the top left
                            prefix = (
                                f"Tile_X{x}Y{flipped_y - (len(supertile.tileMap) - 1)}_"
                            )
                        else:
                            tile_name = None

                if tile_name is None:
                    info(f"Skipping {tile_name}")
                else:
                    if tile_name not in macros:
                        err(f"Could not find {tile_name} in macros")

                    macros[tile_name].instances[f"{prefix}{tile_name}"] = Instance(
                        location=(
                            halo_left + cur_x,
                            halo_bottom + cur_y,
                        ),
                        orientation=Orientation.N,
                    )

                # Add column width only (spacing is included in DIE_AREA calculation)
                cur_x += column_widths[x]

            # Add row height only (spacing is included in DIE_AREA calculation)
            cur_y += row_heights[flipped_y]

        # Validate that no macros overlap before proceeding
        info("Validating macro placements for overlaps...")
        self._validate_no_macro_overlaps(macros, tile_sizes)

        # Set DIE_AREA and FP_SIZING
        self.config = self.config.copy(FP_SIZING="absolute")

        info(f"Setting DIE_AREA to {self.config['DIE_AREA']}")
        info(f"Setting FP_SIZING to {self.config['FP_SIZING']}")
        info(f"Macros: {macros}")

        self.config = self.config.copy(MACROS=macros)

        info(f"Setting MACROS to {self.config['MACROS']}")

        (final_state, steps) = super().run(initial_state, **kwargs)

        final_views_path = (Path() / "macro" / self.config["PDK"]).resolve()
        info(f"Saving final views for FABulous to {final_views_path}")
        final_state.save_snapshot(final_views_path)

        info("Copying FABulous related files.")

        return (final_state, steps)
