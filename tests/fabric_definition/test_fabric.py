"""Tests for hardcoded validation checks in Fabric.__post_init__."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from tests.fabric_definition.conftest import make_empty_tile


class TestFabricValidation:
    """Validate hardcoded bitstream and naming constraints."""

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({}, id="defaults"),
            pytest.param({"numberOfRows": 32}, id="rows_at_boundary"),
            pytest.param({"numberOfColumns": 32}, id="columns_at_boundary"),
            pytest.param(
                {"numberOfRows": 32, "numberOfColumns": 32},
                id="both_at_boundary",
            ),
        ],
    )
    def test_valid_configurations(
        self,
        make_fabric: Callable[..., Fabric],
        overrides: dict,
    ) -> None:
        fabric = make_fabric(**overrides)
        for key, value in overrides.items():
            assert getattr(fabric, key) == value

    @pytest.mark.parametrize(
        ("overrides", "error_match"),
        [
            pytest.param(
                {"numberOfRows": 33},
                "numberOfRows must be less than or equal to 32",
                id="rows_exceed_32",
            ),
            pytest.param(
                {"numberOfRows": 64},
                "numberOfRows must be less than or equal to 32",
                id="rows_far_exceed_32",
            ),
            pytest.param(
                {"numberOfColumns": 33},
                "numberOfColumns must be less than or equal to 32",
                id="columns_exceed_32",
            ),
            pytest.param(
                {"numberOfColumns": 64},
                "numberOfColumns must be less than or equal to 32",
                id="columns_far_exceed_32",
            ),
            pytest.param(
                {"frameBitsPerRow": 16},
                "frameBitsPerRow must be 32",
                id="frame_bits_per_row_wrong",
            ),
            pytest.param(
                {"maxFramesPerCol": 19},
                "maxFramesPerCol must be 20",
                id="max_frames_below_20",
            ),
            pytest.param(
                {"maxFramesPerCol": 21},
                "maxFramesPerCol must be 20",
                id="max_frames_above_20",
            ),
            pytest.param(
                {"frameSelectWidth": 4},
                "frameSelectWidth must be 5",
                id="frame_select_width_wrong",
            ),
            pytest.param(
                {"rowSelectWidth": 3},
                "rowSelectWidth must be 5",
                id="row_select_width_wrong",
            ),
            pytest.param(
                {"desync_flag": 10},
                "desync_flag must be 20",
                id="desync_flag_wrong",
            ),
        ],
    )
    def test_invalid_configurations(
        self,
        make_fabric: Callable[..., Fabric],
        overrides: dict,
        error_match: str,
    ) -> None:
        with pytest.raises(ValueError, match=error_match):
            make_fabric(**overrides)

    @pytest.mark.parametrize(
        ("num_bels", "should_raise"),
        [
            pytest.param(26, False, id="bels_at_boundary"),
            pytest.param(27, True, id="bels_exceed_26"),
            pytest.param(30, True, id="bels_far_exceed_26"),
        ],
    )
    def test_tile_bel_count(
        self,
        make_fabric: Callable[..., Fabric],
        num_bels: int,
        should_raise: bool,
    ) -> None:
        tile = MagicMock(spec=Tile)
        tile.name = "test_tile"
        tile.is_composite = False
        tile.bels = [MagicMock() for _ in range(num_bels)]
        if should_raise:
            with pytest.raises(ValueError, match="cannot have more than 26 BELs"):
                make_fabric(tileDic={"test_tile": tile})
        else:
            fabric = make_fabric(tileDic={"test_tile": tile})
            assert len(fabric.tileDic["test_tile"].bels) == num_bels


def _composite(name: str, tile_map: list[list[Tile | None]]) -> Tile:
    """Build a composite Tile carrying a top-first object tile_map."""
    sub_tiles = [t for row in tile_map for t in row if t is not None]
    return Tile(
        name=name,
        ports=[],
        bels=[],
        tile_dir=Path(),
        matrix_dir=Path(),
        gen_ios=[],
        user_clk=False,
        switch_matrix=SwitchMatrix(matrix_file=Path()),
        tile_map=tile_map,
        sub_tiles=sub_tiles,
        pin_order_config={},
    )


class TestFabricCompositeQueries:
    """``find_tile_positions`` and ``get_all_unique_tiles`` over a composite.

    Layout: a single column with DSP_top over DSP_bot. The composite ``tile_map``
    is top-first ``[[DSP_top], [DSP_bot]]`` while the fabric grid is bottom-first
    ``[[DSP_bot], [DSP_top]]``.
    """

    def _fabric(self, make_fabric: Callable[..., Fabric]) -> tuple[Fabric, Tile]:
        # Leaf sub-tiles for the composite; mark them as belonging to a supertile
        # exactly as the parser does.
        top_def = make_empty_tile("DSP_top", pin_order_config={})
        bot_def = make_empty_tile("DSP_bot", pin_order_config={})
        top_def.part_of_super_tile = True
        bot_def.part_of_super_tile = True
        composite = _composite("DSP", [[top_def], [bot_def]])

        # Grid is bottom-first: row 0 is the bottom (DSP_bot).
        grid_bot = make_empty_tile("DSP_bot", pin_order_config={})
        grid_top = make_empty_tile("DSP_top", pin_order_config={})
        grid_bot.part_of_super_tile = True
        grid_top.part_of_super_tile = True
        plain = make_empty_tile("LUT", pin_order_config={})

        fabric = make_fabric(
            tile=[[grid_bot], [grid_top]],
            numberOfColumns=1,
            tileDic={
                "DSP": composite,
                "DSP_top": grid_top,
                "DSP_bot": grid_bot,
                "LUT": plain,
            },
        )
        return fabric, composite

    def test_find_tile_positions_for_composite(
        self, make_fabric: Callable[..., Fabric]
    ) -> None:
        fabric, composite = self._fabric(make_fabric)
        positions = fabric.find_tile_positions(composite)
        # Both covered cells are reported: bottom (y=0) and top (y=1).
        assert positions is not None
        assert set(positions) == {(0, 0), (0, 1)}

    def test_find_tile_positions_for_leaf(
        self, make_fabric: Callable[..., Fabric]
    ) -> None:
        fabric, _ = self._fabric(make_fabric)
        positions = fabric.find_tile_positions(fabric.tileDic["DSP_top"])
        assert positions == [(0, 1)]

    def test_get_all_unique_tiles_includes_composite_not_subtiles(
        self, make_fabric: Callable[..., Fabric]
    ) -> None:
        fabric, _ = self._fabric(make_fabric)
        names = {t.name for t in fabric.get_all_unique_tiles()}
        # The composite and the standalone leaf are returned; the composite's
        # sub-tiles (part_of_super_tile) are not.
        assert names == {"DSP", "LUT"}
