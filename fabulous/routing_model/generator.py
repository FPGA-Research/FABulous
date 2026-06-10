"""Cohesive nextpnr routing-model generation for FABulous fabrics.

`RoutingModelGenerator` emits the nextpnr model (programmable interconnect points,
basic elements of logic, and placement constraints) for a fabric. Timing is an
optional flag: with no ``mode`` every pip carries a placeholder delay; with a
``mode`` the generator extracts per-pip routing delays from synthesis- and
physical-level timing models, caching results per tile.
"""

import string
from pathlib import Path

from loguru import logger

from fabulous.custom_exception import InvalidState
from fabulous.fabric_definition.cell_spec import (
    STD_CELL_LIBRARY_RELPATH,
    StdCellLibrary,
)
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabulous_settings import get_context
from fabulous.routing_model.graph_algorithms import DelayType
from fabulous.routing_model.tile_timing_model import (
    FABulousTileTimingModel,
    TimingModelMode,
)

PLACEHOLDER_PIP_DELAY = 8
"""Arbitrary pip delay used when no timing model is configured."""

LC_BEL_NAMES = frozenset({"LUT4c_frame_config", "LUT4c_frame_config_dffesr"})
"""BEL names nextpnr models as the generic FABULOUS_LC logic cell."""


class RoutingModelGenerator:
    """Generate the nextpnr routing model for a fabric, optionally with timing.

    Parameters
    ----------
    fabric : Fabric
        Fabric object containing tile information.
    mode : TimingModelMode
        Timing mode. In :attr:`TimingModelMode.PLACEHOLDER` (the default) every pip
        uses :data:`PLACEHOLDER_PIP_DELAY`; otherwise per-pip delays are extracted
        from the timing models built in the given mode.
    consider_wire_delay : bool
        Whether to include wire delay in the physical analysis, by default True.
    delay_type : DelayType
        How multi-corner delays are collapsed to a scalar, by default
        DelayType.MAX_ALL.
    delay_scaling_factor : float
        Scaling factor applied to computed delays, by default 1.0.
    verilog_files : list[Path] | None
        Fabric Verilog source files used to build the per-tile timing models.
        Required when ``mode`` is given, ignored otherwise, by default None.

    Raises
    ------
    ValueError
        If ``mode`` is given without ``verilog_files``, the PDK is not set, or no
        standard-cell liberty is resolved for the active PDK.
    """

    def __init__(
        self,
        fabric: Fabric,
        mode: TimingModelMode = TimingModelMode.PLACEHOLDER,
        consider_wire_delay: bool = True,
        delay_type: DelayType = DelayType.MAX_ALL,
        delay_scaling_factor: float = 1.0,
        verilog_files: list[Path] | None = None,
    ) -> None:
        self.fabric: Fabric = fabric
        self.mode: TimingModelMode = mode

        # Per-tile timing engines and a per-tile pip-delay cache. Both stay empty
        # in placeholder mode; building the engines synthesizes RTL per tile, so it
        # only happens when real delays are requested.
        self._tile_models: dict[str, FABulousTileTimingModel] = {}
        self._delay_cache: dict[str, dict[str, float]] = {}

        # Placeholder mode uses a constant pip delay: no synthesis, no
        # standard-cell library, and no per-tile engines.
        if mode is TimingModelMode.PLACEHOLDER:
            return

        if verilog_files is None:
            raise ValueError("verilog_files is required when timing is enabled.")
        ctx = get_context()
        if ctx.pdk is None:
            raise ValueError("FAB_PDK is not set; cannot build the timing model.")
        # Placeholder values for ${VAR} references in the library's liberty /
        # techmap paths, sourced from the active settings.
        variables = {"PROJ_DIR": str(ctx.proj_dir), "PDK": ctx.pdk}
        if ctx.pdk_root is not None:
            variables["PDK_ROOT"] = str(ctx.pdk_root)
        # Load the standard-cell library once and fail fast before the per-tile
        # loop if the PDK has no liberty configured.
        library = StdCellLibrary.load(ctx.proj_dir, ctx.pdk, variables)
        if not library.liberty_files:
            raise ValueError(
                f"No liberty files configured for PDK {ctx.pdk!r}. "
                f"Set 'liberty_files' in {STD_CELL_LIBRARY_RELPATH} to "
                "characterize timing."
            )
        logger.info(f"Initializing timing models for tiles, with mode: {mode}")
        for tile_name in self.fabric.tileDic:
            self._tile_models[tile_name] = FABulousTileTimingModel(
                fabric=self.fabric,
                verilog_files=verilog_files,
                tile_name=tile_name,
                mode=mode,
                consider_wire_delay=consider_wire_delay,
                delay_type=delay_type,
                delay_scaling_factor=delay_scaling_factor,
                library=library,
            )

    def _pip_delay(self, tile_name: str, src_pip: str, dst_pip: str) -> float:
        """Return the delay of a pip, using the timing model when configured.

        Without a timing mode the placeholder delay is returned. Otherwise the
        per-tile timing engine computes the delay, and the result is cached so a
        repeated ``src_pip`` -> ``dst_pip`` lookup in the same tile is not recomputed.

        Parameters
        ----------
        tile_name : str
            Name of the tile, including the super-tile type when applicable.
        src_pip : str
            Source pip name.
        dst_pip : str
            Destination pip name.

        Returns
        -------
        float
            Delay of the pip.

        Raises
        ------
        ValueError
            If no timing model exists for ``tile_name``.
        """
        if self.mode is TimingModelMode.PLACEHOLDER:
            return PLACEHOLDER_PIP_DELAY

        if tile_name not in self._tile_models:
            raise ValueError(f"Timing model for tile {tile_name!r} not found.")

        key = f"{src_pip}.{dst_pip}"
        tile_cache = self._delay_cache.setdefault(tile_name, {})
        if key in tile_cache:
            logger.info(
                f"Using cached delay for key {key!r} in tile {tile_name!r} "
                f"with delay {tile_cache[key]}"
            )
            return tile_cache[key]

        delay = self._tile_models[tile_name].pip_delay(src_pip, dst_pip)
        tile_cache[key] = delay
        return delay

    def generate(self) -> tuple[str, str, str, str]:
        """Generate the fabric's nextpnr model.

        Returns
        -------
        tuple[str, str, str, str]
            - pipStr: A string with tile-internal and tile-external pip descriptions.
            - belStr: A string with old style BEL definitions.
            - belv2Str: A string with new style BEL definitions.
            - constrainStr: A string with constraint definitions.

        Raises
        ------
        InvalidState
            If a wire in a tile points to an invalid tile outside the fabric bounds.
        """
        fabric = self.fabric
        pipStr = []
        belStr = []
        belv2Str = []
        belStr.append(
            f"# BEL descriptions: top left corner Tile_X0Y0,"
            f" bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
        )
        belv2Str.append(
            f"# BEL descriptions: top left corner Tile_X0Y0, "
            f"bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
        )
        constrainStr = []

        for y, row in enumerate(fabric.tile):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                pipStr.append(f"#Tile-internal pips on tile X{x}Y{y}:")
                for source, sink in tile.switch_matrix.pips():
                    delay = self._pip_delay(tile.name, sink, source)
                    pipStr.append(
                        f"X{x}Y{y},{sink},X{x}Y{y},{source},{delay},{sink}.{source}"
                    )

                pipStr.append(f"#Tile-external pips on tile X{x}Y{y}:")
                for wire in tile.wireList:
                    xDst = x + wire.xOffset
                    yDst = y + wire.yOffset
                    if (not (0 <= xDst <= fabric.numberOfColumns)) or (
                        not (0 <= yDst <= fabric.numberOfRows)
                    ):
                        raise InvalidState(
                            f"Wire {wire} in tile X{x}Y{y} points to an invalid tile "
                            f"X{xDst}Y{yDst}. "
                            "Please check your tile CSV file for unmatching "
                            "wires/offsets!"
                        )

                    delay = self._pip_delay(tile.name, wire.source, wire.destination)
                    pipStr.append(
                        f"X{x}Y{y},{wire.source},"
                        f"X{x + wire.xOffset}Y{y + wire.yOffset},{wire.destination},"
                        f"{delay},"
                        f"{wire.source}.{wire.destination}"
                    )

                # Old style bel definition
                belStr.append(f"#Tile_X{x}Y{y}")
                for i, bel in enumerate(tile.bels):
                    belPort = bel.inputs + bel.outputs
                    cType = "FABULOUS_LC" if bel.name in LC_BEL_NAMES else bel.name
                    letter = string.ascii_uppercase[i]
                    belStr.append(
                        f"X{x}Y{y},X{x},Y{y},{letter},{cType},{','.join(belPort)}"
                    )

                    if bel.name in [
                        "IO_1_bidirectional_frame_config_pass",
                        "InPass4_frame_config",
                        "OutPass4_frame_config",
                        "InPass4_frame_config_mux",
                        "OutPass4_frame_config_mux",
                    ]:
                        constrainStr.append(
                            f"set_io Tile_X{x}Y{y}_{letter} Tile_X{x}Y{y}.{letter}"
                        )
                # New style bel definition
                belv2Str.append(f"#Tile_X{x}Y{y}")
                for i, bel in enumerate(tile.bels):
                    cType = "FABULOUS_LC" if bel.name in LC_BEL_NAMES else bel.name
                    letter = string.ascii_uppercase[i]
                    belv2Str.append(f"BelBegin,X{x}Y{y},{letter},{cType},{bel.prefix}")

                    for inp in bel.inputs:
                        belv2Str.append(
                            f"I,{inp.removeprefix(bel.prefix)},X{x}Y{y}.{inp}"
                        )  # I,<port>,<wire>
                    for outp in bel.outputs:
                        belv2Str.append(
                            f"O,{outp.removeprefix(bel.prefix)},X{x}Y{y}.{outp}"
                        )  # O,<port>,<wire>
                    for feat, _cfg in sorted(
                        bel.belFeatureMap.items(), key=lambda x: x[0]
                    ):
                        belv2Str.append(f"CFG,{feat}")
                    if bel.withUserCLK:
                        belv2Str.append("GlobalClk")
                    belv2Str.append("BelEnd")
        return (
            "\n".join(pipStr),
            "\n".join(belStr),
            "\n".join(belv2Str),
            "\n".join(constrainStr),
        )

    def write_pip_file(self, output_file: Path) -> None:
        """Write the nextpnr pip file for the fabric.

        Parameters
        ----------
        output_file : Path
            File to write the pip information to.
        """
        pip_str, _, _, _ = self.generate()
        output_file.write_text(pip_str, encoding="utf-8")
