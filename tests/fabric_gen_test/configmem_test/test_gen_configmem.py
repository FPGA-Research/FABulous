"""Test module for configuration memory generation functions.

This module contains comprehensive tests for the configuration memory generation
functionality, including CSV initialization file creation and RTL generation.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_cad.gen_bitstream_spec import generateBitstreamSpec
from fabulous.fabric_definition.configmem import ConfigMem, ConfigMemFrame
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_configmem import (
    generate_composite_config_mem,
    generate_tile_config_mem,
    generateConfigMem,
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
        ).to_csv(output_file)
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
        tile_config_bits = tile_config.total_config_bits
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
        ).to_csv(output_file)
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
        tile_config_bits = tile_config.total_config_bits
        has_capacity, max_fabric_bits = _check_fabric_capacity(
            fabric_config, tile_config_bits
        )

        if not has_capacity:
            with pytest.raises((ValueError, RuntimeError, AssertionError)):
                ConfigMem.default(
                    tile_config_bits,
                    frame_bits_per_row=fabric_config.frameBitsPerRow,
                    max_frames_per_col=fabric_config.maxFramesPerCol,
                ).to_csv(tmp_path / "should_fail.csv")
            return

        output_file = tmp_path / f"bitmask_{fabric_config.name}_{tile_config.name}.csv"
        ConfigMem.default(
            tile_config_bits,
            frame_bits_per_row=fabric_config.frameBitsPerRow,
            max_frames_per_col=fabric_config.maxFramesPerCol,
        ).to_csv(output_file)

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
        tile_config_bits = tile_config.total_config_bits
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
                ).to_csv(tmp_path / "should_fail.csv")
            return

        output_file = (
            tmp_path / f"allocation_{fabric_config.name}_{tile_config.name}.csv"
        )
        ConfigMem.default(
            tile_config_bits,
            frame_bits_per_row=fabric_config.frameBitsPerRow,
            max_frames_per_col=fabric_config.maxFramesPerCol,
        ).to_csv(output_file)

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
        tile_config_bits = default_tile.total_config_bits
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
                ).to_csv(output_file)
            return

        ConfigMem.default(
            tile_config_bits,
            frame_bits_per_row=default_fabric.frameBitsPerRow,
            max_frames_per_col=default_fabric.maxFramesPerCol,
        ).to_csv(output_file)

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
        """Test generateConfigMem creates RTL with right number of config_latch."""
        # Create config CSV file path
        config_csv = tmp_path / f"{tile_config.name}_configMem.csv"

        # Create code generator
        writer = code_generator_factory(".v")

        # Call generateConfigMem
        has_capacity, _ = _check_fabric_capacity(
            fabric_config, tile_config.total_config_bits
        )
        if not has_capacity and tile_config.total_config_bits > 0:
            with pytest.raises(ValueError, match="exceed fabric capacity"):
                ConfigMem.for_tile(
                    config_csv,
                    config_bits=tile_config.total_config_bits,
                    frame_bits_per_row=fabric_config.frameBitsPerRow,
                    max_frames_per_col=fabric_config.maxFramesPerCol,
                )
            return

        generateConfigMem(
            writer,
            tile_config.name,
            ConfigMem.for_tile(
                config_csv,
                config_bits=tile_config.total_config_bits,
                frame_bits_per_row=fabric_config.frameBitsPerRow,
                max_frames_per_col=fabric_config.maxFramesPerCol,
            ),
        )

        # Verify output file was created and contains expected content
        output_file = writer.outFileName
        if tile_config.total_config_bits != 0:
            assert output_file.exists(), "Output file should be created"
        else:
            return  # Skip further checks if no config bits are generated

        # Read and verify the generated content
        content = output_file.read_text()

        # Count actual config_latch instantiations in content
        actual_instantiations = content.count("config_latch")
        assert actual_instantiations == tile_config.total_config_bits, (
            f"Expected {tile_config.total_config_bits} config_latch instantiations, "
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
        memory = ConfigMem(
            tuple(config_memlist_data),
            default_fabric.frameBitsPerRow,
            len(config_memlist_data),
        )
        csv_path = tmp_path / f"{default_tile.name}_configMem.csv"
        memory.to_csv(csv_path)

        # Generate the ConfigMem RTL
        generateConfigMem(writer, default_tile.name, memory)

        # Read the generated RTL
        rtl_content = writer.outFileName.read_text()

        # Verify each frame mapping
        for config_mem in config_memlist_data:
            if config_mem.bits_used_in_frame == 0:
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


def _make_composite(tmp_path: Path, *, master_config_bits: int) -> Tile:
    """Build a 1-wide, 2-tall composite `C`: top `C_top` over master `C_bot`.

    The wrapper switch matrix is a real 4-input mux, so the composite carries two
    wrapper config bits. Each sub-tile gets its own directory and a file-shaped
    `tile_dir`, matching what the CSV parser produces, so the master's ConfigMem
    CSV resolves next to its own tile CSV.

    Parameters
    ----------
    tmp_path : Path
        Directory the composite and its sub-tiles live in.
    master_config_bits : int
        Number of config bits the master sub-tile uses for itself.

    Returns
    -------
    Tile
        The composite tile, mastering at its bottom cell.
    """
    sub_tiles = []
    for name, config_bits in (("C_top", 0), ("C_bot", master_config_bits)):
        (tmp_path / name).mkdir(exist_ok=True)
        sub_tiles.append(
            make_empty_tile(
                name,
                tile_dir=tmp_path / name / f"{name}.csv",
                pin_order_config={},
                config_bits=config_bits,
            )
        )
    top, bot = sub_tiles

    wrapper_matrix = tmp_path / "C_matrix.list"
    wrapper_matrix.write_text(
        "\n".join(f"SUPER_A0,{src}" for src in ("C_bot_A0", "GND0", "VCC0", "C_bot_A1"))
        + "\n"
    )
    return Tile(
        name="C",
        ports=[],
        bels=[],
        tile_dir=tmp_path / "C.csv",
        matrix_dir=wrapper_matrix,
        gen_ios=[],
        switch_matrix=SwitchMatrix(
            matrix_file=wrapper_matrix,
            connections={"SUPER_A0": ["C_bot_A0", "GND0", "VCC0", "C_bot_A1"]},
        ),
        tile_map=[[top], [bot]],
        sub_tiles=[top, bot],
        master_offset=(0, 1),
        pin_order_config={},
        userCLK=False,
    )


class TestConfigMemFrameKeySet:
    """`ConfigMem.from_csv` requires exactly one row per frame index.

    A composite is allocated from the free slots of its master's frames, which
    are indexed directly, so a row-count-correct but key-set-incomplete CSV must
    raise rather than default the missing frames to all-free.
    """

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
            # Duplicate frame_index 1 leaves frame_index 2 entirely missing,
            # while the row count (4) still matches max_frames_per_col.
            pytest.param([0, 1, 1, 3], id="duplicate_index"),
            # frame_index 4 is out of range for max_frames_per_col=4 (0..3),
            # while the row count still matches.
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


class TestCompositeConfigMemAllocation:
    """A composite's ConfigMem is allocated from its master's FREE frame slots.

    The master uses two config bits of its own, which `generateConfigMemInit`
    packs into the top two bits of frame 0 (`1100` with four bits per frame), so
    the composite's own two bits must land elsewhere.
    """

    FRAME_BITS = 4
    MAX_FRAMES = 4
    MASTER_MASKS = ["1100", "0000", "0000", "0000"]

    def _generate(
        self, composite: Tile, code_generator_factory: Callable[..., CodeGenerator]
    ) -> Path:
        """Run composite ConfigMem generation and return the composite CSV path."""
        writer = code_generator_factory(".v", f"{composite.name}_ConfigMem")
        generate_composite_config_mem(
            writer,
            composite,
            frame_bits_per_row=self.FRAME_BITS,
            max_frames_per_col=self.MAX_FRAMES,
        )
        return composite.tile_dir.parent / f"{composite.name}_ConfigMem.csv"

    def _master_csv(self, composite: Tile) -> Path:
        """Return the master sub-tile's own ConfigMem CSV path."""
        master = composite.get_master_tile()
        return master.tile_dir.parent / f"{master.name}_ConfigMem.csv"

    def test_fresh_generation_avoids_master_used_bits(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[..., CodeGenerator],
    ) -> None:
        """A freshly generated composite CSV never reuses the master's own bits."""
        composite = _make_composite(tmp_path, master_config_bits=2)
        _write_configmem_csv(
            self._master_csv(composite),
            self.MASTER_MASKS,
            ["1:0", "# NULL", "# NULL", "# NULL"],
        )

        out = self._generate(composite, code_generator_factory)

        masks = _read_masks(out)
        assert sum(mask.count("1") for mask in masks.values()) == 2
        assert all(
            not (a == "1" and b == "1")
            for a, b in zip(masks[0], self.MASTER_MASKS[0], strict=True)
        )

    def test_missing_master_csv_is_generated_first(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[..., CodeGenerator],
    ) -> None:
        """The master's own ConfigMem is generated when it has not been yet."""
        composite = _make_composite(tmp_path, master_config_bits=2)
        master_csv = self._master_csv(composite)
        assert not master_csv.exists()

        out = self._generate(composite, code_generator_factory)

        assert _read_masks(master_csv)[0] == self.MASTER_MASKS[0]
        assert _read_masks(out)[0] == "0011"

    def test_existing_valid_csv_is_reused(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[..., CodeGenerator],
    ) -> None:
        """A valid hand-tuned composite CSV is kept, not overwritten."""
        composite = _make_composite(tmp_path, master_config_bits=2)
        _write_configmem_csv(
            self._master_csv(composite),
            self.MASTER_MASKS,
            ["1:0", "# NULL", "# NULL", "# NULL"],
        )
        out = composite.tile_dir.parent / "C_ConfigMem.csv"
        # Uses the master's free low bits, disjoint from the master's own bits.
        _write_configmem_csv(
            out, ["0000", "0011", "0000", "0000"], ["# NULL", "0;1", "# NULL", "# NULL"]
        )
        before = out.read_text()

        self._generate(composite, code_generator_factory)

        assert out.read_text() == before

    @pytest.mark.parametrize(
        ("masks", "ranges", "error_match"),
        [
            # Bit 0 (MSB) of frame 0 is used by the master (1100) -> conflict.
            pytest.param(
                ["1010", "0000", "0000", "0000"],
                ["0;1", "# NULL", "# NULL", "# NULL"],
                "conflicts with the master",
                id="conflict_with_master",
            ),
            # Only one used bit, but the composite wrapper needs two.
            pytest.param(
                ["0001", "0000", "0000", "0000"],
                ["0", "# NULL", "# NULL", "# NULL"],
                "needs 2",
                id="stale_bit_count",
            ),
        ],
    )
    def test_invalid_existing_csv_raises(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[..., CodeGenerator],
        masks: list[str],
        ranges: list[str],
        error_match: str,
    ) -> None:
        """A stale composite CSV fails at generation time, not at bitstream time."""
        composite = _make_composite(tmp_path, master_config_bits=2)
        _write_configmem_csv(
            self._master_csv(composite),
            self.MASTER_MASKS,
            ["1:0", "# NULL", "# NULL", "# NULL"],
        )
        _write_configmem_csv(
            composite.tile_dir.parent / "C_ConfigMem.csv", masks, ranges
        )

        with pytest.raises(ValueError, match=error_match):
            self._generate(composite, code_generator_factory)

    def test_missing_master_tile_directory_raises(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[..., CodeGenerator],
    ) -> None:
        """A master whose directory does not exist fails loudly, not silently free."""
        composite = _make_composite(tmp_path, master_config_bits=2)
        composite.get_master_tile().tile_dir = tmp_path / "nowhere" / "C_bot.csv"

        with pytest.raises(FileNotFoundError, match="C_bot"):
            self._generate(composite, code_generator_factory)

    def test_unset_master_tile_dir_raises(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[..., CodeGenerator],
    ) -> None:
        """A master with the default empty tile_dir fails loudly, not from the CWD.

        `Path().is_dir()` resolves to the current working directory, so a
        master whose `tile_dir` was never set would otherwise silently pass
        the directory guard and read the wrong ConfigMem file.
        """
        composite = _make_composite(tmp_path, master_config_bits=2)
        composite.get_master_tile().tile_dir = Path()

        with pytest.raises(ValueError, match="unset tile_dir"):
            self._generate(composite, code_generator_factory)


class TestCompositeConfigMemBitstreamSpec:
    """Freshly generated composite ConfigMems survive the bitstream-spec check."""

    def test_generated_composite_bits_pass_bitstream_spec(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[..., CodeGenerator],
    ) -> None:
        """Generation places the wrapper bits outside the master's own frame bits."""
        composite = _make_composite(tmp_path, master_config_bits=2)
        top, bot = composite.get_sub_tiles()
        writer = code_generator_factory(".v", "C_bot_ConfigMem")
        generate_tile_config_mem(
            writer, bot, frame_bits_per_row=32, max_frames_per_col=20
        )
        writer = code_generator_factory(".v", "C_ConfigMem")
        generate_composite_config_mem(
            writer, composite, frame_bits_per_row=32, max_frames_per_col=20
        )
        fabric = Fabric(
            fabric_dir=tmp_path,
            tile=[[bot], [top]],
            numberOfRows=2,
            numberOfColumns=1,
            maxFramesPerCol=20,
            frameBitsPerRow=32,
            tileDic={"C": composite, "C_top": top, "C_bot": bot},
        )

        spec = generateBitstreamSpec(fabric)

        # The master packs its own two bits at the top of frame 0 (physical bits
        # 31 and 30); every wrapper pip bit must sit outside those.
        master_own_bits = {31, 30}
        wrapper_bits = {
            bit
            for pip, bits in spec["TileSpecs"]["X0Y0"].items()
            if pip.endswith(".SUPER_A0")
            for bit in bits
        }
        assert wrapper_bits
        assert wrapper_bits.isdisjoint(master_own_bits)
