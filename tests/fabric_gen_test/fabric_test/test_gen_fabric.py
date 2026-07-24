"""Tests for fabric and composite-tile HDL generation (`gen_fabric` package)."""

import re
from collections.abc import Callable
from pathlib import Path

from pytest_mock import MockerFixture

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, ConfigBitMode, Direction, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_fabric import (
    generateFabric,
    iter_composite_anchors,
)
from fabulous.fabric_generator.gen_fabric.gen_tile import generateTile
from fabulous.fabric_generator.parser.parse_csv import parse_composite_tiles_csv
from tests.conftest import (
    jump_port,
    make_empty_tile,
    make_muladd_bel,
)


def test_generate_fabric_uses_fabric_name(mocker: MockerFixture) -> None:
    """GenerateFabric should use fabric.name as the module name."""
    fabric = mocker.create_autospec(Fabric)
    fabric.name = "test_fabric"
    fabric.tile = []
    fabric.configBitMode = ConfigBitMode.FLIPFLOP_CHAIN
    fabric.maxFramesPerCol = 20
    fabric.frameBitsPerRow = 32
    fabric.numberOfRows = 0
    fabric.numberOfColumns = 0
    fabric.get_all_unique_tiles.return_value = []

    writer = mocker.create_autospec(CodeGenerator)

    generateFabric(writer, fabric)

    writer.addHeader.assert_called_once_with("test_fabric")


def _composite_dsp(
    tmp_path: Path, mocker: MockerFixture, *, bel: Bel | None = None
) -> Tile:
    """Parse a minimal DSP composite: DSP_top over master DSP_bot, one mux bit.

    The wrapper matrix drives a wrapper-BEL input (`SUPER_A0`) from a sub-tile
    output (`DSP_bot_A0`) through a 2-input mux (one config bit), so the
    composite carries a non-empty wrapper switch matrix and one config bit.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory holding the generated CSV/list fixtures.
    mocker : MockerFixture
        Used to stub `parseBelFile` so no real Verilog file is read.
    bel : Bel | None
        The wrapper BEL the `BEL,MULADD.v` line resolves to. `None` (default)
        builds a BEL with the single internal input `SUPER_A0`.

    Returns
    -------
    Tile
        The parsed composite tile.
    """
    if bel is None:
        bel = make_muladd_bel([("SUPER_A0", IO.INPUT)])
    mocker.patch(
        "fabulous.fabric_generator.parser.parse_csv.parseBelFile",
        return_value=bel,
    )

    matrix = tmp_path / "DSP_matrix.list"
    matrix.write_text("SUPER_A0,DSP_bot_A0\nSUPER_A0,GND0\n")

    top = make_empty_tile(
        "DSP_top",
        [jump_port("top2bot", IO.OUTPUT, wire_count=1)],
        tile_dir=tmp_path,
        matrix_dir=tmp_path / "DSP_top_switch_matrix.list",
        pin_order_config={},
    )
    bot = make_empty_tile(
        "DSP_bot",
        [jump_port("A", IO.OUTPUT, wire_count=1)],
        tile_dir=tmp_path,
        matrix_dir=tmp_path / "DSP_bot_switch_matrix.list",
        pin_order_config={},
    )

    body = "BEL,MULADD.v\nMATRIX,DSP_matrix.list\nDSP_top\nDSP_bot,MASTER\n"
    csv_path = tmp_path / "DSP.csv"
    csv_path.write_text(f"SuperTILE,DSP\n{body}EndSuperTILE\n")
    (composite,) = parse_composite_tiles_csv(csv_path, {"DSP_top": top, "DSP_bot": bot})
    return composite


def test_composite_configmem_preloaded_from_master_bitstream(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    mocker: MockerFixture,
) -> None:
    """The composite ConfigMem must take the master cell's emulation bitstream.

    The composite's wrapper config bits live in free slots of the master cell's
    frame space, so in emulation they are preloaded from the master cell's
    `Emulate_Bitstream` parameter. Without this the wrapper mux bits stay 0 and
    the emulated DSP misroutes its operands (`make emu_dsp` fails).
    """
    writer = code_generator_factory(".v", "DSP")
    generateTile(writer, _composite_dsp(tmp_path, mocker))
    rtl = writer.outFileName.read_text()

    inst = re.search(r"DSP_ConfigMem.*?Inst_DSP_ConfigMem", rtl, re.DOTALL)
    assert inst is not None, "composite ConfigMem not instantiated"
    block = inst.group(0)
    # Master cell is DSP_bot at local (0, 1) -> Tile_X0Y1.
    assert "`ifdef EMULATION" in block
    assert ".Emulate_Bitstream(Tile_X0Y1_Emulate_Bitstream)" in block


def _side_port(name: str, side: Side, in_out: IO) -> TilePort:
    """Build a single-bit side port (used as composite perimeter routing)."""
    direction = {
        Side.NORTH: Direction.NORTH,
        Side.SOUTH: Direction.SOUTH,
        Side.EAST: Direction.EAST,
        Side.WEST: Direction.WEST,
    }[side]
    y_offset = -1 if side == Side.NORTH else (1 if side == Side.SOUTH else 0)
    x_offset = 1 if side == Side.EAST else (-1 if side == Side.WEST else 0)
    return TilePort(
        name=name,
        io_direction=in_out,
        width=1,
        side_of_tile=side,
        wire_direction=direction,
        source_name=name if in_out == IO.OUTPUT else "NULL",
        x_offset=x_offset,
        y_offset=y_offset,
        destination_name=name if in_out == IO.INPUT else "NULL",
        wire_count=1,
    )


def _stub_entity(path: Path, name: str) -> None:
    """Write a minimal VHDL entity so `addComponentDeclarationForFile` can read it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"entity {name} is\nend entity {name};\n")


def test_composite_vhdl_declares_all_instantiated_components(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    mocker: MockerFixture,
) -> None:
    """The VHDL composite wrapper must declare every entity it instantiates.

    A missing `component` is legal Verilog but rejected by VHDL analysers, which
    is exactly what broke VHDL supertile projects: the wrapper instantiated its
    own switch matrix, ConfigMem and BEL with no matching declaration, so NVC /
    GHDL left the DSP tiles unbound (all-X output).
    """
    composite = _composite_dsp(tmp_path, mocker)

    # The VHDL wrapper copies a component declaration out of each instantiated
    # entity's file, so unlike Verilog those files must exist with a parseable
    # entity (switch matrix, ConfigMem, BEL, and each sub-tile). `basePath` is
    # the wrapper output file's directory, i.e. `tmp_path`.
    composite.bels[0].src = tmp_path / "MULADD.vhdl"
    _stub_entity(composite.bels[0].src, "MULADD")
    _stub_entity(tmp_path / "DSP_switch_matrix.vhdl", "DSP_switch_matrix")
    _stub_entity(tmp_path / "DSP_ConfigMem.vhdl", "DSP_ConfigMem")
    _stub_entity(tmp_path / "DSP_top" / "DSP_top.vhdl", "DSP_top")
    _stub_entity(tmp_path / "DSP_bot" / "DSP_bot.vhdl", "DSP_bot")

    writer = code_generator_factory(".vhd", "DSP")
    generateTile(writer, composite)
    rtl = writer.outFileName.read_text()

    for entity in (
        "DSP_switch_matrix",
        "DSP_ConfigMem",
        "MULADD",
        "DSP_top",
        "DSP_bot",
    ):
        assert f"component {entity}" in rtl, f"{entity} component not declared"


def test_composite_fabric_wiring_reaches_correct_physical_cell(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """A multi-row composite's fabric wiring must reach the correct physical cell.

    The wrapper names its cells top row first (top `Tile_X0Y0`, bottom
    `Tile_X0Y1`) while the fabric grid is stored bottom row first, so
    `generateFabric` must bind the row-0 net (`Row_Y0_FrameData`) to the BOTTOM
    cell's wrapper port (`Tile_X0Y1_FrameData`) and the row-1 net to the TOP
    cell. Using the fabric offset for the wrapper label too swaps the two rows.
    """
    top = make_empty_tile(
        "C_top",
        [_side_port("N1BEG", Side.NORTH, IO.OUTPUT)],
        tile_dir=tmp_path,
        matrix_dir=tmp_path / "C_top_switch_matrix.list",
        pin_order_config={},
    )
    bot = make_empty_tile(
        "C_bot",
        [_side_port("S1BEG", Side.SOUTH, IO.OUTPUT)],
        tile_dir=tmp_path,
        matrix_dir=tmp_path / "C_bot_switch_matrix.list",
        pin_order_config={},
    )
    top.part_of_composite = True
    bot.part_of_composite = True
    composite = Tile(
        name="C",
        ports=[],
        bels=[],
        tile_dir=tmp_path,
        matrix_dir=None,
        gen_ios=[],
        switch_matrix=SwitchMatrix(matrix_file=Path(), connections={}),
        # tile_map is stored top row first.
        tile_map=[[top], [bot]],
        sub_tiles=[top, bot],
        userCLK=False,
    )
    # Fabric grid is stored bottom row first: C_bot (bottom) at row 0.
    fabric = Fabric(
        fabric_dir=tmp_path,
        tile=[[bot], [top]],
        numberOfRows=2,
        numberOfColumns=1,
        tileDic={"C": composite, "C_top": top, "C_bot": bot},
    )

    writer = code_generator_factory(".v", "eFPGA")
    generateFabric(writer, fabric)
    rtl = writer.outFileName.read_text()

    # Fabric row 0 (bottom) -> wrapper port for the BOTTOM cell (Tile_X0Y1).
    assert ".Tile_X0Y1_FrameData(Row_Y0_FrameData)" in rtl
    # The wrong (swapped) mapping must NOT appear.
    assert ".Tile_X0Y0_FrameData(Row_Y0_FrameData)" not in rtl

    # Perimeter routing: the bottom cell's SOUTH output is exposed at the wrapper
    # port for the bottom cell (Tile_X0Y1), wired to the fabric net at row 0; the
    # top cell's NORTH output is exposed at Tile_X0Y0, wired to the row-1 net.
    assert ".Tile_X0Y1_S1BEG(Tile_X0Y0_S1BEG)" in rtl
    assert ".Tile_X0Y0_N1BEG(Tile_X0Y1_N1BEG)" in rtl


def test_iter_composite_anchors_yields_placement_origin(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Each composite placement yields one anchor at its bottom-left origin.

    `generateFabric` walks the bottom-first grid and instantiates a composite at
    the first covered cell it reaches, which is the placement's bottom-left
    origin, and names the wrapper's EXTERNAL port connections there. The anchor
    must be that same cell (DSP_bot at fabric row 0), not the top-left one.
    """
    composite = _composite_dsp(tmp_path, mocker)
    top, bot = composite.get_sub_tiles()
    # The fabric grid is stored bottom row first: DSP_bot (bottom) at row 0.
    fabric = Fabric(
        fabric_dir=tmp_path,
        tile=[[bot], [top]],
        numberOfRows=2,
        numberOfColumns=1,
        tileDic={"DSP": composite, "DSP_top": top, "DSP_bot": bot},
    )

    anchors = list(iter_composite_anchors(fabric))

    assert anchors == [(0, 0, composite)]


def test_iter_composite_anchors_separates_contiguous_placements(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Two stacked, touching placements of one composite yield two anchors.

    Placement 1 covers fabric rows 0-1 and placement 2 rows 2-3, so the flattened
    set of covered cells is one solid block. Reconstructing origins from that set
    merges the two placements into a single anchor; matching the `tile_map`
    pattern against the grid keeps them apart.
    """
    composite = _composite_dsp(tmp_path, mocker)
    top, bot = composite.get_sub_tiles()
    fabric = Fabric(
        fabric_dir=tmp_path,
        tile=[[bot], [top], [bot], [top]],
        numberOfRows=4,
        numberOfColumns=1,
        tileDic={"DSP": composite, "DSP_top": top, "DSP_bot": bot},
    )

    anchors = list(iter_composite_anchors(fabric))

    assert anchors == [(0, 0, composite), (0, 2, composite)]


def test_composite_external_port_declared_at_instantiation_cell(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    mocker: MockerFixture,
) -> None:
    """A wrapper BEL's EXTERNAL port is declared at the cell it is connected at.

    `generateFabric` instantiates the composite wrapper at the placement's
    bottom-left cell and wires the wrapper's EXTERNAL ports to nets named after
    that cell, so the top-level port declaration must use the same cell. Naming
    the declaration after the top-left cell leaves the connected net undeclared:
    a floating net in Verilog and an elaboration error in VHDL.
    """
    bel = Bel(
        src=Path("MULADD.v"),
        prefix="",
        module_name="MULADD",
        internal=[("SUPER_A0", IO.INPUT)],
        external=[("IO_out", IO.OUTPUT)],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )
    (external,) = bel.externalOutput
    composite = _composite_dsp(tmp_path, mocker, bel=bel)
    top, bot = composite.get_sub_tiles()
    # The fabric grid is stored bottom row first: DSP_bot (bottom) at row 0, so
    # the placement origin (and the instantiation cell) is Tile_X0Y0.
    fabric = Fabric(
        fabric_dir=tmp_path,
        tile=[[bot], [top]],
        numberOfRows=2,
        numberOfColumns=1,
        tileDic={"DSP": composite, "DSP_top": top, "DSP_bot": bot},
    )

    writer = code_generator_factory(".v", "eFPGA")
    generateFabric(writer, fabric)
    rtl = writer.outFileName.read_text()

    assert re.search(rf"output\s+Tile_X0Y0_{external}\b", rtl) is not None
    assert f".{external}(Tile_X0Y0_{external})" in rtl.replace(" ", "")
    # The top-left cell must not be named on either side.
    assert f"Tile_X0Y1_{external}" not in rtl
