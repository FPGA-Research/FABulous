"""Nextpnr model generation for FABulous FPGA fabrics.

This module provides functionality to generate nextpnr models from FABulous fabric
definitions. The nextpnr model includes detailed descriptions of programmable
interconnect points (PIPs), basic elements of logic (BELs), and routing resources needed
for place-and-route operations.

The generated models enable nextpnr to understand the fabric architecture and perform
placement and routing for user designs.
"""

import string
import os
from pathlib import Path

from FABulous.custom_exception import InvalidFileType, InvalidState
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix

from FABulous.fabric_cad.timing_model.FABulous_timing_model_interface import FABulousTimingModelInterface

def genNextpnrModel(fabric: Fabric, delay_model: FABulousTimingModelInterface = None) -> tuple[str, str, str, str]:
    """Generate the fabric's nextpnr model.

    Parameters
    ----------
    fabric : Fabric
        Fabric object containing tile information.
    delay_model : FABulousTimingModelInterface, optional
        Timing model interface to provide delay information, by default None.

    Returns
    -------
    tuple[str, str, str, str]
        - pipStr: A string with tile-internal and tile-external pip descriptions.
        - belStr: A string with old style BEL definitions.
        - belv2Str: A string with new style BEL definitions.
        - constrainStr: A string with constraint definitions.

    Raises
    ------
    InvalidFileType
        If matrixDir of a tile is not '.csv' or '.list' file.
    InvalidState
        If a wire in a tile points to an invalid tile outside the fabric bounds.
    """
    pipStr = []
    belStr = []
    belv2Str = []
    belStr.append(
        f"# BEL descriptions: top left corner Tile_X0Y0,"
        f" bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
    )
    belv2Str.append(
        f"# BEL descriptions: top left corner Tile_X0Y0, "
        f"bottom right Tile_X{fabric.numberOfColumns}Y{fabric.numberOfRows}"
    )
    constrainStr = []

    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is None:
                continue
            pipStr.append(f"#Tile-internal pips on tile X{x}Y{y}:")
            if tile.matrixDir.suffix == ".csv":
                connection = parseMatrix(tile.matrixDir, tile.name)
                for source, sinkList in connection.items():
                    for sink in sinkList:
                        delay: float = 8
                        if delay_model is not None:
                            delay = delay_model.pip_delay(tile.name, f"{sink}.{source}", source, sink)
                        pipStr.append(
                            f"X{x}Y{y},{sink},X{x}Y{y},{source},{delay},{sink}.{source}"
                        )
            elif tile.matrixDir.suffix == ".list":
                connection = parseList(tile.matrixDir)
                for sink, source in connection:
                    delay: float = 8
                    if delay_model is not None:
                        delay = delay_model.pip_delay(tile.name, f"{source}.{sink}", source, sink)
                    pipStr.append(
                        f"X{x}Y{y},{source},X{x}Y{y},{sink},{delay},{source}.{sink}"
                    )
            else:
                raise InvalidFileType(
                    f"File {tile.matrixDir} is not a .csv or .list file"
                )

            pipStr.append(f"#Tile-external pips on tile X{x}Y{y}:")
            for wire in tile.wireList:
                xDst = x + wire.xOffset
                yDst = y + wire.yOffset
                if (not (0 <= xDst <= fabric.numberOfColumns)) or (
                    not (0 <= yDst <= fabric.numberOfRows)
                ):
                    raise InvalidState(
                        f"Wire {wire} in tile X{x}Y{y} points to an invalid tile "
                        f"X{xDst}Y{yDst}. "
                        "Please check your tile CSV file for unmatching wires/offsets!"
                    )
                
                delay: float = 8
                if delay_model is not None:
                    delay = delay_model.pip_delay(
                        tile.name,
                        f"{wire.destination}.{wire.source}",
                        wire.source,
                        wire.destination,
                    )
                pipStr.append(
                    f"X{x}Y{y},{wire.source},"
                    f"X{x + wire.xOffset}Y{y + wire.yOffset},{wire.destination},"
                    f"{delay},"
                    f"{wire.source}.{wire.destination}"
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

                for inp in bel.inputs:
                    belv2Str.append(
                        f"I,{inp.removeprefix(bel.prefix)},X{x}Y{y}.{inp}"
                    )  # I,<port>,<wire>
                for outp in bel.outputs:
                    belv2Str.append(
                        f"O,{outp.removeprefix(bel.prefix)},X{x}Y{y}.{outp}"
                    )  # O,<port>,<wire>
                for feat, _cfg in sorted(bel.belFeatureMap.items(), key=lambda x: x[0]):
                    belv2Str.append(f"CFG,{feat}")
                if bel.withUserCLK:
                    belv2Str.append("GlobalClk")
                belv2Str.append("BelEnd")
    return (
        "\n".join(pipStr),
        "\n".join(belStr),
        "\n".join(belv2Str),
        "\n".join(constrainStr),
    )

def writeNextpnrPipFile(
    fabric: Fabric,
    outputFile: Path,
    delay_model: FABulousTimingModelInterface = None,
) -> None:
    """Write the nextpnr pip file for the given fabric.

    Parameters
    ----------
    fabric : Fabric
        Fabric object containing tile information.
    outputDir : Path
        Directory to write the pip file to.
    """
    pipStr, belStr, belv2Str, constrainStr = genNextpnrModel(fabric, delay_model)

    pipFilePath: Path = outputFile
    with open(pipFilePath, "w") as pipFile:
        pipFile.write(pipStr)