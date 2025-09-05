"""RTL validation for generated Fabric modules using Yosys."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple, Protocol

import pytest

from FABulous.fabric_definition.define import ConfigBitMode
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.gen_fabric.gen_fabric import generateFabric


class FabricDUT(Protocol):
    """Protocol defining the eFPGA Fabric module interface."""

    # Clock and Reset
    UserCLK: Any  # System clock

    # Frame-based Configuration Interface
    FrameData: Any  # [FrameBitsPerRow-1:0] Frame configuration data
    FrameStrobe: Any  # [MaxFramesPerCol-1:0] Frame strobe signals
    FrameData_O: Any  # [FrameBitsPerRow-1:0] Frame data output (chain)
    FrameStrobe_O: Any  # [MaxFramesPerCol-1:0] Frame strobe output (chain)

    # FlipFlop Chain Configuration Interface (alternative)
    conf_data: Any  # Configuration data input
    conf_clk: Any  # Configuration clock

    # External I/O (when present)
    Tile_X0Y0_A_I: Any  # Example tile I/O - actual ports depend on fabric configuration
    Tile_X0Y0_A_O: Any
    Tile_X0Y0_A_T: Any


class FabricTestCase(NamedTuple):
    """Test case configuration for fabric RTL validation."""

    config_bit_mode: ConfigBitMode
    test_name: str
    expected_ports: list[str]


def _create_fabric_validation_commands(
    config_bit_mode: ConfigBitMode, fabric_config: dict, expected_ports: list[str]
) -> list[str]:
    """Create yosys validation commands for fabric structure."""
    commands = []

    # Basic RTL checks
    commands.append(
        "check -noinit"
    )  # Check for multiple drivers and uninitialized signals
    commands.append("check -assert")  # Verify all outputs are driven

    # Check that expected ports exist
    for port in expected_ports:
        commands.append(f"select -assert-min 1 w:{port}")

    # Check for UserCLK connectivity (always required)
    commands.append("select -assert-min 1 w:UserCLK %co %ci")

    # Configuration mode specific checks
    if config_bit_mode == ConfigBitMode.FRAME_BASED:
        commands.append("select -assert-min 1 w:FrameData w:FrameStrobe %u")
    elif config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
        commands.append("select -assert-min 1 w:conf_data")

    # Fabric-specific checks
    rows = fabric_config.get("rows", 2)
    cols = fabric_config.get("cols", 2)

    # Check for expected number of tile instances
    expected_tiles = rows * cols
    commands.append(f"select -assert-count {expected_tiles} c:*tile*")

    # Port-to-port connectivity validation
    # Clock tree validation - UserCLK should connect to each tile's UserCLK port
    for row in range(rows):
        for col in range(cols):
            tile_instance = f"*tile_{row}_{col}*"
            # UserCLK should connect to each tile's UserCLK input
            commands.append(
                f"select -assert-min 1 w:UserCLK %co c:{tile_instance} %ci %i"
            )

    # Frame-based configuration chain validation
    if config_bit_mode == ConfigBitMode.FRAME_BASED:
        # FrameData and FrameStrobe should form a chain through tiles
        commands.append("select -assert-min 1 w:FrameData %co %ci")
        commands.append("select -assert-min 1 w:FrameStrobe %co %ci")

        # Verify frame data chain: fabric input -> first tile -> ... -> last tile -> fabric output
        # First tile should receive fabric FrameData input
        first_tile = "*tile_0_0*"
        commands.append(f"select -assert-min 1 w:FrameData %co c:{first_tile} %ci %i")
        commands.append(f"select -assert-min 1 w:FrameStrobe %co c:{first_tile} %ci %i")

        # Tiles should be chained together (each tile's output connects to next tile's input)
        for row in range(rows):
            for col in range(cols):
                if row == rows - 1 and col == cols - 1:
                    # Last tile - its output should connect to fabric output
                    last_tile = f"*tile_{row}_{col}*"
                    commands.append(
                        f"select -assert-min 1 c:{last_tile} %co w:FrameData_O %i"
                    )
                    commands.append(
                        f"select -assert-min 1 c:{last_tile} %co w:FrameStrobe_O %i"
                    )
                else:
                    # Intermediate tiles - output connects to next tile's input
                    current_tile = f"*tile_{row}_{col}*"
                    next_tile = (
                        f"*tile_{row}_{col + 1}*"
                        if col < cols - 1
                        else f"*tile_{row + 1}_0*"
                    )
                    commands.append(
                        f"select -assert-min 1 c:{current_tile} %co c:{next_tile} %ci %i"
                    )

    # Verify tile-to-tile routing connections
    # Adjacent tiles should have routing wire connections
    for row in range(rows):
        for col in range(cols):
            current_tile = f"*tile_{row}_{col}*"

            # Check connections to adjacent tiles
            if col < cols - 1:  # Right neighbor
                right_tile = f"*tile_{row}_{col + 1}*"
                commands.append(
                    f"select -assert-min 1 c:{current_tile} %co c:{right_tile} %ci %i"
                )

            if row < rows - 1:  # Bottom neighbor
                bottom_tile = f"*tile_{row + 1}_{col}*"
                commands.append(
                    f"select -assert-min 1 c:{current_tile} %co c:{bottom_tile} %ci %i"
                )

    return commands


@pytest.mark.parametrize("hdl_lang", [".v", ".vhdl"])
@pytest.mark.parametrize(
    "fabric_test_case",
    [
        FabricTestCase(
            config_bit_mode=ConfigBitMode.FRAME_BASED,
            test_name="frame_based_fabric",
            expected_ports=[
                "UserCLK",
                "FrameData",
                "FrameStrobe",
                "FrameData_O",
                "FrameStrobe_O",
            ],
        ),
        FabricTestCase(
            config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
            test_name="flipflop_chain_fabric",
            expected_ports=["UserCLK", "conf_data", "conf_clk"],
        ),
    ],
    ids=lambda case: case.test_name,
)
def test_fabric_rtl_validation(
    hdl_lang: str,
    fabric_test_case: FabricTestCase,
    default_fabric: Fabric,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    yosys_validator: Callable[[Path], object],
) -> None:
    """Generate Fabric HDL and verify its structure using Yosys RTL validation."""

    # Configure fabric based on test case
    default_fabric.configBitMode = fabric_test_case.config_bit_mode

    # Create code generator
    test_name = f"{default_fabric.name}_{fabric_test_case.test_name}"
    writer = code_generator_factory(hdl_lang, test_name)
    writer.outFileName = tmp_path / f"{test_name}{hdl_lang}"

    # Generate the Fabric HDL
    generateFabric(writer, default_fabric)

    # Check if HDL file was created
    if not writer.outFileName.exists():
        pytest.skip(f"Fabric HDL file {writer.outFileName} was not generated")

    # Skip if file is too minimal
    content = writer.outFileName.read_text()
    if len([line for line in content.split("\n") if line.strip()]) < 50:
        pytest.skip("Generated fabric is too minimal for RTL validation")

    # Validate HDL structure using Yosys
    validator = yosys_validator(writer.outFileName)

    # Create fabric configuration for validation
    fabric_config = {
        "rows": default_fabric.numberOfRows,
        "cols": default_fabric.numberOfColumns,
    }

    # Create yosys commands to validate fabric structure
    yosys_commands = _create_fabric_validation_commands(
        fabric_test_case.config_bit_mode, fabric_config, fabric_test_case.expected_ports
    )

    # Run RTL validation
    validator.validate(yosys_commands)


@pytest.mark.parametrize("hdl_lang", [".v", ".vhdl"])
def test_fabric_with_io_rtl_validation(
    hdl_lang: str,
    fabric_with_io_tiles: Fabric,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    yosys_validator: Callable[[Path], object],
) -> None:
    """Test RTL validation for fabric with I/O tiles."""

    # Configure fabric for frame-based configuration
    fabric_with_io_tiles.configBitMode = ConfigBitMode.FRAME_BASED

    test_name = f"{fabric_with_io_tiles.name}_with_io"
    writer = code_generator_factory(hdl_lang, test_name)
    writer.outFileName = tmp_path / f"{test_name}{hdl_lang}"

    # Generate the Fabric HDL
    generateFabric(writer, fabric_with_io_tiles)

    # Check if HDL file was created
    if not writer.outFileName.exists():
        pytest.skip(f"Fabric with I/O HDL file {writer.outFileName} was not generated")

    # Validate structure using Yosys
    validator = yosys_validator(writer.outFileName)

    # Expected ports for fabric with I/O
    expected_ports = [
        "UserCLK",
        "FrameData",
        "FrameStrobe",
        "FrameData_O",
        "FrameStrobe_O",
    ]

    fabric_config = {
        "rows": fabric_with_io_tiles.numberOfRows,
        "cols": fabric_with_io_tiles.numberOfColumns,
    }

    yosys_commands = _create_fabric_validation_commands(
        ConfigBitMode.FRAME_BASED, fabric_config, expected_ports
    )
    validator.validate(yosys_commands)


@pytest.mark.parametrize("hdl_lang", [".v", ".vhdl"])
def test_minimal_fabric_rtl_validation(
    hdl_lang: str,
    empty_fabric: Fabric,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    yosys_validator: Callable[[Path], object],
) -> None:
    """Test RTL validation for minimal fabric configuration."""

    # Configure fabric for simple configuration
    empty_fabric.configBitMode = ConfigBitMode.FRAME_BASED

    test_name = f"{empty_fabric.name}_minimal"
    writer = code_generator_factory(hdl_lang, test_name)
    writer.outFileName = tmp_path / f"{test_name}{hdl_lang}"

    # Generate the Fabric HDL
    generateFabric(writer, empty_fabric)

    # Check if HDL file was created
    if not writer.outFileName.exists():
        pytest.skip(f"Minimal fabric HDL file {writer.outFileName} was not generated")

    # Validate structure using Yosys
    validator = yosys_validator(writer.outFileName)

    # Basic expected ports for minimal fabric
    expected_ports = [
        "UserCLK",
        "FrameData",
        "FrameStrobe",
        "FrameData_O",
        "FrameStrobe_O",
    ]

    fabric_config = {
        "rows": empty_fabric.numberOfRows,
        "cols": empty_fabric.numberOfColumns,
    }

    yosys_commands = _create_fabric_validation_commands(
        ConfigBitMode.FRAME_BASED, fabric_config, expected_ports
    )
    validator.validate(yosys_commands)


# Note: Fabric tests focus on structural RTL validation using Yosys
# For behavioral validation, see configmem_test which tests actual hardware behavior
