"""Tests for hardcoded validation checks in Fabric.__post_init__."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from tests.conftest import make_muladd_bel
from tests.fabric_definition.conftest import make_empty_tile


class TestFabricValidation:
    """Validate hardcoded bitstream and naming constraints."""

    @pytest.mark.parametrize(
        ("rows", "columns"),
        [
            pytest.param(15, 15, id="defaults"),
            pytest.param(32, 15, id="rows_at_boundary"),
            pytest.param(15, 32, id="columns_at_boundary"),
            pytest.param(32, 32, id="both_at_boundary"),
        ],
    )
    def test_valid_configurations(
        self,
        make_fabric: Callable[..., Fabric],
        rows: int,
        columns: int,
    ) -> None:
        """Grids up to the 32x32 bitstream limit are accepted unchanged."""
        fabric = make_fabric(numberOfRows=rows, numberOfColumns=columns)

        assert (fabric.numberOfRows, fabric.numberOfColumns) == (rows, columns)
        assert (fabric.frameBitsPerRow, fabric.maxFramesPerCol) == (32, 20)

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
        ("num_bels", "expectation"),
        [
            pytest.param(26, nullcontext(), id="bels_at_boundary"),
            pytest.param(
                27,
                pytest.raises(
                    ValueError, match="tile test_tile cannot have more than 26 BELs"
                ),
                id="bels_exceed_26",
            ),
        ],
    )
    def test_tile_bel_count(
        self,
        make_fabric: Callable[..., Fabric],
        num_bels: int,
        expectation: AbstractContextManager,
    ) -> None:
        """A tile may hold at most 26 BELs, one per BEL naming letter."""
        tile = make_empty_tile("test_tile")
        tile.bels = [make_muladd_bel([]) for _ in range(num_bels)]
        with expectation:
            make_fabric(tileDic={"test_tile": tile})


def test_get_all_unique_bels_one_per_name(make_fabric: Callable[..., Fabric]) -> None:
    """Every BEL name appears once, as the first instance across the tiles."""
    lut = Bel(
        src=Path("LUT4.v"),
        prefix="L_",
        module_name="LUT4",
        internal=[],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )
    first_tile = make_empty_tile("FIRST")
    first_tile.bels = [
        make_muladd_bel([], prefix="A_"),
        make_muladd_bel([], prefix="B_"),
    ]
    second_tile = make_empty_tile("SECOND")
    second_tile.bels = [lut, make_muladd_bel([], prefix="C_")]
    fabric = make_fabric(tileDic={"FIRST": first_tile, "SECOND": second_tile})

    bels = fabric.getAllUniqueBels()

    assert [(bel.prefix, bel.name) for bel in bels] == [
        ("A_", "MULADD"),
        ("L_", "LUT4"),
    ]


class TestGetSuperTileContaining:
    """Resolve which SuperTile (if any) a tile belongs to."""

    @staticmethod
    def _make_super_tile(name: str, tile_names: list[str]) -> SuperTile:
        tiles = [make_empty_tile(tile_name) for tile_name in tile_names]
        return SuperTile(
            name=name,
            tileDir=Path(),
            tiles=tiles,
            tileMap=[tiles],
        )

    def test_returns_supertile_for_member_tile(
        self, make_fabric: Callable[..., Fabric]
    ) -> None:
        super_tile = self._make_super_tile("SUPER_X", ["SUB_A", "SUB_B"])
        fabric = make_fabric(superTileDic={"SUPER_X": super_tile})

        assert fabric.get_super_tile_containing("SUB_A") is super_tile
        assert fabric.get_super_tile_containing("SUB_B") is super_tile

    def test_returns_none_for_non_member_tile(
        self, make_fabric: Callable[..., Fabric]
    ) -> None:
        super_tile = self._make_super_tile("SUPER_X", ["SUB_A"])
        fabric = make_fabric(superTileDic={"SUPER_X": super_tile})

        assert fabric.get_super_tile_containing("OTHER") is None

    def test_returns_none_without_supertiles(
        self, make_fabric: Callable[..., Fabric]
    ) -> None:
        fabric = make_fabric()

        assert fabric.get_super_tile_containing("ANY") is None
