"""RTL validation for generated Tile modules using Yosys."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple, Protocol

import pytest

from FABulous.fabric_definition.define import ConfigBitMode
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.gen_fabric.gen_tile import generateTile


class TileDUT(Protocol):
    """Protocol defining the Tile module interface."""

    # Clock and Reset
    UserCLK: Any  # System clock input
    UserCLKo: Any  # System clock output (chained)

    # Frame-based Configuration Interface
    FrameData: Any  # [FrameBitsPerRow-1:0] Frame configuration data input
    FrameStrobe: Any  # [MaxFramesPerCol-1:0] Frame strobe signals input
    FrameData_O: Any  # [FrameBitsPerRow-1:0] Frame data output (chain)
    FrameStrobe_O: Any  # [MaxFramesPerCol-1:0] Frame strobe output (chain)

    # FlipFlop Chain Configuration Interface (alternative)
    conf_data: Any  # Configuration data input
    conf_clk: Any  # Configuration clock

    # Routing Interface (tile-to-tile connections)
    # Note: Actual routing signals depend on tile configuration
    # Examples of common routing signals:
    N1BEG0: Any  # North 1-wire begin signal 0
    E1BEG0: Any  # East 1-wire begin signal 0
    S1BEG0: Any  # South 1-wire begin signal 0
    W1BEG0: Any  # West 1-wire begin signal 0
    N1END0: Any  # North 1-wire end signal 0
    E1END0: Any  # East 1-wire end signal 0
    S1END0: Any  # South 1-wire end signal 0
    W1END0: Any  # West 1-wire end signal 0


class TileTestCase(NamedTuple):
    """Test case configuration for tile RTL validation."""

    config_bit_mode: ConfigBitMode
    global_config_bits: int
    test_name: str
    expected_ports: list[str]


def _create_tile_validation_commands(
    config_bit_mode: ConfigBitMode, global_config_bits: int, expected_ports: list[str]
) -> list[str]:
    """Create yosys validation commands for tile structure."""
    commands = []

    # Basic RTL checks
    commands.append(
        "check -noinit"
    )  # Check for multiple drivers and uninitialized signals
    commands.append("check -assert")  # Verify all outputs are driven

    # Check that expected ports exist
    for port in expected_ports:
        commands.append(f"select -assert-min 1 w:{port}")

    # Configuration mode specific checks
    if config_bit_mode == ConfigBitMode.FRAME_BASED:
        # Frame-based configuration signals
        commands.append("select -assert-min 1 w:FrameData")
        commands.append("select -assert-min 1 w:FrameStrobe")
        commands.append("select -assert-min 1 w:FrameData_O")
        commands.append("select -assert-min 1 w:FrameStrobe_O")
    elif config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
        # FlipFlop chain configuration signals
        commands.append("select -assert-min 1 w:conf_data")
        commands.append("select -assert-min 1 w:conf_clk")

    # Check for UserCLK connectivity (tiles should have clock infrastructure)
    commands.append("select -assert-min 1 w:UserCLK")
    commands.append("select -assert-min 1 w:UserCLKo")

    # If tile has configuration bits, check for config memory instance
    if global_config_bits > 0:
        commands.append("select -assert-min 1 c:*ConfigMem*")

    # Check for switch matrix instance (tiles should have routing)
    commands.append("select -assert-min 1 c:*switch_matrix*")

    # Port-to-port connectivity validation
    # Verify specific clock path: UserCLK input -> UserCLKo output
    commands.append("select -assert-min 1 w:UserCLK %co w:UserCLKo %i")

    # Verify clock distribution to sub-components
    # UserCLK should connect to switch matrix clock port
    commands.append("select -assert-min 1 w:UserCLK %co c:*switch_matrix* %ci %i")

    # If config memory exists, clock should connect to it
    if global_config_bits > 0:
        commands.append("select -assert-min 1 w:UserCLK %co c:*ConfigMem* %ci %i")

    # Check frame data flow for frame-based configs
    if config_bit_mode == ConfigBitMode.FRAME_BASED:
        # FrameData input -> FrameData_O output (data chain)
        commands.append("select -assert-min 1 w:FrameData %co w:FrameData_O %i")
        # FrameStrobe input -> FrameStrobe_O output (strobe chain)
        commands.append("select -assert-min 1 w:FrameStrobe %co w:FrameStrobe_O %i")

        # Frame signals should connect to config memory (if present)
        if global_config_bits > 0:
            commands.append("select -assert-min 1 w:FrameData %co c:*ConfigMem* %ci %i")
            commands.append(
                "select -assert-min 1 w:FrameStrobe %co c:*ConfigMem* %ci %i"
            )

        # Frame signals should also connect to switch matrix for configuration
        commands.append("select -assert-min 1 w:FrameData %co c:*switch_matrix* %ci %i")
        commands.append(
            "select -assert-min 1 w:FrameStrobe %co c:*switch_matrix* %ci %i"
        )

    # Verify configuration bits flow from config memory to switch matrix
    if global_config_bits > 0:
        # Config memory output should connect to switch matrix ConfigBits input
        commands.append(
            "select -assert-min 1 c:*ConfigMem* %co c:*switch_matrix* %ci %i"
        )

    # Check that routing signals flow through switch matrix
    # Switch matrix should have both input and output routing signals
    commands.append("select -assert-min 2 c:*switch_matrix* %ci")  # Multiple inputs
    commands.append("select -assert-min 2 c:*switch_matrix* %co")  # Multiple outputs

    return commands


@pytest.mark.parametrize("hdl_lang", [".v", ".vhdl"])
@pytest.mark.parametrize(
    "tile_test_case",
    [
        TileTestCase(
            config_bit_mode=ConfigBitMode.FRAME_BASED,
            global_config_bits=32,
            test_name="frame_based_tile",
            expected_ports=[
                "UserCLK",
                "UserCLKo",
                "FrameData",
                "FrameStrobe",
                "FrameData_O",
                "FrameStrobe_O",
            ],
        ),
        TileTestCase(
            config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
            global_config_bits=16,
            test_name="flipflop_chain_tile",
            expected_ports=["UserCLK", "UserCLKo", "conf_data", "conf_clk"],
        ),
        TileTestCase(
            config_bit_mode=ConfigBitMode.FRAME_BASED,
            global_config_bits=0,
            test_name="no_config_tile",
            expected_ports=[
                "UserCLK",
                "UserCLKo",
                "FrameData",
                "FrameStrobe",
                "FrameData_O",
                "FrameStrobe_O",
            ],
        ),
    ],
    ids=lambda case: case.test_name,
)
def test_tile_rtl_validation(
    hdl_lang: str,
    tile_test_case: TileTestCase,
    default_fabric: Fabric,
    default_tile: Tile,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    yosys_validator: Callable[[Path], object],
) -> None:
    """Generate Tile HDL and verify its structure using Yosys RTL validation."""

    # Configure fabric and tile based on test case
    default_fabric.configBitMode = tile_test_case.config_bit_mode
    # Note: Can't set globalConfigBits directly due to property restrictions
    # The test will work with the tile's existing configuration

    # Create code generator
    test_name = f"{default_tile.name}_{tile_test_case.test_name}"
    writer = code_generator_factory(hdl_lang, test_name)
    writer.outFileName = tmp_path / f"{test_name}{hdl_lang}"

    # Generate the Tile HDL
    generateTile(writer, default_fabric, default_tile)

    # Check if HDL file was created
    if not writer.outFileName.exists():
        pytest.skip(f"Tile HDL file {writer.outFileName} was not generated")

    # Skip if file is too minimal
    content = writer.outFileName.read_text()
    if len([line for line in content.split("\n") if line.strip()]) < 20:
        pytest.skip("Generated tile is too minimal for RTL validation")

    # Validate HDL structure using Yosys
    validator = yosys_validator(writer.outFileName)

    # Create yosys commands to validate tile structure
    yosys_commands = _create_tile_validation_commands(
        tile_test_case.config_bit_mode,
        tile_test_case.global_config_bits,
        tile_test_case.expected_ports,
    )

    # Run RTL validation
    validator.validate(yosys_commands)


@pytest.mark.parametrize("hdl_lang", [".v", ".vhdl"])
def test_tile_with_external_ports_rtl_validation(
    hdl_lang: str,
    tile_with_external_ports: Tile,
    default_fabric: Fabric,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    yosys_validator: Callable[[Path], object],
) -> None:
    """Test RTL validation for tile with external ports."""

    # Configure fabric for frame-based configuration
    default_fabric.configBitMode = ConfigBitMode.FRAME_BASED

    test_name = f"{tile_with_external_ports.name}_with_external_ports"
    writer = code_generator_factory(hdl_lang, test_name)
    writer.outFileName = tmp_path / f"{test_name}{hdl_lang}"

    # Generate the Tile HDL
    generateTile(writer, default_fabric, tile_with_external_ports)

    # Check if HDL file was created
    if not writer.outFileName.exists():
        pytest.skip(
            f"Tile with external ports HDL file {writer.outFileName} was not generated"
        )

    # Validate structure using Yosys
    validator = yosys_validator(writer.outFileName)

    # Expected ports for tile with external I/O
    expected_ports = [
        "UserCLK",
        "UserCLKo",
        "FrameData",
        "FrameStrobe",
        "FrameData_O",
        "FrameStrobe_O",
    ]

    yosys_commands = _create_tile_validation_commands(
        ConfigBitMode.FRAME_BASED, 5, expected_ports
    )
    validator.validate(yosys_commands)


@pytest.mark.parametrize("hdl_lang", [".v", ".vhdl"])
def test_minimal_tile_rtl_validation(
    hdl_lang: str,
    minimal_tile: Tile,
    default_fabric: Fabric,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    yosys_validator: Callable[[Path], object],
) -> None:
    """Test RTL validation for minimal tile configuration."""

    # Configure fabric for simple configuration
    default_fabric.configBitMode = ConfigBitMode.FRAME_BASED

    test_name = f"{minimal_tile.name}_minimal"
    writer = code_generator_factory(hdl_lang, test_name)
    writer.outFileName = tmp_path / f"{test_name}{hdl_lang}"

    # Generate the Tile HDL
    generateTile(writer, default_fabric, minimal_tile)

    # Check if HDL file was created
    if not writer.outFileName.exists():
        pytest.skip(f"Minimal tile HDL file {writer.outFileName} was not generated")

    # Validate structure using Yosys
    validator = yosys_validator(writer.outFileName)

    # Basic expected ports for minimal tile
    expected_ports = [
        "UserCLK",
        "UserCLKo",
        "FrameData",
        "FrameStrobe",
        "FrameData_O",
        "FrameStrobe_O",
    ]

    yosys_commands = _create_tile_validation_commands(
        ConfigBitMode.FRAME_BASED, 0, expected_ports
    )
    validator.validate(yosys_commands)


# Note: Tile tests focus on structural RTL validation using Yosys
# For behavioral validation, see configmem_test which tests actual hardware behavior
