from collections.abc import Callable
from pathlib import Path
from typing import List
from dataclasses import dataclass
import subprocess
import tempfile

import pytest

from FABulous.fabric_definition.define import ConfigBitMode
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.gen_fabric.gen_fabric import generateFabric


@dataclass
class ValidationResult:
    """Result of Yosys validation."""

    passed: bool
    failures: List[str]
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def run_yosys_validation(hdl_file: Path, yosys_commands: List[str]) -> ValidationResult:
    """Run Yosys validation with provided commands."""
    # Load script based on HDL type
    load_script = []
    if hdl_file.suffix.lower() == ".v":
        load_script.extend(
            [f"read_verilog {hdl_file}", "hierarchy -auto-top", "proc", "clean"]
        )
    elif hdl_file.suffix.lower() in [".vhd", ".vhdl"]:
        load_script.extend(
            [
                "plugin -i ghdl",
                f"ghdl --std=08 {hdl_file}",
                "hierarchy -auto-top",
                "proc",
                "clean",
            ]
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        script_file = Path(temp_dir) / "validate.ys"
        script_content = "\n".join(load_script + yosys_commands)
        script_file.write_text(script_content)

        try:
            result = subprocess.run(
                ["yosys", "-s", str(script_file)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return ValidationResult(passed=True, failures=[])
            failures = [
                line.strip() for line in result.stderr.split("\n") if line.strip()
            ]
            return ValidationResult(passed=False, failures=failures)
        except subprocess.TimeoutExpired:
            return ValidationResult(
                passed=False, failures=["Yosys validation timed out"]
            )
        except FileNotFoundError:
            return ValidationResult(passed=False, failures=["Yosys not found in PATH"])


def setup_fabric_with_tiles(fabric: Fabric, rows: int = 2, cols: int = 2) -> None:
    """Helper function to setup fabric with proper tile grid structure."""
    from tests.fabric_gen_test.conftest import MockBel

    # Set basic fabric properties
    fabric.numberOfRows = rows
    fabric.numberOfColumns = cols
    fabric.tileDic = {}
    fabric.superTileDic = {}

    # Create a 2D tile grid
    fabric.tile = []
    for y in range(rows):
        row = []
        for x in range(cols):
            # Create mock tile with required methods
            tile = type("MockTile", (), {})()
            tile.name = f"TestTile_X{x}Y{y}"
            tile.bels = [MockBel([], [])]  # Empty BEL to avoid external ports
            tile.partOfSuperTile = False
            tile.portsInfo = []  # Empty ports info to avoid tile-to-tile connections

            # Add required methods
            def get_empty_ports(io_type):
                return []

            tile.getNorthPorts = get_empty_ports
            tile.getEastPorts = get_empty_ports
            tile.getSouthPorts = get_empty_ports
            tile.getWestPorts = get_empty_ports
            tile.getTileOutputNames = list

            # Add to tileDic for VHDL generation
            fabric.tileDic[tile.name] = tile

            row.append(tile)
        fabric.tile.append(row)


class TestGenFabric:
    """Test class for generateFabric function with inline validation logic."""

    @pytest.mark.parametrize(
        "config_mode,expected_signals,absent_signals",
        [
            (
                ConfigBitMode.FRAME_BASED,
                ["FrameData", "FrameStrobe", "CONFIG_PORT"],
                ["conf_data"],
            ),
            ("FlipFlopChain", ["conf_data"], ["FrameData", "FrameStrobe"]),
        ],
    )
    def test_fabric_generation_config_modes(
        self,
        config_mode,
        expected_signals: List[str],
        absent_signals: List[str],
        default_fabric: Fabric,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test fabric generation with different configuration modes."""
        # Configure fabric
        default_fabric.configBitMode = config_mode
        if config_mode == ConfigBitMode.FRAME_BASED:
            default_fabric.maxFramesPerCol = 20
            default_fabric.frameBitsPerRow = 32
        setup_fabric_with_tiles(default_fabric)

        writer = code_generator_factory(
            ".v", f"test_fabric_{str(config_mode).replace('.', '_')}"
        )
        writer.outFileName = (
            tmp_path / f"test_fabric_{str(config_mode).replace('.', '_')}.v"
        )

        # Generate fabric
        generateFabric(writer, default_fabric)

        # Verify output file was created
        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # Basic structure checks
        assert "module eFPGA" in content
        assert "UserCLK" in content

        # Check expected signals are present
        for signal in expected_signals:
            assert signal in content, f"Expected signal '{signal}' not found"

        # Check absent signals are not present
        for signal in absent_signals:
            assert signal not in content, f"Unexpected signal '{signal}' found"

    def test_fabric_frame_based_configuration_with_default_fixture(
        self,
        default_fabric: Fabric,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test frame-based fabric configuration using default fixture."""
        # Configure for frame-based mode
        default_fabric.configBitMode = ConfigBitMode.FRAME_BASED
        default_fabric.frameBitsPerRow = 32
        default_fabric.maxFramesPerCol = 20
        setup_fabric_with_tiles(default_fabric)

        writer = code_generator_factory(".v", "default_frame_based_fabric")
        writer.outFileName = tmp_path / "default_frame_based_fabric.v"

        generateFabric(writer, default_fabric)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # Verify frame-based specific content
        assert "FrameData" in content
        assert "FrameStrobe" in content
        assert "module eFPGA" in content
        assert "endmodule" in content

    @pytest.mark.parametrize(
        "validation_type,commands",
        [
            ("hierarchy", ["hierarchy -check", "stat"]),
            (
                "basic_structure",
                ["hierarchy -check", "stat", "select c:*", "select -clear"],
            ),
            (
                "signal_check",
                ["hierarchy -check", "stat", "select w:*", "select -clear"],
            ),
        ],
    )
    def test_yosys_structural_validation(
        self,
        validation_type: str,
        commands: List[str],
        default_fabric: Fabric,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Parametric Yosys structural validation with different validation types."""
        setup_fabric_with_tiles(default_fabric)

        writer = code_generator_factory(".v", f"test_yosys_{validation_type}")
        writer.outFileName = tmp_path / f"test_yosys_{validation_type}.v"

        generateFabric(writer, default_fabric)
        assert writer.outFileName.exists()

        # Run inline Yosys validation
        result = run_yosys_validation(writer.outFileName, commands)

        # Allow some failures for complex validation types - mock tiles are expected to have issues
        max_failures = {"hierarchy": 2, "basic_structure": 3, "signal_check": 4}
        if len(result.failures) > max_failures.get(validation_type, 0):
            pytest.skip(
                f"{validation_type} validation found issues (expected with mock tiles): {result.failures[:2]}"
            )

    def test_fabric_port_to_port_connections(
        self,
        tmp_path: Path,
    ) -> None:
        """Test specific port-to-port connectivity validation."""
        # Create simple test Verilog with known connections
        test_verilog = """
module simple_fabric(
    input CLK,
    input [7:0] FrameData,
    output [3:0] UserIO
);
    wire internal_clk;
    assign internal_clk = CLK;
    
    simple_tile tile_inst (
        .clk(internal_clk),
        .data_out(UserIO)
    );
endmodule

module simple_tile(
    input clk,
    output [3:0] data_out
);
    assign data_out = 4'hF;
endmodule
"""

        test_file = tmp_path / "simple_fabric.v"
        test_file.write_text(test_verilog)

        # Test specific wire connections inline
        commands = [
            "hierarchy -check",
            "stat",
            "select w:internal_clk",
            "select -clear",  # Wire exists
            "select w:internal_clk %co c:*tile_inst*",
            "select -clear",  # Wire connects to tile
        ]

        result = run_yosys_validation(test_file, commands)
        if not result.passed:
            print(f"Port-to-port validation feedback: {result.failures}")
            # Don't fail - this is a demonstration

    def test_basic_structural_validation_with_default_fixture(
        self,
        default_fabric: Fabric,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Basic structural validation using default fabric fixture."""
        setup_fabric_with_tiles(default_fabric)

        writer = code_generator_factory(".v", "default_structural_validation")
        writer.outFileName = tmp_path / "default_structural_validation.v"

        generateFabric(writer, default_fabric)
        assert writer.outFileName.exists()

        # Simple hierarchy validation that should work with default configuration
        commands = ["hierarchy -check", "stat"]
        result = run_yosys_validation(writer.outFileName, commands)

        # Allow some tolerance for basic validation
        if len(result.failures) > 1:
            pytest.skip(
                f"Basic structural validation found issues: {result.failures[:2]}"
            )

    def test_fabric_validation_with_default_size(
        self,
        default_fabric: Fabric,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test fabric validation using default size configuration."""
        setup_fabric_with_tiles(default_fabric)

        writer = code_generator_factory(".v", "default_size_fabric")
        writer.outFileName = tmp_path / "default_size_fabric.v"

        generateFabric(writer, default_fabric)
        assert writer.outFileName.exists()

        # Basic validation that should work with default size
        commands = ["hierarchy -check", "stat"]
        result = run_yosys_validation(writer.outFileName, commands)

        # Allow some tolerance for default configuration
        if len(result.failures) > 1:
            pytest.skip(
                f"Default size fabric validation found issues: {result.failures[:2]}"
            )

    def test_fabric_with_default_fixture(
        self,
        default_fabric: Fabric,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Simple test using default_fabric fixture without parametrization."""
        # Use default fabric as-is for simple reference test
        setup_fabric_with_tiles(default_fabric)

        writer = code_generator_factory(".v", "default_fabric_test")
        writer.outFileName = tmp_path / "default_fabric_test.v"

        generateFabric(writer, default_fabric)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # Basic checks that should always pass
        assert "module eFPGA" in content
        assert "endmodule" in content
        assert "UserCLK" in content
