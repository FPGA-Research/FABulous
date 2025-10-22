"""Port definition module for FPGA fabric.

This module contains the `Port` class, which represents a connection point on a tile
in the FPGA fabric. Ports define the physical and logical characteristics of wires
entering or leaving a tile, including their direction, source and destination names,
offsets, and wire counts. These definitions are typically parsed from a CSV file
that describes the fabric architecture.
"""

from dataclasses import dataclass

from FABulous.fabric_definition.define import IO, Direction, Side


@dataclass(frozen=True, eq=True)
class Port:
    """Store all the port information defined in the CSV file.

    The `name`, `inOut` and `sideOfTile` are added attributes to aid the generation
    of the fabric.

    The `name` and `inOut` are related. If the `inOut` is `INPUT`,
    then the name is the source name of the port on the tile.
    Otherwise, the name is the destination name of the port on the tile.

    The `sideOfTile` defines where the port is physically located on the tile,
    since for a north direction wire, the input will be physically located on
    the south side of the tile.
    The `sideOfTile` will make determining where the port is located much easier.

    Attributes
    ----------
    wireDirection : Direction
        The direction attribute in the CSV file
    sourceName : str
        The source_name attribute in the CSV file
    xOffset : int
        The X-offset attribute in the CSV file
    yOffset : int
        The Y-offset attribute in the CSV file
    destinationName : str
        The destination_name attribute in the CSV file
    wireCount : int
        The wires attribute in the CSV file
    name : str
        The name of the port
    inOut : IO
        The IO direction of the port
    sideOfTile : Side
        The side on which the port is physically located in the tile
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
        """Return a string representation of the `Port` object.

        Returns
        -------
        str
            A formatted string showing the port's key attributes.
        """
        return (
            f"Port("
            f"Name={self.name},"
            f"IO={self.inOut.value},"
            f"XOffset={self.xOffset},"
            f"YOffset={self.yOffset},"
            f"WireCount={self.wireCount},"
            f"Side={self.sideOfTile.value})"
        )

    def getPortRegex(self, indexed: bool = False, prefix: str = "") -> str:
        """Expand port information to individual wire names.

        Generates a regex expression for this port, accounting for wire count and
        offset calculations.

        Parameters
        ----------
        indexed : bool, optional
            If True, wire names use bracket notation (e.g., `port[0]`).
            If False, wire names use simple concatenation (e.g., `port0`).
            Defaults to False.
        prefix : str, optional
            A prefix to prepend to the port name, by default "".

        Returns
        -------
        str
            A regex expression matching the port's wire names.
        """
        wireCount = (abs(self.xOffset) + abs(self.yOffset)) * self.wireCount

        if wireCount == 1 and self.name != "NULL":
            return f"{prefix}{self.name}"
        if indexed:
            return rf"{prefix}{self.name}\[\d+\]"
        return rf"{prefix}{self.name}\d+"

    def expandPortInfoByName(
        self, indexed: bool = False, prefix: str = "", escape: bool = False
    ) -> list[str]:
        """Expand port information to individual wire names.

        Generates a list of individual wire names for this port, accounting for
        wire count and offset calculations. For termination ports (NULL), the
        wire count is multiplied by the Manhattan distance.

        Parameters
        ----------
        indexed : bool, optional
            If True, wire names use bracket notation (e.g., `port[0]`).
            If False, wire names use simple concatenation (e.g., `port0`).
            Defaults to False.
        prefix : str, optional
            A prefix to prepend to the port name, by default "".
        escape : bool, optional
            If True, escape special characters in the port names (e.g., for regex),
            by default False.

        Returns
        -------
        list[str]
            List of individual wire names for this port.
        """
        if self.sourceName == "NULL" or self.destinationName == "NULL":
            wireCount = (abs(self.xOffset) + abs(self.yOffset)) * self.wireCount
        else:
            wireCount = self.wireCount

        if not indexed:
            return [
                f"{prefix}{self.name}{i}"
                for i in range(wireCount)
                if self.name != "NULL"
            ]

        if escape:
            return [
                rf"{prefix}{self.name}\[{i}\]"
                for i in range(wireCount)
                if self.name != "NULL"
            ]
        return [
            f"{prefix}{self.name}[{i}]" for i in range(wireCount) if self.name != "NULL"
        ]

    def expandPortInfoByNameTop(
        self, indexed: bool = False, prefix: str = "", escape: bool = False
    ) -> list[str]:
        """Expand port information for top-level connections.

        Similar to expandPortInfoByName but specifically for top-level tile
        connections. The start index is calculated differently to handle
        the top slice of wires for routing fabric connections.

        Parameters
        ----------
        indexed : bool, optional
            If True, wire names use bracket notation (e.g., `port[0]`).
            If False, wire names use simple concatenation (e.g., `port0`).
            Defaults to False.
        prefix : str, optional
            A prefix to prepend to the port name, by default "".
        escape : bool, optional
            If True, escape special characters in the port names (e.g., for regex),
            by default False.

        Returns
        -------
        list[str]
            List of individual wire names for top-level connections.
        """
        if self.sourceName == "NULL" or self.destinationName == "NULL":
            startIndex = 0
        else:
            startIndex = ((abs(self.xOffset) + abs(self.yOffset)) - 1) * self.wireCount

        wireCount = (abs(self.xOffset) + abs(self.yOffset)) * self.wireCount

        if not indexed:
            return [
                f"{prefix}{self.name}{i}"
                for i in range(startIndex, wireCount)
                if self.name != "NULL"
            ]

        if escape:
            return [
                rf"{prefix}{self.name}\[{i}\]"
                for i in range(startIndex, wireCount)
                if self.name != "NULL"
            ]
        return [
            f"{prefix}{self.name}[{i}]"
            for i in range(startIndex, wireCount)
            if self.name != "NULL"
        ]

    def expandPortInfo(self, mode: str = "SwitchMatrix") -> tuple[list[str], list[str]]:
        """Expand the port information to the individual bit signal.

        If 'Indexed' is in the mode, then brackets are added to the signal name.

        Parameters
        ----------
        mode : str, optional
            Mode for expansion. Defaults to "SwitchMatrix".
            Possible modes are 'all', 'allIndexed', 'Top', 'TopIndexed', 'AutoTop',
            'AutoTopIndexed', 'SwitchMatrix', 'SwitchMatrixIndexed', 'AutoSwitchMatrix',
            'AutoSwitchMatrixIndexed'

        Returns
        -------
        tuple[list[str], list[str]]
            A tuple of two lists. The first list contains the source names of the ports
            and the second list contains the destination names of the ports.
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
                # the following line connects all wires to the switch matrix in the case
                # one port is NULL (typically termination)
                thisRange = (abs(self.xOffset) + abs(self.yOffset)) * self.wireCount
            else:
                # the following line connects all bottom wires to the switch matrix in
                # the case begin and end ports are used
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

        # the following three lines are needed to get the top line[wires] that
        # are actually the connection from a switch matrix to the routing fabric
        startIndex = 0
        if mode in ["Top", "TopIndexed"]:
            startIndex = ((abs(self.xOffset) + abs(self.yOffset)) - 1) * self.wireCount

        elif mode in ["AutoTop", "AutoTopIndexed"]:
            if self.sourceName == "NULL" or self.destinationName == "NULL":
                # in case one port is NULL, then the all the other port wires get
                # connected to the switch matrix.
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
