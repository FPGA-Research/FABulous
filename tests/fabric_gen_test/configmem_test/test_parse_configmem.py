"""Test module for configuration memory parsing functionality.

This module contains comprehensive tests for the `parseConfigMem` function, including
various valid scenarios, error conditions, input format handling, and edge cases.
It uses parameterized tests to cover a wide range of configuration memory
specifications and validation logic.
"""

from pathlib import Path
from typing import NamedTuple

import pytest

from FABulous.fabric_generator.parser.parse_configmem import parseConfigMem
from tests.fabric_gen_test.conftest import create_config_csv


class ParseConfigTestCase(NamedTuple):
    """Test case for parseConfigMem function."""

    csv_data: list[dict]
    max_frames: int
    frame_bits: int
    global_bits: int
    expected_result_len: int
    expected_error: str | None = None  # If set, this is an error case


@pytest.mark.parametrize(
    "test_case",
    [
        # Basic valid cases
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": "0:1",
                    },
                    {
                        "frame_name": "Frame1",
                        "frame_index": "1",
                        "used_bits_mask": "0011",
                        "ConfigBits_ranges": "2:3",
                    },
                ],
                max_frames=2,
                frame_bits=4,
                global_bits=4,
                expected_result_len=2,
            ),
            id="standard_two_frames",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1111",
                        "ConfigBits_ranges": "3:0",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=4,
                expected_result_len=1,
            ),
            id="single_full_frame",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "0",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_result_len=1,
            ),
            id="single_bit",
        ),
        # Underscore handling
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "11_00",
                        "ConfigBits_ranges": "0:1",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_result_len=1,
            ),
            id="underscore_in_mask",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1_1_0_0",
                        "ConfigBits_ranges": "0:1",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_result_len=1,
            ),
            id="multiple_underscores",
        ),
        # Range variations
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": "1:0",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_result_len=1,
            ),
            id="reversed_range",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": "0;1",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_result_len=1,
            ),
            id="semicolon_separated",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1010",
                        "ConfigBits_ranges": "0;2",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_result_len=1,
            ),
            id="non_consecutive_semicolon",
        ),
        # Whitespace handling
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": " 0 : 1 ",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_result_len=1,
            ),
            id="whitespace_in_ranges",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": "\t0\t:\t1\t",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_result_len=1,
            ),
            id="tabs_in_ranges",
        ),
        # NULL handling
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "0000",
                        "ConfigBits_ranges": "NULL",
                    },
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=0,
                expected_result_len=0,
            ),
            id="null_range",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": "0:1",
                    },
                    {
                        "frame_name": "Frame1",
                        "frame_index": "1",
                        "used_bits_mask": "0000",
                        "ConfigBits_ranges": "NULL",
                    },
                ],
                max_frames=2,
                frame_bits=4,
                global_bits=2,
                expected_result_len=1,
            ),
            id="mixed_with_null",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": "0:1",
                    },
                    {
                        "frame_name": "Frame1",
                        "frame_index": "1",
                        "used_bits_mask": "0000",
                        "ConfigBits_ranges": "NULL",
                    },
                    {
                        "frame_name": "Frame2",
                        "frame_index": "2",
                        "used_bits_mask": "0011",
                        "ConfigBits_ranges": "2:3",
                    },
                ],
                max_frames=3,
                frame_bits=4,
                global_bits=4,
                expected_result_len=2,
            ),
            id="frame_empty_frame",
        ),
        # Error cases marked as expected failures
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": "0:1",
                    }
                ],
                max_frames=2,
                frame_bits=4,
                global_bits=2,
                expected_result_len=0,
                expected_error="entries but MaxFramesPerCol",
            ),
            id="frame_count_mismatch",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "11111",
                        "ConfigBits_ranges": "0:4",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=5,
                expected_result_len=0,
                expected_error="to many 1-elements in bitmask",
            ),
            id="too_many_ones",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1111",
                        "ConfigBits_ranges": "0;1;2",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=4,
                expected_result_len=0,
                expected_error="mismatch between the number of bits used in the frame",
            ),
            id="mask_range_len_mismatch",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "110",
                        "ConfigBits_ranges": "0:1",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=2,
                expected_result_len=0,
                expected_error="too long or short bitmask",
            ),
            id="wrong_bitmask_length",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1100",
                        "ConfigBits_ranges": "0:1",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=3,
                expected_result_len=0,
                expected_error="bitmask mismatch",
            ),
            id="bitmask_count_mismatch",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "0:0",
                    },
                    {
                        "frame_name": "Frame1",
                        "frame_index": "1",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "0:0",
                    },
                ],
                max_frames=2,
                frame_bits=4,
                global_bits=2,
                expected_result_len=0,
                expected_error="already allocated",
            ),
            id="repeated_bits_colon",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "0",
                    },
                    {
                        "frame_name": "Frame1",
                        "frame_index": "1",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "0",
                    },
                ],
                max_frames=2,
                frame_bits=4,
                global_bits=2,
                expected_result_len=0,
                expected_error="already allocated",
            ),
            id="repeated_bits_semicolon",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "0-1",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_result_len=0,
                expected_error="not a valid format",
            ),
            id="invalid_range_format",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_result_len=0,
                expected_error="not a valid format",
            ),
            id="empty_range",
        ),
        pytest.param(
            ParseConfigTestCase(
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
                expected_result_len=0,
                expected_error="invalid literal for int",
            ),
            id="invalid_frame_index",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "a:b",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_result_len=0,
                expected_error="invalid literal for int",
            ),
            id="invalid_colon_range",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "a",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_result_len=0,
                expected_error="not a valid format",
            ),
            id="invalid_semicolon_range",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": "5:",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_result_len=0,
                expected_error="invalid literal for int",
            ),
            id="malformed_colon_right",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": ":5",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_result_len=0,
                expected_error="invalid literal for int",
            ),
            id="malformed_colon_left",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "1000",
                        "ConfigBits_ranges": ":",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=1,
                expected_result_len=0,
                expected_error="invalid literal for int",
            ),
            id="malformed_colon_both",
        ),
        pytest.param(
            ParseConfigTestCase(
                csv_data=[
                    {
                        "frame_name": "Frame0",
                        "frame_index": "0",
                        "used_bits_mask": "0000",
                        "ConfigBits_ranges": "null",
                    }
                ],
                max_frames=1,
                frame_bits=4,
                global_bits=0,
                expected_result_len=0,
                expected_error="not a valid format",
            ),
            id="lowercase_null",
        ),
    ],
)
def test_parsing_scenarios(tmp_path: Path, test_case: ParseConfigTestCase) -> None:
    """Test various valid parsing scenarios and error conditions."""
    csv_file = tmp_path / f"test_{test_case.__class__.__name__}.csv"
    create_config_csv(csv_file, test_case.csv_data)

    if test_case.expected_error:
        # This is an error case - expect ValueError to be raised
        with pytest.raises(ValueError, match=test_case.expected_error):
            parseConfigMem(
                csv_file,
                test_case.max_frames,
                test_case.frame_bits,
                test_case.global_bits,
            )
    else:
        # This is a success case
        result = parseConfigMem(
            csv_file, test_case.max_frames, test_case.frame_bits, test_case.global_bits
        )

        assert len(result) == test_case.expected_result_len

        # Verify basic properties for non-empty results
        if test_case.expected_result_len > 0:
            # Check that we have the expected number of results
            assert len(result) == test_case.expected_result_len

            # Create a mapping of expected non-NULL frames for validation
            expected_frames = [
                frame
                for frame in test_case.csv_data
                if frame["ConfigBits_ranges"].upper() != "NULL"
            ]

            # Verify each returned frame matches the expected data
            for i, frame_result in enumerate(result):
                expected_frame = expected_frames[i]

                assert frame_result.frameName == expected_frame["frame_name"]
                assert frame_result.frameIndex == int(expected_frame["frame_index"])

                # Check underscore removal
                expected_mask = expected_frame["used_bits_mask"].replace("_", "")
                assert frame_result.usedBitMask == expected_mask

                # Verify bits used calculation
                assert frame_result.bitsUsedInFrame == expected_mask.count("1")
