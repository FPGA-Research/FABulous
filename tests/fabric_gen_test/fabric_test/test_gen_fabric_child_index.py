"""Regression tests for child-tile index bugs in generateFabric.

These bugs affect any multi-row or multi-column composite tile (former
supertile) in the fabric flow:

1. Neighbour-connection guards used anchor-relative indices (``y + 1``,
   ``y - 1``, ``x - 1``, ``x + 1``) instead of child-relative ones
   (``y + j + 1``, ``y + j - 1``, ``x + i - 1``, ``x + i + 1``).
   For a 2-tall composite the bottom child (j=1) caused an ``IndexError``
   when the north-neighbour guard was evaluated.

2. The UserCLK boundary check used ``y + 1`` (anchor + 1) instead of
   ``y + j + 1`` (child + 1).  For the bottom child at the fabric edge
   this produced a phantom ``Tile_X*Y*_UserCLKo`` wire that was never
   driven, causing Yosys to insert a tie-low cell that OpenROAD GRT
   could not place (``[GRT-0010] Instance _1_ is not placed``).
"""

from collections.abc import Callable
from pathlib import Path

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_fabric import generateFabric


def test_supertile_edge_child_usrclk_connects_to_global(
    mk_tile: Callable[[str], Tile],
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """The fabric-edge child of a 2-tall composite uses the global UserCLK.

    The UserCLK chain flows south to north, so the cell at the fabric's south
    edge (no tile below) must wire its ``UserCLK`` port to the global
    ``UserCLK`` signal, not to a phantom ``Tile_X*Y*_UserCLKo`` that is never
    driven.

    The old code used an anchor-relative index to decide whether to fall back to
    the global clock, but for a child cell the check must be child-relative;
    the wrong check emitted a wire that does not exist, triggering the OpenROAD
    GRT-0010 error.

    The composite wrapper names its cells top row first, so the south-edge cell
    (``ST_bot``) is ``Tile_X0Y1`` within the wrapper; its UserCLK port carries
    the global clock.
    """
    top = mk_tile("ST_top")
    bot = mk_tile("ST_bot")
    top.part_of_super_tile = True
    bot.part_of_super_tile = True
    composite = Tile(
        name="ST",
        ports=[],
        bels=[],
        tile_dir=top.tile_dir,
        matrix_dir=top.tile_dir,
        gen_ios=[],
        user_clk=False,
        switch_matrix=SwitchMatrix(matrix_file=Path()),
        # tile_map is stored top row first.
        tile_map=[[top], [bot]],
        sub_tiles=[top, bot],
    )
    # The fabric grid is stored bottom row first: ST_bot (bottom) at row 0.
    fabric = Fabric(
        fabric_dir=top.tile_dir,
        tile=[[bot], [top]],
        numberOfRows=2,
        numberOfColumns=1,
        tileDic={"ST": composite, "ST_top": top, "ST_bot": bot},
    )

    writer = code_generator_factory(".v", "eFPGA")
    generateFabric(writer, fabric)
    rtl = writer.outFileName.read_text()

    # The south-edge cell (ST_bot) is Tile_X0Y1 within the wrapper; its UserCLK
    # port must connect to the global UserCLK signal.
    assert ".Tile_X0Y1_UserCLK(UserCLK)" in rtl
    # No phantom wire referencing a row that doesn't exist.
    assert "Tile_X0Y2_UserCLKo" not in rtl
