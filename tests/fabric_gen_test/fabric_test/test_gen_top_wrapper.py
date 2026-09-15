"""Tests for top-level wrapper generation (`gen_top_wrapper`)."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Origin
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.gen_fabric.gen_top_wrapper import generateTopWrapper
from tests.conftest import make_empty_tile

if TYPE_CHECKING:
    from fabulous.fabric_definition.tile import Tile


def _io_bel(name: str) -> Bel:
    """Build a BEL exposing one external output, as an IO tile's BEL does."""
    return Bel(
        src=Path("IO.v"),
        prefix=f"{name}_",
        module_name="IO_stub",
        internal=[],
        external=[("O", IO.OUTPUT)],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )


def _io_column(origin: Origin, rows: int) -> Fabric:
    """A single column of IO tiles, one external output per row."""
    grid: list[list[Tile | None]] = []
    for y in range(rows):
        tile = make_empty_tile(f"IO_Y{y}")
        tile.bels = [_io_bel(f"A{y}")]
        grid.append([tile])
    return Fabric(
        fabric_dir=Path(),
        tile=grid,
        numberOfRows=rows,
        numberOfColumns=1,
        tileDic={t[0].name: t[0] for t in grid},
        origin=origin,
    )


@pytest.mark.parametrize(
    ("origin", "south_y"),
    [(Origin.TOP_LEFT, 2), (Origin.BOTTOM_LEFT, 0)],
    ids=lambda v: str(v),
)
def test_vector_bit_zero_stays_on_the_physical_south_row(
    origin: Origin, south_y: int, tmp_path: Path
) -> None:
    """Bit 0 of a vectorised external port names the physical south tile.

    The origin switch relabels coordinates without moving any tile, so the
    same physical row must keep the same bit. Ordering on the stored `y`
    alone mirrors the vector when the origin flips. `south_y` is the last
    stored row under the top-left origin and row 0 under the bottom-left one.
    """
    out = tmp_path / "top.v"
    writer = VerilogCodeGenerator()
    writer.outFileName = out
    generateTopWrapper(writer, _io_column(origin, rows=3))
    text = out.read_text()

    bit_of_row = {
        int(bit): int(y)
        for y, bit in re.findall(r"\.Tile_X0Y(\d+)_O\(O\[(\d+)\]\)", text)
    }
    assert bit_of_row, f"no vectorised external port emitted:\n{text}"
    assert bit_of_row[0] == south_y, (
        f"bit 0 sits at Y{bit_of_row[0]}, expected the physical south row "
        f"Y{south_y} under {origin}\n{text}"
    )
