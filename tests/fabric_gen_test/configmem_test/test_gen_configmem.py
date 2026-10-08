"""Test module for configuration memory generation functions.

This module contains comprehensive tests for the configuration memory generation
functionality, including CSV initialization file creation and RTL generation.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_configmem import (
    build_super_tile_config_mem_csv,
    generateConfigMem,
    generateConfigMemInit,
)
from tests.fabric_gen_test.conftest import create_config_csv, verify_csv_content


def _has_capacity(fabric_config: Fabric, tile_config_bits: int) -> bool:
    """Return whether the fabric has enough frame bits for the tile."""
    max_fabric_bits = fabric_config.frameBitsPerRow * fabric_config.maxFramesPerCol
    return max_fabric_bits >= tile_config_bits


_FULL_32 = "1111_1111_1111_1111_1111_1111_1111_1111"
_EMPTY_32 = "0000_0000_0000_0000_0000_0000_0000_0000"


class TestGenerateConfigMemInit:
    """`generateConfigMemInit` packs bits MSB-first from frame 0 onwards."""

    @pytest.mark.parametrize(
        ("bits", "frame_bits", "frames", "expected"),
        [
            pytest.param(
                5,
                4,
                3,
                [(4, "1111", "4:1"), (1, "1000", "0:0"), (0, "0000", "# NULL")],
                id="spills_into_second_frame",
            ),
            pytest.param(
                8,
                4,
                2,
                [(4, "1111", "7:4"), (4, "1111", "3:0")],
                id="exact_capacity",
            ),
            pytest.param(
                6,
                8,
                2,
                [(6, "1111_1100", "5:0"), (0, "0000_0000", "# NULL")],
                id="partial_frame_grouped_mask",
            ),
            pytest.param(
                0,
                4,
                2,
                [(0, "0000", "# NULL"), (0, "0000", "# NULL")],
                id="no_config_bits",
            ),
            pytest.param(
                127,
                32,
                20,
                [
                    (32, _FULL_32, "126:95"),
                    (32, _FULL_32, "94:63"),
                    (32, _FULL_32, "62:31"),
                    (31, "1111_1111_1111_1111_1111_1111_1111_1110", "30:0"),
                ]
                + [(0, _EMPTY_32, "# NULL")] * 16,
                id="default_fabric",
            ),
        ],
    )
    def test_configmem_init_rows(
        self,
        tmp_path: Path,
        bits: int,
        frame_bits: int,
        frames: int,
        expected: list[tuple[int, str, str]],
    ) -> None:
        """Every frame row carries its used-bit count, mask and descending range."""
        output_file = tmp_path / "configmem.csv"
        generateConfigMemInit(
            output_file,
            bits,
            frame_bits_per_row=frame_bits,
            max_frame_per_col=frames,
        )

        rows = verify_csv_content(output_file, expected_rows=frames)
        assert [
            (
                r["frame_name"],
                r["frame_index"],
                int(r["bits_used_in_frame"]),
                r["used_bits_mask"],
                r["ConfigBits_ranges"],
            )
            for r in rows
        ] == [
            (f"frame{i}", str(i), used, mask, ranges)
            for i, (used, mask, ranges) in enumerate(expected)
        ]

    @pytest.mark.parametrize(
        ("bits", "frame_bits", "frames"),
        [(9, 4, 2), (2, 1, 1), (257, 64, 4)],
        ids=["one_bit_over", "minimal_fabric", "wide_fabric"],
    )
    def test_configmem_init_rejects_over_capacity(
        self, tmp_path: Path, bits: int, frame_bits: int, frames: int
    ) -> None:
        """A tile needing more bits than the fabric frames hold raises, no file."""
        output_file = tmp_path / "configmem.csv"
        with pytest.raises(ValueError, match="exceed fabric capacity"):
            generateConfigMemInit(
                output_file,
                bits,
                frame_bits_per_row=frame_bits,
                max_frame_per_col=frames,
            )
        assert not output_file.exists()


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
        has_capacity = _has_capacity(fabric_config, tile_config.globalConfigBits)
        if not has_capacity and tile_config.globalConfigBits > 0:
            with pytest.raises(ValueError, match="adjust the configuration."):
                generateConfigMem(
                    writer,
                    tile_config.name,
                    tile_config.globalConfigBits,
                    config_csv,
                    frame_bits_per_row=fabric_config.frameBitsPerRow,
                    max_frame_per_col=fabric_config.maxFramesPerCol,
                )
            return

        generateConfigMem(
            writer,
            tile_config.name,
            tile_config.globalConfigBits,
            config_csv,
            frame_bits_per_row=fabric_config.frameBitsPerRow,
            max_frame_per_col=fabric_config.maxFramesPerCol,
        )

        # Verify output file was created and contains expected content
        output_file = writer.outFileName
        if tile_config.globalConfigBits == 0:
            assert not output_file.exists(), "No RTL without config bits"
            return
        assert output_file.exists(), "Output file should be created"

        # Read and verify the generated content
        content = output_file.read_text()

        # Count actual config_latch instantiations in content
        actual_instantiations = content.count("config_latch")
        assert actual_instantiations == tile_config.globalConfigBits, (
            f"Expected {tile_config.globalConfigBits} config_latch instantiations, "
            f"found {actual_instantiations}"
        )


def _write_configmem_csv(path: Path, masks: list[str], ranges: list[str]) -> None:
    """Write a minimal ConfigMem CSV with the given per-frame masks and ranges."""
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


class TestSuperTileConfigMemReuse:
    """`build_super_tile_config_mem_csv` reuses a valid existing CSV, else regen.

    Master tile has 4 frames of 4 bits each (tiny, for readability). Frame 0 uses
    its top two bits (`1100`), leaving the rest free for the supertile.
    """

    FRAME_BITS = 4
    MAX_FRAMES = 4
    MASTER_MASKS = ["1100", "0000", "0000", "0000"]
    MASTER_RANGES = ["1:0", "# NULL", "# NULL", "# NULL"]

    def _master(self, tmp_path: Path) -> Path:
        master = tmp_path / "DSP_bot_ConfigMem.csv"
        _write_configmem_csv(master, self.MASTER_MASKS, self.MASTER_RANGES)
        return master

    def _build(self, tmp_path: Path, out: Path, bits: int = 2) -> None:
        build_super_tile_config_mem_csv(
            self._master(tmp_path),
            bits,
            out,
            frame_bits_per_row=self.FRAME_BITS,
            max_frames_per_col=self.MAX_FRAMES,
        )

    def test_fresh_generation_when_absent(self, tmp_path: Path) -> None:
        out = tmp_path / "DSP_ConfigMem.csv"
        self._build(tmp_path, out)
        # The two supertile bits take the first free slots in reading order:
        # master frame 0's low bits, which the master leaves unused.
        rows = verify_csv_content(out, expected_rows=self.MAX_FRAMES)
        assert [
            (r["used_bits_mask"], r["bits_used_in_frame"], r["ConfigBits_ranges"])
            for r in rows
        ] == [
            ("0011", "2", "0;1"),
            ("0000", "0", "# NULL"),
            ("0000", "0", "# NULL"),
            ("0000", "0", "# NULL"),
        ]

    def test_existing_valid_csv_is_reused(self, tmp_path: Path) -> None:
        out = tmp_path / "DSP_ConfigMem.csv"
        # A valid supertile CSV using the master's free low bits, disjoint from it.
        _write_configmem_csv(
            out, ["0011", "0000", "0000", "0000"], ["0;1", "# NULL", "# NULL", "# NULL"]
        )
        before = out.read_text()
        self._build(tmp_path, out)
        assert out.read_text() == before  # reused, not regenerated

    @pytest.mark.parametrize(
        ("masks", "ranges", "error_match"),
        [
            # Bit 0 (MSB) is used by the master (1100) -> conflict.
            pytest.param(
                ["1010", "0000", "0000", "0000"],
                ["0;1", "# NULL", "# NULL", "# NULL"],
                "conflicts with the master",
                id="conflict_with_master",
            ),
            # Only one used bit, but the supertile needs two.
            pytest.param(
                ["0001", "0000", "0000", "0000"],
                ["0", "# NULL", "# NULL", "# NULL"],
                "needs 2",
                id="stale_bit_count",
            ),
        ],
    )
    def test_invalid_existing_csv_raises(
        self, tmp_path: Path, masks: list[str], ranges: list[str], error_match: str
    ) -> None:
        out = tmp_path / "DSP_ConfigMem.csv"
        _write_configmem_csv(out, masks, ranges)
        with pytest.raises(ValueError, match=error_match):
            self._build(tmp_path, out, bits=2)
