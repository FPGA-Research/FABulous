import string
from typing import Tuple

from FABulous.fabric_generator.fabric import Fabric, Tile
from FABulous.fabric_generator.file_parser import parseList, parseMatrix
from FABulous.fabric_generator.utilities import *


def genNextpnrModel(fabric: Fabric):
    pipStr = []
    belStr = []
    belv2Str = []
    belStr.append(
        f"# BEL descriptions: top left corner Tile_X0Y0, bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
    )
    belv2Str.append(
        f"# BEL descriptions: top left corner Tile_X0Y0, bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
    )
    constrainStr = []

    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is None:
                continue
            pipStr.append(f"#Tile-internal pips on tile X{x}Y{y}:")
            if tile.matrixDir.endswith(".csv"):
                connection = parseMatrix(tile.matrixDir, tile.name)
                for source, sinkList in connection.items():
                    for sink in sinkList:
                        pipStr.append(
                            f"X{x}Y{y},{sink},X{x}Y{y},{source},{8},{sink}.{source}"
                        )
            elif tile.matrixDir.endswith(".list"):
                connection = parseList(tile.matrixDir)
                for sink, source in connection:
                    pipStr.append(
                        f"X{x}Y{y},{source},X{x}Y{y},{sink},{8},{source}.{sink}"
                    )
            else:
                raise ValueError(
                    f"For model generation {tile.matrixDir} need to a csv or list file"
                )

            pipStr.append(f"#Tile-external pips on tile X{x}Y{y}:")
            for wire in tile.wireList:
                pipStr.append(
                    f"X{x}Y{y},{wire.source},X{x+wire.xOffset}Y{y+wire.yOffset},{wire.destination},{8},{wire.source}.{wire.destination}"
                )

            # Old style bel definition
            belStr.append(f"#Tile_X{x}Y{y}")
            for i, bel in enumerate(tile.bels):
                belPort = bel.inputs + bel.outputs
                cType = bel.name
                if (
                    bel.name == "LUT4c_frame_config"
                    or bel.name == "LUT4c_frame_config_dffesr"
                ):
                    cType = "FABULOUS_LC"
                letter = string.ascii_uppercase[i]
                belStr.append(
                    f"X{x}Y{y},X{x},Y{y},{letter},{cType},{','.join(belPort)}"
                )

                if bel.name in [
                    "IO_1_bidirectional_frame_config_pass",
                    "InPass4_frame_config",
                    "OutPass4_frame_config",
                    "InPass4_frame_config_mux",
                    "OutPass4_frame_config_mux",
                ]:
                    constrainStr.append(
                        f"set_io Tile_X{x}Y{y}_{letter} Tile_X{x}Y{y}.{letter}"
                    )
            # New style bel definition
            belv2Str.append(f"#Tile_X{x}Y{y}")
            for i, bel in enumerate(tile.bels):
                cType = bel.name
                if (
                    bel.name == "LUT4c_frame_config"
                    or bel.name == "LUT4c_frame_config_dffesr"
                ):
                    cType = "FABULOUS_LC"
                letter = string.ascii_uppercase[i]
                belv2Str.append(f"BelBegin,X{x}Y{y},{letter},{cType},{bel.prefix}")

                def strip_prefix(x):
                    if x.startswith(bel.prefix):
                        return x[len(bel.prefix) :]
                    else:
                        return x

                for inp in bel.inputs:
                    belv2Str.append(
                        f"I,{strip_prefix(inp)},X{x}Y{y}.{inp}"
                    )  # I,<port>,<wire>
                for outp in bel.outputs:
                    belv2Str.append(
                        f"O,{strip_prefix(outp)},X{x}Y{y}.{outp}"
                    )  # O,<port>,<wire>
                for feat, cfg in sorted(bel.belFeatureMap.items(), key=lambda x: x[0]):
                    belv2Str.append(f"CFG,{feat}")
                if bel.withUserCLK:
                    belv2Str.append(f"GlobalClk")
                belv2Str.append(f"BelEnd")
    return (
        "\n".join(pipStr),
        "\n".join(belStr),
        "\n".join(belv2Str),
        "\n".join(constrainStr),
    )


def genNextpnrPairModel(fabric: Fabric):
    pass


def genNextpnrModelOld(
    archObject: FabricModelGen, generatePairs=True
) -> Tuple[str, str, str]:
    pipsStr = ""
    belsStr = f"# BEL descriptions: bottom left corner Tile_X0Y0, top right {archObject.tiles[0][archObject.width - 1].genTileLoc()}\n"
    pairStr = ""
    constraintStr = ""
    for line in archObject.tiles:
        for tile in line:
            # Add PIPs
            # Pips within the tile
            tileLoc = tile.genTileLoc()  # Get the tile location string
            pipsStr += f"#Tile-internal pips on tile {tileLoc}:\n"
            for pip in tile.pips:
                # Add the pips (also delay should be done here later, sDelay is a filler)
                pipsStr += ",".join(
                    (
                        tileLoc,
                        pip[0],
                        tileLoc,
                        pip[1],
                        sDelay,
                        ".".join((pip[0], pip[1])),
                    )
                )
                pipsStr += "\n"

            # Wires between tiles
            pipsStr += f"#Tile-external pips on tile {tileLoc}:\n"
            for wire in tile.wires:
                desty = tile.y + int(wire["yoffset"])
                destx = tile.x + int(wire["xoffset"])
                desttileLoc = f"X{destx}Y{desty}"
                for i in range(int(wire["wire-count"])):
                    pipsStr += ",".join(
                        (
                            tileLoc,
                            wire["source"] + str(i),
                            desttileLoc,
                            wire["destination"] + str(i),
                            sDelay,
                            ".".join(
                                (wire["source"] + str(i), wire["destination"] + str(i))
                            ),
                        )
                    )
                    pipsStr += "\n"
            for (
                wire
            ) in (
                tile.atomicWires
            ):  # Very simple - just add wires using values directly from the atomic wire structure
                desttileLoc = wire["destTile"]
                pipsStr += ",".join(
                    (
                        tileLoc,
                        wire["source"],
                        desttileLoc,
                        wire["destination"],
                        sDelay,
                        ".".join((wire["source"], wire["destination"])),
                    )
                )
                pipsStr += "\n"
            # Add BELs
            belsStr += "#Tile_" + tileLoc + "\n"  # Tile declaration as a comment
            for num, belpair in enumerate(tile.bels):
                bel = belpair[0]
                let = letters[num]
                # if bel == "LUT4c_frame_config":
                #     cType = "LUT4"
                #     prefix = "L" + let + "_"
                # elif bel == "IO_1_bidirectional_frame_config_pass":
                #     prefix = let + "_"
                # else:
                #     cType = bel
                #     prefix = ""
                prefix = belpair[1]
                nports = belpair[2]
                if bel == "LUT4c_frame_config":
                    cType = "FABULOUS_LC"  # "LUT4"
                # elif bel == "IO_1_bidirectional_frame_config_pass":
                #    cType = "IOBUF"
                else:
                    cType = bel
                belsStr += (
                    ",".join(
                        (
                            tileLoc,
                            ",".join(tile.genTileLoc(True)),
                            let,
                            cType,
                            ",".join(nports),
                        )
                    )
                    + "\n"
                )
                # Add constraints to fix pin location (based on template generated in genVerilogTemplate)
                if bel in [
                    "IO_1_bidirectional_frame_config_pass",
                    "InPass4_frame_config",
                    "OutPass4_frame_config",
                ]:
                    belName = f"Tile_{tileLoc}_{let}"
                    constraintStr += f"set_io {belName} {tileLoc}.{let}\n"

            if generatePairs:
                # Generate wire beginning to wire beginning pairs for timing analysis
                print("Generating pairs for: " + tile.genTileLoc())
                pairStr += "#" + tileLoc + "\n"
                for wire in tile.wires:
                    for i in range(int(wire["wire-count"])):
                        desty = tile.y + int(wire["yoffset"])
                        destx = tile.x + int(wire["xoffset"])
                        destTile = archObject.getTileByCoords(destx, desty)
                        desttileLoc = f"X{destx}Y{desty}"
                        if (
                            wire["destination"] + str(i)
                        ) not in destTile.pipMuxes_MapSourceToSinks.keys():
                            continue
                        for pipSink in destTile.pipMuxes_MapSourceToSinks[
                            wire["destination"] + str(i)
                        ]:
                            # If there is a multiplexer here, then we can simply add this pair
                            if len(destTile.pipMuxes_MapSinkToSources[pipSink]) > 1:
                                pairStr += (
                                    ",".join(
                                        (
                                            ".".join(
                                                (
                                                    tileLoc,
                                                    wire["source"] + f"[{str(i)}]",
                                                )
                                            ),
                                            ".".join(
                                                (
                                                    desttileLoc,
                                                    addBrackets(pipSink, tile),
                                                )
                                            ),
                                        )
                                    )
                                    + "\n"
                                )  # TODO: add square brackets to end
                            # otherwise, there is no physical pair in the ASIC netlist, so we must propagate back until we hit a multiplexer
                            else:
                                finalDestination = ".".join(
                                    (desttileLoc, addBrackets(pipSink, tile))
                                )
                                foundPhysicalPairs = False
                                curWireTuple = (tile, wire, i)
                                potentialStarts = []
                                stopOffs = []
                                while not foundPhysicalPairs:
                                    cTile = curWireTuple[0]
                                    cWire = curWireTuple[1]
                                    cIndex = curWireTuple[2]
                                    if (
                                        len(
                                            cTile.pipMuxes_MapSinkToSources[
                                                cWire["source"] + str(cIndex)
                                            ]
                                        )
                                        > 1
                                    ):
                                        for wireEnd in cTile.pipMuxes_MapSinkToSources[
                                            cWire["source"] + str(cIndex)
                                        ]:
                                            if wireEnd in cTile.belPorts:
                                                continue
                                            cPair = archObject.getTileAndWireByWireDest(
                                                cTile.genTileLoc(), wireEnd
                                            )
                                            if cPair == None:
                                                continue
                                            potentialStarts.append(
                                                cPair[0].genTileLoc()
                                                + "."
                                                + cPair[1]["source"]
                                                + "["
                                                + str(cPair[2])
                                                + "]"
                                            )
                                        foundPhysicalPairs = True
                                    else:
                                        destPort = cTile.pipMuxes_MapSinkToSources[
                                            cWire["source"] + str(cIndex)
                                        ][0]
                                        destLoc = cTile.genTileLoc()
                                        if destPort in cTile.belPorts:
                                            foundPhysicalPairs = True  # This means it's connected to a BEL
                                            continue
                                        if (
                                            GNDRE.match(destPort)
                                            or VCCRE.match(destPort)
                                            or VDDRE.match(destPort)
                                        ):
                                            foundPhysicalPairs = True
                                            continue
                                        stopOffs.append(destLoc + "." + destPort)
                                        curWireTuple = (
                                            archObject.getTileAndWireByWireDest(
                                                destLoc, destPort
                                            )
                                        )
                                pairStr += (
                                    "#Propagated route for " + finalDestination + "\n"
                                )
                                for index, start in enumerate(potentialStarts):
                                    pairStr += start + "," + finalDestination + "\n"
                                pairStr += "#Stopoffs: " + ",".join(stopOffs) + "\n"

                # Generate pairs for bels:
                pairStr += "#Atomic wire pairs\n"
                for wire in tile.atomicWires:
                    pairStr += (
                        wire["sourceTile"]
                        + "."
                        + addBrackets(wire["source"], tile)
                        + ","
                        + wire["destTile"]
                        + "."
                        + addBrackets(wire["destination"], tile)
                        + "\n"
                    )
                for num, belpair in enumerate(tile.bels):
                    pairStr += "#Bel pairs" + "\n"
                    bel = belpair[0]
                    let = letters[num]
                    prefix = belpair[1]
                    nports = belpair[2]
                    if bel == "LUT4c_frame_config":
                        for i in range(4):
                            pairStr += (
                                tileLoc
                                + "."
                                + prefix
                                + f"D[{i}],"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                        for outPip in tile.pipMuxes_MapSourceToSinks[prefix + "O"]:
                            for i in range(4):
                                pairStr += (
                                    tileLoc
                                    + "."
                                    + prefix
                                    + f"I[{i}],"
                                    + tileLoc
                                    + "."
                                    + addBrackets(outPip, tile)
                                    + "\n"
                                )
                                pairStr += (
                                    tileLoc
                                    + "."
                                    + prefix
                                    + f"Q[{i}],"
                                    + tileLoc
                                    + "."
                                    + addBrackets(outPip, tile)
                                    + "\n"
                                )
                    elif bel == "MUX8LUT_frame_config":
                        for outPip in tile.pipMuxes_MapSourceToSinks["M_AB"]:
                            pairStr += (
                                tileLoc
                                + ".A,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".B,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S0,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                        for outPip in tile.pipMuxes_MapSourceToSinks["M_AD"]:
                            pairStr += (
                                tileLoc
                                + ".A,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".B,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".C,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".D,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S0,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S1,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                        for outPip in tile.pipMuxes_MapSourceToSinks["M_AH"]:
                            pairStr += (
                                tileLoc
                                + ".A,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".B,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".C,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".D,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".E,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".F,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".G,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".H,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S0,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S1,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S2,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S3,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                        for outPip in tile.pipMuxes_MapSourceToSinks["M_EF"]:
                            pairStr += (
                                tileLoc
                                + ".E,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".F,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S0,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                            pairStr += (
                                tileLoc
                                + ".S2,"
                                + tileLoc
                                + "."
                                + addBrackets(outPip, tile)
                                + "\n"
                            )
                    elif bel == "MULADD":
                        for i in range(20):
                            for outPip in tile.pipMuxes_MapSourceToSinks[f"Q{i}"]:
                                for i in range(8):
                                    pairStr += (
                                        tileLoc
                                        + f".A[{i}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                                for i in range(8):
                                    pairStr += (
                                        tileLoc
                                        + f".B[{i}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                                for i in range(20):
                                    pairStr += (
                                        tileLoc
                                        + f".C[{i}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                    elif bel == "RegFile_32x4":
                        for i in range(4):
                            for outPip in tile.pipMuxes_MapSourceToSinks[f"AD{i}"]:
                                pairStr += (
                                    tileLoc
                                    + ".W_en,"
                                    + tileLoc
                                    + "."
                                    + addBrackets(outPip, tile)
                                    + "\n"
                                )
                                for j in range(4):
                                    pairStr += (
                                        tileLoc
                                        + f".D[{j}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                                    pairStr += (
                                        tileLoc
                                        + f".W_ADR[{j}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                                    pairStr += (
                                        tileLoc
                                        + f".A_ADR[{j}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                            for outPip in tile.pipMuxes_MapSourceToSinks[f"BD{i}"]:
                                pairStr += (
                                    tileLoc
                                    + ".W_en,"
                                    + tileLoc
                                    + "."
                                    + addBrackets(outPip, tile)
                                    + "\n"
                                )
                                for j in range(4):
                                    pairStr += (
                                        tileLoc
                                        + f".D[{j}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                                    pairStr += (
                                        tileLoc
                                        + f".W_ADR[{j}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                                    pairStr += (
                                        tileLoc
                                        + f".B_ADR[{j}],"
                                        + tileLoc
                                        + "."
                                        + addBrackets(outPip, tile)
                                        + "\n"
                                    )
                    elif bel == "IO_1_bidirectional_frame_config_pass":
                        # inPorts go into the fabric, outPorts go out
                        for inPort in ("O", "Q"):
                            for outPip in tile.pipMuxes_MapSourceToSinks[
                                prefix + inPort
                            ]:
                                pairStr += (
                                    tileLoc
                                    + "."
                                    + prefix
                                    + inPort
                                    + ","
                                    + tileLoc
                                    + "."
                                    + addBrackets(outPip, tile)
                                    + "\n"
                                )
                        # Outputs are covered by the wire code, as pips will link to them
                    elif bel == "InPass4_frame_config":
                        for i in range(4):
                            for outPip in tile.pipMuxes_MapSourceToSinks[
                                prefix + "O" + str(i)
                            ]:
                                pairStr += (
                                    tileLoc
                                    + "."
                                    + prefix
                                    + f"O{i}"
                                    + ","
                                    + tileLoc
                                    + "."
                                    + addBrackets(outPip, tile)
                                    + "\n"
                                )
                    elif bel == "OutPass4_frame_config":
                        for i in range(4):
                            for inPip in tile.pipMuxes_MapSinkToSources[
                                prefix + "I" + str(i)
                            ]:
                                pairStr += (
                                    tileLoc
                                    + "."
                                    + addBrackets(inPip, tile)
                                    + ","
                                    + tileLoc
                                    + "."
                                    + prefix
                                    + f"I{i}"
                                    + "\n"
                                )
    if generatePairs:
        return (pipsStr, belsStr, constraintStr, pairStr)
    else:
        # Seems a little nicer to have a constant size tuple returned
        return (pipsStr, belsStr, constraintStr, None)
