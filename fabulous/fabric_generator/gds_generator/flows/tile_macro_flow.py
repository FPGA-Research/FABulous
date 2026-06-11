"""Tile optimisation flows for FABulous fabric generation."""

from decimal import Decimal
from pathlib import Path

from librelane.common import GenericDict
from librelane.config.variable import Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow, FlowException
from librelane.flows.sequential import SequentialFlow
from librelane.logging.logger import err, info

from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gds_generator.flows.flow_define import (
    check_steps,
    classic_gating_config_vars,
    prep_steps,
    tile_optimisation_physical_steps,
    vhdl_prep_steps,
    write_out_steps,
)
from fabulous.fabric_generator.gds_generator.helper import (
    get_offset,
    get_pitch,
    get_routing_obstructions,
    round_die_area,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabulous_settings import get_context

configs = Classic.config_vars + [
    Variable(
        "FABULOUS_IGNORE_DEFAULT_DIE_AREA",
        bool,
        "When is true will ignore the provided die area and "
        "use the default one instead.",
        default=False,
    ),
]


class FABulousTileMacroFlow(SequentialFlow):
    """Base tile macro flow for FABulous fabric generation.

    Concrete subclasses pick the HDL language by overriding `Steps` (the
    synthesis/prep portion) and the file-collection class attributes. The Verilog
    variant is the canonical configuration; the VHDL variant swaps in the GHDL-based
    prep steps and reads `.vhdl` sources.
    """

    Steps = (
        prep_steps + tile_optimisation_physical_steps + write_out_steps + check_steps
    )

    config_vars = configs
    gating_config_vars = classic_gating_config_vars

    # HDL source collection (Verilog defaults).
    _hdl_glob_patterns: tuple[str, ...] = ("**/*.v",)
    _hdl_files_config_key: str = "VERILOG_FILES"
    _models_pack_first: bool = False
    _extra_synth_config: dict[str, object] = {}

    def __init__(
        self,
        tile_type: Tile | SuperTile,
        io_pin_config: Path,
        opt_mode: OptMode,
        pdk: str,
        pdk_root: Path,
        models_pack_path: Path | None = None,
        base_config_path: Path | None = None,
        override_config_path: Path | None = None,
        design_dir: Path | None = None,
        **custom_config_overrides: dict,
    ) -> None:
        # Build the HDL source list. `models_pack` lives under Fabric/ (outside the
        # tile glob); for VHDL it must be analysed before the tile sources, so it is
        # prepended rather than appended.
        models_pack = models_pack_path or get_context().models_pack
        if models_pack is None:
            raise FlowException(
                "models_pack is not set in the context, cannot proceed."
            )
        file_list: list[str] = []
        if self._models_pack_first:
            file_list.append(str(models_pack.resolve()))
        file_list += [
            str(f)
            for pattern in self._hdl_glob_patterns
            for f in tile_type.tileDir.parent.glob(pattern)
            if "macro" not in f.parts
        ]
        if not self._models_pack_first:
            file_list.append(str(models_pack.resolve()))

        # Determine logical dimensions
        if isinstance(tile_type, SuperTile):
            logical_width = tile_type.max_width
            logical_height = tile_type.max_height
        else:
            logical_width = 1
            logical_height = 1

        # casting opt_mode
        opt_mode = OptMode(opt_mode)

        # Build tile configuration
        tile_config_dict = {
            "DESIGN_NAME": tile_type.name,
            "FABULOUS_IO_PIN_ORDER_CFG": str(io_pin_config),
            self._hdl_files_config_key: file_list,
            "FABULOUS_OPT_MODE": OptMode(opt_mode),
            **self._extra_synth_config,
        }

        if "FABULOUS_OPT_MODE" in custom_config_overrides:
            custom_config_overrides["FABULOUS_OPT_MODE"] = OptMode(
                custom_config_overrides["FABULOUS_OPT_MODE"]
            )

        final_dir_path = (
            Path(str(design_dir))
            if design_dir is not None
            else tile_type.tileDir.parent / "macro" / opt_mode.value
        )
        final_dir_path.mkdir(parents=True, exist_ok=True)
        final_dir = str(final_dir_path.resolve())

        configs = [
            i
            for i in [
                tile_config_dict,
                base_config_path,
                override_config_path,
                custom_config_overrides,
            ]
            if i is not None
        ]
        super().__init__(
            configs,
            name=tile_type.name,
            design_dir=final_dir,
            pdk=pdk,
            pdk_root=str(pdk_root),
        )
        self.config = self.config.copy(
            FABULOUS_TILE_LOGICAL_WIDTH=logical_width,
            FABULOUS_TILE_LOGICAL_HEIGHT=logical_height,
        )
        final_opt_mode = self.config.get("FABULOUS_OPT_MODE", None)
        if final_opt_mode and final_opt_mode != OptMode.NO_OPT:
            directional = final_opt_mode in (
                OptMode.FIND_MIN_WIDTH,
                OptMode.FIND_MIN_HEIGHT,
            )
            # Directional modes minimise one axis. When the user supplies a
            # DIE_AREA they are fixing the other axis, so keep that value instead
            # of forcing the computed minimum. BALANCE/LARGE have no fixed axis,
            # so they always fall back to full-auto sizing.
            honour_user_die_area = (
                directional
                and self.config.get("DIE_AREA") is not None
                and not self.config["FABULOUS_IGNORE_DEFAULT_DIE_AREA"]
            )
            if honour_user_die_area:
                info(
                    f"FABulous optimisation is set to {final_opt_mode}, honouring "
                    "the user DIE_AREA: the fixed axis is locked and the other "
                    "axis is minimised."
                )
            else:
                info(
                    f"FABulous optimisation is set to {final_opt_mode}, "
                    "default die area is ignored."
                )
                self.config = self.config.copy(FABULOUS_IGNORE_DEFAULT_DIE_AREA=True)

        self.config = _apply_tile_die_area_config(
            self.config, tile_type, final_opt_mode
        )
        self.config = round_die_area(self.config)
        if (
            "ROUTING_OBSTRUCTIONS" not in self.config
            or self.config["ROUTING_OBSTRUCTIONS"] is None
        ) and self.config["ROUTING_OBSTRUCTIONS"] is not False:
            self.config = self.config.copy(
                ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
            )


@Flow.factory.register()
class FABulousTileVerilogMacroFlow(FABulousTileMacroFlow):
    """Tile macro flow for FABulous fabric generation from Verilog."""


@Flow.factory.register()
class FABulousTileVHDLMacroFlow(FABulousTileMacroFlow):
    """Tile macro flow for FABulous fabric generation from VHDL.

    Identical to the Verilog flow apart from the GHDL-based synthesis/prep steps and
    reading `.vhdl` sources (`models_pack` analysed first).
    """

    Steps = (
        vhdl_prep_steps
        + tile_optimisation_physical_steps
        + write_out_steps
        + check_steps
    )

    _hdl_glob_patterns = ("**/*.vhdl", "**/*.vhd")
    _hdl_files_config_key = "VHDL_FILES"
    _models_pack_first = True
    # `--latches`: `models_pack` defines a transparent latch primitive; GHDL errors
    # on inferred latches by default (Verilog synthesis tolerates them).
    _extra_synth_config = {"GHDL_ARGUMENTS": ["--std=08", "-fexplicit", "--latches"]}


def _apply_tile_die_area_config(
    config: GenericDict[str, object],
    tile_type: Tile | SuperTile,
    opt_mode: OptMode | None = None,
) -> GenericDict[str, object]:
    """Populate and validate tile ``DIE_AREA`` using the routing pitch."""
    x_pitch, y_pitch = get_pitch(config)
    get_offset(config)
    min_x, min_y = tile_type.get_min_die_area(
        x_pitch=x_pitch,
        y_pitch=y_pitch,
        x_pin_thickness_mult=config.get("IO_PIN_V_THICKNESS_MULT", Decimal(1)),
        y_pin_thickness_mult=config.get("IO_PIN_H_THICKNESS_MULT", Decimal(1)),
    )

    if opt_mode == OptMode.NO_OPT:
        if not config.get("DIE_AREA"):
            err("If not using any optimisatin, DIE_AREA must be set.")
            raise FlowException("Invalid DIE_AREA configuration.")
        return config

    if config["FABULOUS_IGNORE_DEFAULT_DIE_AREA"] or config.get("DIE_AREA") is None:
        return config.copy(DIE_AREA=(0, 0, min_x, min_y))

    die_area = config.get("DIE_AREA")
    if die_area is None:
        raise ValueError("DIE_AREA metric not found in state.")
    _, _, width, height = die_area
    width = Decimal(width)
    height = Decimal(height)

    if opt_mode == OptMode.FIND_MIN_WIDTH:
        _validate_fixed_axis("height", height, min_y, tile_type.name)
        return config
    if opt_mode == OptMode.FIND_MIN_HEIGHT:
        _validate_fixed_axis("width", width, min_x, tile_type.name)
        return config

    if width < min_x or height < min_y:
        raise FlowException(
            f"DIE_AREA ({width}, {height}) is smaller than the "
            f"minimum required area ({min_x}, {min_y}) for the "
            f"tile {tile_type.name}. Please update the DIE_AREA "
        )
    return config


def _validate_fixed_axis(
    axis: str, value: Decimal, minimum: Decimal, tile_name: str
) -> None:
    """Reject a user-fixed directional axis below its physical IO-pin minimum."""
    if value < minimum:
        raise FlowException(
            f"Fixed {axis} ({value}) is smaller than the minimum required "
            f"{axis} ({minimum}) to fit the IO pins of tile {tile_name}. "
            f"Increase the DIE_AREA {axis} or pick a different optimisation mode."
        )
