"""Fabric generation module for FABulous FPGA architecture.

This module generates the top-level RTL description of an FPGA fabric, handling
tile instantiation, interconnect wiring, and configuration infrastructure. The
generated fabric uses a flat description approach for easier debugging and
verification.

Key features:
- Flat fabric instantiation with direct tile-to-tile connections
- Support for both FlipFlop chain and Frame-based configuration
- External I/O port handling for BEL connections
- Supertile support for hierarchical tile organization
- Configuration data distribution and management
"""

from collections.abc import Generator

from fabulous.fabric_definition.define import IO, ConfigBitMode, Direction
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)

# (wire direction, neighbour dx, dy) for the four fabric edges. A tile's INPUT
# ports of one direction pair with the OUTPUT ports of the same direction on the
# neighbour at the given offset, the two ends of one wire. Bottom-left origin:
# dy grows upward (north).
_SIDE_INPUT_CONNECTIONS = (
    (Direction.NORTH, 0, -1),  # north input <- south neighbour
    (Direction.EAST, -1, 0),  # east input  <- west neighbour
    (Direction.SOUTH, 0, 1),  # south input <- north neighbour
    (Direction.WEST, 1, 0),  # west input  <- east neighbour
)


def iter_composite_anchors(
    fabric: Fabric,
) -> Generator[tuple[int, int, Tile], None, None]:
    """Yield `(anchor_x, anchor_y, composite_tile)` for every composite placement.

    The anchor is the placement's bottom-left origin cell. `generateFabric`
    walks the bottom-first grid and instantiates the composite wrapper at the
    first covered cell it reaches, which is that origin, so naming the wrapper's
    external ports at the anchor keeps the declaration and the connection on the
    same cell.

    Parameters
    ----------
    fabric : Fabric
        The fabric whose grid is scanned for composite tile placements.

    Yields
    ------
    tuple[int, int, Tile]
        The anchor `(x, y)` and the composite `Tile` placed there.
    """
    for composite in fabric.get_all_unique_tiles():
        if not composite.is_composite:
            continue
        for base_fx, base_fy in fabric.find_composite_placement_origins(composite):
            yield base_fx, base_fy, composite


def _composite_cell_offsets(composite: Tile) -> list[tuple[int, int, int, int]]:
    """Return the wrapper label and fabric offset of every populated cell.

    Each entry is `(label_x, label_y, fabric_dx, fabric_dy)` where:

    - `(label_x, label_y)` is the cell's TOP-FIRST `tile_map` index. The
      composite wrapper module (`_generate_composite_tile`) names its own
      per-cell ports `Tile_X{label_x}Y{label_y}_<sig>` using this index, so any
      reference to the wrapper's OWN port must use it.
    - `(fabric_dx, fabric_dy)` is the offset of the cell within the fabric grid,
      which is stored BOTTOM row first, so `fabric_dy = composite.fabric_dy(
      label_y)`. Any reference to a fabric grid net, or any grid indexing, must
      use this offset.

    Entries are returned in fabric scan order (bottom row first, left to right)
    so they match the order in which `generateFabric` walks the grid.

    Parameters
    ----------
    composite : Tile
        The composite tile whose cells are enumerated.

    Returns
    -------
    list[tuple[int, int, int, int]]
        One `(label_x, label_y, fabric_dx, fabric_dy)` entry per populated cell.
    """
    offsets = [(x, y, x, composite.fabric_dy(y)) for (x, y), _ in composite]
    offsets.sort(key=lambda o: (o[3], o[2]))
    return offsets


def _composite_perimeter_by_offset(
    composite: Tile,
) -> dict[tuple[int, int], tuple[tuple[int, int], list]]:
    """Return each composite cell's wrapper label and perimeter ports, by offset.

    Keyed by the cell's fabric `(fabric_dx, fabric_dy)` offset so the caller can
    address the fabric grid net, the value carries both the cell's TOP-FIRST
    wrapper label index `(label_x, label_y)` (for naming the wrapper's own port)
    and its perimeter side-port lists, sourced from
    `Tile.get_ports_around_tile` so the perimeter scan itself lives in one
    place.

    Parameters
    ----------
    composite : Tile
        The composite tile whose perimeter ports are collected.

    Returns
    -------
    dict[tuple[int, int], tuple[tuple[int, int], list]]
        Mapping from `(fabric_dx, fabric_dy)` offset to
        `((label_x, label_y), perimeter_side_port_lists)`.
    """
    if composite.tile_map is None:
        return {}
    ports_by_cell = composite.get_ports_around_tile()
    result: dict[tuple[int, int], tuple[tuple[int, int], list]] = {}
    for (x, y), _ in composite:
        result[(x, composite.fabric_dy(y))] = ((x, y), ports_by_cell[f"{x},{y}"])
    return result


def generateFabric(writer: CodeGenerator, fabric: Fabric) -> None:
    """Generate the fabric.

    This function creates a flat description of the FPGA fabric by instantiating all
    tiles and connecting them based on the provided fabric definition. It handles the
    generation of top-level I/O ports, wiring between adjacent tiles, and the
    configuration infrastructure (either Frame-based or FlipFlop chain).
    """
    # we first scan all tiles if those have IOs that have to go to top
    # the order of this scan is later maintained when instantiating the actual tiles
    # header
    fabricName = fabric.name
    writer.addHeader(fabricName)
    writer.addParameterStart(indentLevel=1)
    writer.addParameter(
        "MaxFramesPerCol", "integer", fabric.maxFramesPerCol, indentLevel=2
    )
    writer.addParameter(
        "FrameBitsPerRow", "integer", fabric.frameBitsPerRow, indentLevel=2
    )
    writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is not None:
                for bel in tile.bels:
                    for i in bel.externalInput:
                        writer.addPortScalar(
                            f"Tile_X{x}Y{y}_{i}", IO.INPUT, indentLevel=2
                        )
                        writer.addComment("EXTERNAL", onNewLine=False)
                    for i in bel.externalOutput:
                        writer.addPortScalar(
                            f"Tile_X{x}Y{y}_{i}", IO.OUTPUT, indentLevel=2
                        )
                        writer.addComment("EXTERNAL", onNewLine=False)

    # supertile-level BEL external ports (the BEL lives in the wrapper, not a
    # child tile); declare them at the placement origin, which is the cell the
    # wrapper is instantiated at and whose name its port connections use.
    for ax, ay, composite in iter_composite_anchors(fabric):
        for bel in composite.bels:
            for i in bel.externalInput:
                writer.addPortScalar(f"Tile_X{ax}Y{ay}_{i}", IO.INPUT, indentLevel=2)
                writer.addComment("EXTERNAL", onNewLine=False)
            for i in bel.externalOutput:
                writer.addPortScalar(f"Tile_X{ax}Y{ay}_{i}", IO.OUTPUT, indentLevel=2)
                writer.addComment("EXTERNAL", onNewLine=False)

    if fabric.configBitMode == ConfigBitMode.FRAME_BASED:
        writer.addPortVector(
            "FrameData",
            IO.INPUT,
            f"(FrameBitsPerRow*{fabric.numberOfRows})-1",
            indentLevel=2,
        )
        writer.addComment("CONFIG_PORT", onNewLine=False)
        writer.addPortVector(
            "FrameStrobe",
            IO.INPUT,
            f"(MaxFramesPerCol*{fabric.numberOfColumns})-1",
            indentLevel=2,
        )
        writer.addComment("CONFIG_PORT", onNewLine=False)

    if not fabric.disableUserCLK:
        writer.addPortScalar("UserCLK", IO.INPUT, indentLevel=2)

    writer.addPortEnd()
    writer.addHeaderEnd(fabricName)
    writer.addDesignDescriptionStart(fabricName)
    writer.addNewLine()

    if isinstance(writer, VHDLCodeGenerator):
        # Declare a component per entity the fabric body instantiates: leaf tiles
        # and composite tiles by their own name. Sub-tiles are instantiated inside
        # the composite wrapper, not the fabric, so they are skipped.
        # Every tile HDL lives at Tile/<name>/<name>.vhdl under the project root
        # (fabric_dir is the fabric.csv, so its parent is that root). This is
        # correct for both per-tile CSVs and the legacy inline fabric.csv, where
        # every tile_dir is the fabric.csv itself rather than a per-tile directory.
        tileRoot = fabric.fabric_dir.parent / "Tile"
        for tile in fabric.tileDic.values():
            if tile.part_of_composite:
                continue
            writer.addComponentDeclarationForFile(
                str(tileRoot / tile.name / f"{tile.name}.vhdl")
            )

    # VHDL signal declarations
    writer.addComment("signal declarations", onNewLine=True, end="\n")

    if not fabric.disableUserCLK:
        for y, row in enumerate(fabric.tile):
            for x, _tile in enumerate(row):
                writer.addConnectionScalar(f"Tile_X{x}Y{y}_UserCLKo")

    writer.addComment("configuration signal declarations", onNewLine=True, end="\n")

    if fabric.configBitMode == "FlipFlopChain":
        tileCounter = 0
        for row in fabric.tile:
            for t in row:
                if t is not None:
                    tileCounter += 1
        writer.addConnectionVector("conf_data", tileCounter)

    if fabric.configBitMode == ConfigBitMode.FRAME_BASED:
        # FrameData       =>     Tile_Y3_FrameData,
        # FrameStrobe      =>     Tile_X1_FrameStrobe
        # MaxFramesPerCol : integer := 20;
        # FrameBitsPerRow : integer := 32;
        for y in range(fabric.numberOfRows):
            writer.addConnectionVector(f"Row_Y{y}_FrameData", "FrameBitsPerRow -1")

        for x in range(fabric.numberOfColumns):
            writer.addConnectionVector(
                f"Column_X{x}_FrameStrobe", "MaxFramesPerCol - 1"
            )

        for y in range(fabric.numberOfRows):
            for x in range(fabric.numberOfColumns):
                writer.addConnectionVector(
                    f"Tile_X{x}Y{y}_FrameData_O", "FrameBitsPerRow - 1"
                )

        for y in range(fabric.numberOfRows + 1):
            for x in range(fabric.numberOfColumns):
                writer.addConnectionVector(
                    f"Tile_X{x}Y{y}_FrameStrobe_O", "MaxFramesPerCol - 1"
                )

    writer.addComment("tile-to-tile signal declarations", onNewLine=True)
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is not None:
                seenPorts = set()
                for p in tile.ports_info:
                    wireLength = (abs(p.x_offset) + abs(p.y_offset)) * p.wire_count - 1
                    # JUMP ports stay inside the tile (a composite's wrapper
                    # matrix handles them), so they need no tile-to-tile wire.
                    if p.source_name == "NULL" or p.wire_direction == Direction.JUMP:
                        continue
                    if p.source_name in seenPorts:
                        continue
                    seenPorts.add(p.source_name)
                    writer.addConnectionVector(
                        f"Tile_X{x}Y{y}_{p.source_name}", wireLength
                    )
    writer.addNewLine()
    # VHDL architecture body
    writer.addLogicStart()

    # top configuration data daisy chaining
    # this is copy and paste from tile code generation
    # (so we can modify this here without side effects)
    if fabric.configBitMode == "FlipFlopChain":
        writer.addComment("configuration data daisy chaining", onNewLine=True)
        writer.addAssignScalar("conf_data'low", "CONFin")
        writer.addComment("conf_data'low=0 and CONFin is from tile entity")
        writer.addAssignScalar("CONFout", "conf_data'high")
        writer.addComment("CONFout is from tile entity")

    if fabric.configBitMode == ConfigBitMode.FRAME_BASED:
        for y in range(len(fabric.tile)):
            writer.addAssignVector(
                f"Row_Y{y}_FrameData",
                "FrameData",
                f"FrameBitsPerRow*({y}+1)-1",
                f"FrameBitsPerRow*{y}",
            )
        for x in range(len(fabric.tile[0])):
            writer.addAssignVector(
                f"Column_X{x}_FrameStrobe",
                "FrameStrobe",
                f"MaxFramesPerCol*({x}+1)-1",
                f"MaxFramesPerCol*{x}",
            )

    instantiatedPosition = []

    # Index each composite by the names of its sub-tiles so the owning composite
    # of a placed sub-tile is an O(1) lookup instead of a per-cell rescan of every
    # unique tile. `setdefault` keeps the first owner in `get_all_unique_tiles`
    # order, matching the original linear scan's break-on-first behavior.
    composite_owner_by_subtile: dict[str, Tile] = {}
    for candidate in fabric.get_all_unique_tiles():
        if not candidate.is_composite:
            continue
        for sub_tile in candidate.get_sub_tiles():
            composite_owner_by_subtile.setdefault(sub_tile.name, candidate)

    # Tile instantiations
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            # Each entry is (label_x, label_y, fabric_dx, fabric_dy): the wrapper
            # top-first label index and the fabric-grid offset of the cell.
            tileLocationOffset: list[tuple[int, int, int, int]] = []
            composite_cells = []
            composite = None
            if tile is None:
                continue

            if (x, y) in instantiatedPosition:
                continue

            # instantiate composite tile when encountered: find the composite
            # that owns this sub-tile, then map its cells to fabric offsets.
            if tile.part_of_composite:
                composite = composite_owner_by_subtile.get(tile.name)

            if composite:
                for label_x, label_y, dx, dy in _composite_cell_offsets(composite):
                    tileLocationOffset.append((label_x, label_y, dx, dy))
                    instantiatedPosition.append((x + dx, y + dy))
                    composite_cells.append((x + dx, y + dy))
            else:
                tileLocationOffset.append((0, 0, 0, 0))

            portsPairs = []
            # use the offset to find all the related tile input, output signal
            # if is a normal tile then the offset is (0, 0). `li`/`lj` are the
            # wrapper top-first label index (for the wrapper's own port name);
            # `i`/`j` are the fabric-grid offset (for grid lookups and nets).
            for li, lj, i, j in tileLocationOffset:
                here = fabric.tile[y + j][x + i]
                in_super = here.part_of_composite

                def _local_names(
                    ports: list,
                    _li: int = li,
                    _lj: int = lj,
                    in_super: bool = in_super,
                ) -> list[str]:
                    """Return local port names."""
                    return (
                        [f"Tile_X{_li}Y{_lj}_{p.name}" for p in ports]
                        if in_super
                        else [p.name for p in ports]
                    )

                # input connection from north side of the south tile
                # (NORTH-direction wires entering this tile from south fabric neighbour)
                for direction, dx, dy in _SIDE_INPUT_CONNECTIONS:
                    neighbor_x, neighbor_y = x + i + dx, y + j + dy
                    if (neighbor_x, neighbor_y) in composite_cells:
                        continue
                    localPorts = _local_names(here.ports_along(direction, IO.INPUT))
                    if (
                        0 <= neighbor_y < len(fabric.tile)
                        and 0 <= neighbor_x < len(fabric.tile[0])
                        and fabric.tile[neighbor_y][neighbor_x] is not None
                    ):
                        neighborInput = [
                            f"Tile_X{neighbor_x}Y{neighbor_y}_{p.name}"
                            for p in fabric.tile[neighbor_y][neighbor_x].ports_along(
                                direction, IO.OUTPUT
                            )
                        ]
                        portsPairs += list(zip(localPorts, neighborInput, strict=False))
                    else:
                        portsPairs += [(p, "") for p in localPorts]

            # output signal name is same as the output port name
            if composite:
                perimeter = _composite_perimeter_by_offset(composite)
                for (i, j), ((li, lj), around) in perimeter.items():
                    for ports in around:
                        for port in ports:
                            if port.is_output and port.name != "NULL":
                                portsPairs.append(
                                    (
                                        f"Tile_X{li}Y{lj}_{port.name}",
                                        f"Tile_X{x + i}Y{y + j}_{port.name}",
                                    )
                                )
            else:
                for i in tile.get_tile_output_names():
                    portsPairs.append((i, f"Tile_X{x}Y{y}_{i}"))

            writer.addNewLine()
            writer.addComment(
                "tile IO port will get directly connected to top-level tile module",
                onNewLine=True,
                indentLevel=0,
            )
            for _li, _lj, i, j in tileLocationOffset:
                for b in fabric.tile[y + j][x + i].bels:
                    for p in b.externalInput:
                        portsPairs.append((p, f"Tile_X{x + i}Y{y + j}_{p}"))

                    for p in b.externalOutput:
                        portsPairs.append((p, f"Tile_X{x + i}Y{y + j}_{p}"))

                    if not fabric.disableUserCLK:
                        for p in b.sharedPort:
                            if "UserCLK" not in p[0]:
                                portsPairs.append(("UserCLK", p[0]))

            # supertile-level BEL external ports: connect the wrapper's external
            # ports to the top-level nets declared at the placement origin, which
            # is this cell -- the first covered cell of the bottom-first scan.
            if composite:
                for b in composite.bels:
                    for p in b.externalInput:
                        portsPairs.append((p, f"Tile_X{x}Y{y}_{p}"))
                    for p in b.externalOutput:
                        portsPairs.append((p, f"Tile_X{x}Y{y}_{p}"))

            if not fabric.disableUserCLK:
                if not composite:
                    # Bottom-left origin: the user clock chains south to north,
                    # so a tile takes it from the tile to its south (y-1) and the
                    # southernmost tile takes the fabric's own UserCLK.
                    if y - 1 >= 0 and fabric.tile[y - 1][x] is not None:
                        portsPairs.append(("UserCLK", f"Tile_X{x}Y{y - 1}_UserCLKo"))
                    else:
                        portsPairs.append(("UserCLK", "UserCLK"))

                    # for userCLKo
                    portsPairs.append(("UserCLKo", f"Tile_X{x}Y{y}_UserCLKo"))
                else:
                    for li, lj, i, j in tileLocationOffset:
                        # prefix for the wrapper's own port (top-first label index)
                        pre = f"Tile_X{li}Y{lj}_"

                        # UserCLK signal
                        # Bottom-left origin: the clock arrives from the tile to
                        # the south (y-1); cells whose southern neighbour is inside
                        # the composite are chained internally instead.
                        south_row = y + j - 1
                        if south_row < 0 or fabric.tile[south_row][x + i] is None:
                            portsPairs.append((f"{pre}UserCLK", "UserCLK"))

                        elif (x + i, south_row) not in composite_cells:
                            portsPairs.append(
                                (f"{pre}UserCLK", f"Tile_X{x + i}Y{south_row}_UserCLKo")
                            )

                        # UserCLKo signal
                        # Bottom-left origin: UserCLKo goes to the tile above (y+1);
                        # expose as a port when that tile is not in the supertile.
                        if (x + i, y + j + 1) not in composite_cells:
                            portsPairs.append(
                                (f"{pre}UserCLKo", f"Tile_X{x + i}Y{y + j}_UserCLKo")
                            )

            if fabric.configBitMode == ConfigBitMode.FRAME_BASED:
                for li, lj, i, j in tileLocationOffset:
                    # prefix for the wrapper's own port (top-first label index)
                    pre = ""
                    if composite:
                        pre = f"Tile_X{li}Y{lj}_"

                    cell_x = x + i
                    cell_y = y + j

                    # Connect the FrameData port to the previous tiles'
                    # (to the west of it) FrameData_O signals.
                    # If the previous tile is NULL, continue the search.
                    # If all previous tiles are NULL, connect to the fabrics
                    # Row_Y{y}_FrameData signals.

                    done = False

                    # Get all x-positions to the west of this tile
                    for search_x in range(cell_x - 1, -1, -1):
                        # Previous tile is part of the same supertile.
                        # FrameData signals are connected internally.
                        # Stop the search and be done.
                        if (search_x, cell_y) in composite_cells:
                            done = True
                            break

                        # Previous tile is NULL, continue search
                        if fabric.tile[cell_y][search_x] is None:
                            continue

                        # Found a non-NULL tile, connect FrameData
                        portsPairs.append(
                            (
                                f"{pre}FrameData",
                                f"Tile_X{search_x}Y{cell_y}_FrameData_O",
                            )
                        )

                        done = True
                        break

                    # No non-NULL tile was found, and tile is not part of a supertile.
                    # Connect to the fabrics Row_Y{y}_FrameData signals.
                    if not done:
                        portsPairs.append(
                            (f"{pre}FrameData", f"Row_Y{cell_y}_FrameData")
                        )

                    # Connecting FrameData_O is easier:
                    # Always connect FrameData_O, except the next tile
                    # (to the east of it)
                    # in the row is part of the supertile
                    # (already connected internally).
                    if (cell_x + 1, cell_y) not in composite_cells:
                        portsPairs.append(
                            (
                                f"{pre}FrameData_O",
                                f"Tile_X{cell_x}Y{cell_y}_FrameData_O",
                            )
                        )

                    # Connect the FrameStrobe port to the previous tiles'
                    # (to the south of it) FrameStrobe_O signals.
                    # If the previous tile is NULL, continue the search.
                    # If all previous tiles are NULL, connect to the fabrics
                    # Column_X{x}_FrameStrobe signals.

                    done = False

                    # Get all y-positions to the south of this tile
                    # Note: the FrameStrobe signals come from the bottom of the
                    #       fabric (y=0), therefore count downwards
                    # Bottom-left origin: south is y-1
                    for search_y in range(cell_y - 1, -1, -1):
                        # Previous tile is part of the same supertile.
                        # FrameStrobe signals are connected internally.
                        # Stop the search and be done.
                        if (cell_x, search_y) in composite_cells:
                            done = True
                            break

                        # Previous tile is NULL, continue search
                        if fabric.tile[search_y][cell_x] is None:
                            continue

                        # Found a non-NULL tile, connect FrameStrobe
                        portsPairs.append(
                            (
                                f"{pre}FrameStrobe",
                                f"Tile_X{cell_x}Y{search_y}_FrameStrobe_O",
                            )
                        )

                        done = True
                        break

                    # No non-NULL tile was found, and tile is not part of a supertile.
                    # Connect to the fabrics Column_X{x}_FrameStrobe signals.
                    if not done:
                        portsPairs.append(
                            (
                                f"{pre}FrameStrobe",
                                f"Column_X{cell_x}_FrameStrobe",
                            )
                        )

                    # Connecting FrameStrobe_O is easier:
                    # Always connect FrameStrobe_O, except the next tile
                    # (to the north of it)
                    # in the column is part of the supertile
                    # (already connected internally).
                    # Bottom-left origin: north is y+1
                    if (cell_x, cell_y + 1) not in composite_cells:
                        portsPairs.append(
                            (
                                f"{pre}FrameStrobe_O",
                                f"Tile_X{cell_x}Y{cell_y}_FrameStrobe_O",
                            )
                        )

            name = ""
            emulateParamPairs = []
            if composite:
                name = composite.name
                for li, lj, i, j in tileLocationOffset:
                    if (y + j) not in (0, fabric.numberOfRows - 1):
                        emulateParamPairs.append(
                            (
                                f"Tile_X{li}Y{lj}_Emulate_Bitstream",
                                f"`Tile_X{x + i}Y{y + j}_Emulate_Bitstream",
                            )
                        )
            else:
                name = tile.name
                if y not in (0, fabric.numberOfRows - 1):
                    emulateParamPairs.append(
                        ("Emulate_Bitstream", f"`Tile_X{x}Y{y}_Emulate_Bitstream")
                    )
            writer.addInstantiation(
                compName=name,
                compInsName=f"Tile_X{x}Y{y}_{name}",
                portsPairs=portsPairs,
                emulateParamPairs=emulateParamPairs,
                add_keep=True,
            )
    writer.addDesignDescriptionEnd()
    writer.writeToFile()
