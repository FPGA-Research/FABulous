"""End-to-end chain test for a composite tile with a populated wrapper.

The DSP reference composite has no wrapper switch matrix or wrapper BEL, so the
populated-wrapper path (unified ``switch_matrix`` with sub-tile-qualified
connections plus wrapper ``bels`` placed at the master cell) is not exercised by
any real fabric fixture. This module builds a minimal composite tile that DOES
carry a wrapper ``MATRIX`` and ``BEL`` line (plus a ``MASTER`` token) and walks
it through the full downstream chain:

parse -> composite ``Tile`` -> tile generation -> nextpnr model -> bitstream
spec -> geometry.

The composite ``C`` is a 1-wide, 2-tall stack (top ``C_top`` over master
``C_bot``). ``tile_map`` is stored top row first, so the master ``C_bot`` is
``tile_map[1]`` and lands on fabric row 0 (the grid is stored bottom row first).
"""

import string
from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.gen_bitstream_spec import generateBitstreamSpec
from fabulous.fabric_cad.gen_npnr_model import (
    composite_master_fabric_coords,
    genNextpnrModel,
)
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_tile import generateTile
from fabulous.fabric_generator.parser.parse_csv import parseSupertilesCSV
from fabulous.geometry_generator.fabric_geometry import FabricGeometry
from tests.conftest import jump_port, make_empty_tile, make_muladd_bel
from tests.fabric_gen_test.conftest import create_switchmatrix_csv


def _write_wrapper_configmem(path: Path) -> None:
    """Write a ConfigMem CSV that allocates the two wrapper config bits.

    The wrapper carries one switch-matrix config bit (index 0) and one wrapper
    BEL config bit (index 1). They live in distinct frames so the bitstream can
    place them at distinct physical positions and the ``[SM][BEL]`` ordering is
    observable: frame 0 carries config bit 0 (the SM bit) at physical bit 0,
    frame 1 carries config bit 1 (the BEL bit) at physical bit 1.

    Parameters
    ----------
    path : Path
        Destination CSV path. The fabric used here has ``maxFramesPerCol == 20``
        and ``frameBitsPerRow == 32``, so the file has 20 frame rows; the first
        two carry one bit each, the rest are empty.
    """
    empty_mask = "0000_0000_0000_0000_0000_0000_0000_0000"
    sm_bit_mask = "0000_0000_0000_0000_0000_0000_0000_0001"
    bel_bit_mask = "0000_0000_0000_0000_0000_0000_0000_0010"
    lines = [
        "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges"
    ]
    lines.append(f"Frame0,0,1,{sm_bit_mask},0")
    lines.append(f"Frame1,1,1,{bel_bit_mask},1")
    for frame_index in range(2, 20):
        lines.append(f"Frame{frame_index},{frame_index},0,{empty_mask},NULL")
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def wrapper_composite(tmp_path: Path, mocker: MockerFixture) -> Tile:
    """Parse a composite ``C`` with a real wrapper MATRIX, BEL and MASTER.

    The wrapper switch matrix drives the wrapper BEL input ``SUPER_A0`` from the
    master sub-tile output ``C_bot_A0`` through a 2-input mux (one config bit),
    and the wrapper BEL itself carries one config bit (a config port + a one-entry
    ``bel_map``). So the composite carries a non-empty wrapper ``switch_matrix`` (one
    config bit) plus one wrapper ``Bel`` (one config bit): two wrapper config bits
    total, ordered ``[switch-matrix bit][BEL bit]``. The master is ``C_bot``.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory holding the generated CSV/list fixtures.
    mocker : MockerFixture
        Used to stub ``Bel.from_hdl`` so no real Verilog file is read.

    Returns
    -------
    Tile
        The parsed composite tile.
    """
    bel = make_muladd_bel(
        [("SUPER_A0", IO.INPUT), ("SUPER_Q0", IO.OUTPUT)],
        config_ports=[("ConfigBits", IO.INPUT)],
        bel_map={"INIT": {0: {0: "1"}}},
    )
    mocker.patch(
        "fabulous.fabric_definition.bel.Bel.from_hdl",
        return_value=bel,
    )

    # Wrapper matrix: two sources into one BEL-input sink -> one config bit.
    wrapper_matrix = tmp_path / "C_matrix.list"
    wrapper_matrix.write_text("SUPER_A0,C_bot_A0\nSUPER_A0,GND0\n")

    # Leaf sub-tiles carry real .csv switch matrices so the fabric-grid PIP loop
    # parses them, and a matrix-facing JUMP output the wrapper matrix consumes.
    top_matrix = tmp_path / "C_top_switch_matrix.csv"
    create_switchmatrix_csv(
        top_matrix, "C_top", destinations=["N1END0"], sources=["N1BEG0"]
    )
    bot_matrix = tmp_path / "C_bot_switch_matrix.csv"
    create_switchmatrix_csv(
        bot_matrix, "C_bot", destinations=["A0"], sources=["S1BEG0"]
    )

    top = make_empty_tile(
        "C_top",
        [jump_port("top2bot", IO.OUTPUT, wire_count=1)],
        tile_dir=tmp_path,
        matrix_dir=top_matrix,
        pin_order_config={},
    )
    bot = make_empty_tile(
        "C_bot",
        [jump_port("A", IO.OUTPUT, wire_count=1)],
        tile_dir=tmp_path,
        matrix_dir=bot_matrix,
        pin_order_config={},
    )

    body = "BEL,MULADD.v\nMATRIX,C_matrix.list\nC_top\nC_bot,MASTER\n"
    csv_path = tmp_path / "C.csv"
    csv_path.write_text(f"SuperTILE,C\n{body}EndSuperTILE\n")
    (composite,) = parseSupertilesCSV(csv_path, {"C_top": top, "C_bot": bot})
    return composite


def _build_fabric(composite: Tile, tmp_path: Path) -> Fabric:
    """Place the composite TWICE contiguously in a 1-wide, 4-tall column.

    The grid is stored bottom row first, so the column is
    ``[[C_bot], [C_top], [C_bot], [C_top]]``: placement 1 occupies fabric rows
    0-1 (master ``C_bot`` at row 0) and placement 2 occupies rows 2-3 (master
    ``C_bot`` at row 2). The two placements are contiguous (placement 2's bottom
    cell touches placement 1's top cell), which is exactly the case that a
    covered-cell origin heuristic would collapse to a single placement.

    Parameters
    ----------
    composite : Tile
        The composite tile to place.
    tmp_path : Path
        Fabric directory.

    Returns
    -------
    Fabric
        A fabric with two stacked, contiguous placements of the composite.
    """
    top, bot = composite.get_sub_tiles()
    return Fabric(
        fabric_dir=tmp_path,
        tile=[[bot], [top], [bot], [top]],
        numberOfRows=4,
        numberOfColumns=1,
        maxFramesPerCol=20,
        frameBitsPerRow=32,
        tileDic={"C": composite, "C_top": top, "C_bot": bot},
    )


class TestParse:
    """The wrapper MATRIX/BEL/MASTER parse into the unified composite model."""

    def test_unified_switch_matrix_and_wrapper_bel(
        self, wrapper_composite: Tile
    ) -> None:
        """The composite carries a unified wrapper matrix, BEL and master offset."""
        assert wrapper_composite.is_composite is True
        # One 2-input mux -> exactly one wrapper config bit.
        assert wrapper_composite.switch_matrix.total_config_bits == 1
        assert [b.name for b in wrapper_composite.bels] == ["MULADD"]
        # MASTER on C_bot, the bottom (second, top-first) row.
        assert wrapper_composite.get_master_offset() == (0, 1)

    def test_total_config_bits_is_matrix_plus_bel(
        self, wrapper_composite: Tile
    ) -> None:
        """``total_config_bits`` is the wrapper matrix bits plus wrapper BEL bits."""
        expected = wrapper_composite.switch_matrix.total_config_bits + sum(
            b.config_bit for b in wrapper_composite.bels
        )
        assert wrapper_composite.total_config_bits == expected


class TestGeneration:
    """Tile generation binds the wrapper to the master cell."""

    def test_wrapper_bel_and_configmem_at_master(
        self,
        wrapper_composite: Tile,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> None:
        """The wrapper BEL and ConfigMem are instantiated at the master cell."""
        writer = code_generator_factory(".v", "C")
        generateTile(writer, wrapper_composite)
        rtl = writer.outFileName.read_text()

        # Wrapper ConfigMem is instantiated and preloaded from the master cell
        # (C_bot at top-first (0, 1) -> Tile_X0Y1) emulation bitstream.
        assert "Inst_C_ConfigMem" in rtl
        assert ".Emulate_Bitstream(Tile_X0Y1_Emulate_Bitstream)" in rtl
        # The wrapper BEL module is instantiated inside the composite wrapper.
        assert "MULADD" in rtl


class TestNextpnrModel:
    """The composite contributes wrapper BELs and unified-matrix PIPs."""

    def test_master_fabric_coordinate_per_placement(
        self, wrapper_composite: Tile
    ) -> None:
        """Every placement yields its own master cell (top-first (0,1) -> bottom).

        The composite is placed twice contiguously, so both masters must appear:
        placement 1 at fabric (0, 0) and placement 2 at fabric (0, 2). A heuristic
        that reconstructs origins from the flattened covered-cell set collapses the
        two contiguous placements and returns only ``[(0, 0)]``; this assertion
        guards that regression.
        """
        fabric = _build_fabric(wrapper_composite, wrapper_composite.tile_dir.parent)
        assert composite_master_fabric_coords(fabric, wrapper_composite) == [
            (0, 0),
            (0, 2),
        ]

    def test_wrapper_bel_in_master_letter_space(self, wrapper_composite: Tile) -> None:
        """The wrapper BEL gets the next BEL letter at every master cell."""
        fabric = _build_fabric(wrapper_composite, wrapper_composite.tile_dir.parent)
        _pips, bel_str, belv2_str, _belv3, _constraints = genNextpnrModel(fabric)

        # Master cell C_bot has no own BELs, so the wrapper BEL takes letter A.
        # Both placements' master cells (X0Y0 and X0Y2) must carry the wrapper BEL.
        master_letter = string.ascii_uppercase[0]
        for master in ("X0Y0", "X0Y2"):
            assert f"{master},X0,Y{master[3]},{master_letter},MULADD," in bel_str
            assert f"BelBegin,{master},{master_letter},MULADD," in belv2_str

    def test_unified_matrix_pip_at_master(self, wrapper_composite: Tile) -> None:
        """The wrapper switch-matrix mux appears as a PIP at every master cell."""
        fabric = _build_fabric(wrapper_composite, wrapper_composite.tile_dir.parent)
        pip_str, _bel, _belv2, _belv3, _constraints = genNextpnrModel(fabric)

        # The wrapper mux drives SUPER_A0 from C_bot_A0 at each master cell.
        for master in ("X0Y0", "X0Y2"):
            assert f"{master},C_bot_A0,{master},SUPER_A0" in pip_str
            assert f"{master},GND0,{master},SUPER_A0" in pip_str


class TestBitstreamSpec:
    """Composite config bits land in each master cell's frame, ``[SM][BEL]``."""

    def test_wrapper_config_bits_in_each_master_frame(
        self, wrapper_composite: Tile
    ) -> None:
        """Both masters carry the wrapper config bits in ``[SM][BEL]`` order.

        The switch-matrix bit is config bit 0 (physical frame 0, bit 0) and the
        wrapper BEL bit is config bit 1 (physical frame 1, bit 1): the BEL feature
        must be placed AFTER the switch-matrix bit, proving the ``[SM][BEL]``
        slicing. Both contiguous placements (master cells X0Y0 and X0Y2) carry it.
        """
        tmp_path = wrapper_composite.tile_dir.parent
        _write_wrapper_configmem(tmp_path / "C_ConfigMem.csv")
        fabric = _build_fabric(wrapper_composite, tmp_path)

        spec = generateBitstreamSpec(fabric)

        # ConfigMem maps config bit 0 to physical bit 0 of frame 0, and config bit
        # 1 to physical bit 1 of frame 1. With frameBitsPerRow of 32 the encoded
        # physical positions are config bit 0 at index 0 (from frameBitsPerRow-1-31
        # plus 32 times frame 0) and config bit 1 at index 33 (from
        # frameBitsPerRow-1-30 plus 32 times frame 1).
        sm_physical_bit = 0
        bel_physical_bit = 33
        for master in ("X0Y0", "X0Y2"):
            master_spec = spec["TileSpecs"][master]
            # Switch-matrix mux: config bit 0 (the FIRST wrapper config bit).
            assert master_spec["C_bot_A0.SUPER_A0"] == {sm_physical_bit: "0"}
            assert master_spec["GND0.SUPER_A0"] == {sm_physical_bit: "1"}
            # Wrapper BEL feature: config bit 1, placed AFTER the SM bit. The
            # master cell has no own BELs, so the wrapper BEL is letter A.
            assert master_spec["A.INIT"] == {bel_physical_bit: "1"}


class TestGeometry:
    """The composite wrapper BEL is drawn once, at the master cell."""

    def test_wrapper_bel_emitted_once_at_master(self, wrapper_composite: Tile) -> None:
        """The master sub-tile geometry hosts the wrapper BEL exactly once."""
        fabric = _build_fabric(wrapper_composite, wrapper_composite.tile_dir.parent)

        geometry = FabricGeometry(fabric)

        # The master sub-tile is C_bot; its geometry must include the single
        # wrapper BEL (drawn once, not duplicated across placements).
        master_geom = geometry.tileGeomMap["C_bot"]
        muladd_bels = [b for b in master_geom.belGeomList if b.name == "MULADD"]
        assert len(muladd_bels) == 1
        # The non-master sub-tile must not host the wrapper BEL.
        top_geom = geometry.tileGeomMap["C_top"]
        assert all(b.name != "MULADD" for b in top_geom.belGeomList)
