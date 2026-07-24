"""Nextpnr model generation for FABulous FPGA fabrics.

This module provides functionality to generate nextpnr models from FABulous fabric
definitions. The nextpnr model includes detailed descriptions of programmable
interconnect points (PIPs), basic elements of logic (BELs), and routing resources needed
for place-and-route operations.

The generated models enable nextpnr to understand the fabric architecture and perform
placement and routing for user designs.
"""

import string
from pathlib import Path

from fabulous.custom_exception import InvalidState
from fabulous.fabric_cad.timing_model.FABulous_timing_model_interface import (
    FABulousTimingModelInterface,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile

# Dummy BEL timing values (ns), mirroring nextpnr's historical hardcoded
# constants (fabulous.cc, seed_default_estimates).
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
# Static until a real timing model exists; reproduces nextpnr's old default.
BASE_DELAY_DEFAULT = 3.0

# Extra nextpnr tunables written to placement_estimate.txt. Values reproduce
# nextpnr's historical hardcoded defaults, so P&R behaviour is unchanged.
DELAY_EPSILON = 0.25
RIPUP_PENALTY = 0.5
CARRY_PREDICT_DELAY = 0.5

# Arbitrary placeholder pip delay used when no delay_model is supplied.
DUMMY_PIP_DELAY = 8

# Representative per-type timing arcs for nextpnr's placement estimate.
# Static while every instance of a type shares these constants (I0-I3 LUT4);
# a real per-instance timing model would regenerate this.
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


# Full static placement_estimate.txt content: nextpnr placer/router tunables
# plus one representative estimate block per timed BEL type. All values
# reproduce nextpnr's historical hardcoded defaults, so P&R behaviour is
# unchanged.
PLACEMENT_ESTIMATE_TEXT: str = (
    "\n".join(
        [
            f"delayScale={BASE_DELAY_DEFAULT}",
            f"delayOffset={BASE_DELAY_DEFAULT}",
            f"delayEpsilon={DELAY_EPSILON}",
            f"ripupPenalty={RIPUP_PENALTY}",
            f"carryPredictDelay={CARRY_PREDICT_DELAY}",
            "BelBegin,FABULOUS_LC",
            *LC_ESTIMATE_LINES,
            "BelEnd",
            "BelBegin,OutPass4_frame_config",
            *[f"SetupHold,I{p},CLK,{IO_SETUP},{IO_HOLD}" for p in range(4)],
            "BelEnd",
            "BelBegin,OutPass4_frame_config_mux",
            *[f"SetupHold,I{p},CLK,{IO_SETUP},{IO_HOLD}" for p in range(4)],
            "BelEnd",
            "BelBegin,InPass4_frame_config",
            *[f"ClkToOut,O{p},CLK,{IO_CLK_TO_OUT}" for p in range(4)],
            "BelEnd",
            "BelBegin,InPass4_frame_config_mux",
            *[f"ClkToOut,O{p},CLK,{IO_CLK_TO_OUT}" for p in range(4)],
            "BelEnd",
        ]
    )
    + "\n"
)

# BEL types whose ports are exposed as fabric pins in the per-tile
# loop; a matching BEL gets a `set_io` constraint line.
IO_BEL_TYPES = (
    "IO_1_bidirectional_frame_config_pass",
    "InPass4_frame_config",
    "OutPass4_frame_config",
    "InPass4_frame_config_mux",
    "OutPass4_frame_config_mux",
)


def belLines(
    bel: Bel, letter: str, x: int, y: int
) -> tuple[str, list[str], list[str], list[str]]:
    """Build a BEL's legacy v1 line, its v2/v3 blocks, and any pin constraint.

    The bel.v3 block additionally carries timing-arc lines, but only for the
    BEL types nextpnr currently times (``FABULOUS_LC``, ``InPass4_frame_config``,
    ``OutPass4_frame_config`` and their ``_mux`` variants); every other type
    gets no arcs so no new timing paths are introduced.

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
    cType = bel.name
    if bel.name in ("LUT4c_frame_config", "LUT4c_frame_config_dffesr"):
        cType = "FABULOUS_LC"
    v1_line = (
        f"X{x}Y{y},X{x},Y{y},{letter},{cType},"
        f"{','.join(bel.input_names + bel.output_names)}"
    )
    inputs = [p.removeprefix(bel.prefix) for p in bel.input_names]
    outputs = [p.removeprefix(bel.prefix) for p in bel.output_names]

    def block(timing: bool) -> list[str]:
        lines = [f"BelBegin,X{x}Y{y},{letter},{cType},{bel.prefix}"]
        for inp, stripped in zip(bel.input_names, inputs, strict=True):
            lines.append(f"I,{stripped},X{x}Y{y}.{inp}")
        for outp, stripped in zip(bel.output_names, outputs, strict=True):
            lines.append(f"O,{stripped},X{x}Y{y}.{outp}")
        for feat, _cfg in sorted(bel.bel_feature_map.items(), key=lambda x: x[0]):
            lines.append(f"CFG,{feat}")
        if timing and cType == "FABULOUS_LC":
            lutInputs = [p for p in inputs if p.startswith("I") and p[1:].isdigit()]
            lines.append("Clock,CLK,FF=1")
            # Combinational (LUT) mode: active when the FF is disabled.
            for p in lutInputs:
                lines.append(f"Delay,{p},O,{LUT_DELAY},FF=0")
            lines.append(f"Delay,Ci,O,{LUT_DELAY},FF=0&I0MUX=1")
            # Carry chain: active when carry-in or carry-out is connected.
            lines.append(f"Delay,Ci,Co,{CARRY_CICO_DELAY},Ci/Co?")
            lines.append(f"Delay,I1,Co,{CARRY_I_DELAY},Ci/Co?")
            lines.append(f"Delay,I2,Co,{CARRY_I_DELAY},Ci/Co?")
            # Registered (FF) mode.
            for p in lutInputs:
                lines.append(f"SetupHold,{p},CLK,{FF_SETUP},{FF_HOLD},FF=1")
            lines.append(f"SetupHold,Ci,CLK,{FF_SETUP},{FF_HOLD},FF=1&I0MUX=1")
            # Q is the cell's renamed FF output (pack.cc renames O -> Q when
            # used); clock-to-Q is BEL-internal, not derivable from pip delay.
            lines.append(f"ClkToOut,Q,CLK,{FF_CLK_TO_Q},FF=1")
        elif timing and cType.startswith("OutPass4_frame_config"):
            for p in inputs:
                if p.startswith("I") and p[1:].isdigit():
                    lines.append(f"SetupHold,{p},CLK,{IO_SETUP},{IO_HOLD}")
        elif timing and cType.startswith("InPass4_frame_config"):
            for p in outputs:
                if p.startswith("O") and p[1:].isdigit():
                    lines.append(f"ClkToOut,{p},CLK,{IO_CLK_TO_OUT}")
        if bel.with_user_clock:
            lines.append("GlobalClk")
        lines.append("BelEnd")
        return lines

    v2_lines = block(timing=False)
    v3_lines = block(timing=True)

    constrain_lines = (
        [f"set_io Tile_X{x}Y{y}_{letter} Tile_X{x}Y{y}.{letter}"]
        if bel.name in IO_BEL_TYPES
        else []
    )

    return v1_line, v2_lines, v3_lines, constrain_lines


def composite_master_fabric_coords(
    fabric: Fabric, composite: Tile
) -> list[tuple[int, int]]:
    """Return the master cell's fabric coordinate for each composite placement.

    The composite's wrapper BELs and config bits physically live at its master
    cell. ``get_master_offset`` gives the master's TOP-FIRST ``tile_map`` index
    ``(mx, my)``; the fabric grid is stored bottom row first, so the master's
    fabric offset within a placement is ``(mx, (max_height - 1) - my)``. One master
    coordinate is emitted per real placement, using the per-placement bottom-left
    origins from :meth:`Fabric.find_composite_placement_origins` (which is correct
    even for contiguous repeated placements of the same composite).

    Parameters
    ----------
    fabric : Fabric
        The fabric whose grid is scanned for placements of the composite.
    composite : Tile
        The composite tile to locate.

    Returns
    -------
    list[tuple[int, int]]
        One ``(x, y)`` master fabric coordinate per placement.
    """
    mx, my = composite.get_master_offset()
    master_dy = (composite.max_height - 1) - my
    return [
        (base_fx + mx, base_fy + master_dy)
        for base_fx, base_fy in fabric.find_composite_placement_origins(composite)
    ]


def genNextpnrModel(
    fabric: Fabric, delay_model: FABulousTimingModelInterface = None
) -> tuple[str, str, str, str, str]:
    """Generate the fabric's nextpnr model.

    Parameters
    ----------
    fabric : Fabric
        Fabric object containing tile information.
    delay_model : FABulousTimingModelInterface, optional
        Timing model interface to provide delay information, by default None.

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
            for source, sinkList in tile.switch_matrix.connections.items():
                for sink in sinkList:
                    delay: float = DUMMY_PIP_DELAY
                    if delay_model is not None:
                        delay = delay_model.pip_delay(tile.name, sink, source)
                    pipStr.append(
                        f"X{x}Y{y},{sink},X{x}Y{y},{source},{delay},{sink}.{source}"
                    )

            pipStr.append(f"#Tile-external pips on tile X{x}Y{y}:")
            for wire in tile.wire_list:
                xDst = x + wire.x_offset
                yDst = y + wire.y_offset
                if (not (0 <= xDst <= fabric.numberOfColumns)) or (
                    not (0 <= yDst <= fabric.numberOfRows)
                ):
                    raise InvalidState(
                        f"Wire {wire} in tile X{x}Y{y} points to an invalid tile "
                        f"X{xDst}Y{yDst}. "
                        "Please check your tile CSV file for unmatching wires/offsets!"
                    )

                delay: float = DUMMY_PIP_DELAY
                if delay_model is not None:
                    delay = delay_model.pip_delay(
                        tile.name,
                        wire.source,
                        wire.destination,
                    )
                pipStr.append(
                    f"X{x}Y{y},{wire.source},"
                    f"X{x + wire.x_offset}Y{y + wire.y_offset},{wire.destination},"
                    f"{delay},"
                    f"{wire.source}.{wire.destination}"
                )

            # BEL definitions: legacy v1, and new-style v2 / v3 (with timing arcs).
            belStr.append(f"#Tile_X{x}Y{y}")
            belv2Str.append(f"#Tile_X{x}Y{y}")
            belv3Str.append(f"#Tile_X{x}Y{y}")
            for i, bel in enumerate(tile.bels):
                letter = string.ascii_uppercase[i]
                v1_line, v2_lines, v3_lines, constrain_lines = belLines(
                    bel, letter, x, y
                )
                belStr.append(v1_line)
                belv2Str.extend(v2_lines)
                belv3Str.extend(v3_lines)
                constrainStr.extend(constrain_lines)

    # Composite wrapper BEL and switch-matrix PIP emission. A composite tile's
    # wrapper BELs and unified switch matrix physically live at its master cell,
    # so they are emitted at the master cell's fabric coordinate. The per-cell
    # internal PIPs of the sub-tiles are already emitted by the per-tile loop
    # above (the fabric grid is flattened to leaf tiles).
    for composite in fabric.get_all_unique_tiles():
        if not composite.is_composite:
            continue
        if not composite.bels and composite.matrix_dir == Path():
            continue

        for ftx, fty in composite_master_fabric_coords(fabric, composite):
            bel_offset = len(fabric.tile[fty][ftx].bels)
            belStr.append(f"#Composite_{composite.name}_X{ftx}Y{fty}")
            belv2Str.append(f"#Composite_{composite.name}_X{ftx}Y{fty}")
            belv3Str.append(f"#Composite_{composite.name}_X{ftx}Y{fty}")
            for i, bel in enumerate(composite.bels):
                letter = string.ascii_uppercase[bel_offset + i]
                v1_line, v2_lines, v3_lines, constrain_lines = belLines(
                    bel, letter, ftx, fty
                )
                belStr.append(v1_line)
                belv2Str.extend(v2_lines)
                belv3Str.extend(v3_lines)
                constrainStr.extend(constrain_lines)

            for sink, sources in composite.switch_matrix.connections.items():
                for src in sources:
                    delay: float = DUMMY_PIP_DELAY
                    if delay_model is not None:
                        delay = delay_model.pip_delay(composite.name, sink, src)
                    pipStr.append(
                        f"X{ftx}Y{fty},{src},X{ftx}Y{fty},{sink},{delay},{src}.{sink}"
                    )

    return (
        "\n".join(pipStr),
        "\n".join(belStr),
        "\n".join(belv2Str),
        "\n".join(belv3Str),
        "\n".join(constrainStr),
    )


def writeNextpnrPipFile(
    fabric: Fabric,
    outputFile: Path,
    delay_model: FABulousTimingModelInterface = None,
) -> None:
    """Write the nextpnr pip file for the given fabric.

    Parameters
    ----------
    fabric : Fabric
        Fabric object containing tile information.
    outputFile : Path
        File to write the pip information to.
    delay_model : FABulousTimingModelInterface, optional
        Timing model interface to provide delay information, by default None.
    """
    pip_str, *_ = genNextpnrModel(fabric, delay_model)
    outputFile.write_text(pip_str, encoding="utf-8")
