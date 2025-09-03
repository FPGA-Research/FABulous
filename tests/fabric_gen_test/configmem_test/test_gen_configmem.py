"""Test module for configuration memory generation functions.

This module contains comprehensive tests for the configuration memory generation
functionality, including CSV initialization file creation and RTL generation.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from FABulous.fabric_definition.ConfigMem import ConfigMem
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.gen_fabric.gen_configmem import (
    generateConfigMem,
    generateConfigMemInit,
)
from tests.fabric_gen_test.conftest import verify_csv_content


def _check_fabric_capacity(
    fabric_config: Fabric, tile_config_bits: int
) -> tuple[bool, int]:
    """Check if fabric has sufficient capacity for config bits."""
    max_fabric_bits = fabric_config.frameBitsPerRow * fabric_config.maxFramesPerCol
    return max_fabric_bits >= tile_config_bits, max_fabric_bits


def _should_skip_test(tile_config_bits: int, max_fabric_bits: int) -> bool:
    """Determine if test should be skipped based on config bits and fabric capacity."""
    return tile_config_bits == 0 or max_fabric_bits == 0


def _expect_capacity_error(
    fabric_config: Fabric, output_file: Path, tile_config_bits: int
) -> None:
    """Test that capacity error is raised with meaningful message."""
    with pytest.raises((ValueError, RuntimeError, AssertionError)) as exc_info:
        generateConfigMemInit(fabric_config, output_file, tile_config_bits)
    # Verify that the error message is meaningful
    error_msg = str(exc_info.value).lower()
    assert "exceed fabric capacity" in error_msg


class TestGenerateConfigMemInit:
    """Parametric test cases for generateConfigMemInit function."""

    def test_configmem_init_generates_correct_csv_structure(
        self, tmp_path: Path, fabric_config: Fabric, tile_config: Tile
    ) -> None:
        """Test that generateConfigMemInit creates CSV with correct structure."""
        output_file = tmp_path / f"test_{fabric_config.name}_{tile_config.name}.csv"
        tile_config_bits = tile_config.globalConfigBits
        has_capacity, max_fabric_bits = _check_fabric_capacity(
            fabric_config, tile_config_bits
        )

        # Expect error when fabric can't accommodate the config bits
        if not has_capacity:
            _expect_capacity_error(fabric_config, output_file, tile_config_bits)
            return

        if tile_config_bits == 0:
            return

        generateConfigMemInit(fabric_config, output_file, tile_config_bits)
        rows = verify_csv_content(
            output_file, expected_rows=fabric_config.maxFramesPerCol
        )

        # Verify frame naming and indexing
        for i, row in enumerate(rows):
            assert row["frame_name"] == f"frame{i}"
            assert row["frame_index"] == str(i)

        # Verify total bits allocation
        total_allocated_bits = sum(int(row["bits_used_in_frame"]) for row in rows)
        assert total_allocated_bits == tile_config_bits

    def test_bitmask_format_is_valid_binary_with_correct_bit_counts(
        self, tmp_path: Path, fabric_config: Fabric, tile_config: Tile
    ) -> None:
        """Test that generated bitmasks are valid."""
        tile_config_bits = tile_config.globalConfigBits
        has_capacity, max_fabric_bits = _check_fabric_capacity(
            fabric_config, tile_config_bits
        )

        if not has_capacity:
            with pytest.raises((ValueError, RuntimeError, AssertionError)):
                generateConfigMemInit(
                    fabric_config, tmp_path / "should_fail.csv", tile_config_bits
                )
            return

        output_file = tmp_path / f"bitmask_{fabric_config.name}_{tile_config.name}.csv"
        generateConfigMemInit(fabric_config, output_file, tile_config_bits)

        rows = verify_csv_content(
            output_file, expected_rows=fabric_config.maxFramesPerCol
        )

        # Validate bitmask format for each frame
        for i, row in enumerate(rows):
            mask = row["used_bits_mask"]
            bits_used = int(row["bits_used_in_frame"])

            # Remove underscores and validate format
            clean_mask = mask.replace("_", "")
            assert len(clean_mask) == fabric_config.frameBitsPerRow, (
                f"Frame {i} mask length mismatch"
            )
            assert clean_mask.count("1") == bits_used, f"Frame {i} bit count mismatch"
            assert all(c in "01" for c in clean_mask), (
                f"Frame {i} contains invalid characters"
            )

    def test_bit_allocation_strategy_follows_frame_priority_order(
        self, tmp_path: Path, fabric_config: Fabric, tile_config: Tile
    ) -> None:
        """Test that bits are allocated across frames following priority order."""
        tile_config_bits = tile_config.globalConfigBits
        has_capacity, max_fabric_bits = _check_fabric_capacity(
            fabric_config, tile_config_bits
        )

        # Skip invalid combinations
        if _should_skip_test(tile_config_bits, max_fabric_bits):
            pytest.skip("Zero config bits or fabric capacity")

        if not has_capacity:
            with pytest.raises((ValueError, RuntimeError, AssertionError)):
                generateConfigMemInit(
                    fabric_config, tmp_path / "should_fail.csv", tile_config_bits
                )
            return

        output_file = (
            tmp_path / f"allocation_{fabric_config.name}_{tile_config.name}.csv"
        )
        generateConfigMemInit(fabric_config, output_file, tile_config_bits)

        rows = verify_csv_content(
            output_file, expected_rows=fabric_config.maxFramesPerCol
        )

        # Verify total bit allocation matches requested
        total_allocated = sum(int(row["bits_used_in_frame"]) for row in rows)
        assert total_allocated == tile_config_bits, (
            f"Total allocated bits {total_allocated} != requested {tile_config_bits}"
        )

        # Verify bits are allocated from highest to lowest (starting from last frames)
        non_zero_frames = [
            i for i, row in enumerate(rows) if int(row["bits_used_in_frame"]) > 0
        ]
        if non_zero_frames:
            # Bits should be allocated starting from frame 0 (highest priority)
            assert non_zero_frames[0] == 0, "Bit allocation should start from frame 0"

    def test_config_bit_ranges_have_valid_descending_format(
        self, tmp_path: Path, default_fabric: Fabric, default_tile: Tile
    ) -> None:
        """Test that ConfigBits_ranges are formatted correctly."""
        tile_config_bits = default_tile.globalConfigBits
        has_capacity, max_fabric_bits = _check_fabric_capacity(
            default_fabric, tile_config_bits
        )

        # Skip scenarios with no config bits or zero fabric parameters
        if _should_skip_test(tile_config_bits, max_fabric_bits):
            pytest.skip("No config bits or zero fabric parameters scenario")

        output_file = (
            tmp_path / f"test_ranges_{default_fabric.name}_{default_tile.name}.csv"
        )

        # Expect error when fabric can't accommodate the config bits
        if not has_capacity:
            with pytest.raises((ValueError, RuntimeError, AssertionError)):
                generateConfigMemInit(default_fabric, output_file, tile_config_bits)
            return

        generateConfigMemInit(default_fabric, output_file, tile_config_bits)

        rows = verify_csv_content(output_file)

        # Verify ranges are properly formatted and sequential
        for row in rows:
            config_range = row["ConfigBits_ranges"]
            if config_range != "# NULL":
                if ":" in config_range:
                    left, right = config_range.split(":")
                    assert int(left) >= int(right)  # Should be descending
                else:
                    # Single bit case
                    assert config_range.isdigit()


class TestGeneratedConfigMemRTL:
    """Parametric test cases for generateConfigMem function."""

    def test_configmem_rtl_generates_correct_lhqd1_instantiations(
        self,
        tmp_path: Path,
        fabric_config: Fabric,
        tile_config: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
    ) -> None:
        """Test generateConfigMem creates RTL with right number of LHQD1."""
        # Create config CSV file path
        config_csv = tmp_path / f"{tile_config.name}_configMem.csv"

        # Create code generator
        writer = code_generator_factory(".v")

        # Call generateConfigMem
        has_capacity, _ = _check_fabric_capacity(
            fabric_config, tile_config.globalConfigBits
        )
        if not has_capacity and tile_config.globalConfigBits > 0:
            with pytest.raises(ValueError, match="adjust the tile configuration."):
                generateConfigMem(writer, fabric_config, tile_config, config_csv)
            return

        generateConfigMem(writer, fabric_config, tile_config, config_csv)

        # Verify output file was created and contains expected content
        output_file = writer.outFileName
        if tile_config.globalConfigBits != 0:
            assert output_file.exists(), "Output file should be created"
        else:
            return  # Skip further checks if no config bits are generated

        # Read and verify the generated content
        content = output_file.read_text()

        # Count actual LHQD1 instantiations in content
        actual_instantiations = content.count("LHQD1")
        assert actual_instantiations == tile_config.globalConfigBits, (
            f"Expected {tile_config.globalConfigBits} LHQD1 instantiations, found"
            f" {actual_instantiations}"
        )

    def test_configmem_rtl_maps_frame_signals_to_config_bits_correctly(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        configmem_list: Callable[[Fabric, Tile], list[ConfigMem]],
        tmp_path: Path,
        code_generator_factory: Callable[[str, str], CodeGenerator],
        mocker: MockerFixture,
    ) -> None:
        """Test that generated RTL correctly maps FrameData and FrameStrobe to
        ConfigBits.
        """
        # Create code generator
        writer = code_generator_factory(".v", f"{default_tile.name}_ConfigMem")
        writer.outFileName = tmp_path / f"{default_tile.name}_ConfigMem.v"

        # Create CSV file path
        csv_path = tmp_path / f"{default_tile.name}_configMem.csv"
        csv_path.touch()

        config_memlist_data = configmem_list(default_fabric, default_tile)

        # Mock parseConfigMem to return our configmem_list fixture
        mock_parse = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_configmem.parseConfigMem"
        )
        mock_parse.return_value = config_memlist_data

        # Generate the ConfigMem RTL
        generateConfigMem(writer, default_fabric, default_tile, csv_path)

        # Read the generated RTL
        rtl_content = writer.outFileName.read_text()

        # Verify each frame mapping
        for config_mem in config_memlist_data:
            if config_mem.bitsUsedInFrame == 0:
                continue

            frame_idx = config_mem.frameIndex
            bit_mask = config_mem.usedBitMask
            expected_config_bits = config_mem.configBitRanges

            # Check each bit in the frame
            config_bit_counter = 0
            for bit_pos in range(len(bit_mask)):
                if bit_mask[bit_pos] == "1":
                    # This bit should be connected
                    frame_data_bit = default_fabric.frameBitsPerRow - 1 - bit_pos
                    frame_strobe_bit = frame_idx
                    expected_config_bit = expected_config_bits[config_bit_counter]

                    # Verify the LHQD1 instantiation exists with correct connections
                    expected_inst_name = (
                        f"Inst_{config_mem.frameName}_bit{frame_data_bit}"
                    )
                    assert expected_inst_name in rtl_content, (
                        f"Missing LHQD1 instantiation: {expected_inst_name}"
                    )

                    # Verify the port connections
                    connection = (
                        f"    .D(FrameData[{frame_data_bit}]),\n"
                        f"    .E(FrameStrobe[{frame_strobe_bit}]),\n"
                        f"    .Q(ConfigBits[{expected_config_bit}]),\n"
                        f"    .QN(ConfigBits_N[{expected_config_bit}])"
                    )
                    assert connection in rtl_content, (
                        f"Missing connection {connection} for {expected_inst_name}"
                    )

                    config_bit_counter += 1
