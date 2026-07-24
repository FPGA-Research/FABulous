"""End-to-end chain test for a composite tile with a populated wrapper.

The DSP reference composite has no wrapper switch matrix or wrapper BEL, so the
populated-wrapper path (unified `switch_matrix` with sub-tile-qualified
connections plus wrapper `bels` placed at the master cell) is not exercised by
any real fabric fixture. This module builds a minimal composite tile that DOES
carry a wrapper `MATRIX` and `BEL` line (plus a `MASTER` token) and walks
it through the full downstream chain:

parse -> composite `Tile` -> tile generation -> nextpnr model -> bitstream
spec -> geometry.

The composite `C` is a 1-wide, 2-tall stack (top `C_top` over master
`C_bot`). `tile_map` is stored top row first, so the master `C_bot` is
`tile_map[1]` and lands on fabric row 0 (the grid is stored bottom row first).
"""

import re
import string
from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.gen_bitstream_spec import generateBitstreamSpec
from fabulous.fabric_cad.gen_npnr_model import genNextpnrModel
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_tile import generateTile
from fabulous.fabric_generator.parser.parse_csv import parse_composite_tiles_csv
from fabulous.geometry_generator.fabric_geometry import FabricGeometry
from tests.conftest import (
    jump_port,
    make_empty_tile,
    make_muladd_bel,
)
from tests.fabric_gen_test.conftest import create_switchmatrix_csv


def _write_wrapper_configmem(path: Path) -> None:
    """Write a ConfigMem CSV that allocates the two wrapper config bits.

    The wrapper carries one switch-matrix config bit (index 0) and one wrapper
    BEL config bit (index 1). They live in distinct frames so the bitstream can
    place them at distinct physical positions and the `[SM][BEL]` ordering is
    observable: frame 0 carries config bit 0 (the SM bit) at physical bit 0,
    frame 1 carries config bit 1 (the BEL bit) at physical bit 1.

    Parameters
    ----------
    path : Path
        Destination CSV path. The fabric used here has `maxFramesPerCol == 20`
        and `frameBitsPerRow == 32`, so the file has 20 frame rows; the first
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


def _make_clocked_muladd_bel(
    internal: list[tuple[str, IO]],
    *,
    name: str = "MULADD",
) -> Bel:
    """Build a MULADD-style wrapper BEL that also carries a `UserCLK` port.

    Mirrors `make_muladd_bel`, but sets `userCLK`, so the wrapper's BEL-clock
    chaining is exercised.

    Parameters
    ----------
    internal : list[tuple[str, IO]]
        Internal BEL pins as `(name, direction)` tuples.
    name : str
        BEL name, which `Bel.name` derives from the source file stem. Defaults
        to "MULADD".

    Returns
    -------
    Bel
        The constructed, clocked BEL.
    """
    return Bel(
        src=Path(f"{name}.v"),
        prefix="",
        module_name=name,
        internal=internal,
        external=[],
        configPort=[],
        sharedPort=[("UserCLK", IO.INPUT)],
        configBit=0,
        belMap={},
        userCLK=True,
        ports_vectors={},
        carry={},
        localShared={},
    )


def _build_clocked_wrapper_composite(
    tmp_path: Path, mocker: MockerFixture, *, master_on_top: bool
) -> Tile:
    """Build the `wrapper_composite`-shaped fabric with a CLOCKED wrapper BEL.

    Same shape as `wrapper_composite` (wrapper matrix driving `SUPER_A0`, a
    single wrapper BEL), except the BEL also carries a `UserCLK` port, so
    generation must bind the BEL's clock to the master's own clock net.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory holding the generated CSV/list fixtures.
    mocker : MockerFixture
        Used to stub `parseBelFile` so no real Verilog file is read.
    master_on_top : bool
        If True, the `MASTER` token is placed on `C_top` (the composite's
        north/top-first row). If False, no `MASTER` token is given at all, so
        the master defaults to the last non-None cell in row-major order,
        `C_bot` (the composite's south/bottom-first row).

    Returns
    -------
    Tile
        The parsed composite tile.
    """
    bel = _make_clocked_muladd_bel([("SUPER_A0", IO.INPUT), ("SUPER_Q0", IO.OUTPUT)])
    mocker.patch(
        "fabulous.fabric_generator.parser.parse_csv.parseBelFile",
        return_value=bel,
    )

    wrapper_matrix = tmp_path / "C_matrix.list"
    wrapper_matrix.write_text("SUPER_A0,C_bot_A0\nSUPER_A0,GND0\n")

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

    top_row = "C_top,MASTER\n" if master_on_top else "C_top\n"
    body = f"BEL,MULADD.v\nMATRIX,C_matrix.list\n{top_row}C_bot\n"
    csv_path = tmp_path / "C.csv"
    csv_path.write_text(f"SuperTILE,C\n{body}EndSuperTILE\n")
    (composite,) = parse_composite_tiles_csv(csv_path, {"C_top": top, "C_bot": bot})
    return composite


def _instance_block(rtl: str, instance_name: str) -> str:
    """Slice out one module instantiation's port-map text from generated RTL.

    Parameters
    ----------
    rtl : str
        The full generated RTL text.
    instance_name : str
        The instance name (`compInsName`) the instantiation was written with.

    Returns
    -------
    str
        The text from the instance name up to its closing `);`.
    """
    start = rtl.index(instance_name)
    end = rtl.index(");", start)
    return rtl[start:end]


def _is_declared_signal(rtl: str, signal: str) -> bool:
    """Check that `signal` is declared as a module port or an internal wire.

    A declaration line ends the signal name with a comma (port list entry),
    a semicolon (`wire ...;`), or a bare newline (the last port in the list,
    whose trailing comma `addPortEnd` strips). A *usage* site (a `.PORT(...)`
    connection) instead follows the signal name with the closing `)` of the
    connection, so it never matches this pattern.

    Parameters
    ----------
    rtl : str
        The full generated RTL text.
    signal : str
        The signal name to look for.

    Returns
    -------
    bool
        True if `signal` is declared as a port or a wire.
    """
    return re.search(rf"\b{re.escape(signal)}\b\s*[,;\n]", rtl) is not None


@pytest.fixture
def wrapper_composite(tmp_path: Path, mocker: MockerFixture) -> Tile:
    """Parse a composite `C` with a real wrapper MATRIX, BEL and MASTER.

    The wrapper switch matrix drives the wrapper BEL input `SUPER_A0` from the
    master sub-tile output `C_bot_A0` through a 2-input mux (one config bit),
    and the wrapper BEL itself carries one config bit (a config port + a one-entry
    `bel_map`). So the composite carries a non-empty wrapper `switch_matrix` (one
    config bit) plus one wrapper `Bel` (one config bit): two wrapper config bits
    total, ordered `[switch-matrix bit][BEL bit]`. The master is `C_bot`.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory holding the generated CSV/list fixtures.
    mocker : MockerFixture
        Used to stub `parseBelFile` so no real Verilog file is read.

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
        "fabulous.fabric_generator.parser.parse_csv.parseBelFile",
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
    (composite,) = parse_composite_tiles_csv(csv_path, {"C_top": top, "C_bot": bot})
    return composite


def _build_fabric(composite: Tile, tmp_path: Path) -> Fabric:
    """Place the composite TWICE contiguously in a 1-wide, 4-tall column.

    The grid is stored bottom row first, so the column is
    `[[C_bot], [C_top], [C_bot], [C_top]]`: placement 1 occupies fabric rows
    0-1 (master `C_bot` at row 0) and placement 2 occupies rows 2-3 (master
    `C_bot` at row 2). The two placements are contiguous (placement 2's bottom
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
        assert wrapper_composite.switch_matrix.no_config_bits == 1
        assert [b.name for b in wrapper_composite.bels] == ["MULADD"]
        # MASTER on C_bot, the bottom (second, top-first) row.
        assert wrapper_composite.get_master_offset() == (0, 1)

    def test_total_config_bits_is_matrix_plus_bel(
        self, wrapper_composite: Tile
    ) -> None:
        """`total_config_bits` is the wrapper matrix bits plus wrapper BEL bits."""
        expected = wrapper_composite.switch_matrix.no_config_bits + sum(
            b.configBit for b in wrapper_composite.bels
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
        two contiguous placements and returns only `[(0, 0)]`; this assertion
        guards that regression.
        """
        fabric = _build_fabric(wrapper_composite, wrapper_composite.tile_dir.parent)
        assert fabric.composite_master_positions(wrapper_composite) == [
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
    """Composite config bits land in each master cell's frame, `[SM][BEL]`."""

    def test_wrapper_config_bits_in_each_master_frame(
        self, wrapper_composite: Tile
    ) -> None:
        """Both masters carry the wrapper config bits in `[SM][BEL]` order.

        The switch-matrix bit is config bit 0 (physical frame 0, bit 0) and the
        wrapper BEL bit is config bit 1 (physical frame 1, bit 1): the BEL feature
        must be placed AFTER the switch-matrix bit, proving the `[SM][BEL]`
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

    def test_south_row_placed_at_screen_bottom(self, tmp_path: Path) -> None:
        """`fabric.tile[0]` (the SOUTH row) must land at the bottom of the screen.

        The grid is stored bottom-first, so `fabric.tile[0]` is the south row
        and `fabric.tile[-1]` is the north row. FABulator (JavaFX) renders with
        y-down screen coordinates, so the north row belongs at `tileY == 0`
        (screen top) and the south row at the largest `tileY` (screen bottom).
        A naive `tileY = cumulative height up to row i` maps row 0 (south) to
        `tileY == 0` instead, mirroring the fabric vertically.
        """
        south_bel = make_muladd_bel([("A0", IO.INPUT), ("Q0", IO.OUTPUT)], name="TALL")
        south = Tile(
            name="South",
            ports=[],
            bels=[south_bel],
            tile_dir=tmp_path,
            matrix_dir=tmp_path / "South.csv",
            gen_ios=[],
            switch_matrix=SwitchMatrix(
                matrix_file=tmp_path / "South.csv", connections={}
            ),
            pin_order_config={},
            userCLK=False,
        )
        north = make_empty_tile(
            "North", tile_dir=tmp_path, matrix_dir=tmp_path / "North.csv"
        )

        fabric = Fabric(
            fabric_dir=tmp_path,
            tile=[[south], [north]],
            numberOfRows=2,
            numberOfColumns=1,
            maxFramesPerCol=20,
            frameBitsPerRow=32,
            tileDic={"South": south, "North": north},
        )

        geometry = FabricGeometry(fabric)

        south_geom = geometry.tileGeomMap["South"]
        north_geom = geometry.tileGeomMap["North"]
        # The south tile carries an extra BEL, so it must be the taller row;
        # otherwise the two rows' tileY values wouldn't distinguish the fix.
        assert south_geom.height != north_geom.height

        south_loc = geometry.tileLocs[0][0]
        north_loc = geometry.tileLocs[1][0]
        assert north_loc.y == 0
        assert south_loc.y == north_geom.height
        assert south_loc.y > north_loc.y
        # The fabric's overall height must span both rows regardless of which
        # row is tallest.
        assert geometry.height == south_geom.height + north_geom.height


class TestWrapperBelClock:
    """A clocked wrapper BEL's clock chains from the master's own clock.

    `tile_map` is top-first storage, so the master's own clock is chained
    from the south cell (`my + 1`), mirroring the sub-tile clock chain and the
    wrapper ConfigMem strobe. For the bottom master (`C_bot`, the composite's
    own south edge) there is no cell further south *within the composite*, so
    the BEL takes the master's own clock input directly; for an explicit top
    master (`C_top`) the south cell `C_bot` exists, so the BEL takes its
    buffered clock output.
    """

    @pytest.mark.parametrize(
        ("master_on_top", "expected_signal"),
        [
            pytest.param(False, "Tile_X0Y1_UserCLK", id="bottom-master-default"),
            pytest.param(True, "Tile_X0Y1_UserCLKo", id="top-master-explicit"),
        ],
    )
    def test_bel_clock_chained_from_south_cell(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        code_generator_factory: Callable[[str, str], CodeGenerator],
        master_on_top: bool,
        expected_signal: str,
    ) -> None:
        """The wrapper BEL's `UserCLK` binds to a declared port or wire."""
        composite = _build_clocked_wrapper_composite(
            tmp_path, mocker, master_on_top=master_on_top
        )
        writer = code_generator_factory(".v", "C")
        generateTile(writer, composite)
        rtl = writer.outFileName.read_text()

        bel_block = _instance_block(rtl, "Inst_ST_MULADD")
        assert f".UserCLK({expected_signal})" in bel_block.replace(" ", "").replace(
            "\n", ""
        )
        # The wrapper carries no clock port of its own for a bottom master
        # (it exposes its own clock input instead); either way the referenced
        # name must be a real port or wire, not an implicit, undriven net.
        assert _is_declared_signal(rtl, expected_signal)
