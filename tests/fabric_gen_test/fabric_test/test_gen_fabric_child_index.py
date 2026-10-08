"""Regression tests for child-tile index bugs in generateFabric.

These bugs existed before the supertile SJUMP feature and affect any
multi-row or multi-column supertile in the legacy flow:

1. Neighbour-connection guards used anchor-relative indices (``y + 1``,
   ``y - 1``, ``x - 1``, ``x + 1``) instead of child-relative ones
   (``y + j + 1``, ``y + j - 1``, ``x + i - 1``, ``x + i + 1``).
   For a 2-tall supertile the bottom child (j=1) caused an ``IndexError``
   when the north-neighbour guard was evaluated.

2. The UserCLK boundary check used ``y + 1`` (anchor + 1) instead of
   ``y + j + 1`` (child + 1).  For the bottom child at the fabric edge
   this produced a phantom ``Tile_X*Y*_UserCLKo`` wire that was never
   driven, causing Yosys to insert a tie-low cell that OpenROAD GRT
   could not place (``[GRT-0010] Instance _1_ is not placed``).
"""

from collections.abc import Callable

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_fabric import generateFabric
from fabulous.fabric_generator.gen_fabric.gen_tile import generateSuperTile
from tests.fabric_gen_test.conftest import Netlist, tile_stub


def test_supertile_bottom_child_usrclk_connects_to_global(
    mk_tile: Callable[[str], Tile],
    code_generator_factory: Callable[[str, str], CodeGenerator],
    elaborate: Callable[..., Netlist],
) -> None:
    """Bottom child of a 2-tall supertile at the fabric edge uses the global UserCLK.

    When a 2-row supertile sits at the bottom of the fabric (no tile below),
    the bottom child's `UserCLK` port must wire to the global `UserCLK`
    signal, not to a phantom `Tile_X*Y*_UserCLKo` that is never driven.

    The old code used `y + 1` (anchor + 1) to decide whether to fall back to
    the global clock, but for the bottom child (`j = 1`) the correct check is
    `y + j + 1`. With `j = 1` and a 2-row fabric `y + 1 = 1` pointed at
    the other child (present), so the code emitted `Tile_X0Y2_UserCLKo`, a
    wire that does not exist, triggering the OpenROAD GRT-0010 error.

    The fabric is elaborated together with the real supertile wrapper, so the
    pin must also exist on the wrapper and reach the bottom child.
    """
    top = mk_tile("ST_top")
    bot = mk_tile("ST_bot")
    top.partOfSuperTile = True
    bot.partOfSuperTile = True
    supertile = SuperTile(
        name="ST",
        tileDir=top.tileDir,
        tiles=[top, bot],
        tileMap=[[top], [bot]],
    )
    fabric = Fabric(
        fabric_dir=top.tileDir,
        tile=[[top], [bot]],
        numberOfRows=2,
        numberOfColumns=1,
        superTileDic={"ST": supertile},
    )

    fabric_writer = code_generator_factory(".v", "eFPGA")
    generateFabric(fabric_writer, fabric)
    wrapper_writer = code_generator_factory(".v", "ST")
    generateSuperTile(wrapper_writer, supertile)
    net = elaborate(
        fabric_writer.outFileName.read_text()
        + "\n"
        + wrapper_writer.outFileName.read_text()
        + tile_stub(top)
        + tile_stub(bot)
    )

    wrapper = net.top.cells["Tile_X0Y0_ST"]
    # Yosys keeps a connection to a pin the wrapper lacks, so check the pin too.
    assert wrapper.port_directions["Tile_X0Y1_UserCLK"] == "input"
    assert wrapper.connections["Tile_X0Y1_UserCLK"] == net.port_net("UserCLK")
