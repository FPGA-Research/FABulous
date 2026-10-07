"""Tests for fabric and supertile HDL generation (`gen_fabric` package)."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import (
    IO,
    USER_CLK_PREDECESSOR,
    ConfigBitMode,
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
from tests.fabric_gen_test.conftest import create_switchmatrix_list


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

    writer = mocker.create_autospec(CodeGenerator)

    generateFabric(writer, fabric)

    writer.addHeader.assert_called_once_with("test_fabric")


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


def test_flipflop_chain_declares_chain_ports(
    mk_tile: Callable[[str], Tile],
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """FF-chain mode must expose CONFin/CONFout/CONF_CLK and no Frame ports."""
    tile = mk_tile("T")
    fabric = Fabric(
        fabric_dir=tile.tileDir,
        tile=[[tile]],
        numberOfRows=1,
        numberOfColumns=1,
        configBitMode=ConfigBitMode.FLIPFLOP_CHAIN,
    )
    writer = code_generator_factory(".v", "eFPGA")
    generateFabric(writer, fabric)
    rtl = writer.outFileName.read_text()

    assert "CONFin" in rtl
    assert "CONFout" in rtl
    assert "CONF_CLK" in rtl
    # Frame-based ports must NOT leak in.
    assert "FrameData" not in rtl
    assert "FrameStrobe" not in rtl


def test_flipflop_chain_conf_data_width_matches_tile_count(
    mk_tile: Callable[[str], Tile],
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """conf_data must have one net per chain junction: N tiles -> N+1 nets.

    The chain convention is: `conf_data[i]` is the net between tile i-1's
    CONFout and tile i's CONFin, so N tiles use conf_data[0..N]. The head is
    driven by `assign conf_data[0] = CONFin`, the tail drives
    `assign CONFout = conf_data[N]`.
    """
    t = mk_tile("T")
    # 2x3 grid with one NULL hole -> 5 instantiated tiles.
    grid = [[t, t, None], [t, t, t]]
    fabric = Fabric(
        fabric_dir=t.tileDir,
        tile=grid,
        numberOfRows=2,
        numberOfColumns=3,
        configBitMode=ConfigBitMode.FLIPFLOP_CHAIN,
    )
    writer = code_generator_factory(".v", "eFPGA")
    generateFabric(writer, fabric)
    rtl = writer.outFileName.read_text()

    # 5 tiles -> 6 nets -> wire[5:0] conf_data;
    assert re.search(r"wire\s*\[\s*5\s*:\s*0\s*\]\s*conf_data\b", rtl), rtl[:400]
    # And the chain ends must be tied to the top-level ports.
    assert "assign conf_data[0] = CONFin;" in rtl
    assert "assign CONFout = conf_data[5];" in rtl


def test_flipflop_chain_links_consecutive_tiles(
    mk_tile: Callable[[str], Tile],
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """Tiles are chained through conf_data nets; head/tail hit top-level ports.

    The fabric wires `conf_data[i]` between consecutive tiles and then ties
    the two endpoints to the fabric's top-level `CONFin` / `CONFout` ports
    with `assign`. Without those assigns the chain is floating at both ends
    (the first tile's CONFin and the fabric's CONFout are undriven).
    """
    t = mk_tile("T")
    fabric = Fabric(
        fabric_dir=t.tileDir,
        tile=[[t, t, t]],
        numberOfRows=1,
        numberOfColumns=3,
        configBitMode=ConfigBitMode.FLIPFLOP_CHAIN,
    )
    writer = code_generator_factory(".v", "eFPGA")
    generateFabric(writer, fabric)
    rtl = writer.outFileName.read_text()

    # Head: fabric-level CONFin drives conf_data[0], which is the first
    # tile's CONFin. (Generator uses the inter-tile net convention, not a
    # direct `.CONFin(CONFin)` on the first instantiation.)
    assert "assign conf_data[0] = CONFin;" in rtl
    first = rtl[rtl.index("Tile_X0Y0_T") :]
    assert ".CONFin(conf_data[0])" in first
    assert ".CONFout(conf_data[1])" in first

    # Middle: chained from conf_data[1], drives conf_data[2].
    mid = rtl[rtl.index("Tile_X1Y0_T") :]
    assert ".CONFin(conf_data[1])" in mid
    assert ".CONFout(conf_data[2])" in mid

    # Tail: last tile drives conf_data[3], tied to fabric-level CONFout.
    last = rtl[rtl.index("Tile_X2Y0_T") :]
    assert ".CONFin(conf_data[2])" in last
    assert ".CONFout(conf_data[3])" in last
    assert "assign CONFout = conf_data[3];" in rtl

    # CONF_CLK is fanned out to every tile.
    assert rtl.count(".CONF_CLK(CONF_CLK)") == 3


@pytest.mark.parametrize("side", sorted(USER_CLK_PREDECESSOR))
def test_user_clk_chains_from_side(
    side: Side,
    mk_tile: Callable[[str], Tile],
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """`Fabric.userCLKSide` selects the neighbour that feeds each tile's UserCLK.

    On a 3x3 grid the centre tile chains from its `side` neighbour and the
    tile on the far edge in that direction takes the global clock.
    """
    tile = mk_tile("T")
    fabric = Fabric(
        fabric_dir=tile.tileDir,
        tile=[[tile] * 3 for _ in range(3)],
        numberOfRows=3,
        numberOfColumns=3,
        userCLKSide=side,
    )
    writer = code_generator_factory(".v", "eFPGA")
    generateFabric(writer, fabric)
    rtl = writer.outFileName.read_text()

    dx, dy = USER_CLK_PREDECESSOR[side]
    centre = rtl[rtl.index("Tile_X1Y1_T") :]
    assert f".UserCLK(Tile_X{1 + dx}Y{1 + dy}_UserCLKo)" in centre
    # The tile at the entry edge has no predecessor -> global UserCLK.
    ex = 1 + dx
    ey = 1 + dy
    edge = rtl[rtl.index(f"Tile_X{ex}Y{ey}_T") :]
    assert ".UserCLK(UserCLK)" in edge[: edge.index(".UserCLKo(")]
