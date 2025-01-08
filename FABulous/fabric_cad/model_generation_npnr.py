import string

from loguru import logger

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.file_parser import parseList, parseMatrix


def genNextpnrModel(fabric: Fabric):
    """Generates Nextpnr model for given fabric

    Parameters
    ----------
    fabric : Fabric
        Fabric object containing tile information.

    Returns
    -------
    Tuple[str, str, str, str]
        - pipStr: A string with tile-internal and tile-external pip descriptions.
        - belStr: A string with old style BEL definitions.
        - belv2Str: A string with new style BEL definitions.
        - constrainStr: A string with constraint definitions.

    Raises
    ------
    ValueError
        If matrixDir of a tile is not '.csv' or '.list' file.
    """
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
            if tile.matrixDir.suffix == ".csv":
                connection = parseMatrix(tile.matrixDir, tile.name)
                for source, sinkList in connection.items():
                    for sink in sinkList:
                        pipStr.append(
                            f"X{x}Y{y},{sink},X{x}Y{y},{source},{8},{sink}.{source}"
                        )
            elif tile.matrixDir.suffix == ".list":
                connection = parseList(tile.matrixDir)
                for sink, source in connection:
                    pipStr.append(
                        f"X{x}Y{y},{source},X{x}Y{y},{sink},{8},{source}.{sink}"
                    )
            else:
                logger.error(
                    f"For model generation {tile.matrixDir} need to a csv or list file"
                )
                raise ValueError

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
                    belv2Str.append("GlobalClk")
                belv2Str.append("BelEnd")
    return (
        "\n".join(pipStr),
        "\n".join(belStr),
        "\n".join(belv2Str),
        "\n".join(constrainStr),
    )


def genNextpnrPairModel(fabric: Fabric):
    pass
