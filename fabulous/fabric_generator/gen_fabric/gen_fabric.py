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

from fabulous.fabric_definition.define import IO, ConfigBitMode, Direction, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)

# (local INPUT side, neighbour OUTPUT side, neighbour dx, dy) for the four fabric
# edges. A wire ends on the opposite side from where it begins, so the local
# input side and the neighbour's output side are opposites: a NORTH-direction
# wire ends on this tile's SOUTH side and begins on the south neighbour's NORTH
# side. Bottom-left origin: dy grows upward (north).
_SIDE_INPUT_CONNECTIONS = (
    (Side.SOUTH, Side.NORTH, 0, -1),  # south input <- south neighbour north output
    (Side.WEST, Side.EAST, -1, 0),  # west input <- west neighbour east output
    (Side.NORTH, Side.SOUTH, 0, 1),  # north input <- north neighbour south output
    (Side.EAST, Side.WEST, 1, 0),  # east input <- east neighbour west output
)


def iter_composite_anchors(
    fabric: Fabric,
) -> Generator[tuple[int, int, Tile], None, None]:
    """Yield ``(anchor_x, anchor_y, composite_tile)`` for every composite placement.

    The anchor is the top-left (first non-None in row-major order) cell of each
    composite placement -- the same position at which ``generateFabric``
    instantiates the composite wrapper and names its external ports.

    Parameters
    ----------
    fabric : Fabric
        The fabric whose grid is scanned for composite tile placements.

    Yields
    ------
    tuple[int, int, Tile]
        The anchor ``(x, y)`` and the composite ``Tile`` placed there.
    """
    seen: set[tuple[int, int]] = set()
    for composite in fabric.get_all_unique_tiles():
        if not composite.is_composite:
            continue
        positions = fabric.find_tile_positions(composite)
        if positions is None:
            continue
        # The composite anchor is its top-left cell (top-first tile_map origin).
        # The fabric grid is stored bottom row first, so that cell maps to the
        # fabric offset (anchor_dx, (max_height - 1) - anchor_dy) from each
        # placement's bottom-left origin.
        anchor_dx, anchor_dy = composite.get_anchor_offset()
        fabric_anchor_dy = (composite.max_height - 1) - anchor_dy
        for base_fx, base_fy in _composite_placement_origins(positions):
            anchor = (base_fx + anchor_dx, base_fy + fabric_anchor_dy)
            if anchor not in seen:
                seen.add(anchor)
                yield anchor[0], anchor[1], composite


def _composite_placement_origins(
    positions: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Return the top-left origin cell of each placement of a composite tile.

    A placement occupies a contiguous block of grid cells. The origin of a block
    is the covered cell with no covered neighbour immediately to its north
    (``y - 1``) or west (``x - 1``); each such cell marks the start of a distinct
    placement.

    Parameters
    ----------
    positions : list[tuple[int, int]]
        Every grid cell covered by any placement of the composite tile.

    Returns
    -------
    list[tuple[int, int]]
        One ``(min_x, min_y)`` origin per placement, in sorted order.
    """
    cells = set(positions)
    origins: list[tuple[int, int]] = []
    for x, y in sorted(cells):
        if (x - 1, y) not in cells and (x, y - 1) not in cells:
            origins.append((x, y))
    return origins


def _composite_cell_offsets(composite: Tile) -> list[tuple[int, int, int, int]]:
    """Return the wrapper label and fabric offset of every populated cell.

    Each entry is ``(label_x, label_y, fabric_dx, fabric_dy)`` where:

    - ``(label_x, label_y)`` is the cell's TOP-FIRST ``tile_map`` index. The
      composite wrapper module (:func:`_generate_composite_tile`) names its own
      per-cell ports ``Tile_X{label_x}Y{label_y}_<sig>`` using this index, so any
      reference to the wrapper's OWN port must use it.
    - ``(fabric_dx, fabric_dy)`` is the offset of the cell within the fabric grid,
      which is stored BOTTOM row first, so ``fabric_dy = (max_height - 1) -
      label_y``. Any reference to a fabric grid net, or any grid indexing, must
      use this offset.

    Entries are returned in fabric scan order (bottom row first, left to right)
    so they match the order in which ``generateFabric`` walks the grid.

    Parameters
    ----------
    composite : Tile
        The composite tile whose cells are enumerated.

    Returns
    -------
    list[tuple[int, int, int, int]]
        One ``(label_x, label_y, fabric_dx, fabric_dy)`` entry per populated cell.
    """
    rows = composite.tile_map
    if rows is None:
        return [(0, 0, 0, 0)]
    height = len(rows)
    offsets: list[tuple[int, int, int, int]] = []
    for ly, row in enumerate(rows):
        for lx, cell in enumerate(row):
            if cell is not None:
                offsets.append((lx, ly, lx, (height - 1) - ly))
    offsets.sort(key=lambda o: (o[3], o[2]))
    return offsets


def _composite_perimeter_by_offset(
    composite: Tile,
) -> dict[tuple[int, int], tuple[tuple[int, int], list]]:
    """Return each composite cell's wrapper label and perimeter ports, by offset.

    Keyed by the cell's fabric ``(fabric_dx, fabric_dy)`` offset so the caller can
    address the fabric grid net, the value carries both the cell's TOP-FIRST
    wrapper label index ``(label_x, label_y)`` (for naming the wrapper's own port)
    and its perimeter side-port lists. A side is included only when it faces the
    composite boundary, mirroring the pre-migration supertile wiring.

    Parameters
    ----------
    composite : Tile
        The composite tile whose perimeter ports are collected.

    Returns
    -------
    dict[tuple[int, int], tuple[tuple[int, int], list]]
        Mapping from ``(fabric_dx, fabric_dy)`` offset to
        ``((label_x, label_y), perimeter_side_port_lists)``.
    """
    rows = composite.tile_map
    if rows is None:
        return {}
    height = len(rows)
    result: dict[tuple[int, int], tuple[tuple[int, int], list]] = {}
    for ly, row in enumerate(rows):
        for lx, cell in enumerate(row):
            if cell is None:
                continue
            offset = (lx, (height - 1) - ly)
            sides: list = []
            # Top-first storage: ly-1 is physically north, ly+1 is south.
            if ly - 1 < 0 or rows[ly - 1][lx] is None:
                sides.append(cell.get_port_on_side(Side.NORTH))
            if lx + 1 >= len(row) or row[lx + 1] is None:
                sides.append(cell.get_port_on_side(Side.EAST))
            if ly + 1 >= len(rows) or rows[ly + 1][lx] is None:
                sides.append(cell.get_port_on_side(Side.SOUTH))
            if lx - 1 < 0 or row[lx - 1] is None:
                sides.append(cell.get_port_on_side(Side.WEST))
            result[offset] = ((lx, ly), sides)
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
                    for i in bel.external_input:
                        writer.addPortScalar(
                            f"Tile_X{x}Y{y}_{i}", IO.INPUT, indentLevel=2
                        )
                        writer.addComment("EXTERNAL", onNewLine=False)
                    for i in bel.external_output:
                        writer.addPortScalar(
                            f"Tile_X{x}Y{y}_{i}", IO.OUTPUT, indentLevel=2
                        )
                        writer.addComment("EXTERNAL", onNewLine=False)

    # supertile-level BEL external ports (the BEL lives in the wrapper, not a
    # child tile); declare them at the wrapper's anchor coordinates.
    for ax, ay, superTile in iter_composite_anchors(fabric):
        for bel in superTile.bels:
            for i in bel.external_input:
                writer.addPortScalar(f"Tile_X{ax}Y{ay}_{i}", IO.INPUT, indentLevel=2)
                writer.addComment("EXTERNAL", onNewLine=False)
            for i in bel.external_output:
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
        # every tileDir is the fabric.csv itself rather than a per-tile directory.
        tileRoot = fabric.fabric_dir.parent / "Tile"
        for tile in fabric.tileDic.values():
            if tile.part_of_super_tile:
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
        writer.addAssignScalar("conf_dat'low", "CONFin")
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
    # unique tile. ``setdefault`` keeps the first owner in ``get_all_unique_tiles``
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
            superTileLoc = []
            superTile = None
            if tile is None:
                continue

            if (x, y) in instantiatedPosition:
                continue

            # instantiate composite tile when encountered: find the composite
            # that owns this sub-tile, then map its cells to fabric offsets.
            if tile.part_of_super_tile:
                superTile = composite_owner_by_subtile.get(tile.name)

            if superTile:
                for label_x, label_y, dx, dy in _composite_cell_offsets(superTile):
                    tileLocationOffset.append((label_x, label_y, dx, dy))
                    instantiatedPosition.append((x + dx, y + dy))
                    superTileLoc.append((x + dx, y + dy))
            else:
                tileLocationOffset.append((0, 0, 0, 0))

            portsPairs = []
            # use the offset to find all the related tile input, output signal
            # if is a normal tile then the offset is (0, 0). ``li``/``lj`` are the
            # wrapper top-first label index (for the wrapper's own port name);
            # ``i``/``j`` are the fabric-grid offset (for grid lookups and nets).
            for li, lj, i, j in tileLocationOffset:
                here = fabric.tile[y + j][x + i]
                in_super = here.part_of_super_tile

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
                for local_side, neighbour_side, dx, dy in _SIDE_INPUT_CONNECTIONS:
                    neighbor_x, neighbor_y = x + i + dx, y + j + dy
                    if (neighbor_x, neighbor_y) in superTileLoc:
                        continue
                    localPorts = _local_names(
                        here.get_port_on_side(local_side, IO.INPUT)
                    )
                    if (
                        0 <= neighbor_y < len(fabric.tile)
                        and 0 <= neighbor_x < len(fabric.tile[0])
                        and fabric.tile[neighbor_y][neighbor_x] is not None
                    ):
                        neighborInput = [
                            f"Tile_X{neighbor_x}Y{neighbor_y}_{p.name}"
                            for p in fabric.tile[neighbor_y][
                                neighbor_x
                            ].get_port_on_side(neighbour_side, IO.OUTPUT)
                        ]
                        portsPairs += list(zip(localPorts, neighborInput, strict=False))
                    else:
                        portsPairs += [(p, "") for p in localPorts]

            # output signal name is same as the output port name
            if superTile:
                perimeter = _composite_perimeter_by_offset(superTile)
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
                    for p in b.external_input:
                        portsPairs.append((p, f"Tile_X{x + i}Y{y + j}_{p}"))

                    for p in b.external_output:
                        portsPairs.append((p, f"Tile_X{x + i}Y{y + j}_{p}"))

                    if not fabric.disableUserCLK:
                        for p in b.shared_port:
                            if "UserCLK" not in p.name:
                                portsPairs.append(("UserCLK", p.name))

            # supertile-level BEL external ports: connect the wrapper's external
            # ports to the top-level nets declared at the anchor coordinates.
            if superTile:
                for b in superTile.bels:
                    for p in b.external_input:
                        portsPairs.append((p, f"Tile_X{x}Y{y}_{p}"))
                    for p in b.external_output:
                        portsPairs.append((p, f"Tile_X{x}Y{y}_{p}"))

            if not fabric.disableUserCLK:
                if not superTile:
                    # for user_clk
                    if (
                        y + 1 < fabric.numberOfRows
                        and fabric.tile[y + 1][x] is not None
                    ):
                        portsPairs.append(("UserCLK", f"Tile_X{x}Y{y + 1}_UserCLKo"))
                    else:
                        portsPairs.append(("UserCLK", "UserCLK"))

                    # for userCLKo
                    portsPairs.append(("UserCLKo", f"Tile_X{x}Y{y}_UserCLKo"))
                else:
                    for li, lj, i, j in tileLocationOffset:
                        # prefix for the wrapper's own port (top-first label index)
                        pre = f"Tile_X{li}Y{lj}_"

                        # UserCLK signal
                        next_row = y + j + 1
                        if (
                            next_row >= fabric.numberOfRows
                            or fabric.tile[next_row][x + i] is None
                        ):
                            portsPairs.append((f"{pre}UserCLK", "UserCLK"))

                        elif (x + i, next_row) not in superTileLoc:
                            portsPairs.append(
                                (f"{pre}UserCLK", f"Tile_X{x + i}Y{next_row}_UserCLKo")
                            )

                        # UserCLKo signal
                        # Bottom-left origin: UserCLKo goes to the tile below (y-1);
                        # expose as a port when that tile is not in the supertile.
                        if (x + i, y + j - 1) not in superTileLoc:
                            portsPairs.append(
                                (f"{pre}UserCLKo", f"Tile_X{x + i}Y{y + j}_UserCLKo")
                            )

            if fabric.configBitMode == ConfigBitMode.FRAME_BASED:
                for li, lj, i, j in tileLocationOffset:
                    # prefix for the wrapper's own port (top-first label index)
                    pre = ""
                    if superTile:
                        pre = f"Tile_X{li}Y{lj}_"

                    supertile_x = x + i
                    supertile_y = y + j

                    # Connect the FrameData port to the previous tiles'
                    # (to the west of it) FrameData_O signals.
                    # If the previous tile is NULL, continue the search.
                    # If all previous tiles are NULL, connect to the fabrics
                    # Row_Y{y}_FrameData signals.

                    done = False

                    # Get all x-positions to the west of this tile
                    for search_x in range(supertile_x - 1, -1, -1):
                        # Previous tile is part of the same supertile.
                        # FrameData signals are connected internally.
                        # Stop the search and be done.
                        if (search_x, supertile_y) in superTileLoc:
                            done = True
                            break

                        # Previous tile is NULL, continue search
                        if fabric.tile[supertile_y][search_x] is None:
                            continue

                        # Found a non-NULL tile, connect FrameData
                        portsPairs.append(
                            (
                                f"{pre}FrameData",
                                f"Tile_X{search_x}Y{supertile_y}_FrameData_O",
                            )
                        )

                        done = True
                        break

                    # No non-NULL tile was found, and tile is not part of a supertile.
                    # Connect to the fabrics Row_Y{y}_FrameData signals.
                    if not done:
                        portsPairs.append(
                            (f"{pre}FrameData", f"Row_Y{supertile_y}_FrameData")
                        )

                    # Connecting FrameData_O is easier:
                    # Always connect FrameData_O, except the next tile
                    # (to the east of it)
                    # in the row is part of the supertile
                    # (already connected internally).
                    if (supertile_x + 1, supertile_y) not in superTileLoc:
                        portsPairs.append(
                            (
                                f"{pre}FrameData_O",
                                f"Tile_X{supertile_x}Y{supertile_y}_FrameData_O",
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
                    for search_y in range(supertile_y - 1, -1, -1):
                        # Previous tile is part of the same supertile.
                        # FrameStrobe signals are connected internally.
                        # Stop the search and be done.
                        if (supertile_x, search_y) in superTileLoc:
                            done = True
                            break

                        # Previous tile is NULL, continue search
                        if fabric.tile[search_y][supertile_x] is None:
                            continue

                        # Found a non-NULL tile, connect FrameStrobe
                        portsPairs.append(
                            (
                                f"{pre}FrameStrobe",
                                f"Tile_X{supertile_x}Y{search_y}_FrameStrobe_O",
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
                                f"Column_X{supertile_x}_FrameStrobe",
                            )
                        )

                    # Connecting FrameStrobe_O is easier:
                    # Always connect FrameStrobe_O, except the next tile
                    # (to the north of it)
                    # in the column is part of the supertile
                    # (already connected internally).
                    # Bottom-left origin: north is y+1
                    if (supertile_x, supertile_y + 1) not in superTileLoc:
                        portsPairs.append(
                            (
                                f"{pre}FrameStrobe_O",
                                f"Tile_X{supertile_x}Y{supertile_y}_FrameStrobe_O",
                            )
                        )

            name = ""
            emulateParamPairs = []
            if superTile:
                name = superTile.name
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
