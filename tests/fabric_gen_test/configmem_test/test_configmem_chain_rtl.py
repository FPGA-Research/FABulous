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
from fabulous.fabric_definition.define import ConfigBitMode
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_configmem import (
    generate_config_mem,
)

# Use parseConfigMem function to get accurate bit mapping
from fabulous.fabric_generator.parser.parse_configmem import parseConfigMem

class ConfigMemChainDUT(Protocol):
    """Protocol for configuration memory DUT.

    Defines the interface for configuration memory testing for type annotation
    """

    CONFin: Any
    CONFout: Any
    CONF_CLK: Any
    ConfigBits: Any
    ConfigBits_N: Any

def load_chain_mapping() -> list[int]:
    """Load the flip-flop chain ordering from JSON: chain_position -> config_bit.

    cocotb's cwd is the build dir, but the pytest wrapper writes
    config_info.json to tmp_path. The test module is copied to
    <tmp_path>/tests/, so anchor on __file__ instead of cwd.
    """
    here = Path(__file__).resolve().parent
    candidates = (
        here.parent / "config_info.json",   # <tmp_path>/config_info.json
        here        / "config_info.json",   # <tmp_path>/tests/config_info.json
        Path.cwd()  / "config_info.json",   # <tmp_path>/cocotb_build/config_info.json
    )
    for candidate in candidates:
        if candidate.exists():
            with candidate.open() as f:
                return json.load(f)["mapped_indices"]
    return []

async def clock_chain(dut: ConfigMemChainDUT) -> None:
    """One rising-edge pulse on CONF_CLK"""
    dut.CONF_CLK.value = 1
    await Timer(10, units="ps")
    dut.CONF_CLK.value = 0
    await Timer(10, units="ps")

async def initialize_configmem_chain(dut: ConfigMemChainDUT) -> None:
    """Initialize the flip-flop chain by clocking zeros through all stages."""
    dut.CONFin.value = 0
    dut.CONF_CLK.value = 0
    await Timer(10, units="ps")

    n = len(dut.ConfigBits)
    for _ in range(n + 1):
        await clock_chain(dut)

def _read_bit(handle, index: int) -> int:
    """Read a single bit from a cocotb signal handle.

    Works around two simulator quirks:
      * Icarus exposes a 1-bit signal as a scalar LogicObject that cannot
        be subscripted.
      * GHDL (VHDL) does not enumerate individual std_logic_vector bits as
        sub-handles, so handle[i] raises IndexError even though the vector
        itself has a .value you can index into.
    """
    try:
        return int(handle[index].value)
    except (TypeError, IndexError):
        pass
    try:
        return int(handle.value[index])
    except (TypeError, IndexError):
        # Scalar 1-bit signal: ignore the index
        return int(handle.value)


@cocotb.test
async def cocotb_test_configmem_chain(dut: ConfigMemChainDUT) -> None:
    """Validate the flip-flop chain: ordering, edge sensitivity, and data integrity."""

    mapped_indices = load_chain_mapping()
    n = len(dut.ConfigBits)

    assert mapped_indices, (
        "config_info.json missing or empty — pytest wrapper did not write it"
    )
    assert len(mapped_indices) == n, (
        f"Chain length mismatch: mapping has {len(mapped_indices)} entries, "
        f"but ConfigBits width is {n}"
    )

    # --- 0. Init: flush all FFs to 0, assert clean state ---
    await initialize_configmem_chain(dut)
    for i in range(n):
        assert _read_bit(dut.ConfigBits, i) == 0, f"ConfigBits[{i}] not 0 after init"
        assert _read_bit(dut.ConfigBits_N, i) == 1, f"ConfigBits_N[{i}] not 1 after init"
    assert dut.CONFout.value == 0

    # --- 1. Edge sensitivity: no shift without a posedge ---
    dut.CONFin.value = 1
    await Timer(10, units="ps")
    assert _read_bit(dut.ConfigBits, mapped_indices[0]) == 0, (
        "CONFin=1 without a clock edge should not shift the chain"
    )
    await clock_chain(dut)
    assert _read_bit(dut.ConfigBits, mapped_indices[0]) == 1, (
        "First rising edge should load CONFin=1 into chain position 0"
    )
    assert _read_bit(dut.ConfigBits_N, mapped_indices[0]) == 0

    # --- 2. Single-1 walk: confirms chain ordering ---
    await initialize_configmem_chain(dut)
    dut.CONFin.value = 1
    await clock_chain(dut)
    dut.CONFin.value = 0

    for pos in range(n):
        for i in range(n):
            expected = 1 if i == mapped_indices[pos] else 0
            assert _read_bit(dut.ConfigBits, i) == expected, (
                f"single-1 walk, chain position {pos}: "
                f"ConfigBits[{i}] expected {expected}, got {_read_bit(dut.ConfigBits, i)}"
            )
        if pos == n - 1:
            assert dut.CONFout.value == 1, (
                "CONFout should be 1 when the 1 has reached the last chain stage"
            )
        else:
            assert dut.CONFout.value == 0
            await clock_chain(dut)

    # --- 3. 1010101 feed: data integrity + complement ---
    await initialize_configmem_chain(dut)
    pattern = [i % 2 for i in range(n)]
    for bit in pattern:
        dut.CONFin.value = bit
        await clock_chain(dut)
    dut.CONFin.value = 0

    for chain_pos, cfg_idx in enumerate(mapped_indices):
        expected = pattern[n - 1 - chain_pos]
        assert _read_bit(dut.ConfigBits, cfg_idx) == expected, (
            f"1010101 feed, chain position {chain_pos} -> ConfigBits[{cfg_idx}]: "
            f"expected {expected}, got {_read_bit(dut.ConfigBits, cfg_idx)}"
        )
        assert _read_bit(dut.ConfigBits_N, cfg_idx) == 1 - expected, (
            f"1010101 feed, ConfigBits_N[{cfg_idx}] expected {1 - expected}"
        )
    assert dut.CONFout.value == pattern[0], (
        f"CONFout expected {pattern[0]} (first bit shifted in, now at chain end)"
    )

def _flatten_mapped_indices(config_mem_entries: list[ConfigMem]) -> list[int]:
    """Flatten configBitRanges across CSV entries, mirroring the generator."""
    mapped_indices: list[int] = []
    for entry in config_mem_entries:
        mapped_indices.extend(entry.configBitRanges)
    return mapped_indices

@pytest.mark.parametrize("hdl_lang", [".v", ".vhd"])
def test_configmem_chain_rtl_with_generated_configmem_simulation(
    hdl_lang: str,
    fabric_config: Fabric,
    tile_config: Tile,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    cocotb_runner: Callable[..., Callable],
) -> None:
    """Generate ConfigMem RTL and verify its chain behavior using cocotb."""

    if fabric_config.configBitMode != ConfigBitMode.FLIPFLOP_CHAIN:
        pytest.skip("FLIPFLOP_CHAIN only; frame-based covered by test_configmem_rtl.py")

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
    generate_config_mem(
        writer,
        tile_config.name,
        tile_config.globalConfigBits,
        csv_path,
        frame_bits_per_row=fabric_config.frameBitsPerRow,
        max_frame_per_col=fabric_config.maxFramesPerCol,
        config_bit_mode=fabric_config.configBitMode,
    )

    # No config bits -> no RTL, no CSV, nothing to simulate
    if tile_config.globalConfigBits == 0:
        return

    assert writer.outFileName.exists(), (
        f"ConfigMem RTL file {writer.outFileName} was not generated."
    )

    # Parse the CSV (now guaranteed to exist, default-generated if absent)
    config_mem_entries = parseConfigMem(
        csv_path,
        fabric_config.maxFramesPerCol,
        fabric_config.frameBitsPerRow,
        tile_config.globalConfigBits,
    )

    mapped_indices = _flatten_mapped_indices(config_mem_entries)

    # Save mapping for the cocotb test to use
    config_info_file = tmp_path / "config_info.json"
    with config_info_file.open("w") as f:
        json.dump({"mapped_indices": mapped_indices}, f, indent=2)

    models_source = Path(__file__).parent.parent / "testdata" / f"models{hdl_lang}"
    cocotb_runner(
        sources=[models_source, writer.outFileName],
        hdl_top_level=f"{tile_config.name}_ConfigMem",
        test_module_path=Path(__file__),
    )


@pytest.mark.parametrize("hdl_lang", [".v", ".vhd"])
def test_configmem_chain_rtl_with_custom_configmem_simulation(
    hdl_lang: str,
    tmp_path: Path,
    default_fabric: Fabric,
    default_tile: Tile,
    configmem_list: Callable[[Fabric, Tile], list[ConfigMem]],
    code_generator_factory: Callable[..., CodeGenerator],
    cocotb_runner: Callable[..., Callable],
    mocker: MockerFixture,
) -> None:
    """Verify chain ordering for a hand-crafted (non-default) ConfigMem."""

    if default_fabric.configBitMode != ConfigBitMode.FLIPFLOP_CHAIN:
        pytest.skip("FLIPFLOP_CHAIN only; frame-based covered by test_configmem_rtl.py")

    # Create code generator using the factory fixture, but with tmp_path output
    writer = code_generator_factory(
        hdl_lang,
        f"{default_tile.name}_ConfigMem",
    )
    writer.outFileName = tmp_path / f"{default_tile.name}_ConfigMem{hdl_lang}"
    writer.outFileName.touch()

    # Create CSV file in tmp_path
    csv_path = tmp_path / f"{default_tile.name}_configMem.csv"
    configmem_list_data = configmem_list(default_fabric, default_tile)

    # Mock parseConfigMem so the generator uses our custom ordering instead of
    # whatever is on disk. This lets us exercise non-default chain orderings.
    mock_parse = mocker.patch(
        "fabulous.fabric_generator.gen_fabric.gen_configmem.parseConfigMem",
        return_value=configmem_list,
    )
    mock_parse.return_value = configmem_list_data

    # Generate the ConfigMem RTL
    generate_config_mem(
        writer,
        default_tile.name,
        default_tile.globalConfigBits,
        csv_path,
        frame_bits_per_row=default_fabric.frameBitsPerRow,
        max_frame_per_col=default_fabric.maxFramesPerCol,
        config_bit_mode=default_fabric.configBitMode,
    )

    mapped_indices = _flatten_mapped_indices(configmem_list_data)

    # Save mapping for the cocotb test to use
    config_info_file = tmp_path / "config_info.json"
    with config_info_file.open("w") as f:
        json.dump({"mapped_indices": mapped_indices}, f, indent=2)

    # Set up cocotb simulation and run using the factory fixture
    models_source = Path(__file__).parent.parent / "testdata" / f"models{hdl_lang}"
    cocotb_runner(
        sources=[models_source, writer.outFileName],
        hdl_top_level=f"{default_tile.name}_ConfigMem",
        test_module_path=Path(__file__),
    )
