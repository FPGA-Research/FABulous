from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from FABulous.fabric_definition.define import ConfigBitMode, Direction, IO
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.gen_fabric.gen_tile import generateTile


class TileTestCase(NamedTuple):
    """Test case configuration for tile generation tests."""

    config_bit_mode: ConfigBitMode
    global_config_bits: int
    test_name: str


class TestGenTile:
    """Test class for generateTile function."""

    def test_basic_tile_generation_frame_based(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test basic tile generation with frame-based configuration."""
        # Setup
        default_fabric.configBitMode = ConfigBitMode.FRAME_BASED
        default_tile.globalConfigBits = 10

        # Mock dependency files that tile generation expects
        switch_matrix_file = tmp_path / f"{default_tile.name}_switch_matrix.v"
        switch_matrix_file.write_text("// Mock switch matrix")
        config_mem_file = tmp_path / f"{default_tile.name}_ConfigMem.v"
        config_mem_file.write_text("// Mock config mem")

        writer = code_generator_factory(".v", f"{default_tile.name}")
        writer.outFileName = tmp_path / f"{default_tile.name}.v"

        generateTile(writer, default_fabric, default_tile)

        # Verify output file was created
        assert writer.outFileName.exists()

        # Read and verify content
        content = writer.outFileName.read_text()

        # Basic structure checks
        assert f"module {default_tile.name}" in content
        assert "MaxFramesPerCol" in content
        assert "FrameBitsPerRow" in content
        assert "NoConfigBits" in content

        # Frame-based configuration ports
        assert "FrameData" in content
        assert "FrameData_O" in content
        assert "FrameStrobe" in content
        assert "FrameStrobe_O" in content
        assert "CONFIG_PORT" in content

        # Clock ports
        assert "UserCLK" in content
        assert "UserCLKo" in content

        # Signal declarations
        assert "signal declarations" in content
        assert "BEL ports" in content

    def test_basic_tile_generation_flipflop_chain(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test basic tile generation with flipflop chain configuration."""
        # Setup
        default_fabric.configBitMode = ConfigBitMode.FLIPFLOP_CHAIN
        default_tile.globalConfigBits = 5

        # Mock dependency files
        switch_matrix_file = tmp_path / f"{default_tile.name}_switch_matrix.v"
        switch_matrix_file.write_text("// Mock switch matrix")
        config_mem_file = tmp_path / f"{default_tile.name}_ConfigMem.v"
        config_mem_file.write_text("// Mock config mem")

        writer = code_generator_factory(".v", f"{default_tile.name}_ff")
        writer.outFileName = tmp_path / f"{default_tile.name}_ff.v"

        generateTile(writer, default_fabric, default_tile)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # FlipFlop chain specific ports
        assert "MODE" in content
        assert "CONFin" in content
        assert "CONFout" in content
        assert "CLK" in content

        # Should not have frame-based ports
        assert "FrameData" not in content
        assert "FrameStrobe" not in content

    def test_tile_generation_no_config_bits(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test tile generation with zero configuration bits."""
        # Setup tile with no config bits
        default_tile.globalConfigBits = 0

        # Mock switch matrix file
        switch_matrix_file = tmp_path / f"{default_tile.name}_switch_matrix.v"
        switch_matrix_file.write_text("// Mock switch matrix")

        writer = code_generator_factory(".v", f"{default_tile.name}_no_config")
        writer.outFileName = tmp_path / f"{default_tile.name}_no_config.v"

        generateTile(writer, default_fabric, default_tile)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # Should not have NoConfigBits parameter
        assert "NoConfigBits" not in content

        # Should still have basic structure
        assert f"module {default_tile.name}" in content
        assert "UserCLK" in content

    @pytest.mark.parametrize("extension", [".v", ".vhdl"])
    def test_tile_generation_different_hdl(
        self,
        extension: str,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test tile generation for both Verilog and VHDL."""
        # Mock dependency files with correct extension
        switch_matrix_file = tmp_path / f"{default_tile.name}_switch_matrix{extension}"
        switch_matrix_file.write_text(
            "-- Mock switch matrix" if extension == ".vhdl" else "// Mock switch matrix"
        )

        if default_tile.globalConfigBits > 0:
            config_mem_file = tmp_path / f"{default_tile.name}_ConfigMem{extension}"
            config_mem_file.write_text(
                "-- Mock config mem" if extension == ".vhdl" else "// Mock config mem"
            )

        writer = code_generator_factory(extension, f"{default_tile.name}_hdl")
        writer.outFileName = tmp_path / f"{default_tile.name}_hdl{extension}"

        generateTile(writer, default_fabric, default_tile)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        if extension == ".v":
            assert f"module {default_tile.name}" in content
            assert "endmodule" in content
        elif extension == ".vhdl":
            assert f"entity {default_tile.name}" in content
            assert f"end {default_tile.name}" in content

    def test_tile_with_external_ports(
        self,
        default_fabric: Fabric,
        tile_with_external_ports: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test tile generation with external I/O ports from BELs."""
        # Mock dependency files
        switch_matrix_file = (
            tmp_path / f"{tile_with_external_ports.name}_switch_matrix.v"
        )
        switch_matrix_file.write_text("// Mock switch matrix")

        if tile_with_external_ports.globalConfigBits > 0:
            config_mem_file = tmp_path / f"{tile_with_external_ports.name}_ConfigMem.v"
            config_mem_file.write_text("// Mock config mem")

        writer = code_generator_factory(".v", f"{tile_with_external_ports.name}_ext")
        writer.outFileName = tmp_path / f"{tile_with_external_ports.name}_ext.v"

        generateTile(writer, default_fabric, tile_with_external_ports)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # Should have external port declarations
        # (Specific port names depend on the fixture implementation)
        assert "Tile IO ports from BELs" in content

    @pytest.mark.parametrize(
        "tile_test_case",
        [
            TileTestCase(
                config_bit_mode=ConfigBitMode.FRAME_BASED,
                global_config_bits=8,
                test_name="frame_based_8_bits",
            ),
            TileTestCase(
                config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
                global_config_bits=12,
                test_name="flipflop_chain_12_bits",
            ),
            TileTestCase(
                config_bit_mode=ConfigBitMode.FRAME_BASED,
                global_config_bits=0,
                test_name="frame_based_no_config",
            ),
        ],
        ids=lambda case: case.test_name,
    )
    def test_different_tile_configurations(
        self,
        tile_test_case: TileTestCase,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test tile generation with different configuration parameters."""
        # Configure tile and fabric
        default_fabric.configBitMode = tile_test_case.config_bit_mode
        default_tile.globalConfigBits = tile_test_case.global_config_bits

        # Mock dependency files
        switch_matrix_file = tmp_path / f"{default_tile.name}_switch_matrix.v"
        switch_matrix_file.write_text("// Mock switch matrix")

        if tile_test_case.global_config_bits > 0:
            config_mem_file = tmp_path / f"{default_tile.name}_ConfigMem.v"
            config_mem_file.write_text("// Mock config mem")

        writer = code_generator_factory(".v", f"test_{tile_test_case.test_name}")
        writer.outFileName = tmp_path / f"test_{tile_test_case.test_name}.v"

        generateTile(writer, default_fabric, default_tile)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # Configuration-specific checks
        if tile_test_case.config_bit_mode == ConfigBitMode.FRAME_BASED:
            assert "FrameData" in content
            assert "FrameStrobe" in content
        elif tile_test_case.config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
            assert "MODE" in content
            assert "CONFin" in content
            assert "CONFout" in content

        if tile_test_case.global_config_bits > 0:
            assert "NoConfigBits" in content
            assert str(tile_test_case.global_config_bits) in content

    def test_vhdl_component_declarations(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test VHDL-specific component declarations in tile generation."""
        # Create VHDL dependency files with proper content
        switch_matrix_file = tmp_path / f"{default_tile.name}_switch_matrix.vhdl"
        switch_matrix_file.write_text(f"""
entity {default_tile.name}_switch_matrix is
end entity;
""")

        if default_tile.globalConfigBits > 0:
            config_mem_file = tmp_path / f"{default_tile.name}_ConfigMem.vhdl"
            config_mem_file.write_text(f"""
entity {default_tile.name}_ConfigMem is
end entity;
""")

        writer = code_generator_factory(".vhdl", f"{default_tile.name}_vhdl")
        writer.outFileName = tmp_path / f"{default_tile.name}_vhdl.vhdl"

        generateTile(writer, default_fabric, default_tile)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # VHDL specific structure
        assert f"entity {default_tile.name}" in content
        assert "architecture" in content

    def test_missing_switch_matrix_file_error(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test error handling when switch matrix file is missing for VHDL."""
        writer = code_generator_factory(".vhdl", f"{default_tile.name}_missing")
        writer.outFileName = tmp_path / f"{default_tile.name}_missing.vhdl"

        # Don't create the switch matrix file to trigger error
        with pytest.raises(FileNotFoundError, match="switch_matrix.vhdl"):
            generateTile(writer, default_fabric, default_tile)

    def test_missing_config_mem_file_error(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test error handling when config mem file is missing for VHDL with config bits."""
        default_tile.globalConfigBits = 10  # Ensure we need config mem

        # Create switch matrix but not config mem
        switch_matrix_file = tmp_path / f"{default_tile.name}_switch_matrix.vhdl"
        switch_matrix_file.write_text("entity switch_matrix is end entity;")

        writer = code_generator_factory(".vhdl", f"{default_tile.name}_missing_config")
        writer.outFileName = tmp_path / f"{default_tile.name}_missing_config.vhdl"

        with pytest.raises(FileNotFoundError, match="ConfigMem.vhdl"):
            generateTile(writer, default_fabric, default_tile)

    def test_tile_with_jump_wires(
        self,
        default_fabric: Fabric,
        tile_with_jump_wires: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test tile generation with jump wire connections."""
        # Mock dependency files
        switch_matrix_file = tmp_path / f"{tile_with_jump_wires.name}_switch_matrix.v"
        switch_matrix_file.write_text("// Mock switch matrix")

        if tile_with_jump_wires.globalConfigBits > 0:
            config_mem_file = tmp_path / f"{tile_with_jump_wires.name}_ConfigMem.v"
            config_mem_file.write_text("// Mock config mem")

        writer = code_generator_factory(".v", f"{tile_with_jump_wires.name}_jump")
        writer.outFileName = tmp_path / f"{tile_with_jump_wires.name}_jump.v"

        generateTile(writer, default_fabric, tile_with_jump_wires)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # Check for jump wire declarations
        assert "Jump wires" in content

    def test_emulation_parameters_verilog_only(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test that emulation parameters are only generated for Verilog."""
        # Mock dependency files
        switch_matrix_file_v = tmp_path / f"{default_tile.name}_switch_matrix.v"
        switch_matrix_file_v.write_text("// Mock switch matrix")

        switch_matrix_file_vhdl = tmp_path / f"{default_tile.name}_switch_matrix.vhdl"
        switch_matrix_file_vhdl.write_text("-- Mock switch matrix")

        # Test Verilog
        writer_v = code_generator_factory(".v", f"{default_tile.name}_emul_v")
        writer_v.outFileName = tmp_path / f"{default_tile.name}_emul_v.v"

        generateTile(writer_v, default_fabric, default_tile)
        content_v = writer_v.outFileName.read_text()

        # Test VHDL
        writer_vhdl = code_generator_factory(".vhdl", f"{default_tile.name}_emul_vhdl")
        writer_vhdl.outFileName = tmp_path / f"{default_tile.name}_emul_vhdl.vhdl"

        generateTile(writer_vhdl, default_fabric, default_tile)
        content_vhdl = writer_vhdl.outFileName.read_text()

        # Emulation should only be in Verilog
        assert "EMULATION" in content_v
        assert "Emulate_Bitstream" in content_v
        assert "EMULATION" not in content_vhdl
        assert "Emulate_Bitstream" not in content_vhdl

    def test_tile_parameters_configuration(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
    ) -> None:
        """Test that tile parameters are correctly configured."""
        # Set specific fabric parameters
        default_fabric.maxFramesPerCol = 30
        default_fabric.frameBitsPerRow = 48
        default_tile.globalConfigBits = 25

        # Mock dependency files
        switch_matrix_file = tmp_path / f"{default_tile.name}_switch_matrix.v"
        switch_matrix_file.write_text("// Mock switch matrix")
        config_mem_file = tmp_path / f"{default_tile.name}_ConfigMem.v"
        config_mem_file.write_text("// Mock config mem")

        writer = code_generator_factory(".v", f"{default_tile.name}_params")
        writer.outFileName = tmp_path / f"{default_tile.name}_params.v"

        generateTile(writer, default_fabric, default_tile)

        assert writer.outFileName.exists()
        content = writer.outFileName.read_text()

        # Check parameter values are preserved
        assert "MaxFramesPerCol" in content
        assert "30" in content
        assert "FrameBitsPerRow" in content
        assert "48" in content
        assert "NoConfigBits" in content
        assert "25" in content
