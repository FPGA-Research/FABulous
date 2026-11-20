"""Nextpnr model generation for FABulous FPGA fabrics.

Emit the files nextpnr reads (pips, BELs, pin constraints, placement estimate)
as a pure function of a timed fabric, and set the placeholder timing that
reproduces nextpnr's historical hardcoded constants. The placeholder BEL arcs
are `Bel.placeholder_arcs`. The file formats are the templates in
`fabulous/template/nextpnr`.
"""

import string
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined
from loguru import logger

from fabulous.custom_exception import InvalidState
from fabulous.fabric_definition.bel import Bel, BelArcs
from fabulous.fabric_definition.define import IO, BelRole
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import BelPort
from fabulous.fabric_definition.timing import Ns, ns

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


@cache
def _template_env() -> Environment:
    """Return the Jinja environment of the nextpnr file templates.

    Returns
    -------
    Environment
        The cached environment.
    """
    return Environment(
        loader=PackageLoader("fabulous", "template"),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


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
    template = _template_env().get_template("nextpnr/arcs.j2")
    return str(template.module.lines(arcs, logic_cell)).splitlines()


def set_placeholder_timing(fabric: Fabric) -> None:
    """Set the timing nextpnr historically assumed on `fabric`.

    Every BEL gets its `Bel.placeholder_arcs`, every pip `DUMMY_PIP_DELAY` and
    the fabric `CLOCK_DELAY` as clock arrival.

    Parameters
    ----------
    fabric : Fabric
        The fabric; its timing is set.
    """
    fabric.set_timing(
        tile_arcs={
            name: [bel.placeholder_arcs() for bel in tile.bels]
            for name, tile in fabric.tileDic.items()
        },
        tile_pip_delays={
            name: dict.fromkeys(pips, DUMMY_PIP_DELAY)
            for name, pips in fabric.pips_by_tile_type().items()
        },
        super_tile_arcs={
            name: [bel.placeholder_arcs() for bel in super_tile.bels]
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
    inputs = [BelPort.free(f"I{i}", IO.INPUT) for i in range(_IO_PORTS)]
    outputs = [BelPort.free(f"O{i}", IO.OUTPUT) for i in range(_IO_PORTS)]
    logic = BelArcs.placeholder(role=BelRole.LOGIC_CELL, inputs=inputs, outputs=[])
    out_pass = BelArcs.placeholder(role=BelRole.OUT_PASS, inputs=inputs, outputs=[])
    in_pass = BelArcs.placeholder(role=BelRole.IN_PASS, inputs=[], outputs=outputs)
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
    bel_v2: str
    bel_v3: str
    pcf: str
    placement_estimate: str


@dataclass(frozen=True, slots=True)
class _BelGroup:
    """The BELs of one tile or supertile at its place in the fabric.

    Attributes
    ----------
    title : str
        The comment line above the group.
    x : int
        Tile X coordinate.
    y : int
        Tile Y coordinate.
    first_z : int
        Z position of the first BEL in the tile.
    bels : list[Bel]
        The BELs of the tile or supertile type, in Z order.
    """

    title: str
    x: int
    y: int
    first_z: int
    bels: list[Bel]

    def letter(self, index: int) -> str:
        """Return the Z position of `bels[index]` as a letter.

        Parameters
        ----------
        index : int
            Index into `bels`.

        Returns
        -------
        str
            `A` for Z 0, `B` for Z 1, and so on.
        """
        return string.ascii_uppercase[self.first_z + index]


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
                        tile.switch_matrix.get_pip_delay(pip),
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
                    wire.get_delay(),
                )
            )
        pip_sections.append(external)
        bel_groups.append(_BelGroup(f"#Tile_X{x}Y{y}", x, y, 0, tile.bels))

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
                ftx,
                fty,
                len(fabric.tile[fty][ftx].bels),
                super_tile.bels,
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
                            super_tile.switch_matrix.get_pip_delay(pip),
                        )
                        for pip in super_tile.switch_matrix.pips()
                    ],
                )
            )

    clocked = any(bel.withUserCLK for group in bel_groups for bel in group.bels)
    header = (
        "# BEL descriptions: top left corner Tile_X0Y0, "
        f"bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
    )
    bels = {
        "header": header,
        "groups": bel_groups,
        "clock_arrival": fabric.get_clock_arrival() if clocked else None,
    }
    return NextpnrModel(
        pips=_render("pips.txt.j2", sections=pip_sections),
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
    """Write all five nextpnr files into `directory`.

    Parameters
    ----------
    model : NextpnrModel
        The nextpnr model.
    directory : Path
        Output directory, normally the project's `.FABulous`.
    """
    for name, text in (
        ("pips.txt", model.pips),
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
