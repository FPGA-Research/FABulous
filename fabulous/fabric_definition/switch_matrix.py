"""Switch matrix construct for the FABulous fabric model.

A tile's switch matrix is the programmable interconnect: which sources may drive
each destination inside the tile. The connectivity is declared in the tile's
matrix file (a ``.csv`` adjacency matrix or a ``.list`` of pairs) and parsed by
:mod:`fabulous.fabric_generator.parser.parse_switchmatrix`. This light dataclass
gives that switch matrix a first-class home in the fabric model so callers work
with a ``SwitchMatrix`` object instead of re-deriving the file dispatch and
parsing at every site.
"""

from dataclasses import dataclass
from pathlib import Path

from fabulous.custom_exception import InvalidFileType


@dataclass
class SwitchMatrix:
    """A tile's switch matrix: its programmable interconnect connectivity.

    Attributes
    ----------
    name : str
        Tile name. Must match the top-left header cell of a ``.csv`` matrix.
    matrix_dir : Path
        Path to the matrix file, either a `.csv` adjacency matrix or a
        `.list` of connection pairs.
    config_bits : int
        Number of configuration bits the switch matrix occupies, by default 0.
    """

    name: str
    matrix_dir: Path
    config_bits: int = 0

    def pips(self) -> list[tuple[str, str]]:
        """Return the switch-matrix connection pairs as ``(source, sink)`` tuples.

        Both file formats are normalized to the same list of pairs, in the order
        the file declares them.

        Returns
        -------
        list[tuple[str, str]]
            One ``(source, sink)`` tuple per programmable connection.

        Raises
        ------
        InvalidFileType
            If the matrix file is neither a ``.csv`` nor a ``.list`` file.
        """
        # Function-local import keeps fabric_definition free of a module-level
        # dependency on fabric_generator (the same pattern Tile uses for its GDS
        # import); the parser itself only depends on custom_exception.
        from fabulous.fabric_generator.parser.parse_switchmatrix import (
            parseList,
            parseMatrix,
        )

        suffix = self.matrix_dir.suffix
        if suffix == ".csv":
            connections = parseMatrix(self.matrix_dir, self.name)
            return [
                (source, sink)
                for source, sinks in connections.items()
                for sink in sinks
            ]
        if suffix == ".list":
            return parseList(self.matrix_dir)
        raise InvalidFileType(f"File {self.matrix_dir} is not a .csv or .list file")
