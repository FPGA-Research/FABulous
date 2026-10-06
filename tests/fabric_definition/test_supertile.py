"""Tests for SuperTile methods.

The supertile aggregates Tile objects into a 2D layout. The methods under test are
pure functions of the ``tileMap`` shape and the constituent tiles' port counts:

- `get_ports_around_tile`: emits side-of-tile port lists for *outer* edges only.
- `get_internal_connections`: emits side-of-tile port lists for *inner* edges only.
- ``__iter__``: yields ``((x, y), tile)`` for every non-None cell.
- ``max_width`` / ``max_height``: dimensions of the layout grid.
- ``get_min_die_area``: pin-density-driven physical minimum.

These were not previously covered and are entry points to the global tile size
optimisation pipeline, so any drift in their semantics propagates silently.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import Side
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from tests.fabric_definition.conftest import make_empty_tile, make_side_port


class TestSuperTileLayout:
    """Geometric properties — independent of the constituent tiles' ports."""

    @pytest.mark.xfail(
        strict=True,
        reason="SuperTile.__iter__ yields (row, column) as (x, y), transposed "
        "against Fabric.__iter__ and get_ports_around_tile",
    )
    def test_iter_yields_only_non_none_tiles_with_xy(self) -> None:
        # Asymmetric layout so a transposed (x, y) is observable:
        #   row0: A, B, None
        #   row1: None, None, C
        a = make_empty_tile("A")
        b = make_empty_tile("B")
        c = make_empty_tile("C")
        st = SuperTile(
            name="ST",
            tileDir=Path(),
            tiles=[a, b, c],
            tileMap=[[a, b, None], [None, None, c]],
        )
        assert list(st) == [((0, 0), a), ((1, 0), b), ((2, 1), c)]

    def test_max_width_uses_widest_row(self) -> None:
        t = make_empty_tile("T")
        # Ragged layout: top row is wider.
        st = SuperTile(
            name="ST",
            tileDir=Path(),
            tiles=[t],
            tileMap=[[t, t, t], [t, None]],
        )
        assert st.max_width == 3

    def test_max_height_is_row_count(self) -> None:
        t = make_empty_tile("T")
        st = SuperTile(
            name="ST",
            tileDir=Path(),
            tiles=[t],
            tileMap=[[t], [t], [t]],
        )
        assert st.max_height == 3


class TestSuperTilePortQueries:
    """`get_ports_around_tile` / `get_internal_connections` partition the four
    edges of every cell into "outer" (boundary or facing a hole) and "inner"
    (facing another tile).

    The implementation calls the side-getter for outer-edges only
    in `get_ports_around_tile` and inner-edges only in `get_internal_connections`.
    """

    @staticmethod
    def _four_sided_tile(name: str) -> tuple[Tile, dict[Side, TilePort]]:
        """Build a real tile with one port on each side, keyed by side."""
        ports = {
            side: make_side_port(side, f"{name}_{side}")
            for side in (Side.NORTH, Side.EAST, Side.SOUTH, Side.WEST)
        }
        return make_empty_tile(name, ports=list(ports.values())), ports

    def test_single_tile_supertile_has_all_outer_edges(self) -> None:
        # A 1x1 supertile: every edge is outer, none are internal.
        tile, p = self._four_sided_tile("T")
        st = SuperTile(name="ST", tileDir=Path(), tiles=[tile], tileMap=[[tile]])

        assert st.get_ports_around_tile() == {
            "0,0": [[p[Side.NORTH]], [p[Side.EAST]], [p[Side.SOUTH]], [p[Side.WEST]]]
        }
        assert st.get_internal_connections() == []

    def test_l_shape_splits_outer_and_inner_edges(self) -> None:
        # Layout (the hole at (1, 1) makes B's south and C's east outer edges):
        #   row0: A, B
        #   row1: C, None
        a, pa = self._four_sided_tile("A")
        b, pb = self._four_sided_tile("B")
        c, pc = self._four_sided_tile("C")
        st = SuperTile(
            name="ST", tileDir=Path(), tiles=[a, b, c], tileMap=[[a, b], [c, None]]
        )

        # Keys are "x,y" for column x, row y; edges listed in N, E, S, W order.
        assert st.get_ports_around_tile() == {
            "0,0": [[pa[Side.NORTH]], [pa[Side.WEST]]],
            "1,0": [[pb[Side.NORTH]], [pb[Side.EAST]], [pb[Side.SOUTH]]],
            "0,1": [[pc[Side.EAST]], [pc[Side.SOUTH]], [pc[Side.WEST]]],
        }
        assert st.get_internal_connections() == [
            ([pa[Side.EAST]], 0, 0),
            ([pa[Side.SOUTH]], 0, 0),
            ([pb[Side.WEST]], 1, 0),
            ([pc[Side.NORTH]], 0, 1),
        ]


class TestSuperTileMinDieArea:
    """``get_min_die_area`` aggregates the maximum per-side port count across
    constituent tiles, then derives a physical floor from the pitch.

    Formula per side: ``min_dim = (max_count * thickness_mult + edge_offset) * pitch``.
    """

    def test_picks_max_side_count_across_tiles(self) -> None:
        # Tile A: 3 north, 1 east. Tile B: 1 north, 2 east.
        # Aggregate max: 3 north (=> width axis), 2 east (=> height axis).
        a = make_empty_tile(
            "A",
            ports=[make_side_port(Side.NORTH, f"AN{i}") for i in range(3)]
            + [make_side_port(Side.EAST, "AE")],
        )
        b = make_empty_tile(
            "B",
            ports=[make_side_port(Side.NORTH, "BN")]
            + [make_side_port(Side.EAST, f"BE{i}") for i in range(2)],
        )

        st = SuperTile(
            name="ST",
            tileDir=Path(),
            tiles=[a, b],
            tileMap=[[a, b]],
        )

        # pitch=1, thickness_mult=1, edge_offset=2.
        # width = (3*1 + 2)*1 = 5 ; height = (2*1 + 2)*1 = 4.
        w, h = st.get_min_die_area(
            x_pitch=Decimal(1),
            y_pitch=Decimal(1),
            x_pin_thickness_mult=Decimal(1),
            y_pin_thickness_mult=Decimal(1),
            edge_offset=2,
        )
        assert w == Decimal(5)
        assert h == Decimal(4)

    def test_thickness_mult_and_pitch_scale_dimensions(self) -> None:
        # 2 ports on south (covers x_io_count via max(north, south)).
        a = make_empty_tile(
            "A",
            ports=[make_side_port(Side.SOUTH, f"AS{i}") for i in range(2)]
            + [make_side_port(Side.WEST, "AW")],
        )
        st = SuperTile(
            name="ST",
            tileDir=Path(),
            tiles=[a],
            tileMap=[[a]],
        )
        # width = (2 * 3 + 2) * 0.5 = 4.0 ; height = (1 * 2 + 2) * 0.25 = 1.0
        w, h = st.get_min_die_area(
            x_pitch=Decimal("0.5"),
            y_pitch=Decimal("0.25"),
            x_pin_thickness_mult=Decimal(3),
            y_pin_thickness_mult=Decimal(2),
            edge_offset=2,
        )
        assert w == Decimal("4.0")
        assert h == Decimal("1.0")
