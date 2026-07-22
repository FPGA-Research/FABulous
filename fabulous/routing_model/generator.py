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
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.cell_spec import (
    STD_CELL_LIBRARY_RELPATH,
    StdCellLibrary,
)
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix
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

IO_BEL_TYPES = frozenset(
    {
        "IO_1_bidirectional_frame_config_pass",
        "InPass4_frame_config",
        "OutPass4_frame_config",
        "InPass4_frame_config_mux",
        "OutPass4_frame_config_mux",
    }
)
"""BEL names whose ports are fabric pins, so they get a `set_io` constraint."""

# Dummy BEL-internal timing (ns), mirroring nextpnr's historical hardcoded
# constants (fabulous.cc, update_cell_timing). These are cell-implementation
# properties, unrelated to interconnect: the routing model's extracted pip
# delays never feed them, and they stay fixed in every timing mode.
LUT_DELAY = 3.0
CARRY_CICO_DELAY = 0.2
CARRY_I_DELAY = 1.0
FF_SETUP = 2.5
FF_HOLD = 0.1
FF_CLK_TO_Q = 1.0
IO_SETUP = 2.5
IO_HOLD = 0.1
IO_CLK_TO_OUT = 2.5

# Base delay (ns) for nextpnr's placement heuristic (placement_estimate.txt).
# Static until a real BEL timing model exists; reproduces nextpnr's old default.
BASE_DELAY_DEFAULT = 3.0

# Extra nextpnr tunables written to placement_estimate.txt. Values reproduce
# nextpnr's historical hardcoded defaults, so P&R behaviour is unchanged.
DELAY_EPSILON = 0.25
RIPUP_PENALTY = 0.5
CARRY_PREDICT_DELAY = 0.5

# Representative FABULOUS_LC timing arcs for nextpnr's placement estimate.
# Static while every LC instance shares these constants (I0-I3 LUT4); a real
# per-instance timing model would regenerate this.
_LC_LUT_INPUTS = ("I0", "I1", "I2", "I3")
LC_ESTIMATE_LINES: list[str] = [
    "Clock,CLK,FF=1",
    *[f"Delay,{p},O,{LUT_DELAY},FF=0" for p in _LC_LUT_INPUTS],
    f"Delay,Ci,O,{LUT_DELAY},FF=0&I0MUX=1",
    f"Delay,Ci,Co,{CARRY_CICO_DELAY},Ci/Co?",
    f"Delay,I1,Co,{CARRY_I_DELAY},Ci/Co?",
    f"Delay,I2,Co,{CARRY_I_DELAY},Ci/Co?",
    *[f"SetupHold,{p},CLK,{FF_SETUP},{FF_HOLD},FF=1" for p in _LC_LUT_INPUTS],
    f"SetupHold,Ci,CLK,{FF_SETUP},{FF_HOLD},FF=1&I0MUX=1",
    f"ClkToOut,Q,CLK,{FF_CLK_TO_Q},FF=1",
]

PLACEMENT_ESTIMATE_TEXT: str = (
    "\n".join(
        [
            f"delayScale={BASE_DELAY_DEFAULT}",
            f"delayOffset={BASE_DELAY_DEFAULT}",
            f"delayEpsilon={DELAY_EPSILON}",
            f"ripupPenalty={RIPUP_PENALTY}",
            f"carryPredictDelay={CARRY_PREDICT_DELAY}",
            *LC_ESTIMATE_LINES,
        ]
    )
    + "\n"
)
"""Static `placement_estimate.txt`: nextpnr tunables plus one FABULOUS_LC block."""


def bel_lines(
    bel: Bel, letter: str, x: int, y: int
) -> tuple[str, list[str], list[str], list[str]]:
    """Build a BEL's legacy v1 line, its v2/v3 blocks, and any pin constraint.

    The v2 and v3 blocks share one structural definition; only v3 additionally
    carries the BEL-internal timing arcs for the types nextpnr times.

    Parameters
    ----------
    bel : Bel
        The BEL to describe.
    letter : str
        The BEL's Z-position letter within its tile.
    x : int
        Tile X coordinate the BEL belongs to.
    y : int
        Tile Y coordinate the BEL belongs to.

    Returns
    -------
    tuple[str, list[str], list[str], list[str]]
        `(v1_line, v2_lines, v3_lines, constrain_lines)` - the legacy bel.txt
        line, the bel.v2/bel.v3 block lines, and zero or one `set_io` line.
    """
    c_type = "FABULOUS_LC" if bel.name in LC_BEL_NAMES else bel.name
    bel_ports = ",".join(bel.inputs + bel.outputs)
    v1_line = f"X{x}Y{y},X{x},Y{y},{letter},{c_type},{bel_ports}"
    inputs = [p.removeprefix(bel.prefix) for p in bel.inputs]
    outputs = [p.removeprefix(bel.prefix) for p in bel.outputs]

    def block(timing: bool) -> list[str]:
        lines = [f"BelBegin,X{x}Y{y},{letter},{c_type},{bel.prefix}"]
        for inp, stripped in zip(bel.inputs, inputs, strict=True):
            lines.append(f"I,{stripped},X{x}Y{y}.{inp}")
        for outp, stripped in zip(bel.outputs, outputs, strict=True):
            lines.append(f"O,{stripped},X{x}Y{y}.{outp}")
        for feat, _cfg in sorted(bel.belFeatureMap.items(), key=lambda x: x[0]):
            lines.append(f"CFG,{feat}")
        if timing and c_type == "FABULOUS_LC":
            lut_inputs = [p for p in inputs if p.startswith("I") and p[1:].isdigit()]
            lines.append("Clock,CLK,FF=1")
            # Combinational (LUT) mode: active when the FF is disabled.
            for p in lut_inputs:
                lines.append(f"Delay,{p},O,{LUT_DELAY},FF=0")
            lines.append(f"Delay,Ci,O,{LUT_DELAY},FF=0&I0MUX=1")
            # Carry chain: active when carry-in or carry-out is connected.
            lines.append(f"Delay,Ci,Co,{CARRY_CICO_DELAY},Ci/Co?")
            lines.append(f"Delay,I1,Co,{CARRY_I_DELAY},Ci/Co?")
            lines.append(f"Delay,I2,Co,{CARRY_I_DELAY},Ci/Co?")
            # Registered (FF) mode.
            for p in lut_inputs:
                lines.append(f"SetupHold,{p},CLK,{FF_SETUP},{FF_HOLD},FF=1")
            lines.append(f"SetupHold,Ci,CLK,{FF_SETUP},{FF_HOLD},FF=1&I0MUX=1")
            # Q is the cell's renamed FF output (pack.cc renames O -> Q when
            # used); clock-to-Q is BEL-internal, not derivable from pip delay.
            lines.append(f"ClkToOut,Q,CLK,{FF_CLK_TO_Q},FF=1")
        elif timing and c_type.startswith("OutPass4_frame_config"):
            for p in inputs:
                if p.startswith("I") and p[1:].isdigit():
                    lines.append(f"SetupHold,{p},CLK,{IO_SETUP},{IO_HOLD}")
        elif timing and c_type.startswith("InPass4_frame_config"):
            for p in outputs:
                if p.startswith("O") and p[1:].isdigit():
                    lines.append(f"ClkToOut,{p},CLK,{IO_CLK_TO_OUT}")
        if bel.withUserCLK:
            lines.append("GlobalClk")
        lines.append("BelEnd")
        return lines

    constrain_lines = (
        [f"set_io Tile_X{x}Y{y}_{letter} Tile_X{x}Y{y}.{letter}"]
        if bel.name in IO_BEL_TYPES
        else []
    )

    return v1_line, block(timing=False), block(timing=True), constrain_lines


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

    def generate(self) -> tuple[str, str, str, str, str]:
        """Generate the fabric's nextpnr model.

        Returns
        -------
        tuple[str, str, str, str, str]
            - pipStr: A string with tile-internal and tile-external pip descriptions.
            - belStr: A string with old style BEL definitions.
            - belv2Str: A string with new style BEL definitions.
            - belv3Str: A string with new style BEL definitions including timing.
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
        belv3Str = []
        belStr.append(
            f"# BEL descriptions: top left corner Tile_X0Y0,"
            f" bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
        )
        belv2Str.append(
            f"# BEL descriptions: top left corner Tile_X0Y0, "
            f"bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
        )
        belv3Str.append(
            f"# BEL descriptions: top left corner Tile_X0Y0, "
            f"bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
        )
        constrainStr = []

        for y, row in enumerate(fabric.tile):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                pipStr.append(f"#Tile-internal pips on tile X{x}Y{y}:")
                for source, sinks in tile.switch_matrix.connections.items():
                    for sink in sinks:
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

                # BEL definitions: legacy v1, and new-style v2 / v3 (with timing).
                belStr.append(f"#Tile_X{x}Y{y}")
                belv2Str.append(f"#Tile_X{x}Y{y}")
                belv3Str.append(f"#Tile_X{x}Y{y}")
                for i, bel in enumerate(tile.bels):
                    letter = string.ascii_uppercase[i]
                    v1_line, v2_lines, v3_lines, constrain_lines = bel_lines(
                        bel, letter, x, y
                    )
                    belStr.append(v1_line)
                    belv2Str.extend(v2_lines)
                    belv3Str.extend(v3_lines)
                    constrainStr.extend(constrain_lines)

        # Supertile BEL and switch-matrix pip emission. A BEL hosted in a
        # supertile's master tile shares the master tile's BEL letter space, so its
        # letters continue after the master tile's own BELs. SJUMP pips live in
        # tile.wireList (added by Fabric.__post_init__) and are already emitted by
        # the per-tile loop above.
        for base_fx, base_fy, super_tile in fabric.iter_super_tile_placements():
            if not super_tile.bels and super_tile.supertile_matrix_dir is None:
                continue

            tx_local, ty_local = super_tile.get_master_tile_coords()
            ftx = base_fx + tx_local
            fty = base_fy + ty_local

            bel_offset = len(fabric.tile[fty][ftx].bels)
            belStr.append(f"#SuperTile_{super_tile.name}_X{ftx}Y{fty}")
            belv2Str.append(f"#SuperTile_{super_tile.name}_X{ftx}Y{fty}")
            belv3Str.append(f"#SuperTile_{super_tile.name}_X{ftx}Y{fty}")
            for i, bel in enumerate(super_tile.bels):
                letter = string.ascii_uppercase[bel_offset + i]
                v1_line, v2_lines, v3_lines, constrain_lines = bel_lines(
                    bel, letter, ftx, fty
                )
                belStr.append(v1_line)
                belv2Str.extend(v2_lines)
                belv3Str.extend(v3_lines)
                constrainStr.extend(constrain_lines)

            if super_tile.supertile_matrix_dir is not None:
                mat_path = super_tile.supertile_matrix_dir
                if mat_path.suffix == ".list":
                    sm_connections: dict[str, list[str]] = {}
                    for dest, src in parseList(mat_path):
                        sm_connections.setdefault(dest, []).append(src)
                else:
                    sm_connections = parseMatrix(mat_path, super_tile.name)
                for sink, sources in sm_connections.items():
                    for src in sources:
                        delay = self._pip_delay(super_tile.name, sink, src)
                        pipStr.append(
                            f"X{ftx}Y{fty},{src},X{ftx}Y{fty},{sink},"
                            f"{delay},{src}.{sink}"
                        )

        return (
            "\n".join(pipStr),
            "\n".join(belStr),
            "\n".join(belv2Str),
            "\n".join(belv3Str),
            "\n".join(constrainStr),
        )

    def write_pip_file(self, output_file: Path) -> None:
        """Write the nextpnr pip file for the fabric.

        Parameters
        ----------
        output_file : Path
            File to write the pip information to.
        """
        pip_str, *_ = self.generate()
        output_file.write_text(pip_str, encoding="utf-8")
