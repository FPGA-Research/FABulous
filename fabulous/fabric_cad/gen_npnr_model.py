"""Nextpnr model generation for FABulous FPGA fabrics.

Emit the files nextpnr reads (pips, BELs, pin constraints, placement estimate)
as a pure function of a fabric and its `TimingDb`. This module owns every
nextpnr rule: file formats, cell types, pin renames and the placeholder timing
that reproduces nextpnr's historical hardcoded constants.
"""

import string
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from loguru import logger

from fabulous.custom_exception import InvalidState
from fabulous.fabric_cad.timing_db import (
    AnyConnected,
    BelArcs,
    BelPin,
    BelTiming,
    ClockArc,
    ClockToOutArc,
    Condition,
    DelayArc,
    FeatureIs,
    Ns,
    Pip,
    PipTiming,
    SetupHoldArc,
    SwitchPip,
    TimingDb,
    WirePip,
    ns,
    switch_pips,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.wire import Wire

# Dummy BEL timing values (ns), mirroring nextpnr's historical hardcoded
# constants (fabulous.cc, seed_default_estimates).
LUT_DELAY = ns(3.0)
CARRY_CICO_DELAY = ns(0.2)
CARRY_I_DELAY = ns(1.0)
FF_SETUP = ns(2.5)
FF_HOLD = ns(0.1)
FF_CLK_TO_Q = ns(1.0)
IO_SETUP = ns(2.5)
IO_HOLD = ns(0.1)
IO_CLK_TO_OUT = ns(2.5)

# Clock arrival time at a flop, written per BEL in bel.v3.txt. Identical
# everywhere until characterisation exists, so zero skew: only differences
# between flops produce skew.
CLOCK_DELAY = ns(1.0)

# Base delay (ns) for nextpnr's placement heuristic (placement_estimate.txt).
# Static until a real timing model exists; reproduces nextpnr's old default.
BASE_DELAY_DEFAULT = 3.0

# Extra nextpnr tunables written to placement_estimate.txt. Values reproduce
# nextpnr's historical hardcoded defaults, so P&R behaviour is unchanged.
DELAY_EPSILON = 0.25
RIPUP_PENALTY = 0.5
CARRY_PREDICT_DELAY = 0.5

# Arbitrary placeholder pip delay used when pips are not characterised.
DUMMY_PIP_DELAY = ns(8)

# Nanoseconds per unit of the pips.txt delay column. 0.05 reproduces nextpnr's
# historical hardcoded factor; characterised pips in real nanoseconds would
# need 1.0.
PIP_DELAY_SCALE = 0.05

_LOGIC_CELLS = frozenset(
    {"FABULOUS_LC", "LUT4c_frame_config", "LUT4c_frame_config_dffesr"}
)

# BEL types whose ports are exposed as fabric pins; each gets a `set_io` line.
_PINNED_IO = frozenset(
    {
        "IO_1_bidirectional_frame_config_pass",
        "InPass4_frame_config",
        "OutPass4_frame_config",
        "InPass4_frame_config_mux",
        "OutPass4_frame_config_mux",
    }
)


class CellKind(Enum):
    """The nextpnr role of a BEL type."""

    LOGIC_CELL = auto()
    OUT_PASS = auto()
    IN_PASS = auto()
    OTHER = auto()


@dataclass(frozen=True, slots=True)
class NextpnrBel:
    """How nextpnr sees a BEL type.

    Attributes
    ----------
    cell_type : str
        nextpnr cell type: `FABULOUS_LC` for a logic cell, else the BEL name.
    kind : CellKind
        The BEL's nextpnr role.
    pinned_io : bool
        Whether the BEL gets a `set_io` line in `template.pcf`.
    """

    cell_type: str
    kind: CellKind
    pinned_io: bool


def nextpnr_bel(bel_name: str) -> NextpnrBel:
    """Classify a BEL type for nextpnr.

    Parameters
    ----------
    bel_name : str
        The BEL type name.

    Returns
    -------
    NextpnrBel
        The nextpnr cell type, role and pin-constraint flag.
    """
    if bel_name in _LOGIC_CELLS:
        kind = CellKind.LOGIC_CELL
    elif bel_name.startswith("OutPass4_frame_config"):
        kind = CellKind.OUT_PASS
    elif bel_name.startswith("InPass4_frame_config"):
        kind = CellKind.IN_PASS
    else:
        kind = CellKind.OTHER
    return NextpnrBel(
        cell_type="FABULOUS_LC" if kind is CellKind.LOGIC_CELL else bel_name,
        kind=kind,
        pinned_io=bel_name in _PINNED_IO,
    )


def _clock_name(pin: BelPin) -> str:
    """Return the nextpnr name of a clock pin; nextpnr calls `UserCLK` `CLK`.

    Parameters
    ----------
    pin : BelPin
        Clock pin.

    Returns
    -------
    str
        The nextpnr clock-port name.
    """
    return "CLK" if pin.port == "UserCLK" else pin.name


def _render_condition(when: Condition) -> str:
    """Return the `bel.v3` condition suffix, empty for an unconditional arc.

    Parameters
    ----------
    when : Condition
        Arc condition.

    Returns
    -------
    str
        `,FF=0&I0MUX=1`, `,Ci/Co?` or the empty string.
    """
    match when:
        case AnyConnected(pins=pins):
            return "," + "/".join(pin.name for pin in pins) + "?"
        case ():
            return ""
        case features:
            return "," + "&".join(
                f"{feature.feature}={int(feature.enabled)}" for feature in features
            )


def render_arcs(arcs: BelArcs, *, kind: CellKind) -> list[str]:
    """Return the `bel.v3` timing lines of one BEL.

    On a logic cell the clock-to-out port `O` is written `Q`, because nextpnr's
    packer renames the registered output.

    Parameters
    ----------
    arcs : BelArcs
        The BEL arcs.
    kind : CellKind
        The BEL's nextpnr role.

    Returns
    -------
    list[str]
        `Clock`, `Delay`, `SetupHold` and `ClkToOut` lines in that order.

    Raises
    ------
    ValueError
        If two clock pins have the same nextpnr name.
    """
    clock_names = [_clock_name(arc.clock) for arc in arcs.clocks]
    if len(set(clock_names)) != len(clock_names):
        raise ValueError(f"Clock pins share a nextpnr name: {arcs.clocks}")
    lines = [
        f"Clock,{_clock_name(arc.clock)}{_render_condition(arc.when)}"
        for arc in arcs.clocks
    ]
    lines.extend(
        f"Delay,{arc.src.name},{arc.dst.name},{arc.delay}{_render_condition(arc.when)}"
        for arc in arcs.delays
    )
    lines.extend(
        f"SetupHold,{arc.data.name},{_clock_name(arc.clock)},{arc.setup},{arc.hold}"
        f"{_render_condition(arc.when)}"
        for arc in arcs.checks
    )
    for arc in arcs.clock_to_outs:
        out = arc.out.name
        if kind is CellKind.LOGIC_CELL and out == "O":
            out = "Q"
        lines.append(
            f"ClkToOut,{out},{_clock_name(arc.clock)},{arc.delay}"
            f"{_render_condition(arc.when)}"
        )
    return lines


def placeholder_bel_arcs(
    *, kind: CellKind, inputs: list[str], outputs: list[str]
) -> BelArcs:
    """Return the hardcoded arcs nextpnr historically used for a BEL role.

    Parameters
    ----------
    kind : CellKind
        The BEL's nextpnr role.
    inputs : list[str]
        Input port names without the BEL prefix.
    outputs : list[str]
        Output port names without the BEL prefix.

    Returns
    -------
    BelArcs
        Logic-cell, input-pass or output-pass arcs; no arcs for other BELs.
    """
    clk = BelPin("CLK")
    match kind:
        case CellKind.LOGIC_CELL:
            lut_inputs = [
                BelPin(p) for p in inputs if p.startswith("I") and p[1:].isdigit()
            ]
            ci, co, out = BelPin("Ci"), BelPin("Co"), BelPin("O")
            ff_on, ff_off = FeatureIs("FF", True), FeatureIs("FF", False)
            i0mux = FeatureIs("I0MUX", True)
            carry = AnyConnected((ci, co))
            return BelArcs(
                clocks=(ClockArc(clk, when=(ff_on,)),),
                delays=(
                    # Combinational (LUT) mode: active when the FF is disabled.
                    *(DelayArc(p, out, LUT_DELAY, when=(ff_off,)) for p in lut_inputs),
                    DelayArc(ci, out, LUT_DELAY, when=(ff_off, i0mux)),
                    DelayArc(ci, co, CARRY_CICO_DELAY, when=carry),
                    DelayArc(BelPin("I1"), co, CARRY_I_DELAY, when=carry),
                    DelayArc(BelPin("I2"), co, CARRY_I_DELAY, when=carry),
                ),
                checks=(
                    *(
                        SetupHoldArc(p, clk, FF_SETUP, FF_HOLD, when=(ff_on,))
                        for p in lut_inputs
                    ),
                    SetupHoldArc(ci, clk, FF_SETUP, FF_HOLD, when=(ff_on, i0mux)),
                ),
                clock_to_outs=(ClockToOutArc(out, clk, FF_CLK_TO_Q, when=(ff_on,)),),
            )
        case CellKind.OUT_PASS:
            return BelArcs(
                checks=tuple(
                    SetupHoldArc(BelPin(p), clk, IO_SETUP, IO_HOLD)
                    for p in inputs
                    if p.startswith("I") and p[1:].isdigit()
                )
            )
        case CellKind.IN_PASS:
            return BelArcs(
                clock_to_outs=tuple(
                    ClockToOutArc(BelPin(p), clk, IO_CLK_TO_OUT)
                    for p in outputs
                    if p.startswith("O") and p[1:].isdigit()
                )
            )
        case CellKind.OTHER:
            return BelArcs()


def _placeholder_arcs_of(bel: Bel) -> BelArcs:
    """Return `placeholder_bel_arcs` for a fabric BEL.

    Parameters
    ----------
    bel : Bel
        The BEL.

    Returns
    -------
    BelArcs
        The placeholder arcs of the BEL's nextpnr role.
    """
    return placeholder_bel_arcs(
        kind=nextpnr_bel(bel.name).kind,
        inputs=[p.removeprefix(bel.prefix) for p in bel.inputs],
        outputs=[p.removeprefix(bel.prefix) for p in bel.outputs],
    )


def wire_pips(tile: Tile) -> Iterator[tuple[Wire, WirePip]]:
    """Yield the pip of each wire of `tile`, in `wireList` order.

    Parameters
    ----------
    tile : Tile
        A placed tile.

    Yields
    ------
    tuple[Wire, WirePip]
        The wire and its pip.
    """
    for wire in tile.wireList:
        yield wire, WirePip(src=wire.source, dst=wire.destination)


def tile_pips(tile: Tile) -> Iterator[Pip]:
    """Yield the pips of `tile` in emission order: switch pips, then wire pips.

    Parameters
    ----------
    tile : Tile
        A placed tile.

    Yields
    ------
    Pip
        Each pip the emitter writes for `tile`.
    """
    yield from switch_pips(tile.switch_matrix.connections)
    for _, pip in wire_pips(tile):
        yield pip


def placeholder_timing(fabric: Fabric) -> TimingDb:
    """Return the timing nextpnr historically assumed for `fabric`.

    Every pip gets `DUMMY_PIP_DELAY` and every BEL its `placeholder_bel_arcs`.

    Parameters
    ----------
    fabric : Fabric
        The fabric.

    Returns
    -------
    TimingDb
        Placeholder pip delays and BEL arcs.
    """
    placed_pips: dict[str, dict[Pip, Ns]] = {}
    tile_bels: dict[str, dict[str, BelArcs]] = {}
    for _, tile in fabric:
        if tile is None:
            continue
        delays = placed_pips.setdefault(tile.name, {})
        for pip in tile_pips(tile):
            delays[pip] = DUMMY_PIP_DELAY
        tile_bels[tile.name] = {
            bel.instance_name: _placeholder_arcs_of(bel) for bel in tile.bels
        }
    super_tile_pips: dict[str, dict[SwitchPip, Ns]] = {}
    super_tile_bels: dict[str, dict[str, BelArcs]] = {}
    for super_tile in fabric.superTileDic.values():
        connections = (
            {}
            if super_tile.switch_matrix is None
            else super_tile.switch_matrix.connections
        )
        super_tile_pips[super_tile.name] = dict.fromkeys(
            switch_pips(connections), DUMMY_PIP_DELAY
        )
        super_tile_bels[super_tile.name] = {
            bel.instance_name: _placeholder_arcs_of(bel) for bel in super_tile.bels
        }
    return TimingDb(
        pips=PipTiming(tiles=placed_pips, super_tiles=super_tile_pips),
        bels=BelTiming(tiles=tile_bels, super_tiles=super_tile_bels),
        clock_arrival=CLOCK_DELAY,
    )


def _estimate_block(cell_type: str, arcs: BelArcs, kind: CellKind) -> list[str]:
    """Return one `placement_estimate.txt` block.

    Parameters
    ----------
    cell_type : str
        nextpnr cell type.
    arcs : BelArcs
        Representative arcs of the cell type.
    kind : CellKind
        The cell type's nextpnr role.

    Returns
    -------
    list[str]
        `BelBegin`, the arcs and `BelEnd`.
    """
    return [f"BelBegin,{cell_type}", *render_arcs(arcs, kind=kind), "BelEnd"]


_IO_PORTS = 4

# nextpnr placer/router tunables plus one representative estimate block per
# timed BEL type. Static while every instance of a type shares the
# placeholder constants (I0-I3 LUT4); a per-instance timing model would
# regenerate it.
PLACEMENT_ESTIMATE_TEXT: str = (
    "\n".join(
        [
            f"delayScale={BASE_DELAY_DEFAULT}",
            f"delayOffset={BASE_DELAY_DEFAULT}",
            f"delayEpsilon={DELAY_EPSILON}",
            f"ripupPenalty={RIPUP_PENALTY}",
            f"carryPredictDelay={CARRY_PREDICT_DELAY}",
            f"pipDelayScale={PIP_DELAY_SCALE}",
            *_estimate_block(
                "FABULOUS_LC",
                placeholder_bel_arcs(
                    kind=CellKind.LOGIC_CELL,
                    inputs=[f"I{i}" for i in range(_IO_PORTS)],
                    outputs=[],
                ),
                CellKind.LOGIC_CELL,
            ),
            *(
                line
                for cell_type in ("OutPass4_frame_config", "OutPass4_frame_config_mux")
                for line in _estimate_block(
                    cell_type,
                    placeholder_bel_arcs(
                        kind=CellKind.OUT_PASS,
                        inputs=[f"I{i}" for i in range(_IO_PORTS)],
                        outputs=[],
                    ),
                    CellKind.OUT_PASS,
                )
            ),
            *(
                line
                for cell_type in ("InPass4_frame_config", "InPass4_frame_config_mux")
                for line in _estimate_block(
                    cell_type,
                    placeholder_bel_arcs(
                        kind=CellKind.IN_PASS,
                        inputs=[],
                        outputs=[f"O{i}" for i in range(_IO_PORTS)],
                    ),
                    CellKind.IN_PASS,
                )
            ),
        ]
    )
    + "\n"
)


@dataclass(frozen=True, slots=True)
class NextpnrModel:
    """The files nextpnr reads from `.FABulous/`.

    Attributes
    ----------
    pips : str
        `pips.txt`.
    bel_v1 : str
        `bel.txt`.
    bel_v2 : str
        `bel.v2.txt`.
    bel_v3 : str
        `bel.v3.txt`.
    pcf : str
        `template.pcf`.
    placement_estimate : str
        `placement_estimate.txt`.
    """

    pips: str
    bel_v1: str
    bel_v2: str
    bel_v3: str
    pcf: str
    placement_estimate: str


def emit_nextpnr_model(fabric: Fabric, timing: TimingDb) -> NextpnrModel:
    """Emit the nextpnr model of `fabric` with the delays in `timing`.

    Walk the fabric grid row-major, then the supertile placements.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    timing : TimingDb
        Timing of every pip and BEL of the fabric.

    Returns
    -------
    NextpnrModel
        The nextpnr files.

    Raises
    ------
    InvalidState
        If a wire in a tile points to a tile outside the fabric bounds.
    """
    header = (
        "# BEL descriptions: top left corner Tile_X0Y0, "
        f"bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
    )
    pips: list[str] = []
    bel_v1 = [header]
    bel_v2 = [header]
    bel_v3 = [header]
    pcf: list[str] = []

    def place_bels(
        bels: list[Bel],
        *,
        first_letter: int,
        x: int,
        y: int,
        arcs_of: Callable[[Bel], BelArcs],
    ) -> None:
        """Append the lines of `bels` placed at tile `(x, y)`.

        Parameters
        ----------
        bels : list[Bel]
            BELs in Z order.
        first_letter : int
            Z index of the first BEL.
        x : int
            Tile X coordinate.
        y : int
            Tile Y coordinate.
        arcs_of : Callable[[Bel], BelArcs]
            Timing lookup of a BEL.
        """
        for i, bel in enumerate(bels):
            letter = string.ascii_uppercase[first_letter + i]
            npnr = nextpnr_bel(bel.name)
            ports = ",".join(bel.inputs + bel.outputs)
            bel_v1.append(f"X{x}Y{y},X{x},Y{y},{letter},{npnr.cell_type},{ports}")
            block = [f"BelBegin,X{x}Y{y},{letter},{npnr.cell_type},{bel.prefix}"]
            block.extend(
                f"I,{p.removeprefix(bel.prefix)},X{x}Y{y}.{p}" for p in bel.inputs
            )
            block.extend(
                f"O,{p.removeprefix(bel.prefix)},X{x}Y{y}.{p}" for p in bel.outputs
            )
            block.extend(f"CFG,{feature}" for feature in sorted(bel.belFeatureMap))
            bel_v2.extend(block)
            bel_v3.extend(block)
            bel_v3.extend(render_arcs(arcs_of(bel), kind=npnr.kind))
            if bel.withUserCLK:
                # Only v3 carries the arrival time; v2 uses nextpnr's default.
                bel_v2.append("GlobalClk")
                bel_v3.append(f"GlobalClk,{timing.clock_arrival}")
            bel_v2.append("BelEnd")
            bel_v3.append("BelEnd")
            if npnr.pinned_io:
                pcf.append(f"set_io Tile_X{x}Y{y}_{letter} Tile_X{x}Y{y}.{letter}")

    for (x, y), tile in fabric:
        if tile is None:
            continue
        pips.append(f"#Tile-internal pips on tile X{x}Y{y}:")
        for pip in switch_pips(tile.switch_matrix.connections):
            delay = timing.pips.tile_delay(tile.name, pip)
            pips.append(
                f"X{x}Y{y},{pip.src},X{x}Y{y},{pip.dst},{delay},{pip.src}.{pip.dst}"
            )

        pips.append(f"#Tile-external pips on tile X{x}Y{y}:")
        for wire, pip in wire_pips(tile):
            x_dst = x + wire.x_offset
            y_dst = y + wire.y_offset
            if (not (0 <= x_dst <= fabric.numberOfColumns)) or (
                not (0 <= y_dst <= fabric.numberOfRows)
            ):
                raise InvalidState(
                    f"Wire {wire} in tile X{x}Y{y} points to an invalid tile "
                    f"X{x_dst}Y{y_dst}. "
                    "Please check your tile CSV file for unmatching wires/offsets!"
                )
            delay = timing.pips.tile_delay(tile.name, pip)
            pips.append(
                f"X{x}Y{y},{pip.src},X{x_dst}Y{y_dst},{pip.dst},"
                f"{delay},{pip.src}.{pip.dst}"
            )

        bel_v1.append(f"#Tile_X{x}Y{y}")
        bel_v2.append(f"#Tile_X{x}Y{y}")
        bel_v3.append(f"#Tile_X{x}Y{y}")
        place_bels(
            tile.bels,
            first_letter=0,
            x=x,
            y=y,
            arcs_of=lambda bel, name=tile.name: timing.bels.tile_arcs(name, bel),
        )

    # SJUMP pips live in tile.wireList (added by Fabric.__post_init__) and are
    # already emitted by the per-tile loop above.
    for base_fx, base_fy, super_tile in fabric.iter_super_tile_placements():
        if not super_tile.bels and super_tile.switch_matrix is None:
            continue

        tx_local, ty_local = super_tile.get_master_tile_coords()
        ftx = base_fx + tx_local
        fty = base_fy + ty_local

        bel_v1.append(f"#SuperTile_{super_tile.name}_X{ftx}Y{fty}")
        bel_v2.append(f"#SuperTile_{super_tile.name}_X{ftx}Y{fty}")
        bel_v3.append(f"#SuperTile_{super_tile.name}_X{ftx}Y{fty}")
        place_bels(
            super_tile.bels,
            first_letter=len(fabric.tile[fty][ftx].bels),
            x=ftx,
            y=fty,
            arcs_of=lambda bel, name=super_tile.name: timing.bels.super_tile_arcs(
                name, bel
            ),
        )

        if super_tile.switch_matrix is not None:
            for pip in switch_pips(super_tile.switch_matrix.connections):
                delay = timing.pips.super_tile_delay(super_tile.name, pip)
                pips.append(
                    f"X{ftx}Y{fty},{pip.src},X{ftx}Y{fty},{pip.dst},{delay},"
                    f"{pip.src}.{pip.dst}"
                )

    return NextpnrModel(
        pips="\n".join(pips),
        bel_v1="\n".join(bel_v1),
        bel_v2="\n".join(bel_v2),
        bel_v3="\n".join(bel_v3),
        pcf="\n".join(pcf),
        placement_estimate=PLACEMENT_ESTIMATE_TEXT,
    )


def write_nextpnr_model(model: NextpnrModel, directory: Path) -> None:
    """Write all six nextpnr files into `directory`.

    Parameters
    ----------
    model : NextpnrModel
        The nextpnr model.
    directory : Path
        Output directory, normally the project's `.FABulous`.
    """
    for name, text in (
        ("pips.txt", model.pips),
        ("bel.txt", model.bel_v1),
        ("bel.v2.txt", model.bel_v2),
        ("bel.v3.txt", model.bel_v3),
        ("template.pcf", model.pcf),
        ("placement_estimate.txt", model.placement_estimate),
    ):
        path = directory / name
        logger.info(f"output file: {path}")
        path.write_text(text, encoding="utf-8")


def write_timing_files(model: NextpnrModel, *, pip_file: Path, bel_file: Path) -> None:
    """Write the pip delays and the `bel.v3` BEL timing of `model`.

    Parameters
    ----------
    model : NextpnrModel
        The nextpnr model.
    pip_file : Path
        Destination of the pip delays.
    bel_file : Path
        Destination of the BEL timing blocks.
    """
    pip_file.write_text(model.pips, encoding="utf-8")
    bel_file.write_text(model.bel_v3, encoding="utf-8")
