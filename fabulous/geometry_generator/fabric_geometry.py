"""Classes for generating and managing the geometry of FPGA fabrics."""

from csv import writer as csvWriter
from pathlib import Path

from loguru import logger

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.geometry_generator.geometry_obj import Border, Location
from FABulous.geometry_generator.tile_geometry import TileGeometry

GENERATOR_VERSION = "1.0.0"


class FabricGeometry:
    """Fetch and hold geometric information about a fabric.

    Objects of this class can be constructed by passing a `Fabric` object
    and optionally, padding.

    Creates the fabric geometry by processing the given fabric definition
    and automatically generating the complete geometric layout.

    Parameters
    ----------
    fabric : Fabric
        The fabric object from CSV definition files
    padding : int, optional
        Padding used throughout the geometry, by default 8

    Attributes
    ----------
    fabric : Fabric
        The fabric object passed from the CSV definition files
    tileNames : set[str]
        Set of unique tileNames in the fabric
    tileGeomMap : dict[str, TileGeometry]
        Map of the geometry of each tile by name
    tileLocs : list[list[Location]]
        Locations of all tiles in the fabric
    padding : int
        Padding used throughout the geometry, in multiples of the width between wires
    width : int
        Width of the fabric
    height : int
        Height of the fabric
    """

    fabric: Fabric
    tileNames: set[str]
    tileGeomMap: dict[str, TileGeometry]
    tileLocs: list[list[Location]]
    padding: int
    width: int
    height: int

    def __init__(self, fabric: Fabric, padding: int = 8) -> None:
        self.fabric = fabric
        self.tileNames = set()
        self.tileGeomMap = {}
        self.tileLocs = []
        self.padding = padding
        self.width = 0
        self.height = 0

        self.generateGeometry()

    def genNeighbourConstraints(self, queried: TileGeometry) -> None:
        """Generate neighbour constraints for a given tile geometry.

        Parameters
        ----------
        queried : TileGeometry
            The tile geometry to generate constraints for
        """
        for i in range(self.fabric.numberOfRows):
            for j in range(self.fabric.numberOfColumns):
                tile = self.fabric.tile[i][j]
                if tile is None:
                    continue
                tileName = tile.name
                tileGeom = self.tileGeomMap[tileName]

                if tileGeom == queried:
                    searchedTile = None
                    if queried.border == Border.NORTHSOUTH:
                        if i == 0:
                            searchedTile = self.fabric.tile[i + 1][j]
                        else:
                            searchedTile = self.fabric.tile[i - 1][j]

                    elif queried.border == Border.EASTWEST:
                        if j == 0:
                            searchedTile = self.fabric.tile[i][j + 1]
                        else:
                            searchedTile = self.fabric.tile[i][j - 1]

                    if searchedTile is not None:
                        searchedTileName = searchedTile.name
                        queried.neighbourConstraints = self.tileGeomMap[
                            searchedTileName
                        ].wireConstraints

    def generateGeometry(self) -> None:
        """Generate the geometric information from the given fabric object.

        The border attribute is set for tiles that are located at a border of the tile.
        This is done to ensure no stair-like wires being generated for these tiles. The
        distinction left/right and top/bottom is made, to prevent generation of
        horizontal and vertical stair-like wires respectively.
        """
        for i in range(self.fabric.numberOfRows):
            for j in range(self.fabric.numberOfColumns):
                tile = self.fabric.tile[i][j]

                if tile is not None:
                    self.tileNames.add(tile.name)

                    if tile.name not in self.tileGeomMap:
                        self.tileGeomMap[tile.name] = TileGeometry()

                    tileGeom = self.tileGeomMap[tile.name]
                    northSouth = i == 0 or i + 1 == self.fabric.numberOfRows
                    eastWest = j == 0 or j + 1 == self.fabric.numberOfColumns

                    if northSouth and eastWest:
                        tileGeom.border = Border.CORNER
                    elif northSouth:
                        tileGeom.border = Border.NORTHSOUTH
                    elif eastWest:
                        tileGeom.border = Border.EASTWEST

        # generate geometry for central tiles first
        # to avoid conflicts at outer tiles:
        # with the geometry of inner tiles already
        # generated, outer tiles can simply generate
        # their wires such that everything lines up.
        innerTileNames = []
        outerTileNames = []

        for tileName in self.tileNames:
            tileGeom = self.tileGeomMap[tileName]
            self.genNeighbourConstraints(tileGeom)

            if tileGeom.border == Border.NONE:
                innerTileNames.append(tileName)
            else:
                outerTileNames.append(tileName)

        for tileName in self.tileNames:
            tile = self.fabric.getTileByName(tileName)
            tileGeom = self.tileGeomMap[tileName]
            tileGeom.generateGeometry(tile, self.padding)

        # This step is for figuring out, which tile
        # is the widest/tallest in each column/row
        # All tiles are resized to those dimensions
        # in order to form a regular grid.
        tileGeometries = []
        for i in range(self.fabric.numberOfRows):
            tileGeometries.append([])
            for j in range(self.fabric.numberOfColumns):
                tile = self.fabric.tile[i][j]

                if tile is None:
                    tileGeometries[i].append(TileGeometry())
                else:
                    tileGeometries[i].append(self.tileGeomMap[tile.name])

        maxWidths = []
        maxSmRelXValues = []
        maxSmWidths = []
        for j in range(self.fabric.numberOfColumns):
            maxWidth = 0
            maxSmRelX = 0
            maxSmWidth = 0
            for i in range(self.fabric.numberOfRows):
                maxWidth = max(maxWidth, tileGeometries[i][j].width)
                maxSmRelX = max(maxSmRelX, tileGeometries[i][j].smGeometry.relX)
                maxSmWidth = max(maxSmWidth, tileGeometries[i][j].smGeometry.width)
            maxWidths.append(maxWidth)
            maxSmRelXValues.append(maxSmRelX)
            maxSmWidths.append(maxSmWidth)

        lowestSmYCoords = []
        maxHeights = []
        for i in range(self.fabric.numberOfRows):
            lowestSmYCoord = 0
            maxHeight = 0
            for j in range(self.fabric.numberOfColumns):
                smRelY = tileGeometries[i][j].smGeometry.relY
                smHeight = tileGeometries[i][j].smGeometry.height
                lowestSmYCoord = max(lowestSmYCoord, smRelY + smHeight)
                maxHeight = max(maxHeight, tileGeometries[i][j].height)
            lowestSmYCoords.append(lowestSmYCoord)
            maxHeights.append(maxHeight)

        for i in range(self.fabric.numberOfRows):
            for j in range(self.fabric.numberOfColumns):
                tile = self.fabric.tile[i][j]

                if tile is not None:
                    maxWidthInColumn = maxWidths[j]
                    maxSmWidthInColumn = maxSmWidths[j]
                    maxSmRelXInColumn = maxSmRelXValues[j]
                    maxHeightInRow = maxHeights[i]
                    tileGeom = self.tileGeomMap[tile.name]

                    tileGeom.adjustDimensions(
                        maxWidthInColumn,
                        maxHeightInRow,
                        maxSmWidthInColumn,
                        maxSmRelXInColumn,
                    )

        for i in range(self.fabric.numberOfRows):
            self.tileLocs.append([])
            for j in range(self.fabric.numberOfColumns):
                tile = self.fabric.tile[i][j]
                if tile is None:
                    self.tileLocs[i].append(None)
                else:
                    tileX = sum([maxWidths[k] for k in range(j)])
                    tileY = sum([maxHeights[k] for k in range(i)])
                    self.tileLocs[i].append(Location(tileX, tileY))

        # this step is for figuring out the fabric dimensions
        # as tile dimensions are fixed by now.
        # Because of the top left point of the fabric being
        # the origin (0, 0), the fabrics dimensions can be
        # figured out by determining the rightmost and
        # bottommost points of the fabric.
        rightMostX = 0
        bottomMostY = 0
        for i in range(self.fabric.numberOfRows):
            tile = self.fabric.tile[i][-1]
            if tile is not None:
                tileGeom = self.tileGeomMap[tile.name]
                tileLoc = self.tileLocs[i][-1]
                tileRightmostX = tileLoc.x + tileGeom.width
                rightMostX = max(rightMostX, tileRightmostX)

        for j in range(self.fabric.numberOfColumns):
            tile = self.fabric.tile[-1][j]
            if tile is not None:
                tileGeom = self.tileGeomMap[tile.name]
                tileLoc = self.tileLocs[-1][j]
                tileBottommostY = tileLoc.y + tileGeom.height
                bottomMostY = max(bottomMostY, tileBottommostY)

        self.width = rightMostX
        self.height = bottomMostY

        # this step is for rearranging the switch matrices by setting
        # the relX/relY appropriately. This is done to ensure that
        # all inter-tile wires line up correctly.
        adjustedTileNames = set()

        for i in range(self.fabric.numberOfRows):
            for j in range(self.fabric.numberOfColumns):
                tile = self.fabric.tile[i][j]

                if tile is not None and tile.name not in adjustedTileNames:
                    lowestSmYInRow = lowestSmYCoords[i]
                    tileGeom = self.tileGeomMap[tile.name]
                    tileGeom.adjustSmPos(lowestSmYInRow, self.padding)
                    adjustedTileNames.add(tile.name)

        # all tiles should now be adjusted
        assert adjustedTileNames == self.tileNames

        # By now, the geometry of the whole fabric is fixed,
        # hence we can start generating the inter-tile wires.
        for tileName in innerTileNames:
            tileGeom = self.tileGeomMap[tileName]
            tileGeom.generateWires(self.padding)

        for tileName in outerTileNames:
            tileGeom = self.tileGeomMap[tileName]
            tileGeom.generateWires(self.padding)

    def totalWireLines(self) -> int:
        """Return the total amount of lines (segments) of wires of the fabrics routing.

        Can, for instance, be used to initialize the size of datastructures in the
        frontend.
        """
        lineGeomMap = {}
        totalWireLines = 0

        for i in range(self.fabric.numberOfRows):
            for j in range(self.fabric.numberOfColumns):
                tile = self.fabric.tile[i][j]
                if tile is None:
                    continue

                if tile.name not in lineGeomMap:
                    tileGeom = self.tileGeomMap[tile.name]
                    tileLines = tileGeom.totalWireLines()
                    lineGeomMap[tile.name] = tileLines
                    totalWireLines += tileLines
                else:
                    totalWireLines += lineGeomMap[tile.name]

        return totalWireLines

    def saveToCSV(self, fileName: str) -> None:
        """Save geometric information of the given fabric for the graphical frontend.

        Parameters
        ----------
        fileName : str
            The name of the csv file
        """
        logger.info(
            f"Generating geometry csv file for {self.fabric.name} # file name: "
            f"{fileName}"
        )

        with Path(f"{fileName}").open("w", newline="", encoding="utf-8") as file:
            writer = csvWriter(file)

            writer.writerows(
                [
                    ["PARAMS"],
                    ["GeneratorVersion"] + [GENERATOR_VERSION],
                    ["Name"] + [self.fabric.name],
                    ["Rows"] + [str(self.fabric.numberOfRows)],
                    ["Columns"] + [str(self.fabric.numberOfColumns)],
                    ["Width"] + [str(self.width)],
                    ["Height"] + [str(self.height)],
                    ["Lines"] + [str(self.totalWireLines())],
                    [],
                ]
            )

            writer.writerow(["FABRIC_DEF"])
            for i in range(self.fabric.numberOfRows):
                writer.writerow(
                    [
                        tile.name if tile is not None else "Null"
                        for tile in self.fabric.tile[i]
                    ]
                )
            writer.writerow([])

            writer.writerow(["FABRIC_LOCS"])
            for i in range(self.fabric.numberOfRows):
                writer.writerow(
                    [loc if loc is not None else "Null" for loc in self.tileLocs[i]]
                )
            writer.writerows([[], []])

            for tileName in sorted(self.tileNames):
                tileGeometry = self.tileGeomMap[tileName]
                tileGeometry.saveToCSV(writer)

    def __repr__(self) -> str:
        """Return the string representation of the fabric geometry.

        Provides a formatted view of the tile dimensions and locations in a
        grid layout showing the fabric structure.

        Returns
        -------
        str
            Multi-line string showing tile dimensions and locations
        """
        geometry = "Respective dimensions of tiles: \n"
        for i in range(self.fabric.numberOfRows):
            for j in range(self.fabric.numberOfColumns):
                tile = self.fabric.tile[i][j]

                if tile is None:
                    geometry += "Null".ljust(8) + "\t"
                else:
                    geometry += f"{str(self.tileGeomMap[tile.name]).ljust(8)}\t "
            geometry += "\n"
        geometry += "Respective locations of tiles: \n"

        for i in range(self.fabric.numberOfRows):
            for j in range(self.fabric.numberOfColumns):
                loc = self.tileLocs[i][j]
                if loc is None:
                    geometry += "Null".ljust(8) + "\t"
                else:
                    geometry += f"{str(loc).ljust(8)}\t "
            geometry += "\n"
        return geometry
