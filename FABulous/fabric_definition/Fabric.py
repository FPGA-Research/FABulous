from dataclasses import dataclass, field
from FABulous.fabric_definition.define import (
    Direction,
    ConfigBitMode,
    MultiplexerStyle,
    IO,
)
from FABulous.fabric_definition.Wire import Wire
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.ConfigMem import ConfigMem


@dataclass
class Fabric:
    """This class is for storing the information and hyperparameters of the fabric. All the information is parsed from the
    CSV file.

    Attributes
    ----------
    tile : list[list[Tile]]
        The tile map of the fabric
    name : str
        The name of the fabric
    numberOfRow : int
        The number of rows of the fabric
    numberOfColumn : int
        The number of columns of the fabric
    configMitMode : ConfigBitMode
        The configuration bit mode of the fabric. Currently supports frame based or ff chain
    frameBitsPerRow : int
        The number of frame bits per row of the fabric
    maxFramesPerCol : int
        The maximum number of frames per column of the fabric
    package : str
        The extra package used by the fabric. Only useful for VHDL output.
    generateDelayInSwitchMatrix : int
        The amount of delay in a switch matrix.
    multiplexerStyle : MultiplexerStyle
        The style of the multiplexer used in the fabric. Currently supports custom or generic
    frameSelectWidth : int
        The width of the frame select signal.
    rowSelectWidth : int
        The width of the row select signal.
    desync_flag : int
        The flag indicating desynchronization status, used to manage timing issues within the fabric.
    numberOfBRAMs : int
        The number of BRAMs in the fabric.
    superTileEnable : bool
        Whether the fabric has super tile.
    tileDic : dict[str, Tile]
        A dictionary of tiles used in the fabric. The key is the name of the tile and the value is the tile.
    superTileDic : dict[str, SuperTile]
        A dictionary of super tiles used in the fabric. The key is the name of the super tile and the value is the super tile.
    """

    tile: list[list[Tile]] = field(default_factory=list)

    name: str = "eFPGA"
    numberOfRows: int = 15
    numberOfColumns: int = 15
    configBitMode: ConfigBitMode = ConfigBitMode.FRAME_BASED
    frameBitsPerRow: int = 32
    maxFramesPerCol: int = 20
    package: str = "use work.my_package.all"
    generateDelayInSwitchMatrix: int = 80
    multiplexerStyle: MultiplexerStyle = MultiplexerStyle.CUSTOM
    frameSelectWidth: int = 5
    rowSelectWidth: int = 5
    desync_flag: int = 20
    numberOfBRAMs: int = 10
    superTileEnable: bool = True

    tileDic: dict[str, Tile] = field(default_factory=dict)
    superTileDic: dict[str, SuperTile] = field(default_factory=dict)
    # wires: list[Wire] = field(default_factory=list)
    commonWirePair: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Generate all the wire pairs in the fabric and get all the wires in the fabric.

        The wire pair are used during model generation when some of the signals have source or destination of "NULL".

        The wires are used during model generation to work with wire that going cross tile.
        """
        for row in self.tile:
            for tile in row:
                if tile == None:
                    continue
                for port in tile.portsInfo:
                    self.commonWirePair.append((port.sourceName, port.destinationName))

        self.commonWirePair = list(dict.fromkeys(self.commonWirePair))
        self.commonWirePair = [
            (i, j) for i, j in self.commonWirePair if i != "NULL" and j != "NULL"
        ]

        for y, row in enumerate(self.tile):
            for x, tile in enumerate(row):
                if tile == None:
                    continue
                for port in tile.portsInfo:
                    if (
                        abs(port.xOffset) <= 1
                        and abs(port.yOffset) <= 1
                        and port.sourceName != "NULL"
                        and port.destinationName != "NULL"
                    ):
                        for i in range(port.wireCount):
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{port.sourceName}{i}",
                                    xOffset=port.xOffset,
                                    yOffset=port.yOffset,
                                    destination=f"{port.destinationName}{i}",
                                    sourceTile="",
                                    destinationTile="",
                                )
                            )
                    elif port.sourceName != "NULL" and port.destinationName != "NULL":
                        # clamp the xOffset to 1 or -1
                        value = min(max(port.xOffset, -1), 1)
                        cascadedI = 0
                        for i in range(port.wireCount * abs(port.xOffset)):
                            if i < port.wireCount:
                                cascadedI = i + port.wireCount * (abs(port.xOffset) - 1)
                            else:
                                cascadedI = i - port.wireCount
                                tile.wireList.append(
                                    Wire(
                                        direction=Direction.JUMP,
                                        source=f"{port.destinationName}{i}",
                                        xOffset=0,
                                        yOffset=0,
                                        destination=f"{port.sourceName}{i}",
                                        sourceTile=f"X{x}Y{y}",
                                        destinationTile=f"X{x}Y{y}",
                                    )
                                )
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{port.sourceName}{i}",
                                    xOffset=value,
                                    yOffset=port.yOffset,
                                    destination=f"{port.destinationName}{cascadedI}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x+value}Y{y+port.yOffset}",
                                )
                            )

                        # clamp the yOffset to 1 or -1
                        value = min(max(port.yOffset, -1), 1)
                        cascadedI = 0
                        for i in range(port.wireCount * abs(port.yOffset)):
                            if i < port.wireCount:
                                cascadedI = i + port.wireCount * (abs(port.yOffset) - 1)
                            else:
                                cascadedI = i - port.wireCount
                                tile.wireList.append(
                                    Wire(
                                        direction=Direction.JUMP,
                                        source=f"{port.destinationName}{i}",
                                        xOffset=0,
                                        yOffset=0,
                                        destination=f"{port.sourceName}{i}",
                                        sourceTile=f"X{x}Y{y}",
                                        destinationTile=f"X{x}Y{y}",
                                    )
                                )
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{port.sourceName}{i}",
                                    xOffset=port.xOffset,
                                    yOffset=value,
                                    destination=f"{port.destinationName}{cascadedI}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x+port.xOffset}Y{y+value}",
                                )
                            )
                    elif port.sourceName != "NULL" and port.destinationName == "NULL":
                        sourceName = port.sourceName
                        destName = ""
                        try:
                            index = [i for i, _ in self.commonWirePair].index(
                                port.sourceName
                            )
                            sourceName = self.commonWirePair[index][0]
                            destName = self.commonWirePair[index][1]
                        except:
                            # if is not in a common pair wire we assume the source name is same as destination name
                            destName = sourceName

                        value = min(max(port.xOffset, -1), 1)
                        for i in range(port.wireCount * abs(port.xOffset)):
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{sourceName}{i}",
                                    xOffset=value,
                                    yOffset=port.yOffset,
                                    destination=f"{destName}{i}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x+value}Y{y+port.yOffset}",
                                )
                            )

                        value = min(max(port.yOffset, -1), 1)
                        for i in range(port.wireCount * abs(port.yOffset)):
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{sourceName}{i}",
                                    xOffset=port.xOffset,
                                    yOffset=value,
                                    destination=f"{destName}{i}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x+port.xOffset}Y{y+value}",
                                )
                            )
                tile.wireList = list(dict.fromkeys(tile.wireList))

    def __repr__(self) -> str:
        fabric = ""
        for i in range(self.numberOfRows):
            for j in range(self.numberOfColumns):
                if self.tile[i][j] is None:
                    fabric += "Null".ljust(15) + "\t"
                else:
                    fabric += f"{str(self.tile[i][j].name).ljust(15)}\t"
            fabric += "\n"

        fabric += f"\n"
        fabric += f"numberOfColumns: {self.numberOfColumns}\n"
        fabric += f"numberOfRows: {self.numberOfRows}\n"
        fabric += f"configBitMode: {self.configBitMode}\n"
        fabric += f"frameBitsPerRow: {self.frameBitsPerRow}\n"
        fabric += f"maxFramesPerCol: {self.maxFramesPerCol}\n"
        fabric += f"package: {self.package}\n"
        fabric += f"generateDelayInSwitchMatrix: {self.generateDelayInSwitchMatrix}\n"
        fabric += f"multiplexerStyle: {self.multiplexerStyle}\n"
        fabric += f"superTileEnable: {self.superTileEnable}\n"
        fabric += f"tileDic: {list(self.tileDic.keys())}\n"
        return fabric

    def getTileByName(self, name: str) -> Tile:
        return self.tileDic[name]

    def getSuperTileByName(self, name: str) -> SuperTile:
        return self.superTileDic[name]
