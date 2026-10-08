"""Test module for configuration memory parsing functionality.

This module contains comprehensive tests for the `parseConfigMem` function, including
various valid scenarios, error conditions, input format handling, and edge cases.
It uses parameterized tests to cover a wide range of configuration memory
specifications and validation logic.
"""

from pathlib import Path
from typing import NamedTuple

import pytest

from fabulous.fabric_definition.configmem import ConfigMem
from fabulous.fabric_generator.parser.parse_configmem import parseConfigMem
from tests.fabric_gen_test.conftest import create_config_csv


def _row(index: int, mask: str, ranges: str) -> dict[str, str]:
    """Build one ConfigMem CSV row for frame `index`."""
    return {
        "frame_name": f"Frame{index}",
        "frame_index": str(index),
        "used_bits_mask": mask,
        "ConfigBits_ranges": ranges,
    }


class ParseConfigTestCase(NamedTuple):
    """A ConfigMem CSV and the `parseConfigMem` result it must produce."""

    csv_data: list[dict[str, str]]
    max_frames: int
    frame_bits: int
    global_bits: int
    expected: list[ConfigMem]


class ParseConfigErrorCase(NamedTuple):
    """A ConfigMem CSV that `parseConfigMem` must reject."""

    csv_data: list[dict[str, str]]
    max_frames: int
    frame_bits: int
    global_bits: int
    expected_error: str


@pytest.mark.parametrize(
    "test_case",
    [
        # Basic valid cases
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1100", "0:1"), _row(1, "0011", "2:3")],
                max_frames=2,
                frame_bits=4,
                global_bits=4,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[0, 1],
                    ),
                    ConfigMem(
                        frameName="Frame1",
                        frameIndex=1,
                        bitsUsedInFrame=2,
                        usedBitMask="0011",
                        configBitRanges=[2, 3],
                    ),
                ],
            ),
            id="standard_two_frames",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1111", "3:0")],
                max_frames=1,
                frame_bits=4,
                global_bits=4,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=4,
                        usedBitMask="1111",
                        configBitRanges=[3, 2, 1, 0],
                    )
                ],
            ),
            id="single_full_frame",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1000", "0")],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=1,
                        usedBitMask="1000",
                        configBitRanges=[0],
                    )
                ],
            ),
            id="single_bit",
        ),
        # Underscore handling
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "11_00", "0:1")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[0, 1],
                    )
                ],
            ),
            id="underscore_in_mask",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1_1_0_0", "0:1")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[0, 1],
                    )
                ],
            ),
            id="multiple_underscores",
        ),
        # Range variations: the list order is the bit order the mask consumes.
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1100", "1:0")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[1, 0],
                    )
                ],
            ),
            id="reversed_range",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1100", "0;1")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[0, 1],
                    )
                ],
            ),
            id="semicolon_separated",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1100", "1;0")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[1, 0],
                    )
                ],
            ),
            id="semicolon_order_kept",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1010", "0;2")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1010",
                        configBitRanges=[0, 2],
                    )
                ],
            ),
            id="non_consecutive_semicolon",
        ),
        # Whitespace handling
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1100", " 0 : 1 ")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[0, 1],
                    )
                ],
            ),
            id="whitespace_in_ranges",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1100", "\t0\t:\t1\t")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[0, 1],
                    )
                ],
            ),
            id="tabs_in_ranges",
        ),
        # NULL handling: a NULL frame yields no entry.
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "0000", "NULL")],
                max_frames=1,
                frame_bits=4,
                global_bits=0,
                expected=[],
            ),
            id="null_range",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[_row(0, "1100", "0:1"), _row(1, "0000", "NULL")],
                max_frames=2,
                frame_bits=4,
                global_bits=2,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[0, 1],
                    )
                ],
            ),
            id="mixed_with_null",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    _row(0, "1100", "0:1"),
                    _row(1, "0000", "NULL"),
                    _row(2, "0011", "2:3"),
                ],
                max_frames=3,
                frame_bits=4,
                global_bits=4,
                expected=[
                    ConfigMem(
                        frameName="Frame0",
                        frameIndex=0,
                        bitsUsedInFrame=2,
                        usedBitMask="1100",
                        configBitRanges=[0, 1],
                    ),
                    ConfigMem(
                        frameName="Frame2",
                        frameIndex=2,
                        bitsUsedInFrame=2,
                        usedBitMask="0011",
                        configBitRanges=[2, 3],
                    ),
                ],
            ),
            id="frame_empty_frame",
        ),
    ],
)
def test_parsing_scenarios(tmp_path: Path, test_case: ParseConfigTestCase) -> None:
    """`parseConfigMem` returns one entry per used frame with its bit order."""
    csv_file = tmp_path / "configmem.csv"
    create_config_csv(csv_file, test_case.csv_data)

    result = parseConfigMem(
        csv_file, test_case.max_frames, test_case.frame_bits, test_case.global_bits
    )

    assert result == test_case.expected


@pytest.mark.parametrize(
    "test_case",
    [
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1100", "0:1")],
                max_frames=2,
                frame_bits=4,
                global_bits=2,
                expected_error="entries but MaxFramesPerCol",
            ),
            id="frame_count_mismatch",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "11111", "0:4")],
                max_frames=1,
                frame_bits=4,
                global_bits=5,
                expected_error="to many 1-elements in bitmask",
            ),
            id="too_many_ones",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1111", "0;1;2")],
                max_frames=1,
                frame_bits=4,
                global_bits=4,
                expected_error="mismatch between the number of bits used in the frame",
            ),
            id="mask_range_len_mismatch",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "110", "0:1")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_error="too long or short bitmask",
            ),
            id="wrong_bitmask_length",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1100", "0:1")],
                max_frames=1,
                frame_bits=4,
                global_bits=3,
                expected_error="bitmask mismatch",
            ),
            id="bitmask_count_mismatch",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", "0:0"), _row(1, "1000", "0:0")],
                max_frames=2,
                frame_bits=4,
                global_bits=2,
                expected_error="already allocated",
            ),
            id="repeated_bits_colon",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", "0"), _row(1, "1100", "1;0")],
                max_frames=2,
                frame_bits=4,
                global_bits=3,
                expected_error="already allocated",
            ),
            id="repeated_bits_semicolon",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", "0"), _row(1, "1000", "0")],
                max_frames=2,
                frame_bits=4,
                global_bits=2,
                expected_error="already allocated",
            ),
            id="repeated_bits_single_index",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1100", "0;0")],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_error="already allocated",
            ),
            id="repeated_bits_within_frame",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", "0-1")],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_error="not a valid format",
            ),
            id="invalid_range_format",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", "")],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_error="not a valid format",
            ),
            id="empty_range",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "invalid",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "0",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_error="invalid literal for int",
            ),
            id="invalid_frame_index",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", "a:b")],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_error="invalid literal for int",
            ),
            id="invalid_colon_range",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", "a")],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_error="not a valid format",
            ),
            id="invalid_semicolon_range",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", "5:")],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_error="invalid literal for int",
            ),
            id="malformed_colon_right",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", ":5")],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_error="invalid literal for int",
            ),
            id="malformed_colon_left",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "1000", ":")],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_error="invalid literal for int",
            ),
            id="malformed_colon_both",
        ),
        pytest.param(
            ParseConfigErrorCase(
                csv_data=[_row(0, "0000", "null")],
                max_frames=1,
                frame_bits=4,
                global_bits=0,
                expected_error="not a valid format",
            ),
            id="lowercase_null",
        ),
    ],
)
def test_parsing_errors(tmp_path: Path, test_case: ParseConfigErrorCase) -> None:
    """`parseConfigMem` rejects a malformed ConfigMem CSV with a `ValueError`."""
    csv_file = tmp_path / "configmem.csv"
    create_config_csv(csv_file, test_case.csv_data)

    with pytest.raises(ValueError, match=test_case.expected_error):
        parseConfigMem(
            csv_file, test_case.max_frames, test_case.frame_bits, test_case.global_bits
        )
