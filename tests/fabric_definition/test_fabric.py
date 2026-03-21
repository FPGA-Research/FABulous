"""Tests for FrameAddressRegister bit-field validation in Fabric.__post_init__."""

from collections.abc import Callable

import pytest

from fabulous.fabric_definition.fabric import Fabric


class TestFrameAddressRegisterValidation:
    """Validate that non-overlapping bit regions are enforced."""

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param(
                {},
                id="defaults",
            ),
            pytest.param(
                {"maxFramesPerCol": 26, "desync_flag": 26},
                id="frame_strobe_at_boundary",
            ),
            pytest.param(
                {"desync_flag": 20, "maxFramesPerCol": 20},
                id="desync_at_frame_strobe_boundary",
            ),
            pytest.param(
                {"numberOfColumns": 16, "frameSelectWidth": 4},
                id="column_bits_exact_fit",
            ),
            pytest.param(
                {
                    "frameBitsPerRow": 10,
                    "maxFramesPerCol": 4,
                    "desync_flag": 4,
                    "frameSelectWidth": 3,
                    "numberOfColumns": 8,
                },
                id="tight_valid_layout",
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
                {"maxFramesPerCol": 28},
                "FrameAddressRegister overflow",
                id="frame_strobe_overlaps_column_select",
            ),
            pytest.param(
                {"desync_flag": 10, "maxFramesPerCol": 20},
                "frame strobe region",
                id="desync_in_frame_strobe",
            ),
            pytest.param(
                {"desync_flag": 28},
                "column select region",
                id="desync_in_column_select",
            ),
            pytest.param(
                {"desync_flag": 27},
                "column select region",
                id="desync_at_column_select_boundary",
            ),
            pytest.param(
                {"desync_flag": 32, "frameBitsPerRow": 32},
                "exceeds FrameAddressRegister width",
                id="desync_exceeds_register_width",
            ),
            pytest.param(
                {"frameSelectWidth": 3},
                "Not enough column address bits",
                id="insufficient_column_bits",
            ),
            pytest.param(
                {"numberOfColumns": 17, "frameSelectWidth": 4},
                "Not enough column address bits",
                id="column_bits_one_over",
            ),
            pytest.param(
                {"frameBitsPerRow": 4, "maxFramesPerCol": 20, "frameSelectWidth": 5},
                "exceeds FrameAddressRegister width",
                id="all_regions_overlap",
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
