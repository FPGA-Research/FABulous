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

from pathlib import Path

from FABulous.fabric_definition.define import IO, ConfigBitMode, Direction
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)


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
    fabricName = "eFPGA"
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

    writer.addPortScalar("UserCLK", IO.INPUT, indentLevel=2)

    writer.addPortEnd()
    writer.addHeaderEnd(fabricName)
    writer.addDesignDescriptionStart(fabricName)
    writer.addNewLine()

    if isinstance(writer, VHDLCodeGenerator):
        added = set()
        for t in fabric.tileDic:
            name = t.split("_")[0]
            if name in added:
                continue
            if name not in fabric.superTileDic:
                writer.addComponentDeclarationForFile(
                    f"{Path(writer.outFileName).parent.parent}/Tile/{t}/{t}.vhdl"
                )
                added.add(t)
            else:
                writer.addComponentDeclarationForFile(
                    f"{Path(writer.outFileName).parent.parent}/Tile/{name}/{name}.vhdl"
                )
                added.add(name)

    # VHDL signal declarations
    writer.addComment("signal declarations", onNewLine=True, end="\n")

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
                for p in tile.portsInfo:
                    wireLength = (abs(p.xOffset) + abs(p.yOffset)) * p.wireCount - 1
                    if p.sourceName == "NULL" or p.wireDirection == Direction.JUMP:
                        continue
                    if p.sourceName in seenPorts:
                        continue
                    seenPorts.add(p.sourceName)
                    writer.addConnectionVector(
                        f"Tile_X{x}Y{y}_{p.sourceName}", wireLength
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
    # Tile instantiations
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            tileLocationOffset: list[tuple[int, int]] = []
            superTileLoc = []
            superTile = None
            if tile is None:
                continue

            if (x, y) in instantiatedPosition:
                continue

            # instantiate super tile when encountered
            # get all the ports of the tile. If is a super tile, we loop over the
            # tile map and find all the offset of the subtile, and all their related
            # ports.
            if tile.partOfSuperTile:
                for k, v in fabric.superTileDic.items():
                    if tile.name in [i.name for i in v.tiles]:
                        superTile = fabric.superTileDic[k]
                        break

            if superTile:
                portsAround = superTile.getPortsAroundTile()
                cord = [
                    (i.split(",")[0], i.split(",")[1]) for i in list(portsAround.keys())
                ]
                for i, j in cord:
                    tileLocationOffset.append((int(i), int(j)))
                    instantiatedPosition.append((x + int(i), y + int(j)))
                    superTileLoc.append((x + int(i), y + int(j)))
            else:
                tileLocationOffset.append((0, 0))

            portsPairs = []
            # use the offset to find all the related tile input, output signal
            # if is a normal tile then the offset is (0, 0)
            for i, j in tileLocationOffset:
                # input connection from north side of the south tile
                if (
                    0 <= y + 1 < len(fabric.tile)
                    and fabric.tile[y + j + 1][x + i] is not None
                    and (x + i, y + j + 1) not in superTileLoc
                ):
                    if fabric.tile[y + j][x + i].partOfSuperTile:
                        northPorts = [
                            f"Tile_X{i}Y{j}_{p.name}"
                            for p in fabric.tile[y + j][x + i].getNorthPorts(IO.INPUT)
                        ]
                    else:
                        northPorts = [
                            i.name
                            for i in fabric.tile[y + j][x + i].getNorthPorts(IO.INPUT)
                        ]

                    northInput = [
                        f"Tile_X{x + i}Y{y + j + 1}_{p.name}"
                        for p in fabric.tile[y + j + 1][x + i].getNorthPorts(IO.OUTPUT)
                    ]
                    portsPairs += list(zip(northPorts, northInput, strict=False))

                # input connection from east side of the west tile
                if (
                    0 <= x - 1 < len(fabric.tile[0])
                    and fabric.tile[y + j][x + i - 1] is not None
                    and (x + i - 1, y + j) not in superTileLoc
                ):
                    if fabric.tile[y + j][x + i].partOfSuperTile:
                        eastPorts = [
                            f"Tile_X{i}Y{j}_{p.name}"
                            for p in fabric.tile[y + j][x + i].getEastPorts(IO.INPUT)
                        ]
                    else:
                        eastPorts = [
                            i.name
                            for i in fabric.tile[y + j][x + i].getEastPorts(IO.INPUT)
                        ]

                    eastInput = [
                        f"Tile_X{x + i - 1}Y{y + j}_{p.name}"
                        for p in fabric.tile[y + j][x + i - 1].getEastPorts(IO.OUTPUT)
                    ]
                    portsPairs += list(zip(eastPorts, eastInput, strict=False))

                # input connection from south side of the north tile
                if (
                    0 <= y - 1 < len(fabric.tile)
                    and fabric.tile[y + j - 1][x + i] is not None
                    and (x + i, y + j - 1) not in superTileLoc
                ):
                    if fabric.tile[y + j][x + i].partOfSuperTile:
                        southPorts = [
                            f"Tile_X{i}Y{j}_{p.name}"
                            for p in fabric.tile[y + j][x + i].getSouthPorts(IO.INPUT)
                        ]
                    else:
                        southPorts = [
                            i.name
                            for i in fabric.tile[y + j][x + i].getSouthPorts(IO.INPUT)
                        ]

                    southInput = [
                        f"Tile_X{x + i}Y{y + j - 1}_{p.name}"
                        for p in fabric.tile[y + j - 1][x + i].getSouthPorts(IO.OUTPUT)
                    ]
                    portsPairs += list(zip(southPorts, southInput, strict=False))

                # input connection from west side of the east tile
                if (
                    0 <= x + 1 < len(fabric.tile[0])
                    and fabric.tile[y + j][x + i + 1] is not None
                    and (x + i + 1, y + j) not in superTileLoc
                ):
                    if fabric.tile[y + j][x + i].partOfSuperTile:
                        westPorts = [
                            f"Tile_X{i}Y{j}_{p.name}"
                            for p in fabric.tile[y + j][x + i].getWestPorts(IO.INPUT)
                        ]
                    else:
                        westPorts = [
                            i.name
                            for i in fabric.tile[y + j][x + i].getWestPorts(IO.INPUT)
                        ]

                    westInput = [
                        f"Tile_X{x + i + 1}Y{y + j}_{p.name}"
                        for p in fabric.tile[y + j][x + i + 1].getWestPorts(IO.OUTPUT)
                    ]
                    portsPairs += list(zip(westPorts, westInput, strict=False))

            # output signal name is same as the output port name
            if superTile:
                portsAround = superTile.getPortsAroundTile()
                cord = [
                    (i.split(",")[0], i.split(",")[1]) for i in list(portsAround.keys())
                ]
                cord = list(zip(cord, portsAround.values(), strict=False))
                for (i, j), around in cord:
                    for ports in around:
                        for port in ports:
                            if port.inOut == IO.OUTPUT and port.name != "NULL":
                                portsPairs.append(
                                    (
                                        f"Tile_X{int(i)}Y{int(j)}_{port.name}",
                                        f"Tile_X{x + int(i)}Y{y + int(j)}_{port.name}",
                                    )
                                )
            else:
                for i in tile.getTileOutputNames():
                    portsPairs.append((i, f"Tile_X{x}Y{y}_{i}"))

            writer.addNewLine()
            writer.addComment(
                "tile IO port will get directly connected to top-level tile module",
                onNewLine=True,
                indentLevel=0,
            )
            for i, j in tileLocationOffset:
                for b in fabric.tile[y + j][x + i].bels:
                    for p in b.externalInput:
                        portsPairs.append((p, f"Tile_X{x + i}Y{y + j}_{p}"))

                    for p in b.externalOutput:
                        portsPairs.append((p, f"Tile_X{x + i}Y{y + j}_{p}"))

                    for p in b.sharedPort:
                        if "UserCLK" not in p[0]:
                            portsPairs.append(("UserCLK", p[0]))

            if not superTile:
                # for userCLK
                if y + 1 < fabric.numberOfRows and fabric.tile[y + 1][x] is not None:
                    portsPairs.append(("UserCLK", f"Tile_X{x}Y{y + 1}_UserCLKo"))
                else:
                    portsPairs.append(("UserCLK", "UserCLK"))

                # for userCLKo
                portsPairs.append(("UserCLKo", f"Tile_X{x}Y{y}_UserCLKo"))
            else:
                for i, j in tileLocationOffset:
                    # prefix for super tile port
                    pre = ""
                    if superTile:
                        pre = f"Tile_X{i}Y{j}_"

                    # UserCLK signal
                    if (
                        y + 1 >= fabric.numberOfRows
                        or y + 1 < fabric.numberOfRows
                        and fabric.tile[y + 1][x] is None
                    ):
                        portsPairs.append((f"{pre}UserCLK", "UserCLK"))

                    elif (x + i, y + j + 1) not in superTileLoc:
                        portsPairs.append(
                            (f"{pre}UserCLK", f"Tile_X{x + i}Y{y + j + 1}_UserCLKo")
                        )

                    # UserCLKo signal
                    if (x + i, y + j - 1) not in superTileLoc:
                        portsPairs.append(
                            (f"{pre}UserCLKo", f"Tile_X{x + i}Y{y + j}_UserCLKo")
                        )

            if fabric.configBitMode == ConfigBitMode.FRAME_BASED:
                for i, j in tileLocationOffset:
                    # prefix for super tile port
                    pre = ""
                    if superTile:
                        pre = f"Tile_X{i}Y{j}_"

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
                    #       fabric, therefore count upwards
                    for search_y in range(supertile_y + 1, fabric.numberOfRows):
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
                    if (supertile_x, supertile_y - 1) not in superTileLoc:
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
                for i, j in tileLocationOffset:
                    if (y + j) not in (0, fabric.numberOfRows - 1):
                        emulateParamPairs.append(
                            (
                                f"Tile_X{i}Y{j}_Emulate_Bitstream",
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
            )
    writer.addDesignDescriptionEnd()
    writer.writeToFile()
