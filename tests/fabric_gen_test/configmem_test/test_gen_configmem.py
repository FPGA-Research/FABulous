"""Test module for configuration memory generation functions.

This module contains comprehensive tests for the configuration memory generation
functionality, including CSV initialization file creation and RTL generation.
"""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from fabulous.fabric_definition.configmem import ConfigMem, ConfigMemFrame
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_configmem import (
    build_super_tile_config_mem,
    generate_config_mem,
    generate_super_tile_config_mem,
    generate_tile_config_mem,
    validate_super_tile_config_mem,
)
from tests.conftest import make_empty_tile
from tests.fabric_gen_test.conftest import create_config_csv, verify_csv_content


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
        ConfigMem.default(
            tile_config_bits,
            frame_bits_per_row=fabric_config.frameBitsPerRow,
            max_frames_per_col=fabric_config.maxFramesPerCol,
            source=output_file,
        ).to_csv()
    # Verify that the error message is meaningful
    error_msg = str(exc_info.value).lower()
    assert "exceed fabric capacity" in error_msg


class TestDefaultConfigMemCsv:
    """Parametric test cases for ConfigMem.default function."""

    def test_configmem_init_generates_correct_csv_structure(
        self, tmp_path: Path, fabric_config: Fabric, tile_config: Tile
    ) -> None:
        """Test that the default mapping writes a CSV with correct structure."""
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

        ConfigMem.default(
            tile_config_bits,
            frame_bits_per_row=fabric_config.frameBitsPerRow,
            max_frames_per_col=fabric_config.maxFramesPerCol,
            source=output_file,
        ).to_csv()
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
                ConfigMem.default(
                    tile_config_bits,
                    frame_bits_per_row=fabric_config.frameBitsPerRow,
                    max_frames_per_col=fabric_config.maxFramesPerCol,
                    source=tmp_path / "should_fail.csv",
                ).to_csv()
            return

        output_file = tmp_path / f"bitmask_{fabric_config.name}_{tile_config.name}.csv"
        ConfigMem.default(
            tile_config_bits,
            frame_bits_per_row=fabric_config.frameBitsPerRow,
            max_frames_per_col=fabric_config.maxFramesPerCol,
            source=output_file,
        ).to_csv()

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
                ConfigMem.default(
                    tile_config_bits,
                    frame_bits_per_row=fabric_config.frameBitsPerRow,
                    max_frames_per_col=fabric_config.maxFramesPerCol,
                    source=tmp_path / "should_fail.csv",
                ).to_csv()
            return

        output_file = (
            tmp_path / f"allocation_{fabric_config.name}_{tile_config.name}.csv"
        )
        ConfigMem.default(
            tile_config_bits,
            frame_bits_per_row=fabric_config.frameBitsPerRow,
            max_frames_per_col=fabric_config.maxFramesPerCol,
            source=output_file,
        ).to_csv()

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
                ConfigMem.default(
                    tile_config_bits,
                    frame_bits_per_row=default_fabric.frameBitsPerRow,
                    max_frames_per_col=default_fabric.maxFramesPerCol,
                    source=output_file,
                ).to_csv()
            return

        ConfigMem.default(
            tile_config_bits,
            frame_bits_per_row=default_fabric.frameBitsPerRow,
            max_frames_per_col=default_fabric.maxFramesPerCol,
            source=output_file,
        ).to_csv()

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
    """Parametric test cases for generate_config_mem function."""

    def test_configmem_rtl_generates_correct_lhqd1_instantiations(
        self,
        fabric_config: Fabric,
        tile_config: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
    ) -> None:
        """Test generate_config_mem creates RTL with right number of config_latch."""
        # Create code generator
        writer = code_generator_factory(".v")

        # Call generate_config_mem
        has_capacity, _ = _check_fabric_capacity(
            fabric_config, tile_config.globalConfigBits
        )
        if not has_capacity and tile_config.globalConfigBits > 0:
            with pytest.raises(ValueError, match="exceed fabric capacity"):
                ConfigMem.default(
                    tile_config.globalConfigBits,
                    frame_bits_per_row=fabric_config.frameBitsPerRow,
                    max_frames_per_col=fabric_config.maxFramesPerCol,
                    source=Path("ConfigMem.csv"),
                )
            return

        generate_config_mem(
            writer,
            tile_config.name,
            ConfigMem.default(
                tile_config.globalConfigBits,
                frame_bits_per_row=fabric_config.frameBitsPerRow,
                max_frames_per_col=fabric_config.maxFramesPerCol,
                source=Path("ConfigMem.csv"),
            ),
        )

        # Verify output file was created and contains expected content
        output_file = writer.outFileName
        if tile_config.globalConfigBits != 0:
            assert output_file.exists(), "Output file should be created"
        else:
            return  # Skip further checks if no config bits are generated

        # Read and verify the generated content
        content = output_file.read_text()

        # Count actual config_latch instantiations in content
        actual_instantiations = content.count("config_latch")
        assert actual_instantiations == tile_config.globalConfigBits, (
            f"Expected {tile_config.globalConfigBits} config_latch instantiations, "
            f"found {actual_instantiations}"
        )

    def test_configmem_rtl_maps_frame_signals_to_config_bits_correctly(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        configmem_list: Callable[[Fabric, Tile], list[ConfigMemFrame]],
        tmp_path: Path,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> None:
        """Test that generated RTL correctly maps FrameData and FrameStrobe to
        ConfigBits."""
        # Create code generator
        writer = code_generator_factory(".v", f"{default_tile.name}_ConfigMem")
        writer.outFileName = tmp_path / f"{default_tile.name}_ConfigMem.v"

        config_memlist_data = configmem_list(default_fabric, default_tile)
        csv_path = tmp_path / f"{default_tile.name}_configMem.csv"
        memory = ConfigMem(
            tuple(config_memlist_data),
            default_fabric.frameBitsPerRow,
            len(config_memlist_data),
            source=csv_path,
        )
        memory.to_csv()

        # Generate the ConfigMem RTL
        generate_config_mem(writer, default_tile.name, memory)

        # Read the generated RTL
        rtl_content = writer.outFileName.read_text()

        # Verify each frame mapping
        for config_mem in config_memlist_data:
            if not config_mem.bits:
                continue

            frame_idx = config_mem.frame_index
            bit_mask = config_mem.used_bits_mask
            expected_config_bits = config_mem.config_bit_ranges

            # Check each bit in the frame
            config_bit_counter = 0
            for bit_pos in range(len(bit_mask)):
                if bit_mask[bit_pos] == "1":
                    # This bit should be connected
                    frame_data_bit = default_fabric.frameBitsPerRow - 1 - bit_pos
                    frame_strobe_bit = frame_idx
                    expected_config_bit = expected_config_bits[config_bit_counter]

                    # Verify the config_latch instantiation exists with correct
                    # connections
                    expected_inst_name = (
                        f"Inst_{config_mem.frame_name}_bit{frame_data_bit}"
                    )
                    assert expected_inst_name in rtl_content, (
                        f"Missing config_latch instantiation: {expected_inst_name}"
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


def _write_configmem_csv(path: Path, masks: list[str], ranges: list[str]) -> None:
    """Write a minimal ConfigMem CSV with the given per-frame masks and ranges.

    Parameters
    ----------
    path : Path
        Destination CSV path.
    masks : list[str]
        One `used_bits_mask` per frame, in frame-index order.
    ranges : list[str]
        One `ConfigBits_ranges` entry per frame, in frame-index order.
    """
    create_config_csv(
        path,
        [
            {
                "frame_name": f"frame{i}",
                "frame_index": i,
                "bits_used_in_frame": mask.count("1"),
                "used_bits_mask": mask,
                "ConfigBits_ranges": rng,
            }
            for i, (mask, rng) in enumerate(zip(masks, ranges, strict=True))
        ],
    )


def _read_masks(path: Path) -> dict[int, str]:
    """Read a ConfigMem CSV into `{frame_index: used_bits_mask}` (no underscores).

    Parameters
    ----------
    path : Path
        The ConfigMem CSV to read.

    Returns
    -------
    dict[int, str]
        Mapping from frame index to its `used_bits_mask`.
    """
    rows = verify_csv_content(path)
    return {int(r["frame_index"]): r["used_bits_mask"].replace("_", "") for r in rows}


class TestConfigMemFrameKeySet:
    """`ConfigMem.from_csv` requires exactly one row per frame index."""

    def test_complete_frame_set_is_read(self, tmp_path: Path) -> None:
        """A CSV with exactly one row per frame index round-trips cleanly."""
        path = tmp_path / "ConfigMem.csv"
        _write_configmem_csv(
            path,
            ["1100", "0000", "0000", "0000"],
            ["0;1", "# NULL", "# NULL", "# NULL"],
        )

        memory = ConfigMem.from_csv(path, frame_bits_per_row=4, max_frames_per_col=4)

        assert [frame.used_bits_mask.to01() for frame in memory.frames] == [
            "1100",
            "0000",
            "0000",
            "0000",
        ]

    @pytest.mark.parametrize(
        "frame_indices",
        [
            # Duplicate index 1, missing index 2, row count still 4.
            pytest.param([0, 1, 1, 3], id="duplicate_index"),
            # Index 4 is out of range for 4 frames, row count still 4.
            pytest.param([0, 1, 2, 4], id="out_of_range_index"),
        ],
    )
    def test_incomplete_frame_key_set_raises(
        self, tmp_path: Path, frame_indices: list[int]
    ) -> None:
        """A row-count-correct but key-set-incomplete CSV raises, not silently."""
        path = tmp_path / "ConfigMem.csv"
        create_config_csv(
            path,
            [
                {
                    "frame_name": f"frame{i}",
                    "frame_index": frame_idx,
                    "bits_used_in_frame": 0,
                    "used_bits_mask": "0000",
                    "ConfigBits_ranges": "# NULL",
                }
                for i, frame_idx in enumerate(frame_indices)
            ],
        )

        with pytest.raises(ValueError, match="indexed 0 .. n-1 in order"):
            ConfigMem.from_csv(path, frame_bits_per_row=4, max_frames_per_col=4)


class TestSuperTileConfigMemAllocation:
    """A supertile's bits take the free crosspoints of its master's memory.

    The master has 4 frames of 4 bits and uses the top two of frame 0 (`1100`).
    """

    FRAME_BITS = 4
    MAX_FRAMES = 4
    MASTER_MASKS = ["1100", "0000", "0000", "0000"]
    MASTER_RANGES = ["1:0", "# NULL", "# NULL", "# NULL"]

    def _master(self, tmp_path: Path) -> ConfigMem:
        path = tmp_path / "DSP_bot_ConfigMem.csv"
        _write_configmem_csv(path, self.MASTER_MASKS, self.MASTER_RANGES)
        return ConfigMem.from_csv(
            path,
            frame_bits_per_row=self.FRAME_BITS,
            max_frames_per_col=self.MAX_FRAMES,
        )

    def _existing(
        self, tmp_path: Path, masks: list[str], ranges: list[str]
    ) -> ConfigMem:
        path = tmp_path / "DSP_ConfigMem.csv"
        _write_configmem_csv(path, masks, ranges)
        return ConfigMem.from_csv(
            path,
            frame_bits_per_row=self.FRAME_BITS,
            max_frames_per_col=self.MAX_FRAMES,
        )

    def test_the_bits_avoid_every_crosspoint_the_master_uses(
        self, tmp_path: Path
    ) -> None:
        master = self._master(tmp_path)

        built = build_super_tile_config_mem(master, 2, source=Path("ST_ConfigMem.csv"))

        assert built.config_bits == 2
        assert set(built.bit_at) <= set(master.free_crosspoints)
        assert not set(built.bit_at) & set(master.bit_at)

    def test_a_master_without_room_is_refused(self, tmp_path: Path) -> None:
        master = self._master(tmp_path)

        with pytest.raises(ValueError, match="Not enough free config bit slots"):
            build_super_tile_config_mem(
                master,
                self.FRAME_BITS * self.MAX_FRAMES,
                source=Path("ST_ConfigMem.csv"),
            )

    def test_an_existing_disjoint_memory_passes(self, tmp_path: Path) -> None:
        master = self._master(tmp_path)
        existing = self._existing(
            tmp_path,
            ["0011", "0000", "0000", "0000"],
            ["0;1", "# NULL", "# NULL", "# NULL"],
        )

        validate_super_tile_config_mem(existing, master, 2)

    @pytest.mark.parametrize(
        ("masks", "ranges", "bits", "error_match"),
        [
            # Bit 0 (MSB) is used by the master (1100) -> conflict.
            pytest.param(
                ["1010", "0000", "0000", "0000"],
                ["0;1", "# NULL", "# NULL", "# NULL"],
                2,
                "conflicts with the master",
                id="conflict_with_master",
            ),
            # Only one used bit, but the supertile needs two.
            pytest.param(
                ["0001", "0000", "0000", "0000"],
                ["0", "# NULL", "# NULL", "# NULL"],
                2,
                "needs 2",
                id="stale_bit_count",
            ),
        ],
    )
    def test_an_invalid_existing_memory_raises(
        self,
        tmp_path: Path,
        masks: list[str],
        ranges: list[str],
        bits: int,
        error_match: str,
    ) -> None:
        master = self._master(tmp_path)
        existing = self._existing(tmp_path, masks, ranges)

        with pytest.raises(ValueError, match=error_match):
            validate_super_tile_config_mem(existing, master, bits)


class TestGenerateSuperTileConfigMem:
    """What `generate_super_tile_config_mem` does with the memory it finds."""

    def test_a_mapping_file_holding_no_bits_is_refused(
        self, tmp_path: Path, code_generator_factory: Callable[..., CodeGenerator]
    ) -> None:
        """An existing file mapping no bits is refused, not rebuilt over."""
        master = ConfigMem.default(
            2, frame_bits_per_row=32, max_frames_per_col=20, source=Path("master.csv")
        )
        stale = ConfigMem.default(
            0,
            frame_bits_per_row=32,
            max_frames_per_col=20,
            source=tmp_path / "ST_ConfigMem.csv",
        )
        stale.to_csv()
        super_tile = SuperTile(
            name="ST",
            tileDir=tmp_path / "ST.csv",
            tiles=[],
            tileMap=[[]],
            switch_matrix=SwitchMatrix(
                matrix_file=tmp_path / "ST_switch_matrix.csv",
                connections={},
                hdl_config_bits=4,
            ),
            config_mem=stale,
        )

        with pytest.raises(ValueError, match="maps no configuration bits"):
            generate_super_tile_config_mem(
                code_generator_factory(".v"), super_tile, master
            )

    def test_a_supertile_declared_in_the_fabric_csv_is_found_by_its_children(
        self, tmp_path: Path, code_generator_factory: Callable[..., CodeGenerator]
    ) -> None:
        """A supertile declared in `fabric.csv` writes beside its children."""
        st_dir = tmp_path / "Tile" / "ST"
        child = make_empty_tile(
            "C",
            tileDir=tmp_path / "fabric.csv",
            matrixDir=st_dir / "C" / "C_switch_matrix.csv",
        )
        master = ConfigMem.default(
            2, frame_bits_per_row=32, max_frames_per_col=20, source=Path("master.csv")
        )
        super_tile = SuperTile(
            name="ST",
            tileDir=tmp_path / "fabric.csv",
            tiles=[child],
            tileMap=[[child]],
            switch_matrix=SwitchMatrix(
                matrix_file=st_dir / "ST_switch_matrix.csv",
                connections={},
                hdl_config_bits=4,
            ),
            config_mem=ConfigMem.default(
                0,
                frame_bits_per_row=32,
                max_frames_per_col=20,
                source=st_dir / "ST_ConfigMem.csv",
            ),
        )

        generate_super_tile_config_mem(code_generator_factory(".v"), super_tile, master)

        assert (st_dir / "ST_ConfigMem.v").is_file()


class TestGenerateTileConfigMem:
    """What `generate_tile_config_mem` does with the memory the tile carries."""

    @staticmethod
    def _tile(tmp_path: Path, memory: ConfigMem) -> Tile:
        tile = make_empty_tile(
            "T",
            config_bits=4,
            tileDir=tmp_path / "T.csv",
            matrixDir=tmp_path / "T_switch_matrix.csv",
        )
        tile.config_mem = replace(memory, source=tmp_path / "T_ConfigMem.csv")
        return tile

    def test_an_unwritten_mapping_is_generated_and_saved(
        self, tmp_path: Path, code_generator_factory: Callable[..., CodeGenerator]
    ) -> None:
        """A tile parsed before any mapping existed gets the default written out."""
        empty = ConfigMem.default(
            0,
            frame_bits_per_row=32,
            max_frames_per_col=20,
            source=Path("ConfigMem.csv"),
        )
        tile = self._tile(tmp_path, empty)

        generate_tile_config_mem(code_generator_factory(".v"), tile)

        assert tile.config_mem.config_bits == 4
        assert (tmp_path / "T_ConfigMem.csv").is_file()

    @pytest.mark.parametrize("relocated", ["CONFIGMEM", "MATRIX"])
    def test_a_relocated_entry_leaves_the_module_in_the_tile_directory(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[..., CodeGenerator],
        relocated: str,
    ) -> None:
        """The module stays in the tile's directory wherever the CSVs point."""
        elsewhere = tmp_path / "elsewhere"
        empty = ConfigMem.default(
            0, frame_bits_per_row=32, max_frames_per_col=20, source=Path("unused.csv")
        )
        tile = self._tile(tmp_path, empty)
        if relocated == "CONFIGMEM":
            tile.config_mem = replace(empty, source=elsewhere / "Shared_ConfigMem.csv")
        else:
            tile.switch_matrix = replace(
                tile.switch_matrix, matrix_file=elsewhere / "Shared_matrix.csv"
            )

        generate_tile_config_mem(code_generator_factory(".v"), tile)

        assert (tmp_path / "T_ConfigMem.v").is_file()
        assert not (elsewhere / "T_ConfigMem.v").exists()

    def test_a_tile_declared_in_the_fabric_csv_is_found_by_its_matrix(
        self, tmp_path: Path, code_generator_factory: Callable[..., CodeGenerator]
    ) -> None:
        """A tile declared in `fabric.csv` writes beside its switch matrix."""
        tile_dir = tmp_path / "Tile" / "T"
        tile_dir.mkdir(parents=True)
        tile = make_empty_tile(
            "T",
            config_bits=4,
            tileDir=tmp_path / "fabric.csv",
            matrixDir=tile_dir / "T_switch_matrix.csv",
        )
        tile.config_mem = replace(tile.config_mem, source=tile_dir / "T_ConfigMem.csv")

        generate_tile_config_mem(code_generator_factory(".v"), tile)

        assert (tile_dir / "T_ConfigMem.v").is_file()

    def test_a_mapping_file_holding_no_bits_is_refused(
        self, tmp_path: Path, code_generator_factory: Callable[..., CodeGenerator]
    ) -> None:
        """An existing file mapping no bits is refused, not overwritten."""
        empty = ConfigMem.default(
            0,
            frame_bits_per_row=32,
            max_frames_per_col=20,
            source=tmp_path / "T_ConfigMem.csv",
        )
        empty.to_csv()
        tile = self._tile(tmp_path, empty)

        with pytest.raises(ValueError, match="maps no configuration bits"):
            generate_tile_config_mem(code_generator_factory(".v"), tile)

    def test_a_mapping_for_another_tile_is_refused(
        self, tmp_path: Path, code_generator_factory: Callable[..., CodeGenerator]
    ) -> None:
        """A file holding a different bit count is a mapping for something else."""
        wrong = ConfigMem.default(
            7,
            frame_bits_per_row=32,
            max_frames_per_col=20,
            source=Path("ConfigMem.csv"),
        )
        tile = self._tile(tmp_path, wrong)

        with pytest.raises(ValueError, match="maps 7 bits but T has 4"):
            generate_tile_config_mem(code_generator_factory(".v"), tile)
