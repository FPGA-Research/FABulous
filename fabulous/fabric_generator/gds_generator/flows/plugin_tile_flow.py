"""Config-driven LibreLane plugin adapter for the FABulous tile flow."""

from decimal import Decimal
from pathlib import Path
from typing import Literal

from librelane.common import GenericDict
from librelane.config.variable import Variable
from librelane.flows.flow import Flow, FlowException
from librelane.flows.sequential import SequentialFlow
from librelane.state.state import State
from librelane.steps.step import Step

from fabulous.custom_exception import (
    InvalidSupertileDefinition,
    InvalidTileDefinition,
)
from fabulous.fabric_definition.define import ConfigBitMode, MultiplexerStyle, Side
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from fabulous.fabric_generator.gds_generator.helper import (
    get_pitch,
    get_routing_obstructions,
    round_die_area,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabric_generator.gen_fabric.gen_configmem import generateConfigMem
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
from fabulous.fabric_generator.gen_fabric.gen_tile import (
    generateSuperTile,
    generateTile,
)
from fabulous.fabric_generator.parser.parse_csv import parse_tile_from_dir
from fabulous.fabulous_settings import get_context, init_context


@Flow.factory.register()
class FABulousTile(SequentialFlow):
    """Drop-in replacement for `librelane_plugin_fabulous.FABulousTile`."""

    Steps = FABulousTileVerilogMacroFlow.Steps

    config_vars = FABulousTileVerilogMacroFlow.config_vars + [
        Variable(
            "FABULOUS_TILE_DIR",
            list[Path],
            "Path to the tile directory containing the tile CSV "
            "(`<tile_name>.csv`) and its associated Verilog sources. "
            "Declared as `list[Path]` so LibreLane's `dir::.` / `refg::` "
            "resolvers validate cleanly; only the first element is used.",
        ),
        Variable(
            "FABULOUS_EXTERNAL_SIDE",
            Literal["N", "E", "S", "W"] | None,
            "The side of the macro at which the external pins are placed. "
            "The pin-ordering YAML is generated from the tile's position in "
            "the parent fabric when available, so this value is a fallback for "
            "standalone plugin tile runs.",
        ),
        Variable(
            "FABULOUS_SUPERTILE",
            bool | None,
            "If true, `FABULOUS_TILE_DIR` refers to a super tile and the "
            "flow generates a super-tile wrapper in addition to the "
            "per-subtile Verilog.",
            default=False,
        ),
        Variable(
            "FABULOUS_CONFIG_BIT_MODE",
            ConfigBitMode,
            "Config-bit storage mode used when regenerating the tile switch "
            "matrix and config memory. Must match the parent fabric; the "
            "standalone tile flow has no fabric to read it from.",
            default=ConfigBitMode.FRAME_BASED,
        ),
        Variable(
            "FABULOUS_MULTIPLEXER_STYLE",
            MultiplexerStyle,
            "Multiplexer implementation style used when regenerating the tile "
            "switch matrix. Must match the parent fabric.",
            default=MultiplexerStyle.CUSTOM,
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

        init_context(api_mode=True)

        tile_name = self.config.get("DESIGN_NAME") or tile_dir.name
        is_supertile = bool(self.config.get("FABULOUS_SUPERTILE", False))

        try:
            tile = parse_tile_from_dir(tile_dir, tile_name, is_supertile)
        except (
            FileNotFoundError,
            InvalidTileDefinition,
            InvalidSupertileDefinition,
        ) as exc:
            raise FlowException(str(exc)) from exc

        config_bit_mode = ConfigBitMode(self.config["FABULOUS_CONFIG_BIT_MODE"])
        multiplexer_style = MultiplexerStyle(self.config["FABULOUS_MULTIPLEXER_STYLE"])
        writer = VerilogCodeGenerator()
        _emit_tile_verilog(
            writer,
            tile,
            tile_dir,
            config_bit_mode=config_bit_mode,
            multiplexer_style=multiplexer_style,
        )

        pin_yaml = Path(self.run_dir) / f"{tile_name}_io_pin_order.yaml"
        external_side_value = self.config.get("FABULOUS_EXTERNAL_SIDE")
        try:
            external_port_side = (
                Side.SOUTH if external_side_value is None else Side(external_side_value)
            )
        except ValueError as exc:
            raise FlowException(
                f"Invalid FABULOUS_EXTERNAL_SIDE={external_side_value!r}"
            ) from exc
        generate_IO_pin_order_config(
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
            FABULOUS_OPT_MODE=OptMode.NO_OPT,
        )

        self.config = _apply_tile_die_area_config(self.config, tile)
        self.config = round_die_area(self.config)

        if self.config.get("ROUTING_OBSTRUCTIONS") is None:
            self.config = self.config.copy(
                ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
            )

        return super().run(initial_state, **kwargs)


# PIP delay only annotates the switch-matrix for simulation timing; it does not
# affect the hardened macro, so it is fixed here rather than exposed as config.
_SWITCH_MATRIX_PIP_DELAY = 80


def _emit_tile_verilog(
    writer: VerilogCodeGenerator,
    tile: Tile | SuperTile,
    tile_dir: Path,
    config_bit_mode: ConfigBitMode,
    multiplexer_style: MultiplexerStyle,
) -> None:
    """Generate switch-matrix, config-mem, and tile Verilog into `tile_dir`."""
    if isinstance(tile, SuperTile):
        for sub_tile in tile.tiles:
            sub_dir = sub_tile.tileDir.parent
            _emit_regular_tile_verilog(
                writer,
                sub_tile,
                sub_dir,
                config_bit_mode,
                multiplexer_style,
            )
        writer.outFileName = tile_dir / f"{tile.name}.v"
        generateSuperTile(
            writer,
            tile,
            disable_user_clk=True,
            config_bit_mode=config_bit_mode,
        )
        return

    _emit_regular_tile_verilog(
        writer, tile, tile_dir, config_bit_mode, multiplexer_style
    )


def _emit_regular_tile_verilog(
    writer: VerilogCodeGenerator,
    tile: Tile,
    tile_dir: Path,
    config_bit_mode: ConfigBitMode,
    multiplexer_style: MultiplexerStyle,
) -> None:
    """Generate Verilog artefacts for one concrete tile."""
    switch_matrix_debug_signal = get_context().switch_matrix_debug_signal

    writer.outFileName = tile_dir / f"{tile.name}_switch_matrix.v"
    genTileSwitchMatrix(
        writer,
        tile,
        switch_matrix_debug_signal,
        config_bit_mode=config_bit_mode,
        multiplexer_style=multiplexer_style,
        default_pip_delay=_SWITCH_MATRIX_PIP_DELAY,
    )
    writer.outFileName = tile_dir / f"{tile.name}_ConfigMem.v"
    generateConfigMem(
        writer,
        tile.name,
        tile.globalConfigBits,
        tile_dir / f"{tile.name}_ConfigMem.csv",
    )
    writer.outFileName = tile_dir / f"{tile.name}.v"
    generateTile(
        writer,
        tile,
        disable_user_clk=True,
        config_bit_mode=config_bit_mode,
    )


def _apply_tile_die_area_config(
    config: GenericDict[str, object],
    tile_type: Tile | SuperTile,
) -> GenericDict[str, object]:
    """Populate plugin tile `DIE_AREA` using patchable local helper imports."""
    x_pitch, y_pitch = get_pitch(config)
    min_x, min_y = tile_type.get_min_die_area(
        x_pitch=x_pitch,
        y_pitch=y_pitch,
        x_pin_thickness_mult=config.get("IO_PIN_V_THICKNESS_MULT", Decimal(1)),
        y_pin_thickness_mult=config.get("IO_PIN_H_THICKNESS_MULT", Decimal(1)),
    )

    if config["FABULOUS_IGNORE_DEFAULT_DIE_AREA"] or config.get("DIE_AREA") is None:
        return config.copy(DIE_AREA=(0, 0, min_x, min_y))

    _, _, width, height = config["DIE_AREA"]
    if width < min_x or height < min_y:
        raise FlowException(
            f"DIE_AREA ({width}, {height}) is smaller than the "
            f"minimum required area ({min_x}, {min_y}) for the "
            f"tile {tile_type.name}. Please update the DIE_AREA "
        )
    return config
