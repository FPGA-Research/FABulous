"""Tests for hardcoded validation checks in Fabric.__post_init__."""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile


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
        tile.bels = [MagicMock() for _ in range(num_bels)]
        if should_raise:
            with pytest.raises(ValueError, match="cannot have more than 26 BELs"):
                make_fabric(tileDic={"test_tile": tile})
        else:
            fabric = make_fabric(tileDic={"test_tile": tile})
            assert len(fabric.tileDic["test_tile"].bels) == num_bels
