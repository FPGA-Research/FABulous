"""Tests for the composite-capable Tile model.

A leaf tile is a 1x1 composite; a former supertile is a Tile whose ``tile_map``
holds a grid of sub-Tile objects. These tests cover the composite-shape queries
(``is_composite``, ``max_width``, ``max_height``, ``__iter__``) and the sub-tile
helpers that now accept either a Tile object or a name string.

Storage convention (matching the existing tile helpers): ``tile_map`` is stored
top row first, so ``tile_map[-1]`` is the bottom row. ``get_sub_tile_offset``
uses a top-left origin (the top-left cell is ``(0, 0)``), matching
``get_anchor_offset`` and ``get_master_offset``. ``is_root_tile`` applies a
bottom-left origin (the bottom-left cell is the root). ``__iter__`` yields the raw
grid index as ``(x=column, y=row)`` with no x/y swap.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Side
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from tests.conftest import make_yosys_module


def _tport(name: str, side: Side) -> TilePort:
    """Build a minimal TilePort located on a given side of the tile."""
    return TilePort(
        name=name,
        io_direction=IO.OUTPUT,
        width=1,
        side_of_tile=side,
        source_name=name,
        destination_name=name,
        wire_count=1,
    )


def _bel(config_bits: int) -> Bel:
    """Build a minimal Bel carrying ``config_bits`` configuration bits."""
    return Bel(
        src=Path("mod.v"),
        prefix="",
        module=make_yosys_module({"A": (IO.INPUT, 1)}, config_bits=config_bits),
        module_name="mod",
    )


def _leaf(
    name: str,
    ports: list[TilePort] | None = None,
    bels: list[Bel] | None = None,
    switch_matrix: SwitchMatrix | None = None,
) -> Tile:
    """Build a minimal leaf (non-composite) Tile."""
    return Tile(
        name=name,
        ports=ports if ports is not None else [],
        bels=bels if bels is not None else [],
        tile_dir=Path(),
        matrix_dir=Path(),
        gen_ios=[],
        user_clk=False,
        switch_matrix=switch_matrix
        if switch_matrix is not None
        else SwitchMatrix.from_connections(matrix_file=Path(), connections={}),
    )


def _composite(
    name: str,
    tile_map: list[list[Tile | None]],
    master_offset: tuple[int, int] | None = None,
    bels: list[Bel] | None = None,
    switch_matrix: SwitchMatrix | None = None,
) -> Tile:
    """Build a composite Tile carrying an object tile_map and flat sub_tiles."""
    sub_tiles = [t for row in tile_map for t in row if t is not None]
    return Tile(
        name=name,
        ports=[],
        bels=bels if bels is not None else [],
        tile_dir=Path(),
        matrix_dir=Path(),
        gen_ios=[],
        user_clk=False,
        switch_matrix=switch_matrix
        if switch_matrix is not None
        else SwitchMatrix.from_connections(matrix_file=Path(), connections={}),
        tile_map=tile_map,
        sub_tiles=sub_tiles,
        master_offset=master_offset,
    )


class TestLeafTile:
    """A leaf tile behaves as a 1x1 composite of itself."""

    def test_is_not_composite(self) -> None:
        """A leaf (tile_map=None) is not composite."""
        assert _leaf("T").is_composite is False

    def test_dimensions(self) -> None:
        """A leaf has width and height of one."""
        leaf = _leaf("T")
        assert leaf.max_width == 1
        assert leaf.max_height == 1

    def test_sub_tiles_returns_self(self) -> None:
        """A leaf reports itself as its only sub-tile."""
        leaf = _leaf("T")
        assert leaf.get_sub_tiles() == [leaf]

    def test_iter_yields_self_at_origin(self) -> None:
        """Iterating a leaf yields a single ((0, 0), self)."""
        leaf = _leaf("T")
        assert list(leaf) == [((0, 0), leaf)]

    def test_subtiles_field_defaults_empty(self) -> None:
        """A leaf has an empty flat sub_tiles list by default."""
        assert _leaf("T").sub_tiles == []


class TestCompositeTile:
    """A composite tile exposes its grid of sub-Tile objects."""

    def test_is_composite(self) -> None:
        """A tile with a tile_map is composite."""
        # tile_map stored top first: [top row], [bottom row].
        top, bot = _leaf("top"), _leaf("bot")
        comp = _composite("C", [[top], [bot]])
        assert comp.is_composite is True

    def test_dimensions(self) -> None:
        """A two-row, one-column composite is 1 wide and 2 tall."""
        top, bot = _leaf("top"), _leaf("bot")
        comp = _composite("C", [[top], [bot]])
        assert comp.max_width == 1
        assert comp.max_height == 2

    def test_get_sub_tiles_returns_objects(self) -> None:
        """get_sub_tiles returns the non-None cell objects."""
        top, bot = _leaf("top"), _leaf("bot")
        comp = _composite("C", [[top], [bot]])
        assert comp.get_sub_tiles() == [top, bot]

    def test_subtiles_field_holds_objects(self) -> None:
        """The flat sub_tiles field holds the constituent tiles."""
        top, bot = _leaf("top"), _leaf("bot")
        comp = _composite("C", [[top], [bot]])
        assert comp.sub_tiles == [top, bot]

    def test_iter_yields_each_cell_with_raw_row_index(self) -> None:
        """__iter__ yields ((x, y), tile) using the raw grid row index."""
        top, bot = _leaf("top"), _leaf("bot")
        comp = _composite("C", [[top], [bot]])
        # Raw enumeration: row 0 is top, row 1 is bottom.
        assert list(comp) == [((0, 0), top), ((0, 1), bot)]

    def test_iter_xy_ordering_is_column_row(self) -> None:
        """For a wider grid, x is the column and y is the row (no swap)."""
        a, b, c, d = _leaf("a"), _leaf("b"), _leaf("c"), _leaf("d")
        comp = _composite("C", [[a, b], [c, d]])
        assert list(comp) == [
            ((0, 0), a),
            ((1, 0), b),
            ((0, 1), c),
            ((1, 1), d),
        ]

    def test_iter_skips_none_cells(self) -> None:
        """None cells in the grid are not yielded."""
        a, d = _leaf("a"), _leaf("d")
        comp = _composite("C", [[a, None], [None, d]])
        assert list(comp) == [((0, 0), a), ((1, 1), d)]


class TestSubTileHelpersAcceptObjectOrName:
    """get_sub_tile_offset / part_of_tile / is_root_tile accept an object or a name."""

    def test_offset_simple_self_by_object_and_name(self) -> None:
        """A leaf is at offset (0, 0) whether queried by object or name."""
        leaf = _leaf("M")
        assert leaf.get_sub_tile_offset(leaf) == (0, 0)
        assert leaf.get_sub_tile_offset("M") == (0, 0)

    def test_offset_simple_missing_raises(self) -> None:
        """Requesting an unknown sub-tile from a leaf raises."""
        with pytest.raises(ValueError, match="not found in tile"):
            _leaf("M").get_sub_tile_offset("Other")

    def test_offset_composite_top_left_origin(self) -> None:
        """Composite offsets use y=0 at the top row, by object or name."""
        tl, tr = _leaf("tl"), _leaf("tr")
        bl, br = _leaf("bl"), _leaf("br")
        # Stored top first: top row then bottom row.
        comp = _composite("C", [[tl, tr], [bl, br]])
        assert comp.get_sub_tile_offset("tl") == (0, 0)
        assert comp.get_sub_tile_offset(tl) == (0, 0)
        assert comp.get_sub_tile_offset("tr") == (1, 0)
        assert comp.get_sub_tile_offset(bl) == (0, 1)
        assert comp.get_sub_tile_offset(br) == (1, 1)

    def test_part_of_tile_by_object_and_name(self) -> None:
        """part_of_tile reflects membership for both object and name."""
        a, b = _leaf("a"), _leaf("b")
        comp = _composite("C", [[a, b]])
        assert comp.part_of_tile("a") is True
        assert comp.part_of_tile(b) is True
        assert comp.part_of_tile("X") is False
        assert comp.part_of_tile(_leaf("X")) is False

    def test_is_root_tile_by_object_and_name(self) -> None:
        """The bottom-left sub-tile is the root, by object or name."""
        leaf = _leaf("M")
        assert leaf.is_root_tile(leaf) is True
        assert leaf.is_root_tile("M") is True

        tl, tr = _leaf("tl"), _leaf("tr")
        bl, br = _leaf("bl"), _leaf("br")
        comp = _composite("C", [[tl, tr], [bl, br]])
        assert comp.is_root_tile("bl") is True
        assert comp.is_root_tile(bl) is True
        assert comp.is_root_tile("tl") is False
        assert comp.is_root_tile(tr) is False


def _leaf_all_sides(name: str) -> Tile:
    """Build a leaf tile carrying one port on each of the four sides."""
    return _leaf(
        name,
        ports=[
            _tport(f"{name}_N", Side.NORTH),
            _tport(f"{name}_S", Side.SOUTH),
            _tport(f"{name}_E", Side.EAST),
            _tport(f"{name}_W", Side.WEST),
        ],
    )


class TestPerimeterAndInternalPorts:
    """Tests for get_ports_around_tile / get_internal_connections on Tile."""

    def test_leaf_has_no_perimeter_or_internal(self) -> None:
        """A leaf tile exposes no composite-level perimeter or internal ports."""
        leaf = _leaf_all_sides("L")
        assert leaf.get_ports_around_tile() == {}
        assert leaf.get_internal_connections() == []

    def test_composite_perimeter_ports(self) -> None:
        """Perimeter cells expose only the sides whose neighbor is absent.

        For a 2-row, 1-column composite stored top first (``[[top], [bot]]``):
        the top cell exposes NORTH, EAST and WEST; the bottom cell exposes
        SOUTH, EAST and WEST. The shared edge (top SOUTH / bottom NORTH) is
        internal and not in the perimeter result.
        """
        top, bot = _leaf_all_sides("top"), _leaf_all_sides("bot")
        comp = _composite("C", [[top], [bot]])

        ports = comp.get_ports_around_tile()

        # Keys follow __iter__ raw (x, y) indexing: top is (0, 0), bot is (0, 1).
        assert set(ports) == {"0,0", "0,1"}

        # Top cell: NORTH exposed (no tile above), EAST and WEST exposed; the
        # SOUTH side faces the bottom cell, so it is not a perimeter side.
        assert top.get_port_on_side(Side.NORTH) in ports["0,0"]
        assert top.get_port_on_side(Side.EAST) in ports["0,0"]
        assert top.get_port_on_side(Side.WEST) in ports["0,0"]
        assert top.get_port_on_side(Side.SOUTH) not in ports["0,0"]

        # Bottom cell: SOUTH exposed (no tile below), EAST and WEST exposed; the
        # NORTH side faces the top cell, so it is not a perimeter side.
        assert bot.get_port_on_side(Side.SOUTH) in ports["0,1"]
        assert bot.get_port_on_side(Side.EAST) in ports["0,1"]
        assert bot.get_port_on_side(Side.WEST) in ports["0,1"]
        assert bot.get_port_on_side(Side.NORTH) not in ports["0,1"]

    def test_composite_internal_connections(self) -> None:
        """The shared edge between stacked cells is reported as internal.

        The top cell's SOUTH side and the bottom cell's NORTH side form the one
        internal edge of the stack.
        """
        top, bot = _leaf_all_sides("top"), _leaf_all_sides("bot")
        comp = _composite("C", [[top], [bot]])

        internal = comp.get_internal_connections()

        # Two directed entries: top->south (at 0,0) and bot->north (at 0,1).
        assert (top.get_port_on_side(Side.SOUTH), 0, 0) in internal
        assert (bot.get_port_on_side(Side.NORTH), 0, 1) in internal
        assert len(internal) == 2


class TestMasterAnchorOffsets:
    """Tests for get_anchor_offset / get_master_offset on Tile."""

    def test_leaf_offsets_are_origin(self) -> None:
        """A leaf tile has anchor and master at the origin."""
        leaf = _leaf("L")
        assert leaf.get_anchor_offset() == (0, 0)
        assert leaf.get_master_offset() == (0, 0)

    def test_composite_anchor_is_first_cell(self) -> None:
        """The anchor is the first non-None cell in row-major order (top-left)."""
        top, bot = _leaf("top"), _leaf("bot")
        # Top-first storage: tile_map[0] is the top row, so (0, 0) is the anchor.
        comp = _composite("C", [[top], [bot]])
        assert comp.get_anchor_offset() == (0, 0)

    def test_composite_master_is_last_cell(self) -> None:
        """The master defaults to the last non-None cell in row-major order."""
        top, bot = _leaf("top"), _leaf("bot")
        comp = _composite("C", [[top], [bot]])
        assert comp.get_master_offset() == (0, 1)

    def test_composite_master_override_honored(self) -> None:
        """An explicit master_offset overrides the row-major default."""
        top, bot = _leaf("top"), _leaf("bot")
        comp = _composite("C", [[top], [bot]], master_offset=(0, 0))
        assert comp.get_master_offset() == (0, 0)

    def test_composite_all_none_master_raises(self) -> None:
        """A composite with an all-None tile_map raises on get_master_offset."""
        comp = _composite("C", [[None], [None]])
        with pytest.raises(ValueError, match="no sub-tiles"):
            comp.get_master_offset()


class TestTotalConfigBits:
    """``total_config_bits`` sums switch matrix bits and all BEL config bits."""

    def test_leaf_sums_matrix_and_bels(self) -> None:
        """A leaf reports switch matrix bits plus the sum of BEL config bits."""
        leaf = _leaf(
            "T",
            bels=[_bel(2), _bel(3)],
            switch_matrix=SwitchMatrix.from_config_bits(4),
        )
        assert leaf.total_config_bits == 4 + 2 + 3

    def test_composite_sums_matrix_and_master_bels(self) -> None:
        """A composite reports its own switch matrix bits plus its BEL bits."""
        top, bot = _leaf("top"), _leaf("bot")
        comp = _composite(
            "C",
            [[top], [bot]],
            bels=[_bel(2)],
            switch_matrix=SwitchMatrix.from_config_bits(4),
        )
        assert comp.total_config_bits == 6


def _ports_on_side(side: Side, count: int, prefix: str) -> list[TilePort]:
    """Build ``count`` single-wire OUTPUT ports on a given side of the tile."""
    return [_tport(f"{prefix}_{side.name}_{i}", side) for i in range(count)]


class TestGetMinDieAreaComposite:
    """``get_min_die_area`` derives min dimensions from per-side pin counts.

    For a composite tile it must take the maximum per-side pin count across all
    constituent sub-tiles; a leaf tile uses its own per-side pin counts.
    """

    def test_leaf_uses_own_port_counts(self) -> None:
        """A leaf derives its min dimensions from its own per-side ports."""
        leaf = _leaf("L", ports=_ports_on_side(Side.NORTH, 4, "L"))
        pitch = Decimal("0.5")
        thickness = Decimal(2)
        mw, _ = leaf.get_min_die_area(
            x_pitch=pitch,
            y_pitch=pitch,
            x_pin_thickness_mult=thickness,
            y_pin_thickness_mult=thickness,
            frame_data_width=0,
            frame_strobe_width=0,
            edge_offset=2,
        )
        # 4 pins x 2 thickness + 2 offset = 10 tracks x 0.5 pitch = 5.0 um.
        assert mw == Decimal("5.0")

    def test_composite_uses_max_per_side_across_subtiles(self) -> None:
        """A composite takes the max per-side pin count across its sub-tiles."""
        # Two stacked sub-tiles: 3 north pins on top, 6 north pins on bottom.
        top = _leaf("top", ports=_ports_on_side(Side.NORTH, 3, "top"))
        bot = _leaf("bot", ports=_ports_on_side(Side.NORTH, 6, "bot"))
        comp = _composite("C", [[top], [bot]])
        pitch = Decimal("0.5")
        thickness = Decimal(2)
        mw, _ = comp.get_min_die_area(
            x_pitch=pitch,
            y_pitch=pitch,
            x_pin_thickness_mult=thickness,
            y_pin_thickness_mult=thickness,
            frame_data_width=0,
            frame_strobe_width=0,
            edge_offset=2,
        )
        # max(3, 6) = 6 pins x 2 thickness + 2 offset = 14 tracks x 0.5 = 7.0 um.
        assert mw == Decimal("7.0")
