"""Switch matrix construct for the FABulous fabric model.

A tile's switch matrix is the programmable interconnect: which sources may drive
each destination inside the tile. The connectivity is declared in the tile's
matrix file (a `.csv` adjacency matrix or a `.list` of pairs) and read **once**
into this dataclass in canonical port/BEL order. It gives the switch matrix a
first-class home in the fabric model so callers work with a `SwitchMatrix` object
instead of re-deriving file dispatch and parsing at every site. RTL generation
lives in :mod:`fabulous.fabric_generator.gen_fabric.gen_switchmatrix`.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.custom_exception import InvalidFileType, InvalidSwitchMatrixDefinition
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix

if TYPE_CHECKING:
    from fabulous.fabric_definition.bel import Bel
    from fabulous.fabric_definition.port import Port


def switch_matrix_signal_order(
    ports: "list[Port]", bels: "list[Bel]"
) -> tuple[list[str], list[str]]:
    """Return the canonical ``(sources, dests)`` signal order for a switch matrix.

    This is the ordering the switch matrix uses for its mux outputs (sources)
    and mux inputs (dests): non-JUMP wire signals first (in tile port order),
    then BEL signals, then JUMP wire signals, each de-duplicated first-seen. It
    depends only on the tile's ports and BELs, so a ``.list`` matrix can be read
    straight into this canonical order without a CSV round trip.

    Parameters
    ----------
    ports : list[Port]
        The tile's ports (``tile.portsInfo``).
    bels : list[Bel]
        The tile's BELs (``tile.bels``).

    Returns
    -------
    tuple[list[str], list[str]]
        ``(sources, dests)`` — the ordered, de-duplicated mux-output and
        mux-input signal names.
    """
    sources: list[str] = []
    dests: list[str] = []
    for port in ports:
        if port.wireDirection != Direction.JUMP:
            port_inputs, port_outputs = port.expandPortInfo("AutoSwitchMatrix")
            sources += port_inputs
            dests += port_outputs
    for bel in bels:
        sources.extend(bel.inputs)
        dests.extend(bel.outputs + bel.externalOutput)
    for port in ports:
        if port.wireDirection == Direction.JUMP:
            port_inputs, port_outputs = port.expandPortInfo("AutoSwitchMatrix")
            sources += port_inputs
            dests += port_outputs
    return list(dict.fromkeys(sources)), list(dict.fromkeys(dests))


@dataclass(frozen=True)
class SwitchMatrix:
    """Encapsulates a tile's switch matrix: source file and connectivity.

    Read once and immutable: the connectivity is fixed at construction, so the
    same object can be safely shared or deep-copied across fabric-grid placements.

    Attributes
    ----------
    matrixFile : Path
        Source file for the switch matrix (``.csv``, ``.list``, or hand-written
        HDL).
    connections : dict[str, list[str]]
        Mux output port → list of mux input signals. Empty for hand-written HDL.
    noConfigBits : int
        Number of configuration bits required by this switch matrix.
    """

    matrixFile: Path
    connections: dict[str, list[str]]
    noConfigBits: int

    @classmethod
    def from_file(
        cls,
        path: Path,
        tile_name: str,
        ports: "list[Port] | None" = None,
        bels: "list[Bel] | None" = None,
        preserve_list_order: bool = False,
    ) -> "SwitchMatrix":
        """Construct a SwitchMatrix by parsing the given source file.

        The matrix is read once into its canonical form. A ``.csv`` is already
        canonical (its authored row/column order is kept). A ``.list`` is read
        into the canonical port/BEL signal order when ``ports`` is supplied,
        matching what the old bootstrap-CSV pipeline produced; without ``ports``
        it falls back to raw ``.list`` order (connectivity only, order not
        canonical). When ``ports`` is supplied every connection is validated
        against the tile's signals (both ``.csv`` and ``.list``); without it no
        validation is possible. Hand-written HDL (``.v``/``.sv``/``.vhdl``/
        ``.vhd``) is an escape hatch: only its ``NumberOfConfigBits`` is read
        and connectivity
        is left empty (the tile supplies its own switch matrix module).

        Parameters
        ----------
        path : Path
            Path to the switch matrix file. Supported extensions: ``.csv``,
            ``.list``, ``.v``, ``.sv``, ``.vhdl``, ``.vhd``.
        tile_name : str
            Tile name, required for CSV tile-name validation.
        ports : list[Port] | None, optional
            Tile ports, required to canonicalise a ``.list`` matrix.
        bels : list[Bel] | None, optional
            Tile BELs, used to canonicalise a ``.list`` matrix.
        preserve_list_order : bool, optional
            When True, a ``.list``'s mux inputs keep the file order (reversed,
            MSB-first) instead of the canonical dest-column order. Defaults to
            False.

        Returns
        -------
        SwitchMatrix
            Fully initialised switch matrix instance.

        Raises
        ------
        InvalidFileType
            If the file extension is not recognised.
        """
        match path.suffix:
            case ".csv":
                connections = parseMatrix(path, tile_name)
                if ports is not None:
                    sources, dests = switch_matrix_signal_order(ports, bels or [])
                    cls._check_signals(connections, sources, dests, path.name)
            case ".list":
                if ports is not None:
                    connections = cls._canonical_list_connections(
                        path, ports, bels or [], preserve_list_order
                    )
                else:
                    connections = parseList(path, "source")
            case ".v" | ".sv" | ".vhdl" | ".vhd":
                logger.warning(
                    f"Switch matrix for tile {tile_name!r} is read from HDL "
                    f"{path.name}: only NumberOfConfigBits is extracted — the "
                    "connectivity is NOT parsed or checked. You are responsible "
                    "for ensuring the HDL matches the fabric's expected ports."
                )
                return cls(
                    matrixFile=path,
                    connections={},
                    noConfigBits=cls._extract_config_bits_from_hdl(path),
                )
            case _:
                raise InvalidFileType(
                    f"Unrecognised switch matrix file extension: {path.suffix}"
                )
        return cls(
            matrixFile=path,
            connections=connections,
            noConfigBits=cls._count_config_bits(connections),
        )

    @classmethod
    def _canonical_list_connections(
        cls,
        path: Path,
        ports: "list[Port]",
        bels: "list[Bel]",
        preserve_list_order: bool,
    ) -> dict[str, list[str]]:
        """Read a ``.list`` into canonical ``{mux_output: [mux_inputs]}`` order.

        Reproduces the old ``bootstrapSwitchMatrix`` + ``list2CSV`` +
        ``parseMatrix`` result without writing a CSV: keys follow the canonical
        source order, and each key's inputs follow the canonical dest-column
        order (or the reversed ``.list`` order when ``preserve_list_order``).

        Parameters
        ----------
        path : Path
            The ``.list`` file.
        ports : list[Port]
            Tile ports, for the canonical signal order.
        bels : list[Bel]
            Tile BELs, for the canonical signal order.
        preserve_list_order : bool
            Keep ``.list`` mux-input order (reversed) instead of dest order.

        Returns
        -------
        dict[str, list[str]]
            Canonically ordered connectivity.
        """
        raw: dict[str, list[str]] = {}
        for source, sink in parseList(path, "pair"):
            raw.setdefault(source, []).append(sink)

        sources, dests = switch_matrix_signal_order(ports, bels)
        dest_index = {d: i for i, d in enumerate(dests)}

        cls._check_signals(raw, sources, dests, path.name)

        connections: dict[str, list[str]] = {}
        for source in sources:
            # Unconnected outputs keep an empty entry so generation's
            # "not connected to anything" check still fires.
            sinks = raw.get(source, [])
            if preserve_list_order:
                connections[source] = list(reversed(sinks))
            else:
                connections[source] = sorted(sinks, key=lambda d: dest_index[d])
        return connections

    @staticmethod
    def _check_signals(
        connections: dict[str, list[str]],
        sources: list[str],
        dests: list[str],
        filename: str,
    ) -> None:
        """Raise if a connection names a signal the tile does not have.

        Parameters
        ----------
        connections : dict[str, list[str]]
            Mux output → mux inputs to validate.
        sources : list[str]
            Valid mux-output (source) signals of the tile.
        dests : list[str]
            Valid mux-input (dest) signals of the tile.
        filename : str
            Matrix file name, used in the error message.

        Raises
        ------
        InvalidSwitchMatrixDefinition
            If any mux output or input is not a signal of the tile.
        """
        source_set, dest_set = set(sources), set(dests)
        for mux_out, mux_ins in connections.items():
            if mux_out not in source_set:
                raise InvalidSwitchMatrixDefinition(
                    f"Switch matrix output {mux_out!r} in {filename} is not a "
                    "signal of the tile"
                )
            for mux_in in mux_ins:
                if mux_in not in dest_set:
                    raise InvalidSwitchMatrixDefinition(
                        f"Switch matrix input {mux_in!r} (driving {mux_out!r}) in "
                        f"{filename} is not a signal of the tile"
                    )

    def to_csv_file(
        self,
        path: Path,
        tile_name: str,
        preserve_list_order: bool = False,
    ) -> None:
        """Write the switch matrix connections to a ``.csv`` file.

        The file is written in the format consumed by :func:`parseMatrix`:
        the header row contains mux-input signal names (column headers),
        each data row is ``mux_output_port, v0, v1, …``, and comment
        annotations (``#,count``) are appended for human readability.

        Parameters
        ----------
        path : Path
            Destination ``.csv`` file. Created (or overwritten) by this call.
        tile_name : str
            Tile name written to the top-left cell of the CSV header.
        preserve_list_order : bool, optional
            When True, encode mux-input ordering with a 1-based descending
            index so that :func:`parseMatrix` recovers the original list-file
            ordering. Defaults to False (all connections written as ``1``).
        """
        # Column headers = unique mux-input signals, in first-seen order.
        mux_inputs_ordered: list[str] = []
        seen: set[str] = set()
        for signals in self.connections.values():
            for s in signals:
                if s not in seen:
                    seen.add(s)
                    mux_inputs_ordered.append(s)

        input_index = {s: j for j, s in enumerate(mux_inputs_ordered)}
        mux_outputs = list(self.connections.keys())

        # matrix[row][col]: row = mux output, col = mux input signal
        matrix: list[list[int]] = [[0] * len(mux_inputs_ordered) for _ in mux_outputs]
        for i, signals in enumerate(self.connections.values()):
            n = len(signals)
            for idx, src in enumerate(signals):
                matrix[i][input_index[src]] = (n - idx) if preserve_list_order else 1

        col_counts = [
            sum(1 for row in matrix if row[j] != 0)
            for j in range(len(mux_inputs_ordered))
        ]

        with path.open("w") as f:
            f.write(f"{tile_name},{','.join(mux_inputs_ordered)}\n")
            for i, dest in enumerate(mux_outputs):
                row_nonzero = sum(1 for v in matrix[i] if v != 0)
                f.write(
                    f"{dest},{','.join(str(v) for v in matrix[i])},#,{row_nonzero}\n"
                )
            f.write(f"#,{','.join(str(c) for c in col_counts)}")

    def to_list_file(self, path: Path) -> None:
        """Write the switch matrix connections to a ``.list`` file.

        Each connection is written as ``mux_output,mux_input`` on its own line,
        matching the format consumed by :func:`parseList`.

        Parameters
        ----------
        path : Path
            Destination ``.list`` file. Created (or overwritten) by this call.
        """
        with path.open("w") as f:
            for mux_output, mux_inputs in self.connections.items():
                for mux_input in mux_inputs:
                    f.write(f"{mux_output},{mux_input}\n")

    @staticmethod
    def _count_config_bits(connections: dict[str, list[str]]) -> int:
        total = 0
        for sources in connections.values():
            if len(sources) >= 2:
                total += (len(sources) - 1).bit_length()
        return total

    @staticmethod
    def _extract_config_bits_from_hdl(path: Path) -> int:
        content = path.read_text(encoding="utf-8")
        if m := re.search(r"NumberOfConfigBits:\s*(\d+)", content):
            return int(m.group(1))
        logger.warning(
            f"Cannot find NumberOfConfigBits in {path}, assuming 0 config bits."
        )
        return 0
