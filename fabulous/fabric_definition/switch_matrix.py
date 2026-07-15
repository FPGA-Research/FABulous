"""Switch matrix construct for the FABulous fabric model.

A tile's switch matrix is the programmable interconnect: which sources may drive
each destination inside the tile. The connectivity is declared in the tile's
matrix file (a `.csv` adjacency matrix or a `.list` of pairs) and read **once**
into this dataclass in canonical port/BEL order. RTL generation
lives in `fabulous.fabric_generator.gen_fabric.gen_switchmatrix`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.custom_exception import InvalidFileType, InvalidSwitchMatrixDefinition
from fabulous.fabric_definition.define import Direction

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_definition.bel import Bel
    from fabulous.fabric_definition.port import Port


def switch_matrix_signal_order(
    ports: list[Port], bels: list[Bel]
) -> tuple[list[str], list[str]]:
    """Return the canonical `(sources, dests)` signal order for a switch matrix.

    This is the ordering the switch matrix uses for its mux outputs (sources)
    and mux inputs (dests): non-JUMP wire signals first (in tile port order),
    then BEL signals, then JUMP wire signals, each de-duplicated first-seen. It
    depends only on the tile's ports and BELs, so a `.list` matrix can be read
    straight into this canonical order without a CSV round trip.

    Parameters
    ----------
    ports : list[Port]
        The tile's ports (`tile.portsInfo`).
    bels : list[Bel]
        The tile's BELs (`tile.bels`).

    Returns
    -------
    tuple[list[str], list[str]]
        `(sources, dests)` - the ordered, de-duplicated mux-output and
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
    matrix_file : Path
        Source file for the switch matrix (`.csv`, `.list`, or hand-written
        HDL).
    connections : dict[str, list[str]]
        Mux output port -> list of mux input signals. Empty for hand-written HDL.
    preserve_list_order : bool
        Whether the mux-input order is significant (MSB-first `.list` order)
        rather than the canonical dest-column order. Recorded once at read time
        and reused when exporting so a round trip is faithful. Default False.
    hdl_config_bits : int | None
        Config-bit count declared by a hand-written HDL matrix. None for parsed
        matrices, whose `no_config_bits` is derived from `connections` instead.
    """

    matrix_file: Path
    connections: dict[str, list[str]]
    preserve_list_order: bool = False
    hdl_config_bits: int | None = None

    @property
    def no_config_bits(self) -> int:
        """Number of configuration bits required by this switch matrix.

        Derived on demand from `connections` (so it tracks any change to them);
        a hand-written HDL matrix has no parsed connections and instead reports
        the count declared in its header (`hdl_config_bits`).

        Returns
        -------
        int
            Total configuration bits across all muxes.
        """
        if self.hdl_config_bits is not None:
            return self.hdl_config_bits
        return self._count_config_bits(self.connections)

    @classmethod
    def from_file(
        cls,
        path: Path,
        tile_name: str,
        ports: list[Port] | None = None,
        bels: list[Bel] | None = None,
        preserve_list_order: bool = False,
    ) -> SwitchMatrix:
        """Construct a SwitchMatrix by parsing the given source file.

        The matrix is read once into its canonical form. A `.csv` is already
        canonical (its authored row/column order is kept). A `.list` is read
        into the canonical port/BEL signal order when `ports` is supplied,
        matching what the old bootstrap-CSV pipeline produced; without `ports`
        it falls back to raw `.list` order (connectivity only, order not
        canonical). When `ports` is supplied every connection is validated
        against the tile's signals (both `.csv` and `.list`); without it no
        validation is possible. Hand-written HDL (`.v`/`.sv`/`.vhdl`/
        `.vhd`) is an escape hatch: only its `NumberOfConfigBits` is read
        and connectivity is left empty.

        Parameters
        ----------
        path : Path
            Path to the switch matrix file. Supported extensions: `.csv`,
            `.list`, `.v`, `.sv`, `.vhdl`, `.vhd`.
        tile_name : str
            Tile name, used only in the hand-written-HDL warning message.
        ports : list[Port] | None, optional
            Tile ports, required to canonicalise a `.list` matrix.
        bels : list[Bel] | None, optional
            Tile BELs, used to canonicalise a `.list` matrix.
        preserve_list_order : bool, optional
            When True, a `.list`'s mux inputs keep the file order (reversed,
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
        # Local import keeps fabric_definition free of a module-level dependency
        # on fabric_generator (the same layering pattern Tile uses for its GDS
        # import); the parser itself only depends on custom_exception.
        from fabulous.fabric_generator.parser.parse_switchmatrix import (
            parseList,
            parseMatrix,
        )

        match path.suffix:
            case ".csv":
                connections = parseMatrix(path, preserve_list_order)
                if ports is not None:
                    sources, dests = switch_matrix_signal_order(ports, bels or [])
                    cls._check_signals(connections, sources, dests, path.name)
            case ".list":
                if ports is not None:
                    connections = cls._canonical_list_connections(
                        path, ports, bels or [], preserve_list_order
                    )
                else:
                    # No tile context to canonicalise against, so honour the
                    # file order; preserve keeps it MSB-first (reversed), the
                    # same convention _canonical_list_connections applies.
                    connections = parseList(path, "source")
                    if preserve_list_order:
                        connections = {
                            k: list(reversed(v)) for k, v in connections.items()
                        }
            case ".v" | ".sv" | ".vhdl" | ".vhd":
                logger.warning(
                    f"Switch matrix for tile {tile_name!r} is read from HDL "
                    f"{path.name}: only NumberOfConfigBits is extracted - the "
                    "connectivity is NOT parsed. This tile therefore contributes "
                    "no tile-internal pips to the nextpnr model and no switch-"
                    "matrix bit mapping to the bitstream (its config bits are "
                    "still reserved). nextpnr cannot route through it; you are "
                    "responsible for ensuring the HDL matches the fabric's ports."
                )
                return cls(
                    matrix_file=path,
                    connections={},
                    preserve_list_order=preserve_list_order,
                    hdl_config_bits=cls._extract_config_bits_from_hdl(path),
                )
            case _:
                raise InvalidFileType(
                    f"Unrecognised switch matrix file extension: {path.suffix}"
                )
        return cls(
            matrix_file=path,
            connections=connections,
            preserve_list_order=preserve_list_order,
        )

    @classmethod
    def _canonical_list_connections(
        cls,
        path: Path,
        ports: list[Port],
        bels: list[Bel],
        preserve_list_order: bool,
    ) -> dict[str, list[str]]:
        """Read a `.list` into canonical `{mux_output: [mux_inputs]}` order.

        Reproduces the old `bootstrapSwitchMatrix` + `list2CSV` +
        `parseMatrix` result without writing a CSV: keys follow the canonical
        source order, and each key's inputs follow the canonical dest-column
        order (or the reversed `.list` order when `preserve_list_order`).

        Parameters
        ----------
        path : Path
            The `.list` file.
        ports : list[Port]
            Tile ports, for the canonical signal order.
        bels : list[Bel]
            Tile BELs, for the canonical signal order.
        preserve_list_order : bool
            Keep `.list` mux-input order (reversed) instead of dest order.

        Returns
        -------
        dict[str, list[str]]
            Canonically ordered connectivity.
        """
        from fabulous.fabric_generator.parser.parse_switchmatrix import parseList

        raw: dict[str, list[str]] = {}
        for source, sink in parseList(path, "pair"):
            raw.setdefault(source, []).append(sink)

        sources, dests = switch_matrix_signal_order(ports, bels)
        dest_index = {d: i for i, d in enumerate(dests)}

        cls._check_signals(raw, sources, dests, path.name)

        connections: dict[str, list[str]] = {}
        for source in sources:
            # Unconnected outputs keep an empty entry so generation's
            # "not connected to anything" check still fires (with final,
            # post-assembly tile ports).
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
            Mux output -> mux inputs to validate.
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

    def to_csv_file(self, path: Path, tile_name: str) -> None:
        """Write the switch matrix connections to a `.csv` file.

        The file is written in the format consumed by `parseMatrix`:
        the header row contains mux-input signal names (column headers),
        each data row is `mux_output_port, v0, v1, ...`, and comment
        annotations (`#,count`) are appended for human readability. Each
        mux input is encoded with a 1-based descending index (not a bare
        `1`) so `parseMatrix` recovers the exact per-mux order regardless of
        the column arrangement, making a `.list` -> `.csv` -> `.list` round
        trip order-faithful.

        Parameters
        ----------
        path : Path
            Destination `.csv` file. Created (or overwritten) by this call.
        tile_name : str
            Tile name written to the top-left cell of the CSV header.
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

        # matrix[row][col]: row = mux output, col = mux input signal. The value
        # is a 1-based descending index (first input = highest) so parseMatrix's
        # (-value, column) sort recovers this exact order, not the column order.
        matrix: list[list[int]] = [[0] * len(mux_inputs_ordered) for _ in mux_outputs]
        for i, signals in enumerate(self.connections.values()):
            n = len(signals)
            for idx, src in enumerate(signals):
                matrix[i][input_index[src]] = n - idx

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
        """Write the switch matrix connections to a `.list` file.

        One line per mux output in the compact form
        `{N}mux_output,[input0|input1|...]` where `N` is the number of mux
        inputs. The `{N}` multiplier repeats the output so `parseList`
        pairs it with each bracketed input. Outputs with no inputs are omitted.

        The inputs are always written reversed (MSB-first), independent of
        `preserve_list_order` - the file always encodes the full order, and the
        reader decides how to interpret it: a `preserve_list_order` read
        recovers this exact order, while a plain read re-derives it from the
        tile's ports.

        Parameters
        ----------
        path : Path
            Destination `.list` file. Created (or overwritten) by this call.
        """
        with path.open("w") as f:
            for mux_output, mux_inputs in self.connections.items():
                if not mux_inputs:
                    continue
                inputs = mux_inputs[::-1]
                f.write(f"{{{len(mux_inputs)}}}{mux_output},[{'|'.join(inputs)}]\n")

    @staticmethod
    def _count_config_bits(connections: dict[str, list[str]]) -> int:
        """Count config bits needed to select each mux's inputs.

        Parameters
        ----------
        connections : dict[str, list[str]]
            Mux output -> mux inputs.

        Returns
        -------
        int
            Total select bits summed over every mux (a mux with fewer than two
            inputs needs none).
        """
        total = 0
        for sources in connections.values():
            if len(sources) >= 2:
                total += (len(sources) - 1).bit_length()
        return total

    @staticmethod
    def _extract_config_bits_from_hdl(path: Path) -> int:
        """Read `NumberOfConfigBits` out of a hand-written HDL matrix.

        Parameters
        ----------
        path : Path
            The `.v`/`.sv`/`.vhdl`/`.vhd` switch matrix file.

        Returns
        -------
        int
            The declared config-bit count, or 0 if none is found (a warning is
            logged in that case).
        """
        content = path.read_text(encoding="utf-8")
        if m := re.search(r"NumberOfConfigBits:\s*(\d+)", content):
            return int(m.group(1))
        logger.warning(
            f"Cannot find NumberOfConfigBits in {path}, assuming 0 config bits."
        )
        return 0
