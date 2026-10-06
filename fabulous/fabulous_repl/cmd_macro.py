"""GDS macro-hardening flow commands for the FABulous REPL.

Harden tiles and the fabric into GDS macros via the LibreLane flow. Every step is
a subcommand of `gen_macro`. The pre-subcommand names stay registered as
deprecated forwarders that pass their raw argument tail on unchanged, so they
cannot drift from the new flag set.

`tile` and `all_tile` share their sizing flags through `TileHardeningOptions`
and the same `_harden_tile` body, so a flag added there reaches both parsers and
needs no per-command wiring. The flags belonging to only one of them
(`--io-pin-config`, `--parallel`) stay on that subcommand, where argparse
rejects them on the other.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated, cast

import yaml
from cmd2 import Statement, with_annotated
from cmd2.annotated import Argument, ArgumentBlock, Option
from loguru import logger

from fabulous.custom_exception import CommandError
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabulous_repl.command_set_base import (
    CMD_FABRIC_FLOW,
    ReplCommandSet,
)
from fabulous.fabulous_settings import get_context, is_pdk_config_set


def _require_directional_mode(
    opt_mode: OptMode, implied: OptMode, flag: str
) -> OptMode:
    """Return the directional mode a ``--fix-*`` flag implies, or raise on conflict.

    Parameters
    ----------
    opt_mode : OptMode
        The mode requested via ``--optimise`` (``NO_OPT`` when unset).
    implied : OptMode
        The directional mode the fix flag requires.
    flag : str
        The flag name, used for the error message.

    Returns
    -------
    OptMode
        ``implied`` when compatible with ``opt_mode``.

    Raises
    ------
    ValueError
        If ``opt_mode`` is an explicit mode other than ``implied``.
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
    """Resolve ``--optimise`` plus ``--fix-*`` into a mode and DIE_AREA override.

    A fixed axis pins one side and minimises the other: ``--fix-width`` pairs with
    ``find_min_height`` and ``--fix-height`` with ``find_min_width``. The minimised
    axis starts square; ``TileOptimisation`` re-seeds it from the synthesised cell
    area, so only the fixed value needs to be supplied.

    Parameters
    ----------
    opt_mode : OptMode
        The mode requested via ``--optimise``.
    fix_width : Decimal | None
        Locked tile width, if ``--fix-width`` was given.
    fix_height : Decimal | None
        Locked tile height, if ``--fix-height`` was given.

    Returns
    -------
    tuple[OptMode, list[int | Decimal] | None]
        The resolved optimisation mode and the DIE_AREA override, or ``None`` when
        neither fix flag is set.

    Raises
    ------
    ValueError
        If both fix flags are given, or a fix flag contradicts ``--optimise``.
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


@dataclass
class TileHardeningOptions(ArgumentBlock):
    """Sizing flags shared by `gen_macro tile` and `gen_macro all_tile`."""

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
    ] = OptMode.NO_OPT
    override: Annotated[
        Path | None,
        Option(
            "--override", help_text="Override config with a custom YAML config file"
        ),
    ] = None
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
    ] = None
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
    ] = None

    def resolve(self) -> tuple[OptMode, dict]:
        """Resolve the flags into an optimisation mode and LibreLane overrides.

        Called once per command invocation rather than once per tile, so a
        conflicting pair aborts the fan-out instead of failing every tile in it.

        Returns
        -------
        tuple[OptMode, dict]
            The optimisation mode, and the config overrides the `--override` file
            and the fix flags imply.

        Raises
        ------
        CommandError
            If the fix flags conflict with each other or with `--optimise`.
        """
        try:
            opt_mode, die_area_override = _resolve_directional_fix(
                self.optimise, self.fix_width, self.fix_height
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        custom_overrides: dict = {}
        if self.override:
            custom_overrides.update(yaml.safe_load(self.override.read_text()) or {})
        if die_area_override is not None:
            custom_overrides["FABULOUS_OPT_MODE"] = opt_mode
            custom_overrides["DIE_AREA"] = die_area_override
        return opt_mode, custom_overrides


class MacroFlowCommandSet(ReplCommandSet):
    """Harden tiles and the fabric into GDS macros via the LibreLane flow."""

    DEFAULT_CATEGORY = CMD_FABRIC_FLOW

    @with_annotated(base_command=True)
    def do_gen_macro(self, cmd2_subcommand_func: Callable[[], None]) -> None:
        """Harden tiles and the fabric into GDS macros.

        Run `gen_macro tile` to harden one tile or `gen_macro all_tile` for every
        tile in the fabric, `gen_macro stitch` to assemble the fabric from the
        hardened tiles, and `gen_macro full` for the automated eFPGA flow.
        """
        cmd2_subcommand_func()

    @with_annotated(subcommand_to="gen_macro", help="Harden a single tile")
    def gen_macro_tile(
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
        options: TileHardeningOptions,
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
        opt_mode, custom_overrides = options.resolve()
        if not is_pdk_config_set():
            logger.error(
                "PDK configuration is not set. Please set the PDK configuration to "
                "generate tile macros."
            )
            return

        self._harden_tile(tile, opt_mode, custom_overrides, io_pin_config=io_pin_config)

    def _harden_tile(
        self,
        tile: str,
        opt_mode: OptMode,
        custom_overrides: dict,
        *,
        io_pin_config: Path | None = None,
    ) -> None:
        """Run the LibreLane flow for one tile.

        Parameters
        ----------
        tile : str
            Name of the tile to harden.
        opt_mode : OptMode
            The optimisation mode resolved by `TileHardeningOptions.resolve`.
        custom_overrides : dict
            The LibreLane config overrides resolved alongside `opt_mode`.
        io_pin_config : Path | None
            Pin order file to use as-is. Defaults to None, which generates the
            tile's pin order from the fabric structure.
        """
        repl = self._cmd
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

    @with_annotated(subcommand_to="gen_macro", help="Harden every tile in the fabric")
    def gen_macro_all_tile(
        self,
        options: TileHardeningOptions,
        parallel: Annotated[
            bool,
            Option("--parallel", "-p", help_text="Generate tile macros in parallel"),
        ] = False,
    ) -> None:
        """Generate GDSII files for all tiles in the fabric."""
        opt_mode, custom_overrides = options.resolve()
        if not is_pdk_config_set():
            logger.error(
                "PDK configuration is not set. Please set the PDK configuration to "
                "generate tile macros."
            )
            return

        repl = self._cmd
        tiles = sorted(repl.all_tile)
        if not parallel:
            for tile in tiles:
                self._harden_tile(tile, opt_mode, custom_overrides)
            return

        with ThreadPoolExecutor(max_workers=repl.max_job) as executor:
            running = {
                executor.submit(
                    self._harden_tile, tile, opt_mode, custom_overrides
                ): tile
                for tile in tiles
            }
            for future in as_completed(running):
                if (exc := future.exception()) is not None:
                    raise CommandError(
                        f"Hardening tile {running[future]} failed"
                    ) from exc

    @with_annotated(
        subcommand_to="gen_macro",
        help="Stitch the hardened tile macros into the fabric macro",
    )
    def gen_macro_stitch(self) -> None:
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

    @with_annotated(
        subcommand_to="gen_macro",
        help="Run the full automated eFPGA macro flow",
    )
    def gen_macro_full(
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

    def _forward_deprecated(
        self, old_name: str, new_command: str, statement: Statement | str
    ) -> None:
        """Run `new_command` with the raw argument tail of a deprecated command.

        Parameters
        ----------
        old_name : str
            The deprecated command name, named in the warning.
        new_command : str
            The `gen_macro` subcommand replacing it.
        statement : Statement | str
            The parsed command line, or the already-joined argument tail the TCL
            bridge hands to a `do_*` method. Either way the tail is appended
            unchanged.

        Raises
        ------
        CommandError
            If `new_command` fails.
        """
        args = statement.args if isinstance(statement, Statement) else statement
        logger.warning(
            f"The '{old_name}' command is deprecated. Use '{new_command}' instead."
        )
        self._cmd.onecmd_plus_hooks(
            f"{new_command} {args}".strip(), add_to_history=False
        )
        # The nested call swallows the failure into `exit_code`, which neither the
        # TCL bridge nor the outer command's stop flag reads.
        if self._cmd.exit_code != 0:
            raise CommandError(f"'{new_command}' failed")

    def do_gen_tile_macro(self, statement: Statement | str) -> None:
        """Run `gen_macro tile`; this name is deprecated."""
        self._forward_deprecated("gen_tile_macro", "gen_macro tile", statement)

    def do_gen_all_tile_macros(self, statement: Statement | str) -> None:
        """Run `gen_macro all_tile`; this name is deprecated."""
        self._forward_deprecated("gen_all_tile_macros", "gen_macro all_tile", statement)

    def do_gen_fabric_macro(self, statement: Statement | str) -> None:
        """Run `gen_macro stitch`; this name is deprecated."""
        self._forward_deprecated("gen_fabric_macro", "gen_macro stitch", statement)

    def do_run_FABulous_eFPGA_macro(self, statement: Statement | str) -> None:
        """Run `gen_macro full`; this name is deprecated."""
        self._forward_deprecated(
            "run_FABulous_eFPGA_macro", "gen_macro full", statement
        )
