import pathlib
from dataclasses import dataclass, field

from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.define import IO, Direction, Side
from FABulous.fabric_definition.Gen_IO import Gen_IO
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.Wire import Wire


@dataclass
class Tile:
    """This class is for storing the information about a tile.

    Attributes
    ----------
    name : str
        The name of the tile
    portsInfo : list[Port]
        The list of ports of the tile
    matrixDir : str
        The directory of the tile matrix
    gen_ios : List[Gen_IO]
        The list of GEN_IOs of the tile
    matrixConfigBits : int
        The number of config bits the tile switch matrix has
    withUserCLK : bool
        Whether the tile has a userCLK port. Default is False.
    wireList : list[Wire]
        The list of wires of the tile
    tileDir : str
        The path to the tile folder
    """

    name: str
    portsInfo: list[Port]
    bels: list[Bel]
    matrixDir: pathlib.Path
    matrixConfigBits: int
    gen_ios: list[Gen_IO]
    withUserCLK: bool = False
    wireList: list[Wire] = field(default_factory=list)
    tileDir: pathlib.Path = pathlib.Path()
    partOfSuperTile = False

    def __init__(
        self,
        name: str,
        ports: list[Port],
        bels: list[Bel],
        tileDir: pathlib.Path,
        matrixDir: pathlib.Path,
        gen_ios: list[Gen_IO],
        userCLK: bool,
        configBit: int = 0,
    ) -> None:
        """Initialize a tile with its components.

        Parameters
        ----------
        name : str
            The name of the tile.
        ports : list[Port]
            List of ports for the tile.
        bels : list[Bel]
            List of Basic Elements (BELs) in the tile.
        tileDir : pathlib.Path
            Directory path for the tile.
        matrixDir : pathlib.Path
            Directory path for the tile matrix.
        gen_ios : list[Gen_IO]
            List of general I/O components.
        userCLK : bool
            Whether the tile has user clock functionality.
        configBit : int, optional
            Number of configuration bits for the matrix. Defaults to 0.
        """
        self.name = name
        self.portsInfo = ports
        self.bels = bels
        self.gen_ios = gen_ios
        self.matrixDir = matrixDir
        self.withUserCLK = userCLK
        self.matrixConfigBits = configBit
        self.wireList = []
        self.tileDir = tileDir

    def __eq__(self, __o: object) -> bool:
        """Check equality between tiles based on name.

        Parameters
        ----------
        __o : object
            The object to compare with.

        Returns
        -------
        bool
            True if both tiles have the same name, False otherwise.
        """
        if __o is None or not isinstance(__o, Tile):
            return False
        return self.name == __o.name

    def getWestSidePorts(self) -> list[Port]:
        """Get all ports physically located on the west side of the tile.

        Returns
        -------
        list[Port]
            List of ports on the west side, excluding NULL ports.
        """
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.WEST and p.name != "NULL"
        ]

    def getEastSidePorts(self) -> list[Port]:
        """Get all ports physically located on the east side of the tile.

        Returns
        -------
        list[Port]
            List of ports on the east side, excluding NULL ports.
        """
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.EAST and p.name != "NULL"
        ]

    def getNorthSidePorts(self) -> list[Port]:
        """Get all ports physically located on the north side of the tile.

        Returns
        -------
        list[Port]
            List of ports on the north side, excluding NULL ports.
        """
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.NORTH and p.name != "NULL"
        ]

    def getSouthSidePorts(self) -> list[Port]:
        """Get all ports physically located on the south side of the tile.

        Returns
        -------
        list[Port]
            List of ports on the south side, excluding NULL ports.
        """
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.SOUTH and p.name != "NULL"
        ]

    def getNorthPorts(self, io: IO) -> list[Port]:
        """Get all ports with north wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[Port]
            List of north-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.NORTH and p.name != "NULL" and p.inOut == io
        ]

    def getSouthPorts(self, io: IO) -> list[Port]:
        """Get all ports with south wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[Port]
            List of south-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.SOUTH and p.name != "NULL" and p.inOut == io
        ]

    def getEastPorts(self, io: IO) -> list[Port]:
        """Get all ports with east wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[Port]
            List of east-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.EAST and p.name != "NULL" and p.inOut == io
        ]

    def getWestPorts(self, io: IO) -> list[Port]:
        """Get all ports with west wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[Port]
            List of west-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.WEST and p.name != "NULL" and p.inOut == io
        ]

    def getTileInputNames(self) -> list[str]:
        """Get all input port destination names for the tile.

        Returns
        -------
        list[str]
            List of destination names for input ports, excluding NULL and JUMP direction ports.
        """
        return [
            p.destinationName
            for p in self.portsInfo
            if p.destinationName != "NULL"
            and p.wireDirection != Direction.JUMP
            and p.inOut == IO.INPUT
        ]

    def getTileOutputNames(self) -> list[str]:
        """Get all output port source names for the tile.

        Returns
        -------
        list[str]
            List of source names for output ports, excluding NULL and JUMP direction ports.
        """
        return [
            p.sourceName
            for p in self.portsInfo
            if p.sourceName != "NULL"
            and p.wireDirection != Direction.JUMP
            and p.inOut == IO.OUTPUT
        ]

    @property
    def globalConfigBits(self) -> int:
        """Get the total number of global configuration bits.

        Calculates the sum of matrix configuration bits and all BEL configuration bits.

        Returns
        -------
        int
            Total number of global configuration bits for the tile.
        """
        ret = self.matrixConfigBits

        for b in self.bels:
            ret += b.configBit

        return ret
