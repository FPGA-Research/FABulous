import math
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Tuple


class IO(Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    INOUT = "INOUT"
    NULL = "NULL"


class Direction(Enum):
    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"
    JUMP = "JUMP"


class Side(Enum):
    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"
    ANY = "ANY"


class MultiplexerStyle(Enum):
    CUSTOM = "CUSTOM"
    GENERIC = "GENERIC"


class ConfigBitMode(Enum):
    FRAME_BASED = "FRAME_BASED"
    FLIPFLOP_CHAIN = "FLIPFLOP_CHAIN"


@dataclass(frozen=True, eq=True)
class Port:
    """
    The port data class contains all the port information from the CSV file.
    The `name`, `inOut` and `sideOfTile` are added attributes to aid the generation of the fabric.
    The name and inOut are related. If the inOut is "INPUT" then the name is the source name of the port on the tile.
    Otherwise the name is the destination name of the port on the tile.
    The `sideOfTile` is where the port physically located on the tile, since for a north direction wire, the input will
    be physical located on the south side of the tile. The `sideOfTile` will make determine where the port is located
    much easier.

    Attributes:
        wireDirection (Direction) : The direction attribute in the CSV file
        sourceName (str) : The source_name attribute in the CSV file
        xOffset (int): The X-offset attribute in the CSV file
        yOffset (int): The Y-offset attribute in the CSV file
        destinationName (str): The destination_name attribute in the CSV file
        wireCount (int): The wires attribute in the CSV file
        name (str): The name of the port
        inOut (IO): The IO direction of the port
        sideOfTile (Side): The side which the port is physically located on the tile
    """

    wireDirection: Direction
    sourceName: str
    xOffset: int
    yOffset: int
    destinationName: str
    wireCount: int
    name: str
    inOut: IO
    sideOfTile: Side

    def __repr__(self) -> str:
        return f"Port(Name={self.name}, IO={self.inOut.value}, XOffset={self.xOffset}, YOffset={self.yOffset}, WireCount={self.wireCount}, Side={self.sideOfTile.value})"

    def expandPortInfoByName(self, indexed=False) -> List[str]:
        if self.sourceName == "NULL" or self.destinationName == "NULL":
            wireCount = (abs(self.xOffset) + abs(self.yOffset)) * self.wireCount
        else:
            wireCount = self.wireCount
        if not indexed:
            return [f"{self.name}{i}" for i in range(wireCount) if self.name != "NULL"]
        else:
            return [
                f"{self.name}[{i}]" for i in range(wireCount) if self.name != "NULL"
            ]

    def expandPortInfoByNameTop(self, indexed=False) -> List[str]:
        if self.sourceName == "NULL" or self.destinationName == "NULL":
            startIndex = 0
        else:
            startIndex = ((abs(self.xOffset) + abs(self.yOffset)) - 1) * self.wireCount

        wireCount = (abs(self.xOffset) + abs(self.yOffset)) * self.wireCount

        if not indexed:
            return [
                f"{self.name}{i}"
                for i in range(startIndex, wireCount)
                if self.name != "NULL"
            ]
        else:
            return [
                f"{self.name}[{i}]"
                for i in range(startIndex, wireCount)
                if self.name != "NULL"
            ]

    def expandPortInfo(self, mode="SwitchMatrix") -> Tuple[List[str], List[str]]:
        """
        Expanding the port information to individual bit signal. If indexed is in the mode, then brackets are added to the signal name.

        Args:
            mode (str, optional): mode for expansion. Defaults to "SwitchMatrix".
                                  Possible modes are 'all', 'allIndexed', 'Top', 'TopIndexed', 'AutoTop',
                                  'AutoTopIndexed', 'SwitchMatrix', 'SwitchMatrixIndexed', 'AutoSwitchMatrix',
                                  'AutoSwitchMatrixIndexed'
        Returns:
            Tuple[List[str], List[str]]: A tuple of two lists. The first list contains the source names of the ports and the second list contains the destination names of the ports.
        """
        inputs, outputs = [], []
        thisRange = 0
        openIndex = ""
        closeIndex = ""

        if "Indexed" in mode:
            openIndex = "("
            closeIndex = ")"

        # range (wires-1 downto 0) as connected to the switch matrix
        if mode == "SwitchMatrix" or mode == "SwitchMatrixIndexed":
            thisRange = self.wireCount
        elif mode == "AutoSwitchMatrix" or mode == "AutoSwitchMatrixIndexed":
            if self.sourceName == "NULL" or self.destinationName == "NULL":
                # the following line connects all wires to the switch matrix in the case one port is NULL (typically termination)
                thisRange = (abs(self.xOffset) + abs(self.yOffset)) * self.wireCount
            else:
                # the following line connects all bottom wires to the switch matrix in the case begin and end ports are used
                thisRange = self.wireCount
        # range ((wires*distance)-1 downto 0) as connected to the tile top
        elif mode in [
            "all",
            "allIndexed",
            "Top",
            "TopIndexed",
            "AutoTop",
            "AutoTopIndexed",
        ]:
            thisRange = (abs(self.xOffset) + abs(self.yOffset)) * self.wireCount

        # the following three lines are needed to get the top line[wires] that are actually the connection from a switch matrix to the routing fabric
        startIndex = 0
        if mode in ["Top", "TopIndexed"]:
            startIndex = ((abs(self.xOffset) + abs(self.yOffset)) - 1) * self.wireCount

        elif mode in ["AutoTop", "AutoTopIndexed"]:
            if self.sourceName == "NULL" or self.destinationName == "NULL":
                # in case one port is NULL, then the all the other port wires get connected to the switch matrix.
                startIndex = 0
            else:
                # "normal" case as for the CLBs
                startIndex = (
                    (abs(self.xOffset) + abs(self.yOffset)) - 1
                ) * self.wireCount
        if startIndex == thisRange:
            thisRange = 1

        for i in range(startIndex, thisRange):
            if self.sourceName != "NULL":
                inputs.append(f"{self.sourceName}{openIndex}{str(i)}{closeIndex}")

            if self.destinationName != "NULL":
                outputs.append(f"{self.destinationName}{openIndex}{str(i)}{closeIndex}")
        return inputs, outputs


@dataclass(frozen=True, eq=True)
class Wire:
    """
    This class is for wire connection that span across multiple tiles. If working for connection between two adjacent tiles, the Port class should have all the required information. The main use of this class is to assist model generation, where information at individual wire level is needed.

    Attributes:
        direction (Direction): The direction of the wire
        source (str): The source name of the wire
        xOffset (int): The X-offset of the wire
        yOffset (int): The Y-offset of the wire
        destination (str): The destination name of the wire
        sourceTile (str): The source tile name of the wire
        destinationTile (str): The destination tile name of the wire
    """

    direction: Direction
    source: str
    xOffset: int
    yOffset: int
    destination: str
    sourceTile: str
    destinationTile: str

    def __repr__(self) -> str:
        return f"{self.source}-X{self.xOffset}Y{self.yOffset}>{self.destination}"

    def __eq__(self, __o: Any) -> bool:
        if __o is None or not isinstance(__o, Wire):
            return False
        return self.source == __o.source and self.destination == __o.destination


@dataclass
class Bel:
    """
    Contains all the information about a single BEL. The information is parsed from the directory of the BEL in the CSV
    definition file. There are something to be noted.

    * The parsed name will contains the prefix of the bel.
    * The `sharedPort` attribute is a list of Tuples with name of the port and IO information which is not expanded out yet.
    * If a port is marked as both shared and external, the port is considered as shared. As a result signal like UserCLK will be in shared port list, but not in external port list.


    Attributes:
        src (str): The source directory of the BEL given in the CSV file.
        prefix (str): The prefix of the BEL given in the CSV file.
        name (str): The name of the BEL, extracted from the source directory.
        inputs (list[str]): All the normal input ports of the BEL.
        outputs (list[str]) : All the normal output ports of the BEL.
        externalInput (list[str]) : ALL the external input ports of the BEL.
        externalOutput: (List[str]) : All the external output ports of the BEL.
        configPort (List[str]) : All the config ports of the BEL.
        sharedPort (List[Tuple[str, IO]]) : All the shared ports of the BEL.
        configBit (int) : The number of config bits of the BEL have.
        belFeatureMap (Dict[str, dict]) : The feature map of the BEL.
        withUserCLK (bool) : Whether the BEL has userCLK port. Default is False.
    """

    src: str
    prefix: str
    name: str
    inputs: List[str]
    outputs: List[str]
    externalInput: List[str]
    externalOutput: List[str]
    configPort: List[str]
    sharedPort: List[Tuple[str, IO]]
    configBit: int
    belFeatureMap: Dict[str, dict] = field(default_factory=dict)
    withUserCLK: bool = False

    def __init__(
        self,
        src: str,
        prefix: str,
        internal,
        external,
        configPort,
        sharedPort,
        configBit: int,
        belMap: Dict[str, dict],
        userCLK: bool,
    ) -> None:
        self.src = src
        self.prefix = prefix
        self.name = src.split("/")[-1].split(".")[0]
        self.inputs = [p for p, io in internal if io == IO.INPUT]
        self.outputs = [p for p, io in internal if io == IO.OUTPUT]
        self.externalInput = [p for p, io in external if io == IO.INPUT]
        self.externalOutput = [p for p, io in external if io == IO.OUTPUT]
        self.configPort = configPort
        self.sharedPort = sharedPort
        self.configBit = configBit
        self.belFeatureMap = belMap
        self.withUserCLK = userCLK


@dataclass(frozen=True, eq=True)
class ConfigMem:
    """
    Data structure to store the information about a config memory. Each structure represent a row of entry in the config memory csv file.

    Attributes:
        frameName (str) : The name of the frame
        frameIndex (int) : The index of the frame
        bitUsedInFrame (int) : The number of bits used in the frame
        usedBitMask (int) : The bit mask of the bits used in the frame
        configBitRanges (List[int]) : A list of config bit mapping values
    """

    frameName: str
    frameIndex: int
    bitsUsedInFrame: int
    usedBitMask: str
    configBitRanges: List[int] = field(default_factory=list)


@dataclass
class Tile:
    """
    This class is for storing the information about a tile.

    attributes:
        name (str) : The name of the tile
        portsInfo (List[Port]) : The list of ports of the tile
        matrixDir (str) : The directory of the tile matrix
        globalConfigBits (int) : The number of config bits the tile have
        withUserCLK (bool) : Whether the tile has userCLK port. Default is False.
        wireList (List[Wire]) : The list of wires of the tile
        filePath (str) : The path of the matrix file
    """

    name: str
    portsInfo: List[Port]
    bels: List[Bel]
    matrixDir: str
    globalConfigBits: int = 0
    withUserCLK: bool = False
    wireList: List[Wire] = field(default_factory=list)
    filePath: str = "."
    partOfSuperTile = False

    def __init__(
        self,
        name: str,
        ports: List[Port],
        bels: List[Bel],
        matrixDir: str,
        userCLK: bool,
        configBit: int = 0,
    ) -> None:
        self.name = name
        self.portsInfo = ports
        self.bels = bels
        self.matrixDir = matrixDir
        self.withUserCLK = userCLK
        self.globalConfigBits = configBit
        self.wireList = []
        self.filePath = os.path.split(matrixDir)[0]

        for b in self.bels:
            self.globalConfigBits += b.configBit

    def __eq__(self, __o: Any) -> bool:
        if __o is None or not isinstance(__o, Tile):
            return False
        return self.name == __o.name

    def getWestSidePorts(self) -> List[Port]:
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.WEST and p.name != "NULL"
        ]

    def getEastSidePorts(self) -> List[Port]:
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.EAST and p.name != "NULL"
        ]

    def getNorthSidePorts(self) -> List[Port]:
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.NORTH and p.name != "NULL"
        ]

    def getSouthSidePorts(self) -> List[Port]:
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.SOUTH and p.name != "NULL"
        ]

    def getNorthPorts(self, io: IO) -> List[Port]:
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.NORTH and p.name != "NULL" and p.inOut == io
        ]

    def getSouthPorts(self, io: IO) -> List[Port]:
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.SOUTH and p.name != "NULL" and p.inOut == io
        ]

    def getEastPorts(self, io: IO) -> List[Port]:
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.EAST and p.name != "NULL" and p.inOut == io
        ]

    def getWestPorts(self, io: IO) -> List[Port]:
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.WEST and p.name != "NULL" and p.inOut == io
        ]

    def getTileInputNames(self) -> List[str]:
        return [
            p.destinationName
            for p in self.portsInfo
            if p.destinationName != "NULL"
            and p.wireDirection != Direction.JUMP
            and p.inOut == IO.INPUT
        ]

    def getTileOutputNames(self) -> List[str]:
        return [
            p.sourceName
            for p in self.portsInfo
            if p.sourceName != "NULL"
            and p.wireDirection != Direction.JUMP
            and p.inOut == IO.OUTPUT
        ]


@dataclass
class SuperTile:
    """
    This class is for storing the information about a super tile.

    attributes:
        name (str) : The name of the super tile
        tiles (List[Tile]) : The list of tiles of that build the super tile
        tileMap (List[List[Tile]]) : The map of the tiles of which build the super tile
        bels (List[Bel]) : The list of bels of that the super tile have
        withUserCLK (bool) : Whether the super tile has userCLK port. Default is False.
    """

    name: str
    tiles: List[Tile]
    tileMap: List[List[Tile]]
    bels: List[Bel] = field(default_factory=list)
    withUserCLK: bool = False

    def getPortsAroundTile(self) -> Dict[str, List[List[Port]]]:
        """
        Return all the ports that are around the super tile. The dictionary key is the location of where the tile located in the super tile map with the format of "X{x}Y{y}" where x is the x coordinate of the tile and y is the y coordinate of the tile. The top left tile will have key "00".

        Returns:
            Dict[str, List[List[Port]]]: The dictionary of the ports around the super tile
        """
        ports = {}
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if self.tileMap[y][x] == None:
                    continue
                ports[f"{x},{y}"] = []
                if y - 1 < 0 or self.tileMap[y - 1][x] == None:
                    ports[f"{x},{y}"].append(tile.getNorthSidePorts())
                if x + 1 >= len(self.tileMap[y]) or self.tileMap[y][x + 1] == None:
                    ports[f"{x},{y}"].append(tile.getEastSidePorts())
                if y + 1 >= len(self.tileMap) or self.tileMap[y + 1][x] == None:
                    ports[f"{x},{y}"].append(tile.getSouthSidePorts())
                if x - 1 < 0 or self.tileMap[y][x - 1] == None:
                    ports[f"{x},{y}"].append(tile.getWestSidePorts())
        return ports

    def getInternalConnections(self) -> List[Tuple[List[Port], int, int]]:
        """
        Return all the internal connections of the super tile.

        Returns:
            List[Tuple[List[Port], int, int]]: A list of tuple which contains the internal connected port and the
                                               x and y coordinate of the tile.
        """
        internalConnections = []
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if 0 <= y - 1 < len(self.tileMap) and self.tileMap[y - 1][x] != None:
                    internalConnections.append((tile.getNorthSidePorts(), x, y))
                if 0 <= x + 1 < len(self.tileMap[0]) and self.tileMap[y][x + 1] != None:
                    internalConnections.append((tile.getEastSidePorts(), x, y))
                if 0 <= y + 1 < len(self.tileMap) and self.tileMap[y + 1][x] != None:
                    internalConnections.append((tile.getSouthSidePorts(), x, y))
                if 0 <= x - 1 < len(self.tileMap[0]) and self.tileMap[y][x - 1] != None:
                    internalConnections.append((tile.getWestSidePorts(), x, y))
        return internalConnections


@dataclass
class Fabric:
    """
    This class is for storing the information and hyper parameter of the fabric. All the information is parsed from the
    CSV file.

    Attributes:
        tile (List[List[Tile]]) : The tile map of the fabric
        name (str) : The name of the fabric
        numberOfRow (int) : The number of row of the fabric
        numberOfColumn (int) : The number of column of the fabric
        configMitMode (ConfigBitMode): The configuration bit mode of the fabric. Currently support frame based or ff chain
        frameBitsPerRow (int) : The number of frame bits per row of the fabric
        maxFramesPerCol (int) : The maximum number of frames per column of the fabric
        package (str) : The extra package used by the fabric. Only useful for VHDL output.
        generateDelayInSwitchMatrix (int) : The amount of delay in a switch matrix.
        multiplexerStyle (MultiplexerStyle) : The style of the multiplexer used in the fabric. Currently support custom or generic
        frameSelectWidth (int) : The width of the frame select signal.
        rowSelectWidth (int) : The width of the row select signal.
        desync_flag (int):
        numberOfBRAMs (int) : The number of BRAMs in the fabric.
        superTileEnable (bool) : Whether the fabric has super tile.
        tileDic (Dict[str, Tile]) : A dictionary of tiles used in the fabric. The key is the name of the tile and the value is the tile.
        superTileDic (Dict[str, SuperTile]) : A dictionary of super tiles used in the fabric. The key is the name of the super tile and the value is the super tile.

    """

    tile: List[List[Tile]] = field(default_factory=list)

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

    tileDic: Dict[str, Tile] = field(default_factory=dict)
    superTileDic: Dict[str, SuperTile] = field(default_factory=dict)
    # wires: List[Wire] = field(default_factory=list)
    commonWirePair: List[Tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        Generate all the wire pair in the fabric and get all the wire in the fabric.
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
