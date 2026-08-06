"""Tests for parsing ``SuperTILE`` blocks into composite ``Tile`` objects.

A ``SuperTILE`` block becomes a single composite :class:`Tile` whose ``tile_map``
holds the grid of sub-tile objects (stored top row first), whose wrapper switch
matrix is its own ``switch_matrix`` and whose wrapper BELs are its own ``bels``.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.parser.parse_csv import parseSupertilesCSV
from tests.conftest import make_empty_tile, make_muladd_bel


def _jump_port(name: str, in_out: IO, wire_count: int = 1) -> TilePort:
    """Build a regular tile port facing the wrapper matrix."""
    return TilePort(
        name=name,
        io_direction=in_out,
        width=wire_count,
        side_of_tile=Side.ANY,
        wire_direction=Direction.JUMP,
        source_name=name if in_out == IO.OUTPUT else "NULL",
        x_offset=0,
        y_offset=0,
        destination_name=name if in_out == IO.INPUT else "NULL",
        wire_count=wire_count,
    )


@pytest.fixture
def dsp_subtiles() -> dict[str, Tile]:
    """Two leaf sub-tiles (top over bottom) exposing matrix-facing ports."""
    top = make_empty_tile(
        "DSP_top",
        [_jump_port("top2bot", IO.OUTPUT, wire_count=1)],
        pin_order_config={},
    )
    bot = make_empty_tile(
        "DSP_bot",
        [
            _jump_port("A", IO.OUTPUT, wire_count=1),
            _jump_port("Q", IO.INPUT, wire_count=1),
        ],
        pin_order_config={},
    )
    return {"DSP_top": top, "DSP_bot": bot}


def _write_supertile_csv(tmp_path: Path, body: str) -> Path:
    """Write a minimal CSV containing a single SuperTILE block."""
    csv_path = tmp_path / "DSP.csv"
    csv_path.write_text(f"SuperTILE,DSP\n{body}EndSuperTILE\n")
    return csv_path


class TestPlainCompositeTile:
    """A plain DSP-style block (no BEL/MATRIX/MASTER) parses to a composite."""

    def test_plain_block_is_composite_with_empty_wrapper(
        self, tmp_path: Path, dsp_subtiles: dict[str, Tile]
    ) -> None:
        csv_path = _write_supertile_csv(tmp_path, "DSP_top\nDSP_bot\n")
        (composite,) = parseSupertilesCSV(csv_path, dsp_subtiles)

        assert composite.name == "DSP"
        assert composite.is_composite is True
        assert composite.bels == []
        # Empty wrapper matrix; sub-tiles keep their own matrices.
        assert composite.switch_matrix.total_config_bits == 0
        assert composite.switch_matrix.muxes == []
        # No explicit MASTER -> defaults to the last non-None cell.
        assert composite.master_offset is None

    def test_tilemap_is_top_first(
        self, tmp_path: Path, dsp_subtiles: dict[str, Tile]
    ) -> None:
        csv_path = _write_supertile_csv(tmp_path, "DSP_top\nDSP_bot\n")
        (composite,) = parseSupertilesCSV(csv_path, dsp_subtiles)

        # CSV order is top-to-bottom, so tile_map[0] is the top row (DSP_top).
        assert composite.tile_map is not None
        names = [[t.name if t else None for t in row] for row in composite.tile_map]
        assert names == [["DSP_top"], ["DSP_bot"]]

    def test_subtiles_marked_part_of_supertile(
        self, tmp_path: Path, dsp_subtiles: dict[str, Tile]
    ) -> None:
        csv_path = _write_supertile_csv(tmp_path, "DSP_top\nDSP_bot\n")
        parseSupertilesCSV(csv_path, dsp_subtiles)
        assert dsp_subtiles["DSP_top"].part_of_super_tile is True
        assert dsp_subtiles["DSP_bot"].part_of_super_tile is True


class TestWrapperCompositeTile:
    """A SuperTILE block with BEL, MATRIX and MASTER populates the composite."""

    def test_wrapper_bel_matrix_and_master(
        self, tmp_path: Path, dsp_subtiles: dict[str, Tile], mocker: MockerFixture
    ) -> None:
        # A wrapper BEL with one input (matrix sink) and one output (matrix
        # source). Bel.from_hdl reads a real Verilog file, so mock it.
        bel = make_muladd_bel([("SUPER_A0", IO.INPUT), ("SUPER_Q0", IO.OUTPUT)])
        mocker.patch(
            "fabulous.fabric_definition.bel.Bel.from_hdl",
            return_value=bel,
        )

        # Wrapper matrix: a 2-input mux into the BEL input (1 config bit) and a
        # reverse connection from the BEL output to the sub-tile input. Each
        # ``.list`` line is ``<dest>,<source>``; two lines feed the same dest.
        matrix = tmp_path / "DSP_matrix.list"
        matrix.write_text("SUPER_A0,DSP_bot_A0\nSUPER_A0,GND0\nDSP_bot_Q0,SUPER_Q0\n")

        body = "BEL,MULADD.v\nMATRIX,DSP_matrix.list\nDSP_top\nDSP_bot,MASTER\n"
        csv_path = _write_supertile_csv(tmp_path, body)
        (composite,) = parseSupertilesCSV(csv_path, dsp_subtiles)

        assert composite.is_composite is True
        assert [b.name for b in composite.bels] == [bel.name]
        # One 2-input mux -> exactly one config bit.
        assert composite.switch_matrix.total_config_bits == 1
        # MASTER on DSP_bot, which is the bottom (second, top-first) row.
        assert composite.master_offset == (0, 1)

    def test_unknown_matrix_name_is_rejected(
        self, tmp_path: Path, dsp_subtiles: dict[str, Tile], mocker: MockerFixture
    ) -> None:
        bel = make_muladd_bel([("SUPER_A0", IO.INPUT), ("SUPER_Q0", IO.OUTPUT)])
        mocker.patch(
            "fabulous.fabric_definition.bel.Bel.from_hdl",
            return_value=bel,
        )
        # ``asdfasd`` is not a sub-tile port, BEL pin, or constant.
        matrix = tmp_path / "DSP_matrix.list"
        matrix.write_text("SUPER_A0,asdfasd\nSUPER_A0,GND0\n")

        body = "BEL,MULADD.v\nMATRIX,DSP_matrix.list\nDSP_top\nDSP_bot\n"
        csv_path = _write_supertile_csv(tmp_path, body)

        from fabulous.custom_exception import InvalidSwitchMatrixDefinition

        with pytest.raises(InvalidSwitchMatrixDefinition, match="asdfasd"):
            parseSupertilesCSV(csv_path, dsp_subtiles)
