"""Nextpnr model generation for FABulous FPGA fabrics.

Emit the files nextpnr reads (pips, BELs, pin constraints, placement estimate)
as a pure function of a timed fabric. This module owns every nextpnr rule: cell
types, pin renames and the placeholder timing that reproduces nextpnr's
historical hardcoded constants. The file formats are the templates in
`fabulous/template/nextpnr`.
"""

import string
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined
from loguru import logger

from fabulous.custom_exception import InvalidState
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, BelRole
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import BelPort
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.timing import (
    AnyConnected,
    BelArcs,
    ClockArc,
    ClockToOutArc,
    DelayArc,
    FeatureIs,
    Ns,
    SetupHoldArc,
    SwitchPip,
    ns,
)
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

# Ports per representative I/O block in placement_estimate.txt.
_IO_PORTS = 4


def pin_name(port: BelPort) -> str:
    """Return the nextpnr name of a BEL port: its name without the BEL prefix.

    Parameters
    ----------
    port : BelPort
        A BEL port.

    Returns
    -------
    str
        The nextpnr pin name.
    """
    return port.name.removeprefix(port.prefix)


def clock_name(port: BelPort) -> str:
    """Return the nextpnr name of a clock port; nextpnr calls `UserCLK` `CLK`.

    Parameters
    ----------
    port : BelPort
        A clock port.

    Returns
    -------
    str
        The nextpnr clock-pin name.
    """
    name = pin_name(port)
    return "CLK" if name == "UserCLK" else name


@cache
def _template_env() -> Environment:
    """Return the Jinja environment of the nextpnr file templates.

    Returns
    -------
    Environment
        The cached environment, with the `pin` and `clock` name filters.
    """
    env = Environment(
        loader=PackageLoader("fabulous", "template"),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["pin"] = pin_name
    env.filters["clock"] = clock_name
    return env


def _check_clock_names(arcs: BelArcs, *, owner: str) -> None:
    """Raise if two clock ports of one BEL get the same nextpnr name.

    Parameters
    ----------
    arcs : BelArcs
        The BEL arcs.
    owner : str
        The BEL, for the error.

    Raises
    ------
    ValueError
        If two clock ports share a nextpnr name.
    """
    names = [clock_name(arc.clock) for arc in arcs.clocks]
    if len(set(names)) != len(names):
        raise ValueError(f"Clock ports of {owner} share a nextpnr name: {names}")


def render_arcs(arcs: BelArcs, *, logic_cell: bool) -> list[str]:
    """Return the `bel.v3` timing lines of one BEL.

    Parameters
    ----------
    arcs : BelArcs
        The BEL arcs.
    logic_cell : bool
        Whether the BEL is a logic cell, whose registered output `O` nextpnr
        calls `Q`.

    Returns
    -------
    list[str]
        `Clock`, `Delay`, `SetupHold` and `ClkToOut` lines in that order.
    """
    _check_clock_names(arcs, owner="the BEL")
    template = _template_env().get_template("nextpnr/arcs.j2")
    return str(template.module.lines(arcs, logic_cell)).splitlines()


def _free_port(name: str, io: IO) -> BelPort:
    """Return a port that belongs to no BEL.

    Parameters
    ----------
    name : str
        The port name.
    io : IO
        The port direction.

    Returns
    -------
    BelPort
        A one-bit port without a prefix.
    """
    return BelPort(name, io, 1, is_clock=name == "UserCLK")


def placeholder_bel_arcs(
    *,
    role: BelRole,
    inputs: Sequence[BelPort],
    outputs: Sequence[BelPort],
    clock: BelPort | None = None,
) -> BelArcs:
    """Return the hardcoded arcs nextpnr historically used for a BEL role.

    nextpnr times a logic cell on the pins of its own `FABULOUS_LC` cell
    (`CLK`, `Ci`, `Co`, `I1`, `I2`, `O`), whether or not the fabric BEL has them.
    An arc uses the BEL's port when it has one of that name, and a port that
    belongs to no BEL otherwise.

    Parameters
    ----------
    role : BelRole
        The BEL's role.
    inputs : Sequence[BelPort]
        Input ports of the BEL.
    outputs : Sequence[BelPort]
        Output ports of the BEL.
    clock : BelPort | None
        The BEL's `UserCLK` port, if it has one.

    Returns
    -------
    BelArcs
        Logic-cell, input-pass or output-pass arcs; no arcs for other BELs.
    """
    clk = clock or _free_port("UserCLK", IO.INPUT)
    own = {pin_name(port): port for port in (*inputs, *outputs)}

    def port(name: str, io: IO) -> BelPort:
        """Return the BEL's port `name`, or a free one.

        Parameters
        ----------
        name : str
            The nextpnr pin name.
        io : IO
            The pin direction.

        Returns
        -------
        BelPort
            The port.
        """
        return own.get(name) or _free_port(name, io)

    def numbered(ports: Sequence[BelPort], letter: str) -> list[BelPort]:
        """Return the ports named `letter` followed by a number.

        Parameters
        ----------
        ports : Sequence[BelPort]
            Ports of the BEL.
        letter : str
            `I` or `O`.

        Returns
        -------
        list[BelPort]
            The matching ports, in order.
        """
        return [
            p
            for p in ports
            if pin_name(p).startswith(letter) and pin_name(p)[1:].isdigit()
        ]

    match role:
        case BelRole.LOGIC_CELL:
            lut_inputs = numbered(inputs, "I")
            ci, co = port("Ci", IO.INPUT), port("Co", IO.OUTPUT)
            out = port("O", IO.OUTPUT)
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
                    DelayArc(port("I1", IO.INPUT), co, CARRY_I_DELAY, when=carry),
                    DelayArc(port("I2", IO.INPUT), co, CARRY_I_DELAY, when=carry),
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
        case BelRole.OUT_PASS:
            return BelArcs(
                checks=tuple(
                    SetupHoldArc(p, clk, IO_SETUP, IO_HOLD)
                    for p in numbered(inputs, "I")
                )
            )
        case BelRole.IN_PASS:
            return BelArcs(
                clock_to_outs=tuple(
                    ClockToOutArc(p, clk, IO_CLK_TO_OUT) for p in numbered(outputs, "O")
                )
            )
        case BelRole.OTHER:
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
        The placeholder arcs of the BEL's role.
    """
    return placeholder_bel_arcs(
        role=bel.role,
        inputs=bel.input_ports,
        outputs=bel.output_ports,
        clock=bel.user_clk_port,
    )


def set_placeholder_timing(fabric: Fabric) -> None:
    """Set the timing nextpnr historically assumed on `fabric`.

    Every BEL gets its `placeholder_bel_arcs`, every pip `DUMMY_PIP_DELAY` and
    the fabric `CLOCK_DELAY` as clock arrival.

    Parameters
    ----------
    fabric : Fabric
        The fabric; its timing is set.
    """
    fabric.set_timing(
        tile_arcs={
            name: [_placeholder_arcs_of(bel) for bel in tile.bels]
            for name, tile in fabric.tileDic.items()
        },
        tile_pip_delays={
            name: dict.fromkeys(pips, DUMMY_PIP_DELAY)
            for name, pips in fabric.pips_by_tile_type().items()
        },
        super_tile_arcs={
            name: [_placeholder_arcs_of(bel) for bel in super_tile.bels]
            for name, super_tile in fabric.superTileDic.items()
        },
        super_tile_pip_delays={
            name: dict.fromkeys(super_tile.switch_matrix.pips(), DUMMY_PIP_DELAY)
            for name, super_tile in fabric.superTileDic.items()
            if super_tile.switch_matrix is not None
        },
        clock_arrival=CLOCK_DELAY,
    )


@dataclass(frozen=True, slots=True)
class _EstimateBlock:
    """One representative timing block of `placement_estimate.txt`.

    Attributes
    ----------
    cell_type : str
        nextpnr cell type.
    arcs : BelArcs
        Representative arcs of the cell type.
    logic_cell : bool
        Whether the cell type is a logic cell.
    """

    cell_type: str
    arcs: BelArcs
    logic_cell: bool


def placement_estimate() -> str:
    """Return `placement_estimate.txt`.

    Static while every instance of a type shares the placeholder constants
    (a LUT4 with `I0` to `I3`); a per-instance timing model would regenerate it.

    Returns
    -------
    str
        The nextpnr tunables and one timing block per timed cell type.
    """
    inputs = [_free_port(f"I{i}", IO.INPUT) for i in range(_IO_PORTS)]
    outputs = [_free_port(f"O{i}", IO.OUTPUT) for i in range(_IO_PORTS)]
    logic = placeholder_bel_arcs(role=BelRole.LOGIC_CELL, inputs=inputs, outputs=[])
    out_pass = placeholder_bel_arcs(role=BelRole.OUT_PASS, inputs=inputs, outputs=[])
    in_pass = placeholder_bel_arcs(role=BelRole.IN_PASS, inputs=[], outputs=outputs)
    return (
        _template_env()
        .get_template("nextpnr/placement_estimate.txt.j2")
        .render(
            delay_scale=BASE_DELAY_DEFAULT,
            delay_offset=BASE_DELAY_DEFAULT,
            delay_epsilon=DELAY_EPSILON,
            ripup_penalty=RIPUP_PENALTY,
            carry_predict_delay=CARRY_PREDICT_DELAY,
            pip_delay_scale=PIP_DELAY_SCALE,
            blocks=[
                _EstimateBlock("FABULOUS_LC", logic, logic_cell=True),
                _EstimateBlock("OutPass4_frame_config", out_pass, logic_cell=False),
                _EstimateBlock("OutPass4_frame_config_mux", out_pass, logic_cell=False),
                _EstimateBlock("InPass4_frame_config", in_pass, logic_cell=False),
                _EstimateBlock("InPass4_frame_config_mux", in_pass, logic_cell=False),
            ],
        )
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


def _placed_arcs(bel: Bel, *, x: int, y: int) -> BelArcs:
    """Return the arcs of `bel` placed at tile `(x, y)`.

    Parameters
    ----------
    bel : Bel
        The BEL.
    x : int
        Tile X coordinate.
    y : int
        Tile Y coordinate.

    Returns
    -------
    BelArcs
        The BEL arcs.

    Raises
    ------
    ValueError
        If `bel` has no timing arcs.
    """
    if bel.arcs is None:
        raise ValueError(f"BEL {bel.prefix}{bel.name} at X{x}Y{y} has no timing arcs.")
    return bel.arcs


def _switch_pip_delay(switch_matrix: SwitchMatrix, pip: SwitchPip, *, owner: str) -> Ns:
    """Return the delay of `pip` of `switch_matrix`.

    Parameters
    ----------
    switch_matrix : SwitchMatrix
        The switch matrix.
    pip : SwitchPip
        One of its pips.
    owner : str
        The placed tile or supertile that holds the switch matrix, for errors.

    Returns
    -------
    Ns
        The pip delay.

    Raises
    ------
    ValueError
        If the switch matrix has no pip delays, or none for `pip`.
    """
    if switch_matrix.pip_delays is None:
        raise ValueError(f"The switch matrix of {owner} has no pip delays.")
    if pip not in switch_matrix.pip_delays:
        raise ValueError(f"No delay for {pip} in the switch matrix of {owner}.")
    return switch_matrix.pip_delays[pip]


def _wire_delay(wire: Wire, *, x: int, y: int) -> Ns:
    """Return the delay of `wire` of the tile at `(x, y)`.

    Parameters
    ----------
    wire : Wire
        The wire.
    x : int
        Tile X coordinate.
    y : int
        Tile Y coordinate.

    Returns
    -------
    Ns
        The wire delay.

    Raises
    ------
    ValueError
        If the wire has no delay.
    """
    if wire.delay is None:
        raise ValueError(f"Wire {wire} of the tile at X{x}Y{y} has no delay.")
    return wire.delay


def _clock_arrival(fabric: Fabric) -> Ns:
    """Return the clock arrival of `fabric`.

    Parameters
    ----------
    fabric : Fabric
        The fabric.

    Returns
    -------
    Ns
        The clock arrival at every flop.

    Raises
    ------
    ValueError
        If the fabric has no clock arrival.
    """
    if fabric.clock_arrival is None:
        raise ValueError(f"Fabric {fabric.name!r} has no clock arrival.")
    return fabric.clock_arrival


@dataclass(frozen=True, slots=True)
class _PlacedBel:
    """A BEL at its place in the fabric.

    Attributes
    ----------
    x : int
        Tile X coordinate.
    y : int
        Tile Y coordinate.
    letter : str
        The BEL's Z position in the tile, as a letter.
    bel : Bel
        The BEL.
    arcs : BelArcs
        Its timing arcs.
    """

    x: int
    y: int
    letter: str
    bel: Bel
    arcs: BelArcs

    @property
    def logic_cell(self) -> bool:
        """Whether the BEL is a logic cell.

        Returns
        -------
        bool
            True for a logic cell.
        """
        return self.bel.role is BelRole.LOGIC_CELL

    @property
    def cell_type(self) -> str:
        """The nextpnr cell type.

        Returns
        -------
        str
            `FABULOUS_LC` for a logic cell, else the BEL name.
        """
        return "FABULOUS_LC" if self.logic_cell else self.bel.name


@dataclass(frozen=True, slots=True)
class _BelGroup:
    """The BELs of one placed tile or supertile.

    Attributes
    ----------
    title : str
        The comment line above the group.
    bels : list[_PlacedBel]
        The BELs in Z order.
    """

    title: str
    bels: list[_PlacedBel]


@dataclass(frozen=True, slots=True)
class _PipLine:
    """One line of `pips.txt`.

    Attributes
    ----------
    x : int
        Source tile X coordinate.
    y : int
        Source tile Y coordinate.
    src : str
        Source wire.
    x_dst : int
        Destination tile X coordinate.
    y_dst : int
        Destination tile Y coordinate.
    dst : str
        Destination wire.
    delay : Ns
        The pip delay.
    """

    x: int
    y: int
    src: str
    x_dst: int
    y_dst: int
    dst: str
    delay: Ns


@dataclass(frozen=True, slots=True)
class _PipSection:
    """Consecutive lines of `pips.txt` under one comment.

    Attributes
    ----------
    title : str | None
        The comment line above the pips, if any.
    pips : list[_PipLine]
        The pips.
    """

    title: str | None
    pips: list[_PipLine]


def _place_bels(
    bels: list[Bel], *, first_letter: int, x: int, y: int
) -> list[_PlacedBel]:
    """Return `bels` placed at tile `(x, y)`.

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

    Returns
    -------
    list[_PlacedBel]
        The placed BELs.
    """
    placed = []
    for i, bel in enumerate(bels):
        arcs = _placed_arcs(bel, x=x, y=y)
        _check_clock_names(arcs, owner=f"BEL {bel.prefix}{bel.name} at X{x}Y{y}")
        placed.append(
            _PlacedBel(x, y, string.ascii_uppercase[first_letter + i], bel, arcs)
        )
    return placed


def emit_nextpnr_model(fabric: Fabric) -> NextpnrModel:
    """Emit the nextpnr model of `fabric` with the timing set on it.

    Walk the fabric grid row-major, then the supertile placements.

    Parameters
    ----------
    fabric : Fabric
        The fabric; every placed BEL must have `Bel.arcs`, every placed switch
        matrix `SwitchMatrix.pip_delays`, every placed wire `Wire.delay`, and a
        fabric with clocked BELs `Fabric.clock_arrival`.

    Returns
    -------
    NextpnrModel
        The nextpnr files.

    Raises
    ------
    InvalidState
        If a wire in a tile points to a tile outside the fabric bounds.
    """
    pip_sections: list[_PipSection] = []
    bel_groups: list[_BelGroup] = []

    for (x, y), tile in fabric:
        if tile is None:
            continue
        pip_sections.append(
            _PipSection(
                f"#Tile-internal pips on tile X{x}Y{y}:",
                [
                    _PipLine(
                        x,
                        y,
                        pip.src,
                        x,
                        y,
                        pip.dst,
                        _switch_pip_delay(
                            tile.switch_matrix,
                            pip,
                            owner=f"tile {tile.name!r} at X{x}Y{y}",
                        ),
                    )
                    for pip in tile.switch_matrix.pips()
                ],
            )
        )
        external = _PipSection(f"#Tile-external pips on tile X{x}Y{y}:", [])
        for wire in tile.wireList:
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
            external.pips.append(
                _PipLine(
                    x,
                    y,
                    wire.source,
                    x_dst,
                    y_dst,
                    wire.destination,
                    _wire_delay(wire, x=x, y=y),
                )
            )
        pip_sections.append(external)
        bel_groups.append(
            _BelGroup(
                f"#Tile_X{x}Y{y}", _place_bels(tile.bels, first_letter=0, x=x, y=y)
            )
        )

    # SJUMP pips live in tile.wireList (added by Fabric.__post_init__) and are
    # already emitted by the per-tile loop above.
    for base_fx, base_fy, super_tile in fabric.iter_super_tile_placements():
        if not super_tile.bels and super_tile.switch_matrix is None:
            continue

        tx_local, ty_local = super_tile.get_master_tile_coords()
        ftx = base_fx + tx_local
        fty = base_fy + ty_local
        bel_groups.append(
            _BelGroup(
                f"#SuperTile_{super_tile.name}_X{ftx}Y{fty}",
                _place_bels(
                    super_tile.bels,
                    first_letter=len(fabric.tile[fty][ftx].bels),
                    x=ftx,
                    y=fty,
                ),
            )
        )
        if super_tile.switch_matrix is not None:
            pip_sections.append(
                _PipSection(
                    None,
                    [
                        _PipLine(
                            ftx,
                            fty,
                            pip.src,
                            ftx,
                            fty,
                            pip.dst,
                            _switch_pip_delay(
                                super_tile.switch_matrix,
                                pip,
                                owner=f"supertile {super_tile.name!r} at X{ftx}Y{fty}",
                            ),
                        )
                        for pip in super_tile.switch_matrix.pips()
                    ],
                )
            )

    clocked = any(
        placed.bel.withUserCLK for group in bel_groups for placed in group.bels
    )
    header = (
        "# BEL descriptions: top left corner Tile_X0Y0, "
        f"bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
    )
    bels = {
        "header": header,
        "groups": bel_groups,
        "clock_arrival": _clock_arrival(fabric) if clocked else None,
    }
    return NextpnrModel(
        pips=_render("pips.txt.j2", sections=pip_sections),
        bel_v1=_render("bel.txt.j2", **bels),
        bel_v2=_render("bel_blocks.j2", timed=False, **bels),
        bel_v3=_render("bel_blocks.j2", timed=True, **bels),
        pcf=_render("template.pcf.j2", groups=bel_groups),
        placement_estimate=placement_estimate(),
    )


def _render(template: str, **context: object) -> str:
    """Render one nextpnr file whose last line has no newline.

    Parameters
    ----------
    template : str
        Template name in `fabulous/template/nextpnr`.
    **context : object
        The template variables.

    Returns
    -------
    str
        The file text.
    """
    text = _template_env().get_template(f"nextpnr/{template}").render(**context)
    return text.removesuffix("\n")


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

    A file that already exists is kept beside the new one as
    `<name>.backup.txt`.

    Parameters
    ----------
    model : NextpnrModel
        The nextpnr model.
    pip_file : Path
        Destination of the pip delays.
    bel_file : Path
        Destination of the BEL timing blocks.

    Raises
    ------
    ValueError
        If both destinations are the same file.
    """
    if pip_file == bel_file:
        raise ValueError("Pip and BEL timing output paths must be different.")
    for path, text in ((pip_file, model.pips), (bel_file, model.bel_v3)):
        if path.exists():
            backup = path.with_suffix(".backup.txt")
            logger.info(f"Backing up {path.name} to {backup}")
            path.replace(backup)
        logger.info(f"Output timing model file: {path}")
        path.write_text(text, encoding="utf-8")
