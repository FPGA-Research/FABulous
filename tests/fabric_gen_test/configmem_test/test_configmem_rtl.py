"""RTL behavior validation for generated ConfigMem modules using cocotb."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

# Cocotb test module - these functions are called by cocotb during simulation
import cocotb
import pytest
from cocotb.triggers import Timer
from pytest_mock import MockerFixture

from fabulous.fabric_definition.configmem import ConfigMem
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_configmem import generateConfigMem

# Use parseConfigMem function to get accurate bit mapping
from fabulous.fabric_generator.parser.parse_configmem import parseConfigMem


class ConfigMemDUT(Protocol):
    """Protocol for configuration memory DUT.

    Defines the interface for configuration memory testing for type annotation
    """

    FrameData: Any
    FrameStrobe: Any
    ConfigBits: Any
    ConfigBits_N: Any


def write_bit_mapping(
    config_mems: list[ConfigMem], frame_bits_per_row: int, path: Path
) -> None:
    """Write the `"frame, framedata_bit"` -> config bit mapping to `path` as JSON.

    The simulator runs the cocotb test in its own process and working directory,
    so the mapping reaches it as a file whose path travels in a plusarg.
    """
    bit_mapping: dict[str, int] = {}
    for config_mem in config_mems:
        # Same reading as the bitstream spec: mask character k, left to right,
        # is FrameData bit `frame_bits_per_row - 1 - k` and takes the next
        # entry of configBitRanges.
        config_bits = iter(config_mem.configBitRanges)
        for k, bit in enumerate(config_mem.usedBitMask):
            if bit == "1":
                framedata_bit_idx = frame_bits_per_row - 1 - k
                bit_mapping[f"{config_mem.frameIndex}, {framedata_bit_idx}"] = next(
                    config_bits
                )
    path.write_text(json.dumps(bit_mapping, indent=2))


async def initialize_configmem(dut: ConfigMemDUT) -> None:
    """Initialize ConfigMem by setting all bits to 0 using frame strobing."""
    # Set FrameData to 0
    dut.FrameData.value = 0

    # Strobe all available frames to initialize ConfigBits to 0
    max_frames = len(dut.FrameStrobe)
    for frame_idx in range(max_frames):
        frame_strobe_val = 1 << frame_idx
        dut.FrameStrobe.value = frame_strobe_val
        await Timer(10, units="ps")

    # Deassert all strobes
    dut.FrameStrobe.value = 0
    await Timer(10, units="ps")


@cocotb.test
async def cocotb_test_configmem_settings(dut: ConfigMemDUT) -> None:
    """Test exact bit mapping from FrameData to ConfigBits using direct mapping."""
    await initialize_configmem(dut)

    bit_mapping: dict[str, int] = json.loads(
        Path(cocotb.plusargs["CONFIG_INFO"]).read_text()
    )
    # An empty mapping would skip every check below and pass vacuously.
    assert bit_mapping, "CONFIG_INFO holds no mapped config bits"

    max_frames = len(dut.FrameStrobe)
    all_config_bits = (1 << len(dut.ConfigBits)) - 1

    valid_framedata_bits = sorted({int(key.split(", ")[1]) for key in bit_mapping})

    # Whole-vector writes and reads, because Icarus exposes a one-bit port as a
    # scalar that cannot be indexed.
    for frame_idx in range(max_frames):
        for framedata_bit_idx in valid_framedata_bits:
            await initialize_configmem(dut)
            where = f"Frame {frame_idx}, FrameData bit {framedata_bit_idx}"

            dut.FrameData.value = 1 << framedata_bit_idx
            dut.FrameStrobe.value = 1 << frame_idx
            await Timer(10, units="ps")

            mapping_key = f"{frame_idx}, {framedata_bit_idx}"
            if mapping_key not in bit_mapping:
                assert int(dut.ConfigBits.value) == 0, (
                    f"{where}: no mapping, so no ConfigBits should be set"
                )
                continue

            expected = 1 << bit_mapping[mapping_key]
            assert int(dut.ConfigBits.value) == expected, (
                f"{where}: expected ConfigBits=0x{expected:x}, "
                f"got 0x{int(dut.ConfigBits.value):x}"
            )
            assert int(dut.ConfigBits_N.value) == all_config_bits ^ expected, (
                f"{where}: ConfigBits_N is not the complement of ConfigBits"
            )

            # The latch holds its value once the strobe drops.
            dut.FrameStrobe.value = 0
            await Timer(10, units="ps")
            assert int(dut.ConfigBits.value) == expected, (
                f"{where}: ConfigBits did not hold after the strobe dropped"
            )


@pytest.mark.parametrize("hdl_lang", [".v", ".vhd"])
def test_configmem_rtl_with_generated_configmem_simulation(
    hdl_lang: str,
    fabric_config: Fabric,
    tile_config: Tile,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    cocotb_runner: Callable[..., Callable],
) -> None:
    """Generate ConfigMem RTL and verify its behavior using cocotb simulation."""
    # Skip impossible configurations where fabric capacity < tile requirements
    fabric_capacity = fabric_config.frameBitsPerRow * fabric_config.maxFramesPerCol
    tile_requirements = tile_config.globalConfigBits
    if fabric_capacity < tile_requirements and tile_requirements > 0:
        pytest.skip(
            f"Impossible configuration: fabric capacity ({fabric_capacity}) < "
            f"tile requirements ({tile_requirements})"
        )

    # Create code generator using the factory fixture, but with tmp_path output
    writer = code_generator_factory(hdl_lang, f"{tile_config.name}_ConfigMem")
    # Override the output path to use tmp_path
    writer.outFileName = tmp_path / f"{tile_config.name}_ConfigMem{hdl_lang}"

    # Create CSV file in tmp_path
    csv_path = tmp_path / f"{tile_config.name}_configMem.csv"

    # Generate the ConfigMem RTL
    generateConfigMem(
        writer,
        tile_config.name,
        tile_config.globalConfigBits,
        csv_path,
        frame_bits_per_row=fabric_config.frameBitsPerRow,
        max_frame_per_col=fabric_config.maxFramesPerCol,
    )

    # Check if RTL file was created - skip if no config bits were generated
    if tile_config.globalConfigBits != 0:
        assert writer.outFileName.exists(), (
            f"ConfigMem RTL file {writer.outFileName} was not generated."
        )
    else:
        return

    config_info = tmp_path / "config_info.json"
    write_bit_mapping(
        parseConfigMem(
            csv_path,
            fabric_config.maxFramesPerCol,
            fabric_config.frameBitsPerRow,
            tile_config.globalConfigBits,
        ),
        fabric_config.frameBitsPerRow,
        config_info,
    )

    models_source = Path(__file__).parent.parent / "testdata" / f"models{hdl_lang}"
    cocotb_runner(
        sources=[models_source, writer.outFileName],
        hdl_top_level=f"{tile_config.name}_ConfigMem",
        test_module_path=Path(__file__),
        plusargs=[f"+CONFIG_INFO={config_info}"],
    )


@pytest.mark.parametrize("hdl_lang", [".v", ".vhd"])
def test_configmem_rtl_with_custom_configmem_simulation(
    hdl_lang: str,
    tmp_path: Path,
    default_fabric: Fabric,
    default_tile: Tile,
    configmem_list: Callable[[Fabric, Tile], list[ConfigMem]],
    code_generator_factory: Callable[..., CodeGenerator],
    cocotb_runner: Callable[..., Callable],
    mocker: MockerFixture,
) -> None:
    """Generate ConfigMem RTL and verify its behavior using cocotb simulation."""
    # Skip impossible configurations where fabric capacity < tile requirements
    fabric_capacity = default_fabric.frameBitsPerRow * default_fabric.maxFramesPerCol
    tile_requirements = default_tile.globalConfigBits
    if fabric_capacity < tile_requirements and tile_requirements > 0:
        pytest.skip(
            f"Impossible configuration: fabric capacity ({fabric_capacity}) < "
            f"tile requirements ({tile_requirements})"
        )

    # Create code generator using the factory fixture, but with tmp_path output
    writer = code_generator_factory(
        hdl_lang,
        f"{default_tile.name}_ConfigMem",
    )
    # Override the output path to use tmp_path
    writer.outFileName = tmp_path / f"{default_tile.name}_ConfigMem{hdl_lang}"
    writer.outFileName.touch()

    # Create CSV file in tmp_path
    csv_path = tmp_path / f"{default_tile.name}_configMem.csv"
    configmem_list_data = configmem_list(default_fabric, default_tile)

    mocker.patch(
        "fabulous.fabric_generator.gen_fabric.gen_configmem.parseConfigMem",
        return_value=configmem_list_data,
    )

    # Generate the ConfigMem RTL
    generateConfigMem(
        writer,
        default_tile.name,
        default_tile.globalConfigBits,
        csv_path,
        frame_bits_per_row=default_fabric.frameBitsPerRow,
        max_frame_per_col=default_fabric.maxFramesPerCol,
    )

    config_info = tmp_path / "config_info.json"
    write_bit_mapping(configmem_list_data, default_fabric.frameBitsPerRow, config_info)

    # Set up cocotb simulation and run using the factory fixture
    models_source = Path(__file__).parent.parent / "testdata" / f"models{hdl_lang}"
    cocotb_runner(
        sources=[models_source, writer.outFileName],
        hdl_top_level=f"{default_tile.name}_ConfigMem",
        test_module_path=Path(__file__),
        plusargs=[f"+CONFIG_INFO={config_info}"],
    )
