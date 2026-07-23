"""GDS macro-hardening flow commands for the FABulous REPL.

Harden tiles and the fabric into GDS macros via the LibreLane flow.
"""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, cast

import yaml
from cmd2 import with_annotated, with_category
from cmd2.annotated import Argument, Option
from loguru import logger

from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabulous_repl.command_set_base import (
    CMD_FABRIC_FLOW,
    ReplCommandSet,
)
from fabulous.fabulous_repl.helper import (
    CommandPipeline,
)
from fabulous.fabulous_settings import get_context, is_pdk_config_set


def _require_directional_mode(
    opt_mode: OptMode, implied: OptMode, flag: str
) -> OptMode:
    """Return the directional mode a `--fix-*` flag implies, or raise on conflict.

    Parameters
    ----------
    opt_mode : OptMode
        The mode requested via `--optimise` (`NO_OPT` when unset).
    implied : OptMode
        The directional mode the fix flag requires.
    flag : str
        The flag name, used for the error message.

    Returns
    -------
    OptMode
        `implied` when compatible with `opt_mode`.

    Raises
    ------
    ValueError
        If `opt_mode` is an explicit mode other than `implied`.
    """
    if opt_mode in (OptMode.NO_OPT, implied):
        return implied
    raise ValueError(
        f"{flag} is only valid with --optimise {implied.value}, not {opt_mode.value}."
    )


def _resolve_directional_fix(
    opt_mode: OptMode,
    fix_width: Decimal | None,
    fix_height: Decimal | None,
) -> tuple[OptMode, list[int | Decimal] | None]:
    """Resolve `--optimise` plus `--fix-*` into a mode and DIE_AREA override.

    A fixed axis pins one side and minimises the other: `--fix-width` pairs with
    `find_min_height` and `--fix-height` with `find_min_width`. The minimised
    axis starts square; `TileOptimisation` re-seeds it from the synthesised cell
    area, so only the fixed value needs to be supplied.

    Parameters
    ----------
    opt_mode : OptMode
        The mode requested via `--optimise`.
    fix_width : Decimal | None
        Locked tile width, if `--fix-width` was given.
    fix_height : Decimal | None
        Locked tile height, if `--fix-height` was given.

    Returns
    -------
    tuple[OptMode, list[int | Decimal] | None]
        The resolved optimisation mode and the DIE_AREA override, or `None` when
        neither fix flag is set.

    Raises
    ------
    ValueError
        If both fix flags are given, or a fix flag contradicts `--optimise`.
    """
    if fix_width is not None and fix_height is not None:
        raise ValueError("Specify only one of --fix-width / --fix-height.")
    if fix_width is not None:
        mode = _require_directional_mode(
            opt_mode, OptMode.FIND_MIN_HEIGHT, "--fix-width"
        )
        return mode, [0, 0, fix_width, fix_width]
    if fix_height is not None:
        mode = _require_directional_mode(
            opt_mode, OptMode.FIND_MIN_WIDTH, "--fix-height"
        )
        return mode, [0, 0, fix_height, fix_height]
    return opt_mode, None


class MacroFlowCommandSet(ReplCommandSet):
    """Harden tiles and the fabric into GDS macros via the LibreLane flow."""

    @with_category(CMD_FABRIC_FLOW)
    @with_annotated
    def do_gen_tile_macro(
        self,
        tile: Annotated[
            str,
            Argument(
                help_text="A tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
        optimise: Annotated[
            OptMode,
            Option(
                "--optimise",
                "-opt",
                nargs="?",
                const=OptMode.BALANCE,
                help_text=(
                    "Optimize the GDS layout. Available modes: "
                    + ", ".join(m.value for m in OptMode)
                ),
            ),
        ] = OptMode.NO_OPT,
        override: Annotated[
            Path | None,
            Option(
                "--override", help_text="Override config with a custom YAML config file"
            ),
        ] = None,
        fix_width: Annotated[
            Decimal | None,
            Option(
                "--fix-width",
                metavar="WIDTH",
                help_text=(
                    "Lock the tile width to WIDTH and minimise the height "
                    "(implies --optimise find_min_height)."
                ),
            ),
        ] = None,
        fix_height: Annotated[
            Decimal | None,
            Option(
                "--fix-height",
                metavar="HEIGHT",
                help_text=(
                    "Lock the tile height to HEIGHT and minimise the width "
                    "(implies --optimise find_min_width)."
                ),
            ),
        ] = None,
        io_pin_config: Annotated[
            Path | None,
            Option(
                "--io-pin-config",
                help_text="Path to a custom IO pin config YAML file",
            ),
        ] = None,
    ) -> None:
        """Generate GDSII files for a specific tile.

        This command generates GDSII files for the specified tile, allowing for the
        physical representation of the tile to be created.
        """
        repl = self._cmd
        if not tile:
            logger.error("Tile name must be specified")
            return

        if not is_pdk_config_set():
            logger.error(
                "PDK configuration is not set. Please set the PDK configuration to "
                "generate tile macros."
            )
            return

        try:
            opt_mode, die_area_override = _resolve_directional_fix(
                optimise, fix_width, fix_height
            )
        except ValueError as exc:
            logger.error(str(exc))
            return

        custom_overrides: dict = {}
        if override:
            custom_overrides.update(yaml.safe_load(override.read_text()) or {})
        if die_area_override is not None:
            custom_overrides["FABULOUS_OPT_MODE"] = opt_mode
            custom_overrides["DIE_AREA"] = die_area_override

        tile_dir = repl.projectDir / "Tile" / tile
        pin_order_file = tile_dir / f"{tile}_io_pin_order.yaml"

        if not tile_dir.exists():
            logger.error(f"Tile directory {tile_dir} does not exist")
            return

        if not io_pin_config:
            if tile_obj := repl.fabulousAPI.getTile(tile):
                repl.fabulousAPI.gen_io_pin_order_config(tile_obj, pin_order_file)
            else:
                super_tile = repl.fabulousAPI.getSuperTile(tile)
                if super_tile is None:
                    logger.error(f"Tile {tile} not found in fabric definition")
                    return
                repl.fabulousAPI.gen_io_pin_order_config(super_tile, pin_order_file)
        else:
            pin_order_file = io_pin_config.resolve()

        repl.fabulousAPI.genTileMacro(
            tile_dir,
            pin_order_file,
            tile_dir / "macro",
            cast("str", get_context().pdk),
            cast("Path", get_context().pdk_root),
            optimisation=opt_mode,
            base_config_path=repl.projectDir / "Tile" / "include" / "gds_config.yaml",
            config_override_path=tile_dir / "gds_config.yaml",
            custom_config_overrides=custom_overrides or None,
        )

    @with_annotated
    @with_category(CMD_FABRIC_FLOW)
    def do_gen_all_tile_macros(
        self,
        parallel: Annotated[
            bool,
            Option("--parallel", "-p", help_text="Generate tile macros in parallel"),
        ] = False,
        optimise: Annotated[
            OptMode | None,
            Option(
                "--optimise",
                "-opt",
                nargs="?",
                const=OptMode.BALANCE,
                help_text=(
                    "Optimize the GDS layout of all tiles. Available modes: "
                    + ", ".join(m.value for m in OptMode)
                ),
            ),
        ] = None,
    ) -> None:
        """Generate GDSII files for all tiles in the fabric."""
        repl = self._cmd
        commands = CommandPipeline(self._cmd)
        for i in sorted(repl.all_tile):
            if optimise:
                commands.add_step(f"gen_tile_macro {i} --optimise {optimise.value}")
            else:
                commands.add_step(f"gen_tile_macro {i}")
        if not parallel:
            commands.execute()
        else:
            commands.execute_parallel()

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_fabric_macro(self, *_args: str) -> None:
        """Generate GDSII files for the entire fabric."""
        repl = self._cmd
        if not is_pdk_config_set():
            logger.error(
                "PDK configuration is not set. Please set the PDK configuration to "
                "generate fabric macros."
            )
            return

        tile_macro_root = repl.projectDir / "Tile"
        tile_macro_paths: dict[str, Path] = {}

        for tile_dir in tile_macro_root.iterdir():
            if not tile_dir.is_dir():
                continue
            macro_dir = tile_dir / "macro" / "final_views"
            if macro_dir.exists():
                tile_macro_paths[tile_dir.name] = macro_dir

        if not tile_macro_paths:
            logger.error(
                "No tile macro directories found. Generate tile GDS results first."
            )
            return

        (repl.projectDir / "gds").mkdir(exist_ok=True)
        (repl.projectDir / "Fabric" / "macro").mkdir(exist_ok=True)
        repl.fabulousAPI.fabric_stitching(
            tile_macro_paths,
            repl.projectDir
            / "Fabric"
            / f"{repl.fabulousAPI.fabric.name}.{repl.extension}",
            repl.projectDir / "Fabric" / "macro",
            cast("str", get_context().pdk),
            cast("Path", get_context().pdk_root),
            base_config_path=repl.projectDir / "Fabric" / "gds_config.yaml",
        )

    @with_category(CMD_FABRIC_FLOW)
    @with_annotated
    def do_run_FABulous_eFPGA_macro(
        self,
        tile_opt_info: Annotated[
            str | None,
            Option(
                "--tile-opt-info",
                help_text="Path to tile optimisation summary JSON to skip Step 1",
            ),
        ] = None,
        nlp_only: Annotated[
            bool,
            Option(
                "--nlp-only",
                help_text="Run exploration and NLP only, skip recompilation",
            ),
        ] = False,
        nlp_area_margin: Annotated[
            float,
            Option(
                "--nlp-area-margin",
                help_text="Area margin for NLP constraint (default: 0.05 = 5%%)",
            ),
        ] = 0.05,
    ) -> None:
        """Run the full FABulous eFPGA macro generation flow."""
        repl = self._cmd
        if not is_pdk_config_set():
            logger.error(
                "PDK configuration is not set. Please set the PDK configuration to "
                "run the full FABulous eFPGA macro generation flow."
            )
            return

        (repl.projectDir / "Fabric" / "macro").mkdir(exist_ok=True)
        tile_opt_config = Path(tile_opt_info) if tile_opt_info else None
        repl.fabulousAPI.full_fabric_automation(
            repl.projectDir,
            repl.projectDir / "Fabric" / "macro",
            cast("str", get_context().pdk),
            cast("Path", get_context().pdk_root),
            base_config_path=repl.projectDir / "Fabric" / "gds_config.yaml",
            tile_opt_config=tile_opt_config,
            nlp_only=nlp_only,
            nlp_area_margin=nlp_area_margin,
        )
