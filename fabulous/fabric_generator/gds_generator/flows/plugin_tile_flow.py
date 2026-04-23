"""Drop-in LibreLane plugin wrapper for the FABulous tile flow.

Exposes :class:`FABulousTile`, a LibreLane-factory-compatible flow that accepts
the same ``FABULOUS_TILE_DIR`` / ``FABULOUS_EXTERNAL_SIDE`` / ``FABULOUS_SUPERTILE``
config variables as ``mole99/librelane_plugin_fabulous`` and drives the existing
:class:`FABulousTileVerilogMacroFlow` pipeline.

Unlike ``FABulousTileVerilogMacroFlow`` (which is instantiated programmatically
from the FABulous CLI with a pre-parsed ``Tile`` object), this wrapper is
config-driven: LibreLane constructs it from a ``config.yaml`` and the flow loads
the tile CSV directly, emits the per-tile Verilog, and builds the pin-ordering
YAML inside ``run()``.
"""

from decimal import Decimal
from pathlib import Path
from typing import Literal

from librelane.config.variable import Variable
from librelane.flows.flow import Flow, FlowException
from librelane.flows.sequential import SequentialFlow
from librelane.state.state import State
from librelane.steps.step import Step

from fabulous.fabric_definition.define import ConfigBitMode, MultiplexerStyle, Side
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)
from fabulous.fabric_generator.gds_generator.helper import (
    get_offset,
    get_pitch,
    get_routing_obstructions,
    round_die_area,
)
from fabulous.fabric_generator.gen_fabric.gen_configmem import generateConfigMem
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
from fabulous.fabric_generator.gen_fabric.gen_tile import (
    generateSuperTile,
    generateTile,
)
from fabulous.fabric_generator.parser.parse_csv import parseSupertilesCSV, parseTilesCSV
from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_settings import get_context, init_context


@Flow.factory.register()
class FABulousTile(SequentialFlow):
    """Drop-in replacement for ``librelane_plugin_fabulous.FABulousTile``.

    Reuses the step list, substitutions, config variables, and gating variables
    of :class:`FABulousTileVerilogMacroFlow`, and adds the three plugin-level
    variables that ``mole99/librelane_plugin_fabulous`` exposes so a mole99-shaped
    ``config.yaml`` validates against this flow.
    """

    Steps = FABulousTileVerilogMacroFlow.Steps

    config_vars = FABulousTileVerilogMacroFlow.config_vars + [
        Variable(
            "FABULOUS_TILE_DIR",
            list[Path],
            "Path to the tile directory containing the tile CSV "
            "(``<tile_name>.csv``) and its associated Verilog sources. "
            "Declared as ``list[Path]`` so LibreLane's ``dir::.`` / ``refg::`` "
            "resolvers validate cleanly; only the first element is used.",
        ),
        Variable(
            "FABULOUS_EXTERNAL_SIDE",
            Literal["N", "E", "S", "W"] | None,
            "The side of the macro at which the external pins are placed. "
            "Mirrors the mole99 plugin variable; the pin-ordering YAML is "
            "generated from the tile's position in the parent fabric, so "
            "this value is informational for tiles that sit on the fabric "
            "border.",
        ),
        Variable(
            "FABULOUS_SUPERTILE",
            bool | None,
            "If true, ``FABULOUS_TILE_DIR`` refers to a super tile and the "
            "flow generates a super-tile wrapper in addition to the "
            "per-subtile Verilog.",
            default=False,
        ),
    ]

    gating_config_vars = FABulousTileVerilogMacroFlow.gating_config_vars

    def run(
        self,
        initial_state: State,
        **kwargs: object,
    ) -> tuple[State, list[Step]]:
        """Prepare FABulous inputs, then run the tile macro pipeline."""
        tile_dir_entries = self.config["FABULOUS_TILE_DIR"]
        if not tile_dir_entries:
            raise FlowException("FABULOUS_TILE_DIR is empty")
        tile_dir = Path(tile_dir_entries[0]).resolve()
        if not tile_dir.is_dir():
            raise FlowException(f"FABULOUS_TILE_DIR={tile_dir} is not a directory")

        # Bypass project-dir validation: this plugin targets a single tile
        # (optionally from a tile library) and doesn't require a full
        # FABulous project with a ``.FABulous/`` marker.
        init_context(api_mode=True)

        tile_name = self.config.get("DESIGN_NAME") or tile_dir.name
        is_supertile = bool(self.config.get("FABULOUS_SUPERTILE", False))

        tile = _parse_plugin_tile(tile_dir, tile_name, is_supertile)
        writer = VerilogCodeGenerator()
        _emit_tile_verilog(writer, tile, tile_dir)

        pin_yaml = Path(self.run_dir) / f"{tile_name}_io_pin_order.yaml"
        api = FABulous_API(writer=writer)
        external_side_value = self.config.get("FABULOUS_EXTERNAL_SIDE")
        try:
            external_port_side = (
                Side.SOUTH if external_side_value is None else Side(external_side_value)
            )
        except ValueError as exc:
            raise FlowException(
                f"Invalid FABULOUS_EXTERNAL_SIDE={external_side_value!r}"
            ) from exc
        api.gen_io_pin_order_config(
            tile,
            pin_yaml,
            external_port_side=external_port_side,
        )

        file_list = [str(f) for f in self.config.get("VERILOG_FILES", []) or []]
        if isinstance(tile, SuperTile):
            concrete_tiles = list(tile.tiles)
            generated_files = [tile_dir / f"{tile.name}.v"]
        else:
            concrete_tiles = [tile]
            generated_files = []

        for concrete_tile in concrete_tiles:
            concrete_tile_dir = concrete_tile.tileDir.parent
            generated_files.extend(
                [
                    concrete_tile_dir / f"{concrete_tile.name}.v",
                    concrete_tile_dir / f"{concrete_tile.name}_switch_matrix.v",
                    concrete_tile_dir / f"{concrete_tile.name}_ConfigMem.v",
                ]
            )
            for bel in concrete_tile.bels:
                file_list.append(str(bel.src))

        file_list.extend(str(f) for f in generated_files if f.exists())
        file_list = list(dict.fromkeys(file_list))
        if models_pack := get_context().models_pack:
            file_list.append(str(models_pack.resolve()))

        if isinstance(tile, SuperTile):
            logical_width = tile.max_width
            logical_height = tile.max_height
        else:
            logical_width = 1
            logical_height = 1

        self.config = self.config.copy(
            DESIGN_NAME=tile_name,
            VERILOG_FILES=file_list,
            FABULOUS_IO_PIN_ORDER_CFG=str(pin_yaml),
            FABULOUS_TILE_LOGICAL_WIDTH=logical_width,
            FABULOUS_TILE_LOGICAL_HEIGHT=logical_height,
        )

        self._resolve_die_area(tile)
        self.config = round_die_area(self.config)

        if (
            "ROUTING_OBSTRUCTIONS" not in self.config
            or self.config["ROUTING_OBSTRUCTIONS"] is None
        ) and self.config["ROUTING_OBSTRUCTIONS"] is not False:
            self.config = self.config.copy(
                ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
            )

        return super().run(initial_state, **kwargs)

    def _resolve_die_area(self, tile: Tile | SuperTile) -> None:
        """Populate ``DIE_AREA`` if unset, mirroring the macro flow."""
        x_pitch, y_pitch = get_pitch(self.config)
        get_offset(self.config)
        min_x, min_y = tile.get_min_die_area(
            x_pitch,
            y_pitch,
            self.config.get("IO_PIN_V_THINKNESS_MULT", Decimal(1)),
            self.config.get("IO_PIN_H_THINKNESS_MULT", Decimal(1)),
            x_pitch,
            y_pitch,
        )
        ignore_default = bool(
            self.config.get("FABULOUS_IGNORE_DEFAULT_DIE_AREA", False)
        )
        existing = self.config.get("DIE_AREA")
        if ignore_default or existing is None:
            self.config = self.config.copy(DIE_AREA=(0, 0, min_x, min_y))
            return
        _, _, width, height = existing
        width, height = Decimal(width), Decimal(height)
        if width < min_x or height < min_y:
            raise FlowException(
                f"DIE_AREA ({width}, {height}) is smaller than the minimum "
                f"required area ({min_x}, {min_y}) for the tile."
            )


def _emit_tile_verilog(
    writer: VerilogCodeGenerator,
    tile: Tile | SuperTile,
    tile_dir: Path,
) -> None:
    """Generate switch-matrix, config-mem, and tile Verilog into ``tile_dir``.

    Mirrors the CLI's ``do_gen_tile`` orchestration so the output tree matches
    what :class:`FABulousTileVerilogMacroFlow` expects to glob for
    ``VERILOG_FILES``.
    """
    if isinstance(tile, SuperTile):
        for sub_tile in tile.tiles:
            sub_dir = sub_tile.tileDir.parent
            _emit_regular_tile_verilog(writer, sub_tile, sub_dir)
        writer.outFileName = tile_dir / f"{tile.name}.v"
        generateSuperTile(
            writer,
            tile,
            disable_user_clk=True,
            config_bit_mode=ConfigBitMode.FRAME_BASED,
        )
        return

    _emit_regular_tile_verilog(writer, tile, tile_dir)


def _emit_regular_tile_verilog(
    writer: VerilogCodeGenerator,
    tile: Tile,
    tile_dir: Path,
) -> None:
    """Generate Verilog artefacts for one concrete tile."""
    switch_matrix_debug_signal = get_context().switch_matrix_debug_signal

    writer.outFileName = tile_dir / f"{tile.name}_switch_matrix.v"
    genTileSwitchMatrix(
        writer,
        tile,
        switch_matrix_debug_signal,
        config_bit_mode=ConfigBitMode.FRAME_BASED,
        multiplexer_style=MultiplexerStyle.CUSTOM,
        generate_delay_in_switch_matrix=80,
    )
    writer.outFileName = tile_dir / f"{tile.name}_ConfigMem.v"
    generateConfigMem(writer, tile, tile_dir / f"{tile.name}_ConfigMem.csv")
    writer.outFileName = tile_dir / f"{tile.name}.v"
    generateTile(
        writer,
        tile,
        disable_user_clk=True,
        config_bit_mode=ConfigBitMode.FRAME_BASED,
    )


def _parse_plugin_tile(
    tile_dir: Path,
    tile_name: str,
    is_supertile: bool,
) -> Tile | SuperTile:
    """Parse the plugin tile directory without constructing a Fabric."""
    tile_csv = tile_dir / f"{tile_name}.csv"
    if not tile_csv.exists():
        raise FlowException(f"Tile CSV {tile_csv} does not exist")

    if not is_supertile:
        tiles, _ = parseTilesCSV(tile_csv)
        for tile in tiles:
            if tile.name == tile_name:
                return tile
        raise FlowException(f"Tile {tile_name!r} not found in {tile_csv}")

    tile_dic: dict[str, Tile] = {}
    subtile_names: list[str] = []
    with tile_csv.open("r", encoding="utf-8") as f:
        f.readline()  # SuperTILE header
        for raw in f:
            line = raw.strip()
            if "EndSuperTILE" in line:
                break
            for cell in line.split(","):
                name = cell.strip()
                if name:
                    subtile_names.append(name)

    for subtile_name in subtile_names:
        subtile_csv = tile_dir / subtile_name / f"{subtile_name}.csv"
        tiles, _ = parseTilesCSV(subtile_csv)
        tile_dic.update({tile.name: tile for tile in tiles})

    supertiles = parseSupertilesCSV(tile_csv, tile_dic)
    for supertile in supertiles:
        if supertile.name == tile_name:
            return supertile
    raise FlowException(f"SuperTile {tile_name!r} not found in {tile_csv}")
