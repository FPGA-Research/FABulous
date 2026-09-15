"""Fabric and tile HDL-generation commands for the FABulous REPL.

Generate config memory, switch matrices, tiles, IO, and the fabric.
"""

import csv
import pickle
import shutil
from pathlib import Path
from typing import Annotated

from cmd2 import with_annotated, with_category
from cmd2.annotated import Argument, Option
from loguru import logger

from fabulous.custom_exception import CommandError, GDSFlowError
from fabulous.fabric_cad.gen_npnr_model import PLACEMENT_ESTIMATE_TEXT
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.tile_interface import Axis
from fabulous.fabric_generator.gds_generator.opt.placement_search import (
    search_tile_from_placement,
    won_config_mapping,
    won_interface_order,
)
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    InterfaceOrder,
    fixed_order_from_references,
    ordered_neighbours,
    read_interface_order,
    tile_pin_yaml,
    write_ordered_pin_yaml,
)
from fabulous.fabric_generator.gen_fabric.fabric_automation import (
    generateCustomTileConfig,
)
from fabulous.fabric_generator.gen_fabric.gen_configmem import (
    generate_composite_config_mem,
    generate_tile_config_mem,
)
from fabulous.fabric_generator.parser.parse_csv import config_mem_csv_of, parseTilesCSV
from fabulous.fabulous_repl.command_set_base import (
    CMD_FABRIC_FLOW,
    CMD_TOOLS,
    META_DATA_DIR,
    ReplCommandSet,
)
from fabulous.fabulous_repl.helper import (
    CommandPipeline,
)


class FabricGenCommandSet(ReplCommandSet):
    """Generate config memory, switch matrices, tiles, IO, and the fabric."""

    DEFAULT_CATEGORY = CMD_FABRIC_FLOW

    @with_annotated
    def do_gen_config_mem(
        self,
        tiles: Annotated[
            list[str],
            Argument(
                help_text="A list of tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
        opt_config_mapping: Annotated[
            bool,
            Option(
                "--opt-config-mapping",
                help_text=(
                    "Map each configuration bit to the frame crosspoint nearest "
                    "its placed latch, rather than taking the mapping the tile's "
                    "ConfigMem.csv already holds. Searches the tile through the "
                    "LibreLane flow, so it needs a PDK, a DIE_AREA on the tile "
                    "and a frame-based fabric."
                ),
            ),
        ] = False,
        iterations: Annotated[
            int | None,
            Option(
                "--iterations",
                help_text="Placements to spend on the search. Defaults to 10.",
            ),
        ] = None,
        override: Annotated[
            Path | None,
            Option(
                "--override", help_text="Override config with a custom YAML config file"
            ),
        ] = None,
    ) -> None:
        """Generate configuration memory of the given tile.

        Parsing input arguments and calling `generate_tile_config_mem`.

        With `--opt-config-mapping` the mapping is searched from the tile's own
        placement before the module is generated, so the flag changes where the
        mapping comes from rather than adding a stage. Each tile is searched in
        turn, which costs a LibreLane run apiece.

        Logs generation processes for each specified tile.
        """
        repl = self._cmd
        logger.info(f"Generating Config Memory for {' '.join(tiles)}")
        fabric = repl.fabulousAPI.fabric
        for i in tiles:
            logger.info(f"Generating configMem for {i}")
            tile = fabric.getTileByName(i)
            if tile is None:
                logger.error(f"Tile {i} not found in the fabric definition")
                return
            if opt_config_mapping and not self._map_config_from_placement(
                tile, iterations=iterations, override=override
            ):
                return
            generate_tile_config_mem(
                repl.fabulousAPI.writer,
                tile,
                frame_bits_per_row=fabric.frameBitsPerRow,
                max_frames_per_col=fabric.maxFramesPerCol,
            )
        if opt_config_mapping:
            logger.info("Run next: gen_bitStream_spec")
        logger.info("ConfigMem generation complete")

    def _map_config_from_placement(
        self,
        tile: Tile,
        *,
        iterations: int | None,
        override: Path | None,
    ) -> bool:
        """Search the tile's placement for its mapping and write it as the tile's CSV.

        `generate_tile_config_mem` reads that CSV back, so writing it here is
        what makes the search the generation method.

        Parameters
        ----------
        tile : Tile
            The tile to search.
        iterations : int | None
            Placements to spend on the search.
        override : Path | None
            A YAML of further config for the flow.

        Returns
        -------
        bool
            True when a mapping was written, False when the search refused or
            no iteration reached a proposal.
        """
        repl = self._cmd
        try:
            state = search_tile_from_placement(
                tile,
                project_dir=repl.projectDir,
                fabric=repl.fabulousAPI.fabric,
                config_mapping=True,
                tile_interface=False,
                iterations=iterations,
                override=override,
            )
        except GDSFlowError as error:
            logger.error(str(error))
            return False
        won = won_config_mapping(state)
        if won is None:
            logger.error(
                f"No iteration of the {tile.name} search implemented a mapping, "
                "so there is nothing to generate from; raise --iterations"
            )
            return False
        destination = config_mem_csv_of(tile)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(won, destination)
        logger.info(f"Mapped {tile.name} from its placement into {destination}")
        return True

    @with_annotated
    def do_gen_switch_matrix(
        self,
        tiles: Annotated[
            list[str],
            Argument(
                help_text="A list of tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
    ) -> None:
        """Generate switch matrix of given tile.

        Parsing input arguments and calling `genSwitchMatrix`.

        Also logs generation process for each specified tile.
        """
        repl = self._cmd
        logger.info(f"Generating switch matrix for {' '.join(tiles)}")
        for i in tiles:
            logger.info(f"Generating switch matrix for {i}")
            repl.fabulousAPI.setWriterOutputFile(
                repl.projectDir / f"Tile/{i}/{i}_switch_matrix.{repl.extension}"
            )
            repl.fabulousAPI.genSwitchMatrix(i)
        logger.info("Switch matrix generation complete")

    @with_annotated
    def do_gen_tile(
        self,
        tiles: Annotated[
            list[str],
            Argument(
                help_text="A list of tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
    ) -> None:
        """Generate given tile with switch matrix and configuration memory.

        Parsing input arguments, call functions such as `genSwitchMatrix` and
        `generate_tile_config_mem`. Handle both regular tiles and super tiles
        with sub-tiles.

        Also logs generation process for each specified tile and sub-tile.
        """
        repl = self._cmd
        fabric = repl.fabulousAPI.fabric
        logger.info(f"Generating tile {' '.join(tiles)}")
        for t in tiles:
            if sub_tiles := [
                f.stem
                for f in (repl.projectDir / f"Tile/{t}").iterdir()
                if f.is_dir() and f.name != "macro"
            ]:
                logger.info(
                    f"{t} is a super tile, generating {t} with sub tiles "
                    f"{' '.join(sub_tiles)}"
                )
                for st in sub_tiles:
                    # Gen switch matrix
                    logger.info(f"Generating switch matrix for tile {t}")
                    logger.info(f"Generating switch matrix for {st}")
                    repl.fabulousAPI.setWriterOutputFile(
                        f"{repl.projectDir}/Tile/{t}/{st}/{st}_switch_matrix.{repl.extension}"
                    )
                    repl.fabulousAPI.genSwitchMatrix(st)
                    logger.info(f"Generated switch matrix for {st}")

                    # Gen config mem
                    logger.info(f"Generating configMem for tile {t}")
                    logger.info(f"Generating ConfigMem for {st}")
                    generate_tile_config_mem(
                        repl.fabulousAPI.writer,
                        repl.fabulousAPI.fabric.getTileByName(st),
                        frame_bits_per_row=fabric.frameBitsPerRow,
                        max_frames_per_col=fabric.maxFramesPerCol,
                    )
                    logger.info(f"Generated configMem for {st}")

                    # Gen tile
                    logger.info(f"Generating subtile for tile {t}")
                    logger.info(f"Generating subtile {st}")
                    repl.fabulousAPI.setWriterOutputFile(
                        f"{repl.projectDir}/Tile/{t}/{st}/{st}.{repl.extension}"
                    )
                    repl.fabulousAPI.genTile(st)
                    logger.info(f"Generated subtile {st}")

                # A composite tile is a Tile, so its wrapper switch matrix,
                # config memory and module are generated by the same unified
                # entry points used for leaf tiles.

                # Gen composite wrapper switch matrix (empty when no wrapper muxes)
                logger.info(f"Generating switch matrix for composite tile {t}")
                repl.fabulousAPI.setWriterOutputFile(
                    f"{repl.projectDir}/Tile/{t}/{t}_switch_matrix.{repl.extension}"
                )
                repl.fabulousAPI.genSwitchMatrix(t)
                logger.info(f"Generated switch matrix for composite tile {t}")

                # Gen composite wrapper ConfigMem (no-op without wrapper bits)
                logger.info(f"Generating ConfigMem for composite tile {t}")
                composite = fabric.getTileByName(t)
                if composite is None:
                    logger.error(f"Composite tile {t} not found in the fabric")
                    return
                generate_composite_config_mem(
                    repl.fabulousAPI.writer,
                    composite,
                    frame_bits_per_row=fabric.frameBitsPerRow,
                    max_frames_per_col=fabric.maxFramesPerCol,
                )
                logger.info(f"Generated ConfigMem for composite tile {t}")

                # Gen composite tile wrapper module
                logger.info(f"Generating composite tile {t}")
                repl.fabulousAPI.setWriterOutputFile(
                    f"{repl.projectDir}/Tile/{t}/{t}.{repl.extension}"
                )
                repl.fabulousAPI.genTile(t)
                logger.info(f"Generated composite tile {t}")
                continue

            # Gen switch matrix
            repl.onecmd_plus_hooks(f"gen_switch_matrix {t}")
            if repl.exit_code != 0:
                raise CommandError(f"Switch matrix generation failed for tile {t}")

            # Gen config mem
            repl.onecmd_plus_hooks(f"gen_config_mem {t}")
            if repl.exit_code != 0:
                raise CommandError(f"Config memory generation failed for tile {t}")

            logger.info(f"Generating tile {t}")
            # Gen tile
            repl.fabulousAPI.setWriterOutputFile(
                f"{repl.projectDir}/Tile/{t}/{t}.{repl.extension}"
            )
            repl.fabulousAPI.genTile(t)
            logger.info(f"Generated tile {t}")

        logger.info("Tile generation complete")

    def do_gen_all_tile(self, *_ignored: str) -> None:
        """Generate all tiles by calling `do_gen_tile`."""
        repl = self._cmd
        logger.info("Generating all tiles")
        repl.onecmd_plus_hooks(f"gen_tile {' '.join(repl.all_tile)}")
        if repl.exit_code != 0:
            raise CommandError("Tile generation failed")
        logger.info("All tiles generation complete")

    def do_gen_fabric(self, *_ignored: str) -> None:
        """Generate fabric based on the loaded fabric.

        Calling `gen_all_tile` and `genFabric`.

        Logs start and completion of fabric generation process.
        """
        repl = self._cmd
        logger.info(f"Generating fabric {repl.fabulousAPI.fabric.name}")
        repl.onecmd_plus_hooks("gen_all_tile")
        if repl.exit_code != 0:
            raise CommandError("Tile generation failed")
        repl.fabulousAPI.setWriterOutputFile(
            f"{repl.projectDir}/Fabric/{repl.fabulousAPI.fabric.name}.{repl.extension}"
        )
        repl.fabulousAPI.genFabric()
        logger.info("Fabric generation complete")

    @with_annotated
    def do_gen_geometry(
        self,
        padding: Annotated[
            int,
            Argument(
                help_text="Padding value for geometry generation",
                choices=range(4, 33),
                metavar="[4-32]",
            ),
        ] = 8,
    ) -> None:
        """Generate geometry of fabric for FABulator.

        Checking if fabric is loaded, and calling 'genGeometry' and passing on padding
        value. Default padding is '8'.

        Also logs geometry generation, the used padding value and any warning about
        faulty padding arguments, as well as errors if the fabric is not loaded or the
        padding is not within the valid range of 4 to 32.
        """
        repl = self._cmd
        logger.info(f"Generating geometry for {repl.fabulousAPI.fabric.name}")
        geom_file = f"{repl.projectDir}/{repl.fabulousAPI.fabric.name}_geometry.csv"
        repl.fabulousAPI.setWriterOutputFile(geom_file)

        repl.fabulousAPI.genGeometry(padding)
        logger.info("Geometry generation complete")
        logger.info(f"{geom_file} can now be imported into FABulator")

    def do_gen_bitStream_spec(self, *_ignored: str) -> None:
        """Generate bitstream specification of the fabric.

        By calling `genBitStreamSpec` and saving the specification to a binary and CSV
        file.

        Also logs the paths of the output files.
        """
        repl = self._cmd
        logger.info("Generating bitstream specification")
        spec_object = repl.fabulousAPI.genBitStreamSpec()

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bitStreamSpec.bin")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bitStreamSpec.bin").open(
            "wb"
        ) as out_file:
            pickle.dump(spec_object, out_file)

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bitStreamSpec.csv")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bitStreamSpec.csv").open(
            "w", encoding="utf-8", newline="\n"
        ) as f:
            w = csv.writer(f)
            for key1 in spec_object["TileSpecs"]:
                w.writerow([key1])
                for key2, val in spec_object["TileSpecs"][key1].items():
                    w.writerow([key2, val])
        logger.info("Bitstream specification generation complete")

    def do_gen_top_wrapper(self, *_ignored: str) -> None:
        """Generate top wrapper of the fabric by calling `genTopWrapper`."""
        repl = self._cmd
        logger.info("Generating top wrapper")
        repl.fabulousAPI.setWriterOutputFile(
            f"{repl.projectDir}/Fabric/{repl.fabulousAPI.fabric.name}_top.{repl.extension}"
        )
        repl.fabulousAPI.genTopWrapper()
        logger.info("Top wrapper generation complete")

    def do_run_fab(self, *_ignored: str) -> None:
        """Generate the fabric based on the CSV file.

        Create bitstream specification of the fabric, top wrapper of the fabric, Nextpnr
        model of the fabric and geometry information of the fabric.
        """
        logger.info("Running FABulous")

        success = (
            CommandPipeline(self._cmd)
            .add_step("gen_io_fabric")
            .add_step("gen_fabric", "Fabric generation failed")
            .add_step("gen_bitStream_spec", "Bitstream specification generation failed")
            .add_step("gen_top_wrapper", "Top wrapper generation failed")
            .add_step("gen_model_npnr", "Nextpnr model generation failed")
            .add_step("gen_geometry", "Geometry generation failed")
            .execute()
        )

        if success:
            logger.info("FABulous fabric flow complete")

    def do_run_FABulous_fabric(self, *_ignored: str) -> None:
        """Generate the fabric based on the CSV file.

        deprecated: Use ``run_fab`` instead.
        """
        repl = self._cmd
        logger.warning(
            "The 'run_FABulous_fabric' command is deprecated. Use 'run_fab' instead."
        )
        repl.onecmd_plus_hooks("run_fab")
        if repl.exit_code != 0:
            raise CommandError("FABulous fabric flow failed")

    def do_gen_model_npnr(self, *_ignored: str) -> None:
        """Generate Nextpnr model of fabric.

        By parsing various required files for place and route such as `pips.txt`,
        `bel.txt`, `bel.v2.txt` and `template.pcf`. Output files are written to the
        directory specified by `metaDataDir` within `projectDir`.

        Logs output file directories.
        """
        repl = self._cmd
        logger.info("Generating npnr model")
        npnr_model = repl.fabulousAPI.gen_routing_model()
        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/pips.txt")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/pips.txt").open("w") as f:
            f.write(npnr_model[0])

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bel.txt")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bel.txt").open("w") as f:
            f.write(npnr_model[1])

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bel.v2.txt")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bel.v2.txt").open("w") as f:
            f.write(npnr_model[2])

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bel.v3.txt")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bel.v3.txt").open("w") as f:
            f.write(npnr_model[3])

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/template.pcf")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/template.pcf").open("w") as f:
            f.write(npnr_model[4])

        estimate_path = Path(
            f"{repl.projectDir}/{META_DATA_DIR}/placement_estimate.txt"
        )
        logger.info(f"output file: {estimate_path}")
        estimate_path.write_text(PLACEMENT_ESTIMATE_TEXT)

        logger.info("Generated npnr model")

    @with_annotated
    def do_gen_io_tiles(
        self,
        tiles: Annotated[
            list[str],
            Argument(
                help_text="A list of tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
    ) -> None:
        """Generate I/O BELs for specified tiles.

        This command generates Input/Output Basic Elements of Logic (BELs) for the
        specified tiles, enabling external connectivity for the FPGA fabric.
        """
        repl = self._cmd
        for tile in tiles:
            repl.fabulousAPI.genIOBelForTile(tile)

    def do_gen_io_fabric(self, _args: str) -> None:
        """Generate I/O BELs for the entire fabric.

        This command generates Input/Output Basic Elements of Logic (BELs) for all
        applicable tiles in the fabric, providing external connectivity
        across the entire FPGA design.

        Parameters
        ----------
        _args : str
            Command arguments (unused for this command).
        """
        repl = self._cmd
        repl.fabulousAPI.genFabricIOBels()

    @with_annotated
    def do_gen_io_pin_config(
        self,
        tile: Annotated[
            str,
            Argument(
                help_text="A tile or supertile",
                completer=lambda self: self._cmd.all_tile,
            ),
        ],
        output: Annotated[
            Path | None,
            Argument(help_text="Output path for the generated IO pin config YAML"),
        ] = None,
        opt_tile_interface: Annotated[
            bool,
            Option(
                "--opt-tile-interface",
                help_text=(
                    "Order the border pins by the placed logic they feed, rather "
                    "than taking the layout the tile's ports enumerate. Searches "
                    "the tile through the LibreLane flow, so it needs a PDK and a "
                    "DIE_AREA on the tile."
                ),
            ),
        ] = False,
        reference: Annotated[
            list[str] | None,
            Option(
                "--reference",
                action="append",
                help_text=(
                    "A tile this one abuts, or a pin YAML in this tile's names, "
                    "whose order it keeps. A border belongs to a whole row or "
                    "column, so a reference settles that axis and leaves the "
                    "other to be searched. Repeatable."
                ),
            ),
        ] = None,
        obey_neighbours: Annotated[
            bool,
            Option(
                "--obey-neighbours",
                help_text=(
                    "Take every tile abutting this one whose pin YAML already "
                    "ranks their shared border as a reference."
                ),
            ),
        ] = False,
        iterations: Annotated[
            int | None,
            Option(
                "--iterations",
                help_text="Placements to spend on the search. Defaults to 10.",
            ),
        ] = None,
        override: Annotated[
            Path | None,
            Option(
                "--override", help_text="Override config with a custom YAML config file"
            ),
        ] = None,
    ) -> None:
        """Generate an IO pin configuration YAML file for a tile or supertile.

        With `--opt-tile-interface` the order is searched from the tile's own
        placement before the YAML is written, so the flag changes where the
        order comes from rather than adding a stage. References fix the borders
        this tile shares with tiles already ordered, which is what keeps the two
        abutting; without one every border is searched free, so order the
        majority tile first and reference it from the rest.
        """
        repl = self._cmd
        logger.info(f"Generating IO pin config for {tile}")

        tile_obj = repl.fabulousAPI.getTile(tile)
        if tile_obj is None:
            logger.error(f"Tile {tile} not found in fabric definition")
            return
        if opt_tile_interface and output is not None:
            logger.error(
                "--opt-tile-interface writes the tile's own pin YAML, since that "
                "is the file it is hardened from; drop the output argument"
            )
            return

        fabric = repl.fabulousAPI.fabric
        tile_root = repl.projectDir / "Tile"
        names = list(reference or [])
        try:
            if obey_neighbours:
                names += [
                    neighbour.name
                    for neighbour in ordered_neighbours(fabric, tile_obj, tile_root)
                    if neighbour.name not in names
                ]
            order = fixed_order_from_references(fabric, tile_obj, tile_root, names)
        except GDSFlowError as error:
            logger.error(str(error))
            return
        if names:
            logger.info(f"{tile} keeps the order of {', '.join(names)}")

        if opt_tile_interface:
            order = self._order_from_placement(
                tile_obj, order, iterations=iterations, override=override
            )
            if order is None:
                return

        output_path = output or tile_pin_yaml(tile_root, tile)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_ordered_pin_yaml(tile_obj, output_path, order, fabric=fabric)

        logger.info(f"Generated IO pin config at {output_path}")
        if opt_tile_interface:
            logger.info(
                f"Run next: gen_tile_macro {tile}; every tile sharing a border "
                "with it needs ordering against it and hardening again"
            )
        logger.info("IO pin config generation complete")

    def _order_from_placement(
        self,
        tile: Tile,
        fixed: InterfaceOrder | None,
        *,
        iterations: int | None,
        override: Path | None,
    ) -> InterfaceOrder | None:
        """Search the tile's placement for the border order it prefers.

        Parameters
        ----------
        tile : Tile
            The tile to search.
        fixed : InterfaceOrder | None
            The ranks the references settled, which the search keeps.
        iterations : int | None
            Placements to spend on the search.
        override : Path | None
            A YAML of further config for the flow.

        Returns
        -------
        InterfaceOrder | None
            The order the winning iteration implemented, `fixed` itself when
            the references leave no axis free, or None when the search refused
            or reached no proposal.
        """
        repl = self._cmd
        if fixed is not None and not [
            axis for axis in Axis if not any(fixed.get(side) for side in axis.sides)
        ]:
            logger.info(
                f"The references rank both axes of {tile.name}, so there is "
                "nothing left to search"
            )
            return fixed
        try:
            state = search_tile_from_placement(
                tile,
                project_dir=repl.projectDir,
                fabric=repl.fabulousAPI.fabric,
                config_mapping=False,
                tile_interface=True,
                fixed_order=fixed,
                iterations=iterations,
                override=override,
            )
        except GDSFlowError as error:
            logger.error(str(error))
            return None
        won = won_interface_order(state)
        if won is None:
            logger.error(
                f"No iteration of the {tile.name} search implemented an order, "
                "so there is nothing to generate from; raise --iterations"
            )
            return None
        logger.info(f"Ordered {tile.name} from its own placement")
        return read_interface_order(won)

    @with_category(CMD_TOOLS)
    @with_annotated
    def do_generate_custom_tile_config(
        self,
        tile_path: Annotated[
            Path, Argument(help_text="Path to the target tile directory")
        ],
        switch_matrix: Annotated[
            bool,
            Option(
                "--switch-matrix",
                "-sm",
                help_text="Generate a Tile Switch Matrix (enabled by default)",
            ),
        ] = True,
    ) -> None:
        """Generate a custom tile configuration for a given tile folder.

        Or path to bel folder. A tile `.csv` file and a switch matrix `.list` file will
        be generated.

        The provided path may contain bel files, which will be included in the generated
        tile .csv file as well as the generated switch matrix .list file.
        """
        if not tile_path.is_dir():
            logger.error(f"{tile_path} is not a directory or does not exist")
            return

        tile_csv = generateCustomTileConfig(tile_path)

        if switch_matrix:
            parseTilesCSV(tile_csv)
