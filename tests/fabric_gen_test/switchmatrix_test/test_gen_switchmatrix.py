from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from FABulous.custom_exception import InvalidFileType
from FABulous.fabric_definition.define import (
    ConfigBitMode,
    MultiplexerStyle,
)
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
from tests.fabric_gen_test.conftest import SwitchMatrixConfig


class MuxTestCase(NamedTuple):
    """Test case configuration for multiplexer size calculations."""

    connections: dict[str, list[str]]
    expected_config_bits: int
    test_name: str


class TestGenTileSwitchMatrix:
    """Test class for genTileSwitchMatrix function."""

    def test_basic_matrix_generation(
        self,
        switchmatrix_config: SwitchMatrixConfig,
        default_fabric: Fabric,
        default_tile: Tile,
        sample_connections: dict[str, list[str]],
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test switch matrix generation from CSV files."""
        # Setup test case configuration
        default_fabric.configBitMode = switchmatrix_config.fabric_config_bits
        default_fabric.multiplexerStyle = switchmatrix_config.multiplexer_style
        default_tile.matrixDir = (
            tmp_path / f"test_matrix{switchmatrix_config.matrix_suffix}"
        )

        # Create CSV matrix file
        default_tile.matrixDir.touch()
        # Test both Verilog and VHDL generation
        writer: CodeGenerator = code_generator_factory(".v")

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: sample_connections,
        )

        # Execute the function
        if switchmatrix_config.matrix_suffix not in [".v", ".vhdl", ".csv", ".list"]:
            with pytest.raises(InvalidFileType):
                genTileSwitchMatrix(
                    writer,
                    default_fabric,
                    default_tile,
                    switchmatrix_config.debug_signals,
                )
            return

        genTileSwitchMatrix(
            writer, default_fabric, default_tile, switchmatrix_config.debug_signals
        )

        # Verify output file was created
        assert writer.outFileName.exists()

        # Read and verify the generated content
        content: str = writer.outFileName.read_text()

        # Basic structure checks
        assert "NumberOfConfigBits:" in content
        assert f"{default_tile.name}_switch_matrix" in content

        # Check for proper port declarations
        assert "N1BEG0" in content
        assert "E1END0" in content
        assert "LUT_A" in content
        assert "O_A" in content

        # Configuration-specific checks
        if switchmatrix_config.fabric_config_bits == ConfigBitMode.FRAME_BASED:
            assert "ConfigBits" in content
            assert "ConfigBits_N" in content
        elif switchmatrix_config.fabric_config_bits == ConfigBitMode.FLIPFLOP_CHAIN:
            assert "MODE" in content
            assert "CONFin" in content
            assert "CONFout" in content
            assert "CLK" in content

        # Debug signal checks
        if switchmatrix_config.debug_signals:
            assert "DEBUG_select_" in content

        # Multiplexer style checks
        if switchmatrix_config.multiplexer_style == MultiplexerStyle.CUSTOM:
            assert "cus_mux" in content
        else:
            # Generic multiplexer should use input array with ConfigBits indexing
            assert "_input(" in content or "_input[" in content

        # Constants declaration checks
        assert "GND0" in content
        assert "VCC0" in content

    @pytest.mark.parametrize(
        "extension",
        [".v", ".vhdl"],
    )
    def test_existing_hdl_file_skips_generation(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        extension: str,
    ) -> None:
        """Test that existing HDL files skip matrix generation."""

        # Setup HDL file
        hdl_file = tmp_path / f"test_matrix{extension}"
        default_tile.matrixDir = hdl_file
        hdl_file.write_text("// Existing HDL content")

        writer: CodeGenerator = code_generator_factory(extension)

        # Execute the function
        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        # Verify no output file was created (generation was skipped)
        assert not writer.outFileName.exists()
        assert "// Existing HDL content" in hdl_file.read_text()

    def test_invalid_file_format_raises_error(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test that invalid file formats raise InvalidFileType."""
        # Setup invalid file
        invalid_file = tmp_path / "test_matrix.txt"
        default_tile.matrixDir = invalid_file
        invalid_file.write_text("Invalid content")

        writer: CodeGenerator = code_generator_factory(".v")

        # Execute and verify error
        with pytest.raises(InvalidFileType, match="Invalid matrix file format"):
            genTileSwitchMatrix(writer, default_fabric, default_tile, False)

    def test_unconnected_port_raises_error(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that unconnected ports raise ValueError."""
        # Setup CSV with unconnected port
        csv_file = tmp_path / "test_matrix.csv"
        csv_file.touch()
        default_tile.matrixDir = csv_file

        writer: CodeGenerator = code_generator_factory(".v")

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: {"E1END0": []},  # Empty connections
        )

        with pytest.raises(ValueError, match="not connected to anything"):
            genTileSwitchMatrix(writer, default_fabric, default_tile, False)

    def test_no_config_bits_generation(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test switch matrix generation when no configuration bits are needed."""
        # Setup simple direct connections (no muxes)
        csv_file = tmp_path / "test_matrix.csv"
        default_tile.matrixDir = csv_file

        writer: CodeGenerator = code_generator_factory(".v")

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: {
                "E1END0": ["N1BEG0"],
                "LUT_A": ["VCC"],
            },  # Single connections only
        )

        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        content: str = writer.outFileName.read_text()

        # Should have no config bits
        assert "NumberOfConfigBits: 0" in content
        assert "ConfigBits" not in content or "NoConfigBits" not in content

    @pytest.mark.parametrize(
        "mux_test_case",
        [
            # Single connections - no config bits needed
            MuxTestCase(
                connections={"single_wire": ["input0"]},
                expected_config_bits=0,
                test_name="single_connection",
            ),
            # 2-input mux - 1 config bit
            MuxTestCase(
                connections={"mux2": ["in0", "in1"]},
                expected_config_bits=1,
                test_name="two_input_mux",
            ),
            # 3-input mux - padded to 4, needs 2 config bits
            MuxTestCase(
                connections={"mux3": ["in0", "in1", "in2"]},
                expected_config_bits=2,
                test_name="three_input_mux_padded",
            ),
            # 4-input mux - 2 config bits
            MuxTestCase(
                connections={"mux4": ["in0", "in1", "in2", "in3"]},
                expected_config_bits=2,
                test_name="four_input_mux",
            ),
            # 8-input mux - 3 config bits
            MuxTestCase(
                connections={"mux8": [f"in{i}" for i in range(8)]},
                expected_config_bits=3,
                test_name="eight_input_mux",
            ),
            # 16-input mux - 4 config bits
            MuxTestCase(
                connections={"mux16": [f"in{i}" for i in range(16)]},
                expected_config_bits=4,
                test_name="sixteen_input_mux",
            ),
            # Multiple muxes - combined config bits
            MuxTestCase(
                connections={
                    "mux2": ["in0", "in1"],  # 1 bit
                    "mux4": ["in0", "in1", "in2", "in3"],  # 2 bits
                    "mux3": ["in0", "in1", "in2"],  # 2 bits (padded to 4)
                    "mux8": [
                        "in0",
                        "in1",
                        "in2",
                        "in3",
                        "in4",
                        "in5",
                        "in6",
                        "in7",
                    ],  # 3 bits
                    "single": ["in0"],  # 0 bits
                },
                expected_config_bits=8,  # 1 + 2 + 2 + 3 + 0
                test_name="multiple_mux_sizes",
            ),
            # Odd-sized muxes that need padding
            MuxTestCase(
                connections={
                    "mux5": [f"in{i}" for i in range(5)],  # Padded to 8 -> 3 bits
                    "mux6": [f"in{i}" for i in range(6)],  # Padded to 8 -> 3 bits
                    "mux7": [f"in{i}" for i in range(7)],  # Padded to 8 -> 3 bits
                },
                expected_config_bits=9,  # 3 + 3 + 3
                test_name="odd_sized_muxes",
            ),
            # Large mux scenarios
            MuxTestCase(
                connections={
                    "large_mux": [f"input{i}" for i in range(32)],  # 5 config bits
                    "medium_mux": [
                        f"input{i}" for i in range(12)
                    ],  # Padded to 16 -> 4 bits
                },
                expected_config_bits=9,  # 5 + 4
                test_name="large_mux_scenarios",
            ),
        ],
        ids=lambda case: case.test_name,
    )
    def test_mux_size_calculations(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mux_test_case: MuxTestCase,
    ) -> None:
        """Test proper calculation of multiplexer sizes and config bits."""
        csv_file = tmp_path / f"test_matrix_{mux_test_case.test_name}.csv"
        default_tile.matrixDir = csv_file

        writer: CodeGenerator = code_generator_factory(".v")

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: mux_test_case.connections,
        )

        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        content: str = writer.outFileName.read_text()

        # Check config bits calculation
        assert f"NumberOfConfigBits: {mux_test_case.expected_config_bits}" in content

    def test_vhdl_specific_features(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test VHDL-specific code generation features."""
        csv_file = tmp_path / "test_matrix.csv"
        default_tile.matrixDir = csv_file

        writer: CodeGenerator = code_generator_factory(".vhdl")

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: {"E1END0": ["N1BEG0", "VCC"]},
        )

        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        content: str = writer.outFileName.read_text()

        # VHDL should use different constant syntax
        assert "GND0" in content
        assert "VCC0" in content
        # VHDL constants should be defined without 1'b prefix
        assert "1'b0" not in content

    def test_debug_signal_generation(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test generation of debug signals for switch matrix."""
        csv_file = tmp_path / "test_matrix.csv"
        default_tile.matrixDir = csv_file

        writer: CodeGenerator = code_generator_factory(".v")

        connections: dict[str, list[str]] = {
            "mux4": ["in0", "in1", "in2", "in3"],  # 4 inputs -> needs debug signal
            "mux2": ["in0", "in1"],  # 2 inputs -> needs debug signal
            "single": ["in0"],  # 1 input -> no debug signal needed
        }

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: connections,
        )

        genTileSwitchMatrix(writer, default_fabric, default_tile, True)

        content: str = writer.outFileName.read_text()

        # Check for debug signals
        assert "DEBUG_select_mux4" in content
        assert "DEBUG_select_mux2" in content
        assert (
            "DEBUG_select_single" not in content
        )  # Single connections don't need debug

    def test_different_config_bit_modes(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test different configuration bit modes."""
        csv_file = tmp_path / "test_matrix.csv"
        default_tile.matrixDir = csv_file

        connections: dict[str, list[str]] = {"mux2": ["in0", "in1"]}

        # Test FRAME_BASED mode
        default_fabric.configBitMode = ConfigBitMode.FRAME_BASED
        writer: CodeGenerator = code_generator_factory(".v", "frame_based")

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: connections,
        )

        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        content: str = writer.outFileName.read_text()
        assert "ConfigBits" in content
        assert "ConfigBits_N" in content

        # Test FLIPFLOP_CHAIN mode
        default_fabric.configBitMode = ConfigBitMode.FLIPFLOP_CHAIN
        writer_ff: CodeGenerator = code_generator_factory(".v", "flipflop_chain")

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: connections,
        )

        genTileSwitchMatrix(writer_ff, default_fabric, default_tile, False)

        content: str = writer_ff.outFileName.read_text()
        assert "MODE" in content
        assert "CONFin" in content
        assert "CONFout" in content

    def test_edge_cases(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test edge cases and boundary conditions."""
        csv_file = tmp_path / "test_matrix.csv"
        default_tile.matrixDir = csv_file

        writer: CodeGenerator = code_generator_factory(".v")

        # Test edge cases
        edge_connections: dict[str, list[str]] = {
            "empty_connections": [],  # Should raise error
            "single_connection": ["input0"],  # No config bits
            "two_connections": ["input0", "input1"],  # 1 config bit
            "large_mux": [f"input{i}" for i in range(16)],  # 4 config bits
            "odd_mux": [f"input{i}" for i in range(5)],  # Padded to 8 -> 3 config bits
        }

        # Test empty connections (should raise error)
        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: {"empty_port": []},
        )

        with pytest.raises(ValueError, match="not connected to anything"):
            genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        # Test valid edge cases
        valid_connections: dict[str, list[str]] = {
            k: v for k, v in edge_connections.items() if v
        }

        monkeypatch.setattr(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            lambda x, y: valid_connections,
        )

        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        content: str = writer.outFileName.read_text()

        # Verify large mux handling
        assert "large_mux" in content
        assert "odd_mux" in content

        # Check config bits calculation
        # single_connection: 0, two_connections: 1, large_mux: 4, odd_mux: 3
        # Total: 8 config bits
        assert "NumberOfConfigBits: 8" in content
