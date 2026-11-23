"""Tests for how a BEL's external vector ports are exported from the fabric.

A BEL with the `VECTOR_PORTS` attribute exports an external vector port as one
vector port of the tile and of the fabric. Without the attribute the port is
exported one bit at a time. Every test runs both ways, with the pad BEL of
`make_pad_bel`: `DI[3:0]` and `EN` are inputs, `DO[3:0]` is an output.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.custom_exception import InvalidSwitchMatrixDefinition
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import (
    SwitchMatrix,
    switch_matrix_signal_order,
)
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_fabric import generateFabric
from fabulous.fabric_generator.gen_fabric.gen_tile import (
    generateSuperTile,
    generateTile,
)
from fabulous.fabric_generator.gen_fabric.gen_top_wrapper import generateTopWrapper
from fabulous.geometry_generator.bel_geometry import BelGeometry
from tests.conftest import make_empty_tile, make_fabric_from_grid, make_pad_bel
from tests.fabric_gen_test.conftest import create_switchmatrix_list


def squash(text: str) -> str:
    """Collapse runs of whitespace, so assertions ignore the code layout."""
    return re.sub(r"\s+", " ", text)


def stub_entity(path: Path, name: str) -> None:
    """Write a VHDL file holding an empty entity, for component declarations."""
    path.write_text(f"entity {name} is\nend entity {name};\n")


def make_pad_tile(tmp_path: Path, keep_vector_ports: bool, name: str = "PAD") -> Tile:
    """Build a tile under `tmp_path` whose only BEL is the pad BEL."""
    tile = make_empty_tile(
        name,
        tileDir=tmp_path / f"{name}.csv",
        matrixDir=tmp_path / f"{name}_switch_matrix.list",
        pinOrderConfig={},
    )
    tile.bels = [make_pad_bel(keep_vector_ports)]
    return tile


@pytest.mark.parametrize(
    ("extension", "keep_vector_ports", "expected"),
    [
        pytest.param(
            ".v",
            False,
            [
                "input A_DI0, input A_DI1, input A_DI2, input A_DI3, input A_EN, "
                "output A_DO0, output A_DO1, output A_DO2, output A_DO3,",
                ".DI({A_DI3, A_DI2, A_DI1, A_DI0}), .EN(A_EN), "
                ".DO({A_DO3, A_DO2, A_DO1, A_DO0})",
            ],
            id="verilog_split",
        ),
        pytest.param(
            ".v",
            True,
            [
                "input [3:0] A_DI, input A_EN, output [3:0] A_DO,",
                ".DI(A_DI), .EN(A_EN), .DO(A_DO)",
            ],
            id="verilog_vector_ports",
        ),
        pytest.param(
            ".vhd",
            False,
            [
                "A_DI3 : in STD_LOGIC; A_EN : in STD_LOGIC; A_DO0 : out STD_LOGIC;",
                "DI(3) => A_DI3, DI(2) => A_DI2, DI(1) => A_DI1, DI(0) => A_DI0, "
                "EN => A_EN, DO(3) => A_DO3,",
            ],
            id="vhdl_split",
        ),
        pytest.param(
            ".vhd",
            True,
            [
                "A_DI : in STD_LOGIC_VECTOR( 3 downto 0 ); A_EN : in STD_LOGIC; "
                "A_DO : out STD_LOGIC_VECTOR( 3 downto 0 );",
                "DI => A_DI, EN => A_EN, DO => A_DO",
            ],
            id="vhdl_vector_ports",
        ),
    ],
)
def test_tile_ports_and_bel_instance(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    extension: str,
    keep_vector_ports: bool,
    expected: list[str],
) -> None:
    """The tile declares the external ports and connects them to the BEL."""
    tile = make_pad_tile(tmp_path, keep_vector_ports)
    if extension == ".vhd":
        stub_entity(tmp_path / "Pads.vhdl", "Pads")
        stub_entity(tmp_path / "PAD_switch_matrix.vhdl", "PAD_switch_matrix")
        tile.bels[0].src = tmp_path / "Pads.vhdl"

    writer = code_generator_factory(extension, "PAD")
    generateTile(writer, tile)
    rtl = squash(writer.outFileName.read_text())

    for fragment in expected:
        assert fragment in rtl


@pytest.mark.parametrize(
    ("keep_vector_ports", "expected"),
    [
        pytest.param(
            False,
            [
                "input SUPER_DI0, input SUPER_DI1,",
                ".DI({SUPER_DI3, SUPER_DI2, SUPER_DI1, SUPER_DI0}), .EN(SUPER_EN), "
                ".DO({SUPER_DO3, SUPER_DO2, SUPER_DO1, SUPER_DO0})",
            ],
            id="split",
        ),
        pytest.param(
            True,
            [
                "input [3:0] SUPER_DI, input SUPER_EN, output [3:0] SUPER_DO,",
                ".DI(SUPER_DI), .EN(SUPER_EN), .DO(SUPER_DO)",
            ],
            id="vector_ports",
        ),
    ],
)
def test_supertile_bel_ports_and_instance(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    keep_vector_ports: bool,
    expected: list[str],
) -> None:
    """A supertile-level BEL exports its external ports from the wrapper."""
    child = make_empty_tile("Child", tileDir=tmp_path, pinOrderConfig={})
    supertile = SuperTile(
        name="ST",
        tileDir=tmp_path,
        tiles=[child],
        tileMap=[[child]],
        bels=[make_pad_bel(keep_vector_ports, prefix="SUPER_")],
    )

    writer = code_generator_factory(".v", "ST")
    generateSuperTile(writer, supertile)
    rtl = squash(writer.outFileName.read_text())

    for fragment in expected:
        assert fragment in rtl


@pytest.mark.parametrize(
    ("extension", "keep_vector_ports", "expected"),
    [
        pytest.param(
            ".v",
            False,
            [
                "input Tile_X0Y1_A_DI0, //EXTERNAL input Tile_X0Y1_A_DI1, //EXTERNAL",
                "output Tile_X0Y1_A_DO3, //EXTERNAL",
                ".A_DI0(Tile_X0Y1_A_DI0), .A_DI1(Tile_X0Y1_A_DI1),",
            ],
            id="verilog_split",
        ),
        pytest.param(
            ".v",
            True,
            [
                "input [3:0] Tile_X0Y1_A_DI, //EXTERNAL input Tile_X0Y1_A_EN, "
                "//EXTERNAL output [3:0] Tile_X0Y1_A_DO, //EXTERNAL",
                ".A_DI(Tile_X0Y1_A_DI), .A_EN(Tile_X0Y1_A_EN), .A_DO(Tile_X0Y1_A_DO),",
            ],
            id="verilog_vector_ports",
        ),
        pytest.param(
            ".vhd",
            False,
            [
                "Tile_X0Y1_A_DI0 : in STD_LOGIC; -- EXTERNAL",
                "A_DI0 => Tile_X0Y1_A_DI0,",
            ],
            id="vhdl_split",
        ),
        pytest.param(
            ".vhd",
            True,
            [
                "Tile_X0Y1_A_DI : in STD_LOGIC_VECTOR( 3 downto 0 ); -- EXTERNAL",
                "Tile_X0Y1_A_DO : out STD_LOGIC_VECTOR( 3 downto 0 ); -- EXTERNAL",
                "A_DI => Tile_X0Y1_A_DI, A_EN => Tile_X0Y1_A_EN, "
                "A_DO => Tile_X0Y1_A_DO,",
            ],
            id="vhdl_vector_ports",
        ),
    ],
)
def test_fabric_ports_and_tile_instance(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    extension: str,
    keep_vector_ports: bool,
    expected: list[str],
) -> None:
    """The fabric declares the external ports and connects them to the tile."""
    tile = make_pad_tile(tmp_path, keep_vector_ports)
    fabric = make_fabric_from_grid([[None], [tile]])
    if extension == ".vhd":
        fabric.fabric_dir = tmp_path / "fabric.csv"
        (tmp_path / "Tile" / "PAD").mkdir(parents=True)
        stub_entity(tmp_path / "Tile" / "PAD" / "PAD.vhdl", "PAD")

    writer = code_generator_factory(extension, "eFPGA")
    generateFabric(writer, fabric)
    rtl = squash(writer.outFileName.read_text())

    for fragment in expected:
        assert fragment in rtl


def test_fabric_exports_supertile_bel_vector_ports(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
) -> None:
    """A supertile-level BEL's vector ports are fabric ports at the anchor."""
    child = make_empty_tile("Child", tileDir=tmp_path, pinOrderConfig={})
    child.partOfSuperTile = True
    supertile = SuperTile(
        name="ST",
        tileDir=tmp_path,
        tiles=[child],
        tileMap=[[child]],
        bels=[make_pad_bel(keep_vector_ports=True, prefix="SUPER_")],
    )
    fabric = Fabric(
        fabric_dir=tmp_path,
        tile=[[child]],
        numberOfRows=1,
        numberOfColumns=1,
        tileDic={"Child": child},
        superTileDic={"ST": supertile},
    )

    writer = code_generator_factory(".v", "eFPGA")
    generateFabric(writer, fabric)
    rtl = squash(writer.outFileName.read_text())

    assert "input [3:0] Tile_X0Y0_SUPER_DI, //EXTERNAL" in rtl
    assert "output [3:0] Tile_X0Y0_SUPER_DO, //EXTERNAL" in rtl
    assert ".SUPER_DI(Tile_X0Y0_SUPER_DI)," in rtl
    assert ".SUPER_DO(Tile_X0Y0_SUPER_DO)," in rtl


def top_wrapper_rtl(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    extension: str,
    keep_vector_ports: list[bool],
) -> str:
    """Generate `eFPGA_top` for a one-column fabric with a pad tile per row.

    Parameters
    ----------
    tmp_path : Path
        Directory the tiles and the output are rooted in.
    code_generator_factory : Callable[[str, str], CodeGenerator]
        The code generator factory fixture.
    extension : str
        `.v` or `.vhd`.
    keep_vector_ports : list[bool]
        Whether the pad BEL of each row, top to bottom, sets `VECTOR_PORTS`.

    Returns
    -------
    str
        The generated code with whitespace collapsed.
    """
    grid = [
        [make_pad_tile(tmp_path, keep, name=f"PAD{y}")]
        for y, keep in enumerate(keep_vector_ports)
    ]
    fabric = make_fabric_from_grid(grid)
    writer = code_generator_factory(extension, "eFPGA_top")
    if extension == ".vhd":
        for name in ("Frame_Data_Reg", "Frame_Select", "eFPGA_Config", "BlockRAM_1KB"):
            stub_entity(tmp_path / f"{name}.vhdl", name)
        stub_entity(tmp_path / f"{fabric.name}.vhdl", fabric.name)
    generateTopWrapper(writer, fabric)
    return squash(writer.outFileName.read_text())


def fabric_bit_connections(rtl: str) -> dict[str, str]:
    """Map every bit of the fabric's external ports to its `eFPGA_top` bit.

    A fabric vector port connected to a slice is expanded with the names its
    bits have when the port is split, so both forms give the same mapping.

    Parameters
    ----------
    rtl : str
        The Verilog code of `eFPGA_top`.

    Returns
    -------
    dict[str, str]
        `{"Tile_X0Y0_A_DI2": "A_DI[2]", ...}` for the pad BEL ports.
    """
    connections: dict[str, str] = {}
    for port, signal, msb, lsb in re.findall(
        r"\.(Tile_\w+)\((\w+)\[(\d+)(?::(\d+))?\]\)", rtl
    ):
        if lsb == "":
            connections[port] = f"{signal}[{msb}]"
            continue
        for offset in range(int(msb) - int(lsb) + 1):
            connections[f"{port}{offset}"] = f"{signal}[{int(lsb) + offset}]"
    return connections


@pytest.mark.parametrize(
    "keep_vector_ports",
    [
        pytest.param([False, False, False], id="split"),
        pytest.param([True, True, True], id="vector_ports"),
        pytest.param([True, False, True], id="mixed"),
    ],
)
def test_top_wrapper_keeps_its_ports_and_bit_order(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    keep_vector_ports: list[bool],
) -> None:
    """`eFPGA_top` has the same ports and bit order whatever the BELs opt into.

    The tiles are grouped bottom row first, each taking four bits of `A_DI`
    and `A_DO` and one bit of `A_EN`.
    """
    rtl = top_wrapper_rtl(tmp_path, code_generator_factory, ".v", keep_vector_ports)

    assert "output [11:0] A_DO, input [2:0] A_EN," in rtl
    assert "input [11:0] A_DI," in rtl
    expected: dict[str, str] = {}
    for group_index, y in enumerate([2, 1, 0]):
        expected[f"Tile_X0Y{y}_A_EN"] = f"A_EN[{group_index}]"
        for bit in range(4):
            top_bit = 4 * group_index + bit
            expected[f"Tile_X0Y{y}_A_DI{bit}"] = f"A_DI[{top_bit}]"
            expected[f"Tile_X0Y{y}_A_DO{bit}"] = f"A_DO[{top_bit}]"
    assert fabric_bit_connections(rtl) == expected


@pytest.mark.parametrize(
    ("extension", "expected"),
    [
        pytest.param(
            ".v",
            [
                ".Tile_X0Y1_A_DI(A_DI[3:0]), .Tile_X0Y0_A_DI(A_DI[7:4]),",
                ".Tile_X0Y1_A_EN(A_EN[0]), .Tile_X0Y0_A_EN(A_EN[1]),",
            ],
            id="verilog",
        ),
        pytest.param(
            ".vhd",
            [
                "A_DI : in STD_LOGIC_VECTOR( 7 downto 0 );",
                "Tile_X0Y1_A_DI => A_DI(3 downto 0), "
                "Tile_X0Y0_A_DI => A_DI(7 downto 4),",
                "Tile_X0Y1_A_EN => A_EN(0), Tile_X0Y0_A_EN => A_EN(1),",
            ],
            id="vhdl",
        ),
    ],
)
def test_top_wrapper_connects_fabric_vector_ports_by_slice(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    extension: str,
    expected: list[str],
) -> None:
    """A fabric vector port takes a slice of the grouped `eFPGA_top` port."""
    rtl = top_wrapper_rtl(tmp_path, code_generator_factory, extension, [True, True])

    for fragment in expected:
        assert fragment in rtl


@pytest.mark.parametrize(
    ("keep_vector_ports", "expected"),
    [
        pytest.param(False, ["A_DO0", "A_DO1", "A_DO2", "A_DO3"], id="split"),
        pytest.param(True, [], id="vector_ports"),
    ],
)
def test_switch_matrix_destinations(
    keep_vector_ports: bool, expected: list[str]
) -> None:
    """Only a one-bit external output is a signal the switch matrix can name."""
    _sources, dests = switch_matrix_signal_order([], [make_pad_bel(keep_vector_ports)])

    assert dests == expected


def test_switch_matrix_rejects_a_bit_of_an_external_vector_port(
    tmp_path: Path,
) -> None:
    """A matrix naming a bit of an exported vector port fails to load."""
    matrix = tmp_path / "PAD_switch_matrix.list"
    create_switchmatrix_list(matrix, [("A_DI0", "A_DO0")])

    with pytest.raises(InvalidSwitchMatrixDefinition):
        SwitchMatrix.from_file(
            matrix, "PAD", ports=[], bels=[make_pad_bel(keep_vector_ports=True)]
        )


@pytest.mark.parametrize(
    ("keep_vector_ports", "inputs", "outputs"),
    [
        pytest.param(
            False,
            ["A_DI0", "A_DI1", "A_DI2", "A_DI3", "A_EN"],
            ["A_DO0", "A_DO1", "A_DO2", "A_DO3"],
            id="split",
        ),
        pytest.param(
            True,
            ["A_DI[0]", "A_DI[1]", "A_DI[2]", "A_DI[3]", "A_EN"],
            ["A_DO[0]", "A_DO[1]", "A_DO[2]", "A_DO[3]"],
            id="vector_ports",
        ),
    ],
)
def test_bel_geometry_lists_one_external_port_per_bit(
    keep_vector_ports: bool, inputs: list[str], outputs: list[str]
) -> None:
    """The geometry keeps one port per bit, named like the tile pin."""
    geometry = BelGeometry()
    geometry.generateGeometry(make_pad_bel(keep_vector_ports), padding=8)

    assert geometry.externalInputs == inputs
    assert geometry.externalOutputs == outputs
    assert len(geometry.externalPortGeoms) == len(inputs) + len(outputs)
