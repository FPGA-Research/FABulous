"""Tests for fabric and supertile HDL generation (`gen_fabric` package)."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import (
    IO,
    USER_CLK_PREDECESSOR,
    Side,
)
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import Port
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_fabric import (
    generateFabric,
    iter_super_tile_anchors,
)
from fabulous.fabric_generator.gen_fabric.gen_tile import generateSuperTile
from tests.conftest import make_empty_tile, make_muladd_bel, sjump_port
from tests.fabric_gen_test.conftest import (
    Netlist,
    create_switchmatrix_list,
    tile_stub,
)


def _supertile(tmp_path: Path) -> SuperTile:
    """A minimal DSP-like supertile: DSP_top over master DSP_bot, one mux bit."""
    mat = tmp_path / "supertile_matrix.list"
    create_switchmatrix_list(mat, [("{2}SUPER_A0", "[DSP_bot_A0|DSP_bot_A1]")])

    def mk(name: str, ports: list[Port]) -> Tile:
        """Build a minimal child tile rooted at `tmp_path`."""
        return make_empty_tile(
            name,
            ports,
            tileDir=tmp_path,
            matrixDir=tmp_path / f"{name}_switch_matrix.list",
            pinOrderConfig={},
        )

    top = mk("DSP_top", [sjump_port("top2bot", IO.OUTPUT)])
    bot = mk("DSP_bot", [sjump_port("A", IO.OUTPUT)])
    bel = make_muladd_bel([("SUPER_A0", IO.INPUT)])
    return SuperTile(
        name="DSP",
        tileDir=tmp_path,
        tiles=[top, bot],
        tileMap=[[top], [bot]],
        bels=[bel],
        switch_matrix=SwitchMatrix.from_file(mat, "DSP"),
    )


def test_supertile_configmem_preloaded_from_master_bitstream(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """The supertile ConfigMem must take the master tile's emulation bitstream.

    The supertile's config bits live in free slots of the master tile's frame
    space, so in emulation they are preloaded from the master tile's
    `Emulate_Bitstream` parameter. Without this the supertile mux bits stay 0
    and the emulated DSP misroutes its operands (`make emu_dsp` fails).
    """
    writer = code_generator_factory(".v", "DSP")
    generateSuperTile(writer, _supertile(tmp_path))
    rtl = writer.outFileName.read_text()

    inst = re.search(r"DSP_ConfigMem.*?Inst_DSP_ConfigMem", rtl, re.DOTALL)
    assert inst is not None, "supertile ConfigMem not instantiated"
    block = inst.group(0)
    # Master tile is DSP_bot at local (0, 1) -> Tile_X0Y1.
    assert "`ifdef EMULATION" in block
    assert ".Emulate_Bitstream(Tile_X0Y1_Emulate_Bitstream)" in block


def _stub_entity(path: Path, name: str) -> None:
    """Write a minimal VHDL entity so `addComponentDeclarationForFile` can read it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"entity {name} is\nend entity {name};\n")


def _vhdl_supertile(tmp_path: Path) -> SuperTile:
    """A DSP-like supertile plus the on-disk VHDL stubs the VHDL wrapper reads.

    The VHDL wrapper copies a component declaration out of each instantiated
    entity's file, so unlike the Verilog fixture those files must exist with a
    parseable entity (switch matrix, ConfigMem, BEL, and each sub-tile).
    """
    mat = tmp_path / "supertile_matrix.list"
    create_switchmatrix_list(mat, [("{2}SUPER_A0", "[DSP_bot_A0|DSP_bot_A1]")])

    def mk(name: str, ports: list[Port]) -> Tile:
        """Build a minimal child tile rooted at `tmp_path`."""
        return make_empty_tile(
            name,
            ports,
            tileDir=tmp_path,
            matrixDir=tmp_path / f"{name}_switch_matrix.list",
            pinOrderConfig={},
        )

    top = mk("DSP_top", [sjump_port("top2bot", IO.OUTPUT)])
    bot = mk("DSP_bot", [sjump_port("A", IO.OUTPUT)])
    bel = make_muladd_bel([("SUPER_A0", IO.INPUT)])
    bel.src = tmp_path / "MULADD.vhdl"

    _stub_entity(bel.src, "MULADD")
    _stub_entity(tmp_path / "DSP_switch_matrix.vhdl", "DSP_switch_matrix")
    _stub_entity(tmp_path / "DSP_ConfigMem.vhdl", "DSP_ConfigMem")
    _stub_entity(tmp_path / "DSP_top" / "DSP_top.vhdl", "DSP_top")
    _stub_entity(tmp_path / "DSP_bot" / "DSP_bot.vhdl", "DSP_bot")

    return SuperTile(
        name="DSP",
        tileDir=tmp_path,
        tiles=[top, bot],
        tileMap=[[top], [bot]],
        bels=[bel],
        switch_matrix=SwitchMatrix.from_file(mat, "DSP"),
    )


def test_supertile_vhdl_declares_all_instantiated_components(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """The VHDL supertile wrapper must declare every entity it instantiates.

    A missing `component` is legal Verilog but rejected by VHDL analysers, which
    is exactly what broke VHDL supertile projects: the wrapper instantiated its
    own switch matrix, ConfigMem and BEL with no matching declaration, so NVC /
    GHDL left the DSP tiles unbound (all-X output).
    """
    writer = code_generator_factory(".vhd", "DSP")
    generateSuperTile(writer, _vhdl_supertile(tmp_path))
    rtl = writer.outFileName.read_text()

    for entity in (
        "DSP_switch_matrix",
        "DSP_ConfigMem",
        "MULADD",
        "DSP_top",
        "DSP_bot",
    ):
        assert f"component {entity}" in rtl, f"{entity} component not declared"


def test_iter_supertile_anchors_yields_top_left_anchor(tmp_path: Path) -> None:
    """Each supertile placement yields one anchor at its top-left child tile.

    `generateFabric` names a supertile's top-level EXTERNAL ports at this
    anchor (matching the wrapper instance `Tile_X{x}Y{y}_DSP`), so the helper
    must return the top-left child (DSP_top), not the master (DSP_bot below it).
    """
    supertile = _supertile(tmp_path)
    top, bot = supertile.tiles
    top.partOfSuperTile = True
    bot.partOfSuperTile = True
    fabric = Fabric(
        fabric_dir=tmp_path,
        tile=[[top], [bot]],
        numberOfRows=2,
        numberOfColumns=1,
        superTileDic={"DSP": supertile},
    )

    anchors = list(iter_super_tile_anchors(fabric))

    # One placement; anchor is the top-left child at (0, 0), i.e. DSP_top.
    assert anchors == [(0, 0, supertile)]


def _supertile_children(tmp_path: Path, names: str) -> list[Tile]:
    """Build one empty child tile per character of `names`, marked as subtiles."""
    tiles = [make_empty_tile(n, tileDir=tmp_path, pinOrderConfig={}) for n in names]
    for tile in tiles:
        tile.partOfSuperTile = True
    return tiles


def test_supertile_with_null_top_left_wired_from_tilemap_origin(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    elaborate: Callable[..., Netlist],
) -> None:
    """Child offsets are measured from the tileMap origin, not from the anchor.

    With the top-left tileMap cell NULL the wrapper is instantiated once at its
    first non-NULL child X1Y0, while its children stay at X1Y0, X0Y1 and X1Y1.
    """
    a, b, c = _supertile_children(tmp_path, "ABC")
    tile_map: list[list[Tile | None]] = [[None, a], [b, c]]
    supertile = SuperTile(
        name="ST", tileDir=tmp_path, tiles=[a, b, c], tileMap=tile_map
    )
    fabric = Fabric(
        fabric_dir=tmp_path,
        tile=tile_map,
        numberOfRows=2,
        numberOfColumns=2,
        superTileDic={"ST": supertile},
        name="test_fabric",
    )
    st_writer = code_generator_factory(".v", "ST")
    generateSuperTile(st_writer, supertile)
    writer = code_generator_factory(".v", "test_fabric")
    generateFabric(writer, fabric)
    net = elaborate(
        "\n".join(
            [writer.outFileName.read_text(), st_writer.outFileName.read_text()]
            + [tile_stub(t) for t in (a, b, c)]
        )
    )

    assert net.cell_names() == {"Tile_X1Y0_ST"}
    frame_data = net.port_net("FrameData")
    frame_strobe = net.port_net("FrameStrobe")
    expected = {
        "Tile_X1Y0_FrameData": frame_data[0:32],
        "Tile_X0Y1_FrameData": frame_data[32:64],
        "Tile_X0Y1_FrameStrobe": frame_strobe[0:20],
        "Tile_X1Y1_FrameStrobe": frame_strobe[20:40],
        "Tile_X0Y1_UserCLK": net.port_net("UserCLK"),
        "Tile_X1Y1_UserCLK": net.port_net("UserCLK"),
    }
    for port, bits in expected.items():
        assert net.cell_net("Tile_X1Y0_ST", port) == bits, port


def test_truncated_supertile_rejected(
    tmp_path: Path,
    mk_tile: Callable[[str], Tile],
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """A subtile with no complete supertile placement around it fails loudly."""
    a, b = _supertile_children(tmp_path, "AB")
    supertile = SuperTile(name="ST", tileDir=tmp_path, tiles=[a, b], tileMap=[[a], [b]])
    t = mk_tile("T")
    # A sits on the bottom edge, so the B below it falls off the grid.
    fabric = Fabric(
        fabric_dir=tmp_path,
        tile=[[t, t], [t, a]],
        numberOfRows=2,
        numberOfColumns=2,
        superTileDic={"ST": supertile},
    )

    with pytest.raises(ValueError, match=r"Tile A at X1Y1 .* no complete placement"):
        generateFabric(code_generator_factory(".v", "test_fabric"), fabric)


@pytest.mark.parametrize("side", sorted(USER_CLK_PREDECESSOR))
def test_user_clk_chains_from_side(
    side: Side,
    mk_tile: Callable[[str], Tile],
    code_generator_factory: Callable[[str, str], CodeGenerator],
    elaborate: Callable[..., Netlist],
) -> None:
    """`Fabric.userCLKSide` selects the neighbour that feeds each tile's UserCLK.

    On a 3x3 grid every tile's UserCLK must be the UserCLKo net of its `side`
    neighbour, and a tile with no such neighbour takes the global clock. The
    fabric module carries the fabric's name.
    """
    tile = mk_tile("T")
    fabric = Fabric(
        fabric_dir=tile.tileDir,
        tile=[[tile] * 3 for _ in range(3)],
        numberOfRows=3,
        numberOfColumns=3,
        userCLKSide=side,
        name="test_fabric",
    )
    writer = code_generator_factory(".v", "test_fabric")
    generateFabric(writer, fabric)
    net = elaborate(writer.outFileName.read_text() + tile_stub(tile))

    assert net.top_name == "test_fabric"
    dx, dy = USER_CLK_PREDECESSOR[side]
    for y in range(3):
        for x in range(3):
            clk = net.cell_net(f"Tile_X{x}Y{y}_T", "UserCLK")
            if 0 <= x + dx < 3 and 0 <= y + dy < 3:
                assert clk == net.cell_net(f"Tile_X{x + dx}Y{y + dy}_T", "UserCLKo")
            else:
                assert clk == net.port_net("UserCLK")
