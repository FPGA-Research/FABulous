"""Connectivity tests for `generateSuperTile` RTL emission.

Every test here elaborates the generated supertile with Yosys (via
`YosysJson`) and checks the _netlist_, not the RTL text. Two terminals are
connected iff they share Yosys net IDs, so a signal that merely appears in the
RTL but is wired to the wrong net (undeclared or truncated) fails.

A supertile wraps a 2D grid of tiles and chains their configuration and clock
signals. The directions:

- _FrameData_ flows West to East: tile `(x, y)` consumes the `FrameData_O`
  of tile `(x-1, y)`; the first column reads a boundary input port and the
  last column drives a boundary output port.
- _FrameStrobe_ and _UserCLK_ both climb from the south edge. Tile `(x, y)`
  consumes the `FrameStrobe_O` and the `UserCLKo` of the tile to its south,
  which is `(x, y - north_step)`. Every test here runs under both origins.

A tile's output is wired to a neighbour when that neighbour exists inside the
grid, otherwise to the matching supertile boundary port. Issue #875 was a
one-index error that wired the inter-column FrameData net to the wrong place;
the connectivity checks below pin the full electrical chain, holes included.

These tests need a real Yosys on `PATH` (the project's Nix toolchain). They
skip cleanly when it is absent.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import (
    IO,
    ConfigBitMode,
    Direction,
    Origin,
    Side,
)
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.gen_fabric.gen_tile import generateSuperTile
from tests.fabric_definition.conftest import make_empty_tile
from tests.fabric_gen_test.conftest import GridConnectivity, Netlist


def grid(rows: int, cols: int) -> list[list[Tile]]:
    """Build a fully-populated `rows` x `cols` tile grid."""
    return [[make_empty_tile(f"T_X{x}Y{y}") for x in range(cols)] for y in range(rows)]


def shape(layout: list[str]) -> list[list[Tile | None]]:
    """Build a tileMap from ASCII art: `#` is a tile, `.` is an empty cell.

    All rows must be the same length (a rectangular bounding box with holes).
    """
    return [
        [
            make_empty_tile(f"T_X{x}Y{y}") if cell == "#" else None
            for x, cell in enumerate(row)
        ]
        for y, row in enumerate(layout)
    ]


# Non-rectangular layouts (bounding box with holes). These exercise boundary
# detection on every interior and exterior edge far more than a full grid.
SHAPES = {
    "I_vertical": ["#", "#", "#"],
    "I_horizontal": ["###"],
    "L": ["#..", "#..", "###"],
    "T": ["###", ".#.", ".#."],
    "C": ["###", "#..", "###"],
    "U": ["#.#", "#.#", "###"],
    "O_ring": ["###", "#.#", "###"],
    "S": [".##", ".#.", "##."],
    "Z": ["##.", ".#.", ".##"],
    "plus": [".#.", "###", ".#."],
    "staircase": ["#..", "##.", ".##"],
}


def _tile_stub(tile: Tile) -> str:
    """Emit a body-less module matching `tile`'s wrapper-facing interface.

    Yosys needs each instantiated sub-tile defined so it can resolve the
    hierarchy and assign net IDs to every instance port. The body is empty on
    purpose, since the tests check how the wrapper wires instances together, not
    what a tile does internally. Port set / widths mirror what
    `generateSuperTile` connects (FrameBitsPerRow=32, MaxFramesPerCol=20).
    """
    decls: list[str] = []
    for p in (
        tile.getNorthSidePorts()
        + tile.getEastSidePorts()
        + tile.getWestSidePorts()
        + tile.getSouthSidePorts()
    ):
        width = (abs(p.x_offset) + abs(p.y_offset)) * p.wire_count - 1
        direction = "input" if p.io_direction == IO.INPUT else "output"
        decls.append(f"    {direction} [{width}:0] {p.name}")
    for bel in tile.bels:
        decls += [f"    input {p}" for p in bel.externalInput]
        decls += [f"    output {p}" for p in bel.externalOutput]
    decls += [
        "    input  UserCLK",
        "    output UserCLKo",
        "    output [19:0] FrameStrobe_O",
        "    input  [31:0] FrameData",
        "    input  [19:0] FrameStrobe",
        "    output [31:0] FrameData_O",
    ]
    body = ",\n".join(decls)
    return (
        f"\nmodule {tile.name} #(parameter [639:0] Emulate_Bitstream=640'b0) (\n"
        f"{body}\n);\nendmodule\n"
    )


def supertile_grid(
    netlist: Netlist, tileMap: list[list[Tile | None]]
) -> GridConnectivity:
    """Wrap an elaborated supertile in the generic `GridConnectivity` facade.

    Supplies the supertile's `Tile_X{x}Y{y}_<name>` instance naming and derives
    cell occupancy from `tileMap`. The `Tile_X#Y#_` coordinate pattern keeps the
    phantom-cell check from matching BEL or boundary ports that lack it.
    """
    occupied = {
        (x, y)
        for y, row in enumerate(tileMap)
        for x in range(len(row))
        if tileMap[y][x] is not None
    }

    def instance_name(x: int, y: int) -> str:
        return f"Tile_X{x}Y{y}_{tileMap[y][x].name}"

    return GridConnectivity(
        netlist,
        occupied=occupied,
        instance_name=instance_name,
        coord_pattern=r"Tile_X(\d+)Y(\d+)_",
    )


@pytest.fixture(params=list(Origin), ids=lambda o: o.value)
def origin(request: pytest.FixtureRequest) -> Origin:
    """Run every connectivity test under both coordinate origins."""
    return request.param


@pytest.fixture
def north_step(origin: Origin) -> int:
    """Return the tileMap y increment that moves one sub-tile north."""
    return 1 if origin is Origin.BOTTOM_LEFT else -1


@pytest.fixture
def supertile_netlist(
    elaborate: Callable[..., Netlist], tmp_path: Path, origin: Origin
) -> Callable[..., GridConnectivity]:
    """Render a supertile (plus stub sub-tiles) and elaborate it with Yosys."""

    def _build(tileMap: list[list[Tile | None]], **kwargs: object) -> GridConnectivity:
        tiles = [t for row in tileMap for t in row if t is not None]
        st = SuperTile(
            name="ST", tileDir=Path(), tiles=tiles, tileMap=tileMap, origin=origin
        )
        out = tmp_path / "ST.v"
        writer = VerilogCodeGenerator()
        writer.outFileName = out
        generateSuperTile(writer, st, **kwargs)
        text = out.read_text()
        for tile in {t.name: t for t in tiles}.values():
            text += _tile_stub(tile)
        return supertile_grid(elaborate(text, name="ST"), tileMap)

    return _build


# (1, 1) is the degenerate single-tile supertile: a normal tile is exactly this
# case, so the config/clock chain must wire every terminal straight to a boundary
# port (no neighbours, no internal nets). See TestSingleTile for the explicit
# equivalence contract.
GRIDS = [(1, 1), (1, 2), (2, 2), (5, 2), (3, 3)]


class TestConfigChainConnectivity:
    """Each tile's config/clock terminals tie to the correct neighbour or port."""

    def _check(
        self,
        net: GridConnectivity,
        tileMap: list[list[Tile | None]],
        north_step: int,
    ) -> None:
        for y in range(len(tileMap)):
            for x in range(len(tileMap[y])):
                if not net.exists(x, y):
                    continue

                # FrameData flows West->East.
                fd_in = net.cell_net(x, y, "FrameData")
                if net.exists(x - 1, y):
                    assert fd_in == net.cell_net(x - 1, y, "FrameData_O")
                else:
                    assert fd_in == net.top_port_net(f"Tile_X{x}Y{y}_FrameData")

                fd_out = net.cell_net(x, y, "FrameData_O")
                if net.exists(x + 1, y):
                    assert fd_out == net.cell_net(x + 1, y, "FrameData")
                else:
                    assert fd_out == net.top_port_net(f"Tile_X{x}Y{y}_FrameData_O")

                # FrameStrobe climbs from the south edge, so a tile's producer
                # is its south neighbour under either origin.
                south, north = y - north_step, y + north_step
                fs_in = net.cell_net(x, y, "FrameStrobe")
                if net.exists(x, south):
                    assert fs_in == net.cell_net(x, south, "FrameStrobe_O")
                else:
                    assert fs_in == net.top_port_net(f"Tile_X{x}Y{y}_FrameStrobe")

                fs_out = net.cell_net(x, y, "FrameStrobe_O")
                if net.exists(x, north):
                    assert fs_out == net.cell_net(x, north, "FrameStrobe")
                else:
                    assert fs_out == net.top_port_net(f"Tile_X{x}Y{y}_FrameStrobe_O")

                # UserCLK climbs from the south edge too, so a tile's clock
                # producer is its south neighbour and its sink the north one.
                clk_in = net.cell_net(x, y, "UserCLK")
                if net.exists(x, south):
                    assert clk_in == net.cell_net(x, south, "UserCLKo")
                else:
                    assert clk_in == net.top_port_net(f"Tile_X{x}Y{y}_UserCLK")

                clk_out = net.cell_net(x, y, "UserCLKo")
                if net.exists(x, north):
                    assert clk_out == net.cell_net(x, north, "UserCLK")
                else:
                    assert clk_out == net.top_port_net(f"Tile_X{x}Y{y}_UserCLKo")

    @pytest.mark.parametrize(("rows", "cols"), GRIDS)
    def test_rectangular_grids(
        self,
        supertile_netlist: Callable[..., GridConnectivity],
        rows: int,
        cols: int,
        north_step: int,
    ) -> None:
        tileMap = grid(rows, cols)
        self._check(supertile_netlist(tileMap), tileMap, north_step)

    @pytest.mark.parametrize("name", sorted(SHAPES))
    def test_irregular_shapes(
        self,
        supertile_netlist: Callable[..., GridConnectivity],
        name: str,
        north_step: int,
    ) -> None:
        tileMap = shape(SHAPES[name])
        self._check(supertile_netlist(tileMap), tileMap, north_step)


class TestCrossBoundaryDriverSinks:
    """The library's driver/sink API confirms cross-tile nets, bit by bit."""

    def test_cross_column_framedata_net(
        self, supertile_netlist: Callable[..., GridConnectivity]
    ) -> None:
        # The column-0 -> column-1 FrameData net is the exact path issue #875
        # broke. Check every bit: the bug truncated the 32-bit bus to a 1-bit
        # implicit net, so the upper bits resolved to constants, not the driver.
        net = supertile_netlist(grid(1, 2))
        fd_out = net.cell_net(0, 0, "FrameData_O")
        assert len(fd_out) == 32

        for bit in fd_out:
            assert net.driver(bit) == ("Tile_X0Y0_T_X0Y0", "FrameData_O")
            assert ("Tile_X1Y0_T_X1Y0", "FrameData") in net.sinks(bit)

    def test_cross_row_framestrobe_net(
        self, supertile_netlist: Callable[..., GridConnectivity], north_step: int
    ) -> None:
        """The strobe climbs from the south row to the north one."""
        net = supertile_netlist(grid(2, 1))
        south, north = (0, 1) if north_step == 1 else (1, 0)
        fs_out = net.cell_net(0, south, "FrameStrobe_O")
        assert len(fs_out) == 20

        for bit in fs_out:
            assert net.driver(bit) == (
                f"Tile_X0Y{south}_T_X0Y{south}",
                "FrameStrobe_O",
            )
            assert (f"Tile_X0Y{north}_T_X0Y{north}", "FrameStrobe") in net.sinks(bit)


class TestNoPhantomCells:
    """Holes must never leak a phantom tile into the generated interface."""

    @pytest.mark.parametrize("name", sorted(SHAPES))
    def test_only_occupied_cells_are_referenced(
        self, supertile_netlist: Callable[..., GridConnectivity], name: str
    ) -> None:
        tileMap = shape(SHAPES[name])
        net = supertile_netlist(tileMap)

        # Exact equality: every occupied cell is named, and no hole leaks in.
        assert net.referenced_cells() == net.occupied


class TestClockMode:
    """`disable_user_clk` drops the clock network from the interface."""

    def test_disable_user_clk_removes_clock_ports(
        self, supertile_netlist: Callable[..., GridConnectivity]
    ) -> None:
        net = supertile_netlist(grid(2, 2), disable_user_clk=True)
        assert not any("UserCLK" in p for p in net.top_port_names())
        # The config chain is unaffected: column 0 still feeds column 1.
        assert net.cell_net(0, 0, "FrameData_O") == net.cell_net(1, 0, "FrameData")


class TestConfigBitMode:
    """`FLIPFLOP_CHAIN` has no frame-based configuration interface."""

    def test_flipflop_chain_has_no_frame_ports(
        self, supertile_netlist: Callable[..., GridConnectivity]
    ) -> None:
        net = supertile_netlist(
            grid(1, 2), config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN
        )
        assert not any("FrameData" in p for p in net.top_port_names())
        assert not any("FrameStrobe" in p for p in net.top_port_names())


class TestBelExternalPorts:
    """BEL external IO is wired straight through to the supertile boundary."""

    def test_external_bel_ports_connect_to_boundary(
        self, supertile_netlist: Callable[..., GridConnectivity]
    ) -> None:
        bel = Bel(
            src=Path("MyBel.v"),
            prefix="",
            module_name="MyBel",
            internal=[],
            external=[("io_in", IO.INPUT), ("io_out", IO.OUTPUT)],
            configPort=[],
            sharedPort=[],
            configBit=0,
            belMap={},
            userCLK=False,
            ports_vectors={},
            carry={},
            localShared={},
        )
        tile = Tile(
            name="BelTile",
            ports=[],
            bels=[bel],
            tileDir=Path(),
            switch_matrix=SwitchMatrix(matrix_file=Path(), connections={}),
            gen_ios=[],
            userCLK=False,
        )
        net = supertile_netlist([[tile]])

        assert net.top_port_net("io_in") == net.cell_net(0, 0, "io_in")
        assert net.cell_net(0, 0, "io_out") == net.top_port_net("io_out")


class TestInterTileRouting:
    """Routing outputs on an inner edge reach the neighbouring tile's input."""

    def test_inner_edge_output_reaches_neighbour(
        self, supertile_netlist: Callable[..., GridConnectivity]
    ) -> None:
        # Left tile drives a 2-wide East-going bus out of its east side; the
        # right tile reads it in on its west side.
        left = Tile(
            name="Left",
            ports=[
                TilePort(
                    name="E_out",
                    io_direction=IO.OUTPUT,
                    width=2,
                    side_of_tile=Side.EAST,
                    wire_direction=Direction.EAST,
                    source_name="E_out",
                    x_offset=1,
                    y_offset=0,
                    destination_name="E_out",
                    wire_count=2,
                )
            ],
            bels=[],
            tileDir=Path(),
            switch_matrix=SwitchMatrix(matrix_file=Path(), connections={}),
            gen_ios=[],
            userCLK=False,
        )
        right = Tile(
            name="Right",
            ports=[
                TilePort(
                    name="E_in",
                    io_direction=IO.INPUT,
                    width=2,
                    side_of_tile=Side.WEST,
                    wire_direction=Direction.EAST,
                    source_name="E_in",
                    x_offset=1,
                    y_offset=0,
                    destination_name="E_in",
                    wire_count=2,
                )
            ],
            bels=[],
            tileDir=Path(),
            switch_matrix=SwitchMatrix(matrix_file=Path(), connections={}),
            gen_ios=[],
            userCLK=False,
        )
        net = supertile_netlist([[left, right]])

        e_out = net.cell_net(0, 0, "E_out")
        assert len(e_out) == 2
        assert e_out == net.cell_net(1, 0, "E_in")


class TestSingleTile:
    """A single-tile supertile is a transparent wrapper around one tile.

    This pins the invariant the planned `Tile`/`SuperTile` unification relies on:
    a normal tile is a 1x1 supertile. With no neighbours, every config/clock
    terminal must surface straight to a same-named boundary port, the wrapper
    must declare no internal cross-tile nets, and the single occupant is the only
    referenced cell.
    """

    # (terminal port, boundary suffix, expected bit width); UserCLK* are scalar.
    CONFIG_CLOCK_PORTS = [
        ("FrameData", "FrameData", 32),
        ("FrameData_O", "FrameData_O", 32),
        ("FrameStrobe", "FrameStrobe", 20),
        ("FrameStrobe_O", "FrameStrobe_O", 20),
        ("UserCLK", "UserCLK", 1),
        ("UserCLKo", "UserCLKo", 1),
    ]

    def test_every_terminal_reaches_boundary(
        self, supertile_netlist: Callable[..., GridConnectivity]
    ) -> None:
        net = supertile_netlist(grid(1, 1))

        for port, suffix, width in self.CONFIG_CLOCK_PORTS:
            cell = net.cell_net(0, 0, port)
            assert len(cell) == width
            assert cell == net.top_port_net(f"Tile_X0Y0_{suffix}")

    def test_no_internal_nets_or_phantom_cells(
        self, supertile_netlist: Callable[..., GridConnectivity]
    ) -> None:
        net = supertile_netlist(grid(1, 1))
        assert net.referenced_cells() == {(0, 0)}
