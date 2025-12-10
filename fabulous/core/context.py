"""Fabric processing context - holds state for the processing pipeline.

Similar to request context in web frameworks, this holds the fabric state
and writer configuration throughout the processing pipeline.
"""

from collections.abc import Iterable
from pathlib import Path

from fabulous.backend.geometry.generator import GeometryGenerator
from fabulous.backend.hdl.code_generator import CodeGenerator
from fabulous.model.fabric import Fabric
from fabulous.model.supertile import SuperTile
from fabulous.model.tile import Tile


class FabricContext:
    """Fabric processing context - holds state for the processing pipeline.

    Similar to request context in web frameworks, this holds the fabric
    state and writer configuration throughout the processing pipeline.
    Transforms operate on this context, exporters read from it.

    Parameters
    ----------
    writer : CodeGenerator
        Code generator instance (Verilog or VHDL)
    fabric_file : str | Path | None, optional
        Path to fabric definition file. If provided, fabric is loaded automatically.

    Attributes
    ----------
    writer : CodeGenerator
        Code generator for HDL output
    fabric : Fabric | None
        Loaded fabric definition
    geometryGenerator : GeometryGenerator | None
        Geometry generator initialized with fabric
    """

    def __init__(
        self, writer: CodeGenerator, fabric_file: str | Path | None = None
    ) -> None:
        self.writer = writer
        self.fabric: Fabric | None = None
        self.geometryGenerator: GeometryGenerator | None = None
        self._reader = None

        if fabric_file:
            self.load_fabric(Path(fabric_file))

    def load_fabric(self, fabric_path: Path, reader=None) -> None:
        """Load fabric using appropriate reader and initialize geometry generator.

        Parameters
        ----------
        fabric_path : Path
            Path to fabric definition file
        reader : Reader | None, optional
            Optional explicit reader. If None, auto-detects from file extension.

        Raises
        ------
        ValueError
            If file format is not supported
        """
        if reader is None:
            from fabulous.core.reader import create_reader

            reader = create_reader(fabric_path)

        self._reader = reader
        self.fabric = reader.read(fabric_path)
        self.geometryGenerator = GeometryGenerator(self.fabric)

    def set_output(self, output_path: Path) -> None:
        """Set writer output file.

        Parameters
        ----------
        output_path : Path
            Path where generated HDL will be written
        """
        self.writer.outFileName = output_path

    @property
    def tiles(self) -> dict[str, Tile]:
        """Get all tiles in the fabric.

        Returns
        -------
        dict[str, Tile]
            Dictionary of tile name to Tile object
        """
        return self.fabric.tileDic if self.fabric else {}

    @property
    def super_tiles(self) -> dict[str, SuperTile]:
        """Get all super tiles in the fabric.

        Returns
        -------
        dict[str, SuperTile]
            Dictionary of super tile name to SuperTile object
        """
        return self.fabric.superTileDic if self.fabric else {}

    def get_tile(self, name: str, *, required: bool = False) -> Tile | SuperTile | None:
        """Get tile by name with optional validation.

        Parameters
        ----------
        name : str
            Name of the tile to retrieve
        required : bool, optional
            If True, raises KeyError when tile not found. Default False.

        Returns
        -------
        Tile | SuperTile | None
            The tile object, or None if not found and required=False

        Raises
        ------
        RuntimeError
            If no fabric is loaded
        KeyError
            If tile not found and required=True
        """
        if not self.fabric:
            raise RuntimeError("No fabric loaded")
        try:
            return self.fabric.getTileByName(name)
        except KeyError:
            if required:
                raise
            return None

    def get_super_tile(self, name: str, *, required: bool = False) -> SuperTile | None:
        """Get super tile by name with optional validation.

        Parameters
        ----------
        name : str
            Name of the super tile to retrieve
        required : bool, optional
            If True, raises KeyError when super tile not found. Default False.

        Returns
        -------
        SuperTile | None
            The super tile object, or None if not found and required=False

        Raises
        ------
        RuntimeError
            If no fabric is loaded
        KeyError
            If super tile not found and required=True
        """
        if not self.fabric:
            raise RuntimeError("No fabric loaded")
        try:
            return self.fabric.getSuperTileByName(name)
        except KeyError:
            if required:
                raise
            return None

    def get_tiles(self) -> Iterable[Tile]:
        """Get all tiles in the fabric.

        Returns
        -------
        Iterable[Tile]
            Collection of all tiles

        Raises
        ------
        RuntimeError
            If no fabric is loaded
        """
        if not self.fabric:
            raise RuntimeError("No fabric loaded")
        return self.fabric.tileDic.values()

    def get_super_tiles(self) -> Iterable[SuperTile]:
        """Get all super tiles in the fabric.

        Returns
        -------
        Iterable[SuperTile]
            Collection of all super tiles

        Raises
        ------
        RuntimeError
            If no fabric is loaded
        """
        if not self.fabric:
            raise RuntimeError("No fabric loaded")
        return self.fabric.superTileDic.values()
