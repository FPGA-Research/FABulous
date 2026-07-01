"""Conftest file providing fixtures for fabric generator tests."""

import csv
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
from cocotb_tools.runner import get_runner
from pytest_mock import MockerFixture

from fabulous.fabric_definition.configmem import ConfigMem
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.yosys_obj import YosysJson
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV
from fabulous.fabulous_settings import get_context, init_context


class FabricConfig(NamedTuple):
    """Configuration parameters for fabric testing."""

    name: str
    frame_bits_per_row: int
    max_frames_per_col: int


class TileConfig(NamedTuple):
    """Configuration parameters for tile testing."""

    name: str
    global_config_bits: int


@pytest.fixture
def mk_tile(tmp_path: Path) -> Callable[[str], Tile]:
    """Factory fixture that creates minimal real Tile instances.

    Parameters
    ----------
    tmp_path : Path
        Pytest-provided temporary directory used to root the tile files.

    Returns
    -------
    Callable[[str], Tile]
        A factory that accepts a tile name and returns a `Tile` with no
        ports, no BELs, and files rooted under `tmp_path`.
    """

    def _create(name: str) -> Tile:
        return Tile(name, [], [], tmp_path, tmp_path / f"{name}.list", [], False)

    return _create


@pytest.fixture
def default_fabric(mocker: MockerFixture) -> Fabric:
    """Create a Fabric instance with given parameters."""
    fabric = mocker.create_autospec(Fabric, spec_set=False)
    fabric.frameBitsPerRow = 32
    fabric.maxFramesPerCol = 20
    fabric.name = "DefaultFabric"
    return fabric


@pytest.fixture
def default_tile(mocker: MockerFixture) -> Tile:
    """Create a Tile instance with given parameters."""
    tile = mocker.create_autospec(Tile, spec_set=False)
    tile.name = "DefaultTile"
    tile.globalConfigBits = 127
    return tile


def find_switch_matrix_tile(fabric: Fabric) -> Tile:
    """Return the first fabric tile whose switch matrix is parseable.

    Tiles whose `matrixDir` is a `.list` or `.csv` file drive the real
    switch-matrix generation path; Verilog/VHDL matrix files are skipped.

    Parameters
    ----------
    fabric : Fabric
        The parsed fabric to search.

    Returns
    -------
    Tile
        The first tile with a `.list` or `.csv` switch matrix.

    Raises
    ------
    ValueError
        If no tile has a parseable switch matrix.
    """
    for tile in fabric.tileDic.values():
        if tile.matrixDir.suffix in (".list", ".csv"):
            return tile
    raise ValueError("no tile with a parseable switch matrix in fabric")


@pytest.fixture
def parsed_default_fabric(project: Path) -> Fabric:
    """Parse the default project fabric through the real parser stack.

    Unlike `default_fabric`, this returns a fully parsed `Fabric` with real
    tiles, ports and switch matrices, suitable for exercising generation end
    to end.

    Parameters
    ----------
    project : Path
        Temp directory of a freshly created default project.

    Returns
    -------
    Fabric
        The parsed fabric of the default project.
    """
    init_context(project)
    return parseFabricCSV(str(project / "fabric.csv"))


@pytest.fixture
def switch_matrix_tile(parsed_default_fabric: Fabric) -> Tile:
    """Return a default-project tile with a parseable switch matrix."""
    return find_switch_matrix_tile(parsed_default_fabric)


@pytest.fixture(
    params=[
        FabricConfig(
            frame_bits_per_row=32, max_frames_per_col=20, name="StandardFabric"
        ),
        FabricConfig(frame_bits_per_row=8, max_frames_per_col=5, name="SmallFabric"),
        FabricConfig(frame_bits_per_row=1, max_frames_per_col=1, name="MinimalFabric"),
        FabricConfig(frame_bits_per_row=1, max_frames_per_col=64, name="ThinFabric"),
        FabricConfig(frame_bits_per_row=64, max_frames_per_col=1, name="WideFabric"),
        FabricConfig(frame_bits_per_row=5, max_frames_per_col=7, name="IrregularSmall"),
        FabricConfig(
            frame_bits_per_row=33, max_frames_per_col=21, name="IrregularLarge"
        ),
        FabricConfig(frame_bits_per_row=7, max_frames_per_col=13, name="PrimeFabric"),
        FabricConfig(
            frame_bits_per_row=256, max_frames_per_col=100, name="VeryLargeFabric"
        ),
    ],
    ids=lambda config: config.name,
)
def fabric_config(request: pytest.FixtureRequest, mocker: MockerFixture) -> Fabric:
    """Parametric fabric configurations for testing different scenarios."""
    config = request.param
    fabric = mocker.create_autospec(Fabric, spec_set=False)
    fabric.frameBitsPerRow = config.frame_bits_per_row
    fabric.maxFramesPerCol = config.max_frames_per_col
    fabric.name = config.name
    return fabric


@pytest.fixture(
    params=[
        TileConfig("StandardTile", 16),
        TileConfig("EmptyTile", 0),
        TileConfig("MinimalTile", 1),
        TileConfig("MaxTile", 256),
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


def create_config_csv(file_path: Path, data: list[dict]) -> None:
    """Create config memory CSV files from dictionary data.

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
    """Verify CSV content and return parsed data.

    Parameters
    ----------
    file_path : Path
        The path to the CSV file to verify
    expected_rows : int | None, optional
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


def create_switchmatrix_list(
    file_path: Path,
    connections: list[tuple[str, str]] | None = None,
) -> None:
    """Create a valid .list switch matrix file for testing.

    Parameters
    ----------
    file_path : Path
        The path where the .list file should be created
    connections : list[tuple[str, str]] | None
        List of (source, destination) connection pairs.
        Defaults to [("N1BEG0", "E1END0")]
    """
    connections = connections or [("N1BEG0", "E1END0")]
    lines = [f"{src},{dst}" for src, dst in connections]
    file_path.write_text("\n".join(lines) + "\n")


def create_switchmatrix_csv(
    file_path: Path,
    tile_name: str,
    destinations: list[str] | None = None,
    sources: list[str] | None = None,
) -> None:
    """Create a valid .csv switch matrix file for testing.

    Parameters
    ----------
    file_path : Path
        The path where the CSV file should be created
    tile_name : str
        The name of the tile (used as the top-left cell value)
    destinations : list[str] | None
        List of destination port names. Defaults to ["DEST0"]
    sources : list[str] | None
        List of source port names. Defaults to ["SRC0"]
    """
    destinations = destinations or ["DEST0"]
    sources = sources or ["SRC0"]

    lines = [f"{tile_name}," + ",".join(destinations)]
    for src in sources:
        lines.append(f"{src}," + ",".join(["1"] * len(destinations)))

    file_path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def connections_factory() -> Callable[..., dict[str, list[str]]]:
    """Factory fixture for creating switch matrix connection dictionaries.

    Returns a factory function that creates connection dictionaries with
    configurable complexity.

    Usage:
        connections = connections_factory()  # minimal
        connections = connections_factory(size="sample")  # typical config
        connections = connections_factory(custom={"OUT": ["IN1", "IN2"]})
    """

    def _create(
        size: str = "minimal",
        custom: dict[str, list[str]] | None = None,
    ) -> dict[str, list[str]]:
        if custom is not None:
            return custom

        if size == "minimal":
            return {"E1END0": ["N1BEG0"]}

        if size == "sample":
            return {
                "E1END0": ["N1BEG0", "O_A"],
                "E1END1": ["N1BEG1", "O_B", "VCC", "GND"],
                "LUT_A": ["N1BEG0"],
                "LUT_B": ["N1BEG1", "VCC"],
                "O_A": ["FF_D"],
                "GND": ["0"],
                "VCC": ["1"],
            }

        return {"E1END0": ["N1BEG0"]}

    return _create


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

        poss = list(
            itertools.product(
                range(fabric.maxFramesPerCol), range(fabric.frameBitsPerRow + 1)
            )
        )
        shuffle(poss)
        config_final = poss[: tile.globalConfigBits]

        def generate_mask(bits_used: int, total_bits: int) -> str:
            """Generate a random bit mask with specified number of '1's and '0's.

            Parameters
            ----------
            bits_used : int
                Number of bits that should be set to '1'.
            total_bits : int
                Total length of the bit mask.

            Returns
            -------
            str
                Random bit mask string with bits_used '1's and remaining '0's.
            """
            if bits_used == 0:
                return "0" * total_bits
            if bits_used >= total_bits:
                return "1" * total_bits

            mask_bits = ["1"] * bits_used + ["0"] * (total_bits - bits_used)
            shuffle(mask_bits)

            return "".join(mask_bits)

        configmems = []
        total_bits_assigned = 0

        frame_groups = {}
        for frame_index, bits_in_frame in config_final:
            if frame_index not in frame_groups:
                frame_groups[frame_index] = []
            frame_groups[frame_index].append(bits_in_frame)

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
    """Create code generators with temporary output files."""

    def _create_generator(extension: str, name: str = "test_output") -> CodeGenerator:
        from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
            VerilogCodeGenerator,
        )
        from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
            VHDLCodeGenerator,
        )

        output_file = tmp_path / f"{name}{extension}"

        if extension == ".v":
            writer = VerilogCodeGenerator()
            writer.outFileName = output_file
            return writer
        if extension == ".vhd":
            writer = VHDLCodeGenerator()
            writer.outFileName = output_file
            return writer
        raise ValueError(f"Unsupported extension: {extension}")

    return _create_generator


@pytest.fixture
def cocotb_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable:
    """Create cocotb runners for RTL simulation."""

    def _create_runner(
        sources: list[Path],
        hdl_top_level: str,
        test_module_path: Path,
        plusargs: list[str] | None = None,
        testcase: str | None = None,
    ) -> None:
        lang = set([i.suffix for i in sources])

        if len(lang) > 1:
            raise ValueError("All source files must have the same HDL language suffix")

        hdl_toplevel_lang = lang.pop()
        if hdl_toplevel_lang == ".v":
            sim, test_lang = "icarus", "verilog"
        elif hdl_toplevel_lang in {".vhd", ".vhdl"}:
            test_lang = "vhdl"
            if shutil.which("nvc") is not None:
                sim = "nvc"
            elif shutil.which("ghdl") is not None:
                sim = "ghdl"
                hdl_top_level = hdl_top_level.lower()
            else:
                raise RuntimeError("No VHDL simulator available: install nvc or ghdl.")
        else:
            raise ValueError(f"Unsupported HDL language: {hdl_toplevel_lang}")
        runner = get_runner(sim)

        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)

        shutil.copy(test_module_path, test_dir / test_module_path.name)

        # cocotb_tools.runner exports the parent's sys.path to the simulator
        # subprocess as PYTHONPATH; prepend test_dir so the copied test module
        # imports as a top-level module by its stem.
        monkeypatch.syspath_prepend(str(test_dir))

        build_dir = tmp_path / "cocotb_build"
        build_kwargs: dict = {
            "sources": sources,
            "hdl_toplevel": hdl_top_level,
            "always": True,
            "build_dir": build_dir,
        }
        if test_lang == "verilog":
            build_kwargs["timescale"] = ("1ps", "1ps")
        elif sim == "nvc":
            build_kwargs["build_args"] = [
                "--std=2008",
                "-H",
                "2g",
                "-M",
                "1g",
                "--ieee-warnings=off",
            ]
        runner.build(**build_kwargs)

        if sim == "ghdl":
            for file in build_dir.iterdir():
                if file.is_file():
                    shutil.copy(file, test_dir / file.name)

        runner.test(
            hdl_toplevel=hdl_top_level,
            hdl_toplevel_lang=test_lang,
            test_module=test_module_path.stem,
            plusargs=plusargs or [],
            testcase=testcase,
        )

    return _create_runner


class Netlist:
    """Connectivity view over a Yosys-elaborated design.

    Wraps a `YosysJson` so `gen_*` tests can assert that generated RTL
    is _wired_ correctly, not merely that the right identifiers appear in the
    text. Two terminals are electrically connected iff they share Yosys net IDs,
    so a signal bound to the wrong net (undeclared or truncated) fails.

    Terminals are addressed by name: top-level ports by port name, sub-instance
    pins by `(instance_name, port_name)`. Net IDs come back as plain `int`
    lists (one per bit); equal lists mean the same physical net.
    """

    def __init__(self, yj: YosysJson) -> None:
        self.yj = yj
        self.top_name, self.top = yj.getTopModule()

    def port_net(self, name: str) -> list[int]:
        """Net IDs bound to top-level port `name`."""
        return list(self.top.ports[name].bits)

    def cell_net(self, instance: str, port: str) -> list[int]:
        """Net IDs on `port` of sub-instance `instance`."""
        return list(self.top.cells[instance].connections[port])

    def port_names(self) -> set[str]:
        """Names of every top-level port."""
        return set(self.top.ports)

    def cell_names(self) -> set[str]:
        """Names of every sub-instance."""
        return set(self.top.cells)

    def driver(self, bit: int) -> tuple[str, str]:
        """The `(instance, port)` driving net `bit` (`("", "z")` if undriven)."""
        return self.yj.getNetPortSrcSinks(bit)[0]

    def sinks(self, bit: int) -> list[tuple[str, str]]:
        """The `(instance, port)` terminals driven by net `bit`."""
        return self.yj.getNetPortSrcSinks(bit)[1]


class GridConnectivity:
    """Coordinate-addressed connectivity view over a 2D grid of HDL instances.

    Many FABulous generators emit a 2D array of sub-instances (supertile,
    fabric, ...). This wraps a `Netlist` so tests can address a cell by its
    `(x, y)` grid coordinate instead of by raw instance name. Cell occupancy and
    the coordinate-to-instance naming are supplied by the caller; net queries
    delegate to the wrapped `Netlist`.

    Parameters
    ----------
    netlist : Netlist
        The elaborated design to view.
    occupied : set[tuple[int, int]]
        Grid coordinates that hold an instance.
    instance_name : Callable[[int, int], str]
        Maps an occupied `(x, y)` coordinate to its instance name in `netlist`.
    coord_pattern : str
        Regex with two capture groups (x, y) used by `referenced_cells` to read
        coordinates back out of instance and port names. Default
        `X(\\d+)Y(\\d+)` matches the FABulous `X#Y#` naming convention.
    """

    def __init__(
        self,
        netlist: Netlist,
        occupied: set[tuple[int, int]],
        instance_name: Callable[[int, int], str],
        coord_pattern: str = r"X(\d+)Y(\d+)",
    ) -> None:
        self.netlist = netlist
        self._occupied = occupied
        self._instance_name = instance_name
        self._coord_re = re.compile(coord_pattern)

    @property
    def occupied(self) -> set[tuple[int, int]]:
        """Grid coordinates that hold an instance."""
        return self._occupied

    def exists(self, x: int, y: int) -> bool:
        """Whether grid cell `(x, y)` holds an instance."""
        return (x, y) in self._occupied

    def cell_net(self, x: int, y: int, port: str) -> list[int]:
        """Net IDs on `port` of the instance at grid cell `(x, y)`."""
        return self.netlist.cell_net(self._instance_name(x, y), port)

    def top_port_net(self, name: str) -> list[int]:
        """Net IDs bound to the top-level boundary port `name`."""
        return self.netlist.port_net(name)

    def top_port_names(self) -> set[str]:
        """Names of every top-level boundary port."""
        return self.netlist.port_names()

    def driver(self, bit: int) -> tuple[str, str]:
        """The `(instance, port)` driving net `bit`."""
        return self.netlist.driver(bit)

    def sinks(self, bit: int) -> list[tuple[str, str]]:
        """The `(instance, port)` terminals driven by net `bit`."""
        return self.netlist.sinks(bit)

    def referenced_cells(self) -> set[tuple[int, int]]:
        """Grid coordinates named by any instance or top-level port.

        A correctly built grid never names an empty cell, so a hole leaking
        into the interface surfaces here as a coordinate outside `occupied`.
        """
        coords: set[tuple[int, int]] = set()
        for name in self.netlist.cell_names() | self.netlist.port_names():
            if m := self._coord_re.search(name):
                coords.add((int(m.group(1)), int(m.group(2))))
        return coords


@pytest.fixture
def elaborate(tmp_path: Path) -> Callable[..., Netlist]:
    """Elaborate generated HDL with Yosys and return a `Netlist`.

    Pass either raw Verilog text (written to a temp `.v`) or a `Path` to an
    existing source file. Skips when Yosys is unavailable, so suites still run
    outside the Nix toolchain; under the Nix shell it gives real netlist-level
    connectivity checks reusable across `gen_*` tests.
    """
    if shutil.which(str(get_context().yosys_path)) is None:
        pytest.skip("yosys not on PATH; connectivity checks need the Nix toolchain")

    def _elaborate(source: str | Path, name: str = "dut") -> Netlist:
        if isinstance(source, Path):
            path = source
        else:
            path = tmp_path / f"{name}.v"
            path.write_text(source)
        return Netlist(YosysJson(path))

    return _elaborate
