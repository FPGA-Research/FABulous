"""Conftest file providing fixtures for fabric generator tests."""

import csv
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
from cocotb.runner import get_runner
from pytest_mock import MockerFixture

from FABulous.fabric_definition.ConfigMem import ConfigMem
from FABulous.fabric_definition.define import (
    IO,
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
)
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator


class FabricConfig(NamedTuple):
    """Configuration parameters for fabric testing."""

    name: str
    frame_bits_per_row: int
    max_frames_per_col: int


class TileConfig(NamedTuple):
    """Configuration parameters for tile testing."""

    name: str
    global_config_bits: int


class SwitchMatrixConfig(NamedTuple):
    """Configuration parameters for switch matrix testing."""

    name: str
    matrix_suffix: str
    fabric_config_bits: ConfigBitMode
    multiplexer_style: MultiplexerStyle
    debug_signals: bool
    expected_error: str | None = None


@pytest.fixture
def default_fabric(mocker: MockerFixture) -> Fabric:
    """Helper function to create a Fabric instance with given parameters."""
    fabric = mocker.create_autospec(Fabric, spec_set=False)
    fabric.frameBitsPerRow = 32
    fabric.maxFramesPerCol = 20
    fabric.name = "DefaultFabric"
    fabric.numberOfBRAMs = 0
    fabric.numberOfRows = 4
    fabric.numberOfColumns = 4
    fabric.desync_flag = 0
    fabric.frameSelectWidth = 8
    fabric.rowSelectWidth = 8
    fabric.tileDic = {}
    fabric.tile = []
    # Add minimal tile structure
    for y in range(4):
        row = []
        for x in range(4):
            tile = type("MockTile", (), {})()
            tile.name = f"DefaultTile_X{x}Y{y}"
            tile.bels = [MockBel([], [])]
            tile.partOfSuperTile = False
            tile.portsInfo = []
            fabric.tileDic[tile.name] = tile
            row.append(tile)
        fabric.tile.append(row)
    # Additional properties from mock_fabric
    fabric.configBitMode = ConfigBitMode.FRAME_BASED
    fabric.multiplexerStyle = MultiplexerStyle.CUSTOM
    fabric.generateDelayInSwitchMatrix = 80
    return fabric


@pytest.fixture
def default_tile(tmp_path: Path, mocker: MockerFixture) -> Tile:
    """Create a default tile for testing with complex configuration."""
    tile = mocker.create_autospec(Tile, spec_set=False)
    tile.name = "DefaultTile"
    tile.globalConfigBits = 127
    tile.matrixDir = tmp_path / "DefaultTile_matrix.csv"

    # Add comprehensive port configuration (merged from complex tile)
    tile.portsInfo = [
        MockPortInfo(Direction.NORTH, IO.INPUT, "N1BEG", 4),
        MockPortInfo(Direction.NORTH, IO.OUTPUT, "N1END", 4),
        MockPortInfo(Direction.EAST, IO.INPUT, "E2BEG", 8),
        MockPortInfo(Direction.EAST, IO.OUTPUT, "E2END", 8),
        MockPortInfo(Direction.SOUTH, IO.INPUT, "S4BEG", 4),
        MockPortInfo(Direction.SOUTH, IO.OUTPUT, "S4END", 4),
        MockPortInfo(Direction.WEST, IO.INPUT, "W6BEG", 2),
        MockPortInfo(Direction.WEST, IO.OUTPUT, "W6END", 2),
        MockPortInfo(Direction.JUMP, IO.INPUT, "VCC", 1),
        MockPortInfo(Direction.JUMP, IO.OUTPUT, "GND", 1),
        MockPortInfo(Direction.JUMP, IO.INPUT, "CLK", 1),
        MockPortInfo(Direction.JUMP, IO.OUTPUT, "RST", 1),
    ]

    # Add comprehensive BEL configuration (merged from complex tile)
    tile.bels = [
        MockBel(["LUT_A0", "LUT_A1", "LUT_A2", "LUT_A3"], ["O_A"]),
        MockBel(["LUT_B0", "LUT_B1", "LUT_B2", "LUT_B3"], ["O_B"]),
        MockBel(["FF_D", "FF_CLK", "FF_RST"], ["FF_Q"]),
        MockBel(["MUX_A", "MUX_B", "MUX_SEL"], ["MUX_O"]),
    ]

    # Add required side port methods
    def get_north_ports():
        return [p for p in tile.portsInfo if p.wireDirection == Direction.NORTH]

    def get_east_ports():
        return [p for p in tile.portsInfo if p.wireDirection == Direction.EAST]

    def get_south_ports():
        return [p for p in tile.portsInfo if p.wireDirection == Direction.SOUTH]

    def get_west_ports():
        return [p for p in tile.portsInfo if p.wireDirection == Direction.WEST]

    tile.getNorthSidePorts = get_north_ports
    tile.getEastSidePorts = get_east_ports
    tile.getSouthSidePorts = get_south_ports
    tile.getWestSidePorts = get_west_ports

    return tile


@pytest.fixture(
    params=[
        # Standard configurations
        FabricConfig(
            frame_bits_per_row=32, max_frames_per_col=20, name="StandardFabric"
        ),
        FabricConfig(frame_bits_per_row=8, max_frames_per_col=5, name="SmallFabric"),
        # Boundary conditions
        FabricConfig(frame_bits_per_row=1, max_frames_per_col=1, name="MinimalFabric"),
        FabricConfig(frame_bits_per_row=1, max_frames_per_col=64, name="ThinFabric"),
        FabricConfig(frame_bits_per_row=64, max_frames_per_col=1, name="WideFabric"),
        # Non-power-of-2 configurations
        FabricConfig(frame_bits_per_row=5, max_frames_per_col=7, name="IrregularSmall"),
        FabricConfig(
            frame_bits_per_row=33, max_frames_per_col=21, name="IrregularLarge"
        ),
        FabricConfig(frame_bits_per_row=7, max_frames_per_col=13, name="PrimeFabric"),
        # Large-scale configurations
        FabricConfig(
            frame_bits_per_row=256, max_frames_per_col=100, name="VeryLargeFabric"
        ),
    ],
    ids=lambda config: config.name,
)
def fabric_config(request: pytest.FixtureRequest, mocker: MockerFixture) -> Fabric:
    """Comprehensive parametric fabric configurations for testing different scenarios."""
    config = request.param
    fabric = mocker.create_autospec(Fabric, spec_set=False)
    fabric.frameBitsPerRow = config.frame_bits_per_row
    fabric.maxFramesPerCol = config.max_frames_per_col
    fabric.name = config.name
    return fabric


@pytest.fixture(
    params=[
        # Boundary conditions
        TileConfig("StandardTile", 16),
        TileConfig("EmptyTile", 0),
        TileConfig("MinimalTile", 1),
        TileConfig("MaxTile", 256),
        # Non-power-of-2 configurations
        TileConfig("Irregular7Tile", 7),
        TileConfig("Irregular33Tile", 33),
    ],
    ids=lambda config: config.name,
)
def tile_config(request: pytest.FixtureRequest, mocker: MockerFixture) -> Tile:
    """Comprehensive parametric tile configurations covering various component types."""
    config = request.param
    tile = mocker.create_autospec(Tile, spec_set=False)
    tile.name = config.name
    tile.globalConfigBits = config.global_config_bits
    return tile


@pytest.fixture(
    params=[
        # Generate all combinations of key parameters systematically
        *[
            SwitchMatrixConfig(
                name=f"{suffix.replace('.', '')}_{config_bits.value}_{mux_style.value}{'_debug' if debug else ''}",
                matrix_suffix=suffix,
                fabric_config_bits=config_bits,
                multiplexer_style=mux_style,
                debug_signals=debug,
            )
            for suffix in [".csv", ".list"]  # File format variants
            for config_bits in [
                ConfigBitMode.FRAME_BASED,
                ConfigBitMode.FLIPFLOP_CHAIN,
            ]  # Config variants
            for mux_style in [
                MultiplexerStyle.CUSTOM,
                MultiplexerStyle.GENERIC,
            ]  # Multiplexer variants
            for debug in [False, True]  # Debug variants
        ],
        # Add specific edge cases and error scenarios
        SwitchMatrixConfig(
            name="ErrorMatrix_invalid_format",
            matrix_suffix=".txt",
            fabric_config_bits=ConfigBitMode.FRAME_BASED,
            multiplexer_style=MultiplexerStyle.CUSTOM,
            debug_signals=False,
            expected_error="Invalid matrix file format",
        ),
        SwitchMatrixConfig(
            name="MinimalMatrix_edge_case",
            matrix_suffix=".csv",
            fabric_config_bits=ConfigBitMode.FRAME_BASED,
            multiplexer_style=MultiplexerStyle.CUSTOM,
            debug_signals=False,
        ),
        SwitchMatrixConfig(
            name="ComplexMatrix_all_features",
            matrix_suffix=".csv",
            fabric_config_bits=ConfigBitMode.FLIPFLOP_CHAIN,
            multiplexer_style=MultiplexerStyle.GENERIC,
            debug_signals=True,
        ),
    ],
    ids=lambda config: config.name,
)
def switchmatrix_config(request: pytest.FixtureRequest) -> SwitchMatrixConfig:
    """Comprehensive parametric switch matrix configurations for testing different scenarios."""
    return request.param


class SwitchMatrixTestCase(NamedTuple):
    """Test case configuration for switch matrix generation tests."""

    name: str
    matrix_suffix: str
    fabric_config_bits: ConfigBitMode
    multiplexer_style: MultiplexerStyle
    debug_signals: bool
    expected_error: str | None = None


class MockPortInfo:
    """Mock for PortInfo with required attributes for testing."""

    def __init__(
        self,
        wire_direction: Direction = Direction.NORTH,
        in_out: IO = IO.INPUT,
        name: str = "TestPort",
        wire_count: int = 1,
    ) -> None:
        self.wireDirection = wire_direction
        self.inOut = in_out
        self.name = name
        self.wireCount = wire_count
        self.sideOfTile = wire_direction  # Same as wire direction
        self.xOffset = 0  # Default offset
        self.yOffset = 0  # Default offset

    def expandPortInfoByName(self) -> list[str]:
        """Mock method to expand port names."""
        return [f"{self.name}{i}" for i in range(self.wireCount)]

    def expandPortInfo(self, mode="SwitchMatrix") -> tuple[list[str], list[str]]:
        return [f"{self.name}{i}" for i in range(self.wireCount)], [
            f"{self.name}{i}" for i in range(self.wireCount)
        ]


class MockBel:
    """Mock for BEL with required attributes for testing."""

    def __init__(self, inputs: list | None = None, outputs: list | None = None) -> None:
        self.inputs = inputs or ["input0", "input1"]
        self.outputs = outputs or ["output0", "output1"]
        self.externalInput = self.inputs
        self.externalOutput = self.outputs
        self.sharedPort = []  # Empty list for shared ports
        self.prefix = ""  # Empty prefix for signal naming
        self.src = ""  # Empty src for VHDL component declaration


@pytest.fixture
def sample_connections() -> dict[str, list[str]]:
    """Sample connection dictionary for switch matrix testing."""
    return {
        "E1END0": ["N1BEG0", "O_A"],
        "E1END1": ["N1BEG1", "O_B", "VCC", "GND"],
        "LUT_A": ["N1BEG0"],
        "LUT_B": ["N1BEG1", "VCC"],
        "O_A": ["FF_D"],
        "GND": ["0"],
        "VCC": ["1"],
    }


def create_config_csv(file_path: Path, data: list[dict]) -> None:
    """Helper function to create config memory CSV files from dictionary data.

    Parameters
    ----------
    file_path : Path
        The path where the CSV file should be created
    data : list[dict]
        List of dictionaries containing the CSV row data
    """
    with file_path.open("w", newline="") as f:
        if data:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)


def verify_csv_content(file_path: Path, expected_rows: int | None = None) -> list[dict]:
    """Helper function to verify CSV content and return parsed data.

    Parameters
    ----------
    file_path : Path
        The path to the CSV file to verify
    expected_rows : int, optional
        Expected number of rows in the CSV

    Returns
    -------
    list[dict]
        The parsed CSV data as a list of dictionaries
    """
    assert file_path.exists(), f"CSV file {file_path} does not exist"

    with file_path.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert rows[0].keys() == {
        "frame_name",
        "frame_index",
        "bits_used_in_frame",
        "used_bits_mask",
        "ConfigBits_ranges",
    }, f"CSV file {file_path} has unexpected headers"

    if expected_rows is not None:
        assert len(rows) == expected_rows, (
            f"Expected {expected_rows} rows, got {len(rows)}"
        )

    return rows


class ConfigMemConfig(NamedTuple):
    """Configuration for ConfigMem test scenarios."""

    name: str
    scenario: str


@pytest.fixture(params=[1, 2, 3, 4, 5], ids=lambda param: f"ConfigMemPattern{param}")
def configmem_list(
    request: pytest.FixtureRequest,
) -> Callable[[Fabric, Tile], list[ConfigMem]]:
    """Parameterized fixture returning various ConfigMem object lists."""

    def _create(fabric: Fabric, tile: Tile) -> list[ConfigMem]:
        import itertools
        import random
        from random import shuffle

        random.seed(request.param)

        # Generate all possible (frame_index, bits_used) combinations
        poss = list(
            itertools.product(
                range(fabric.maxFramesPerCol), range(fabric.frameBitsPerRow + 1)
            )
        )
        shuffle(poss)
        config_final = poss[: tile.globalConfigBits]

        # Helper function to generate random bit mask
        def generate_mask(bits_used: int, total_bits: int) -> str:
            if bits_used == 0:
                return "0" * total_bits
            if bits_used >= total_bits:
                return "1" * total_bits

            # Create a list with the right number of 1s and 0s
            mask_bits = ["1"] * bits_used + ["0"] * (total_bits - bits_used)
            # Randomly shuffle the bits to create a random pattern
            shuffle(mask_bits)

            return "".join(mask_bits)

        # Generate ConfigMem objects based on config_final
        configmems = []
        total_bits_assigned = 0

        # Group config_final by frame_index to consolidate bits per frame
        frame_groups = {}
        for frame_index, bits_in_frame in config_final:
            if frame_index not in frame_groups:
                frame_groups[frame_index] = []
            frame_groups[frame_index].append(bits_in_frame)

        # Create ConfigMem objects for each frame
        for frame_index in range(fabric.maxFramesPerCol):
            if frame_index not in frame_groups:
                configmems.append(
                    ConfigMem(
                        frameName=f"frame{frame_index}",
                        frameIndex=frame_index,
                        bitsUsedInFrame=0,
                        usedBitMask=generate_mask(0, fabric.frameBitsPerRow),
                        configBitRanges=[],
                    )
                )
                continue
            bits_list = frame_groups[frame_index]
            total_bits_in_frame = len(bits_list)

            # Ensure we don't exceed frame capacity
            bits_used = min(total_bits_in_frame, fabric.frameBitsPerRow)

            if bits_used > 0:
                bit_ranges = list(
                    range(total_bits_assigned, total_bits_assigned + bits_used)
                )
                random.shuffle(bit_ranges)
                configmems.append(
                    ConfigMem(
                        frameName=f"frame{frame_index}",
                        frameIndex=frame_index,
                        bitsUsedInFrame=bits_used,
                        usedBitMask=generate_mask(bits_used, fabric.frameBitsPerRow),
                        configBitRanges=bit_ranges,
                    )
                )
                total_bits_assigned += bits_used
        return configmems

    return _create


@pytest.fixture
def code_generator_factory(tmp_path: Path) -> Callable[[str, str], CodeGenerator]:
    """Factory fixture to create code generators with temporary output files."""

    def _create_generator(extension: str, name: str = "test_output") -> CodeGenerator:
        from FABulous.fabric_generator.code_generator.code_generator_Verilog import (
            VerilogCodeGenerator,
        )
        from FABulous.fabric_generator.code_generator.code_generator_VHDL import (
            VHDLCodeGenerator,
        )

        output_file = tmp_path / f"{name}{extension}"

        if extension == ".v":
            writer = VerilogCodeGenerator()
            writer.outFileName = output_file
            return writer
        if extension in [".vhd", ".vhdl"]:
            writer = VHDLCodeGenerator()
            writer.outFileName = output_file
            return writer
        raise ValueError(f"Unsupported extension: {extension}")

    return _create_generator


@pytest.fixture
def cocotb_runner(tmp_path: Path) -> Callable:
    """Factory fixture to create cocotb runners for RTL simulation."""

    def _create_runner(
        sources: list[Path], hdl_top_level: str, test_module_path: Path
    ) -> None:
        lang = set([i.suffix for i in sources])

        if len(lang) > 1:
            raise ValueError("All source files must have the same HDL language suffix")

        hdl_toplevel_lang = lang.pop()  # Get the single language suffix
        if hdl_toplevel_lang not in {".v", ".vhd"}:
            raise ValueError(f"Unsupported HDL language: {hdl_toplevel_lang}")

        if hdl_toplevel_lang == ".v":
            sim = "icarus"
        elif hdl_toplevel_lang == ".vhd":
            sim = "ghdl"
        runner = get_runner(sim)

        sources.insert(
            0, Path(__file__).parent / "testdata" / f"models{hdl_toplevel_lang}"
        )
        # Copy test module and models to temp directory for cocotb
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)

        # Copy this test file to the test directory so cocotb can find it
        shutil.copy(test_module_path, test_dir / test_module_path.name)

        # Build directory
        build_dir = tmp_path / "cocotb_build"

        # Configure sources based on HDL language
        if hdl_toplevel_lang == ".v":
            runner.build(
                verilog_sources=sources,
                hdl_toplevel=hdl_top_level,
                always=True,
                build_dir=build_dir,
            )
        elif hdl_toplevel_lang == ".vhd":
            # GHDL converts identifiers to lowercase for elaboration and execution
            hdl_top_level = hdl_top_level.lower()
            runner.build(
                vhdl_sources=sources,
                hdl_toplevel=hdl_top_level,
                always=True,
                build_dir=build_dir,
            )

            # Copy all files from build_dir to test_dir
            for file in build_dir.iterdir():
                if file.is_file():
                    shutil.copy(file, test_dir / file.name)

        runner.test(
            hdl_toplevel=hdl_top_level,
            test_module=test_module_path.stem,
            build_dir=build_dir,
            test_dir=test_dir,
        )

    return _create_runner
