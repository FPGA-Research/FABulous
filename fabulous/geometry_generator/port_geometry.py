"""Port geometry definitions."""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from fabulous.fabric_definition.define import IO, Direction, Side

if TYPE_CHECKING:
    from _csv import Writer


class PortType(Enum):
    """Enumeration for different types of ports in the fabric geometry.

    Defines the various categories of ports that can exist within the fabric:
    - SWITCH_MATRIX: Ports connected to switch matrices
    - JUMP: Jump ports for long-distance connections
    - BEL: Ports connected to Basic Elements of Logic
    """

    SWITCH_MATRIX = "PORT"
    JUMP = "JUMP_PORT"
    BEL = "BEL_PORT"


@dataclass
class PortGeometry:
    """A data structure representing the geometry of a Port.

    Attributes
    ----------
    name : str
        Name of the port
    source_name : str
        Name of the port source
    destName : str
        Name of the port destination
    type : PortType
        Type of the port
    io_direction : IO
        IO direction of the port.
    relX : int
        X coordinate of the port, relative to its parent (bel, switch matrix).
    relY : int
        Y coordinate of the port, relative to its parent (bel, switch matrix).
    side_of_tile : Side
        Side of the tile the port's wire is on.
    offset : int
        Offset to the connected port.
    wire_direction : Direction
        Direction of the ports wire; `Direction.JUMP` for ports that have no
        cardinal direction, matching `TilePort.wire_direction`.
    groupId : int
        ID of the port group.
    groupWires : int
        Number of wires in the port group.
    nextId : int
        ID of the next port in the group.
    """

    name: str
    source_name: str
    destName: str
    type: PortType
    io_direction: IO
    relX: int
    relY: int
    side_of_tile: Side = Side.ANY
    offset: int = 0
    wire_direction: Direction = Direction.JUMP
    groupId: int = 0
    groupWires: int = 0
    nextId: int = 1

    def saveToCSV(self, writer: "Writer") -> None:
        """Save port geometry data to CSV format.

        Writes the port geometry information including type, name,
        source/destination connections, I/O direction, and relative
        position to a CSV file using the provided writer.

        Parameters
        ----------
        writer : Writer
            The CSV `writer` object to use for output
        """
        writer.writerows(
            [
                [self.type.value],
                ["Name"] + [self.name],
                ["Source"] + [self.source_name],
                ["Dest"] + [self.destName],
                ["IO"] + [self.io_direction.value],
                ["RelX"] + [str(self.relX)],
                ["RelY"] + [str(self.relY)],
                [],
            ]
        )
