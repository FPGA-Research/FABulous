"""Switch matrix construct for the FABulous fabric model.

A tile's switch matrix is the programmable interconnect: which sources may drive
each destination inside the tile. The connectivity is declared in the tile's
matrix file (a `.csv` adjacency matrix or a `.list` of pairs) and read **once**
into this dataclass in canonical port/BEL order. RTL generation
lives in `fabulous.fabric_generator.gen_fabric.gen_switchmatrix`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path
from typing import NamedTuple, Self

from loguru import logger

from fabulous.custom_exception import InvalidFileType, InvalidSwitchMatrixDefinition
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction
from fabulous.fabric_definition.port import (
    GenericPort,
    Port,
    SharedPort,
    SlicedPort,
)


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
        The tile's ports (`tile.ports_info`).
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
        if port.wire_direction != Direction.JUMP:
            port_inputs, port_outputs = port.expand_port_info("AutoSwitchMatrix")
            sources += port_inputs
            dests += port_outputs
    for bel in bels:
        sources.extend(bel.input_names)
        dests.extend(bel.output_names)
        dests.extend(p.name for p in bel.external_outputs)
    for port in ports:
        if port.wire_direction == Direction.JUMP:
            port_inputs, port_outputs = port.expand_port_info("AutoSwitchMatrix")
            sources += port_inputs
            dests += port_outputs
    return list(dict.fromkeys(sources)), list(dict.fromkeys(dests))


class SliceRange(NamedTuple):
    """Named tuple representing an inclusive bit slice range.

    Attributes
    ----------
    start : int
        The start index of the slice
    end : int
        The end index of the slice
    """

    start: int
    end: int


@dataclass
class SlicedSignal:
    """A signal representing a slice of a port.

    Attributes
    ----------
    port : GenericPort
        The port being sliced
    slice_range : SliceRange
        The range of the slice (start, end)
    """

    port: GenericPort
    slice_range: SliceRange

    def serialize(self) -> dict:
        """Serialize the sliced signal to a dictionary."""
        return {
            "port": self.port.serialize(),
            "slice_range": self.slice_range._asdict(),
        }


class Mux:
    """Represents a multiplexer in the switch matrix.

    A multiplexer selects one of several input signals to route to a single
    output based on configuration bits.

    Parameters
    ----------
    output : GenericPort
        The output port of the multiplexer
    inputs : list[GenericPort]
        List of input ports to select from
    prefix : str, optional
        Prefix for the mux name. Defaults to ""

    Raises
    ------
    ValueError
        If input port widths don't match output port width
    """

    _output: GenericPort
    _inputs: list[GenericPort]
    _width: int

    def __init__(
        self, output: GenericPort, inputs: list[GenericPort], prefix: str = ""
    ) -> None:
        for p in inputs:
            if p.width != output.width:
                raise ValueError(
                    f"All inputs {inputs} and output {output} must have the same width"
                )

        self._name = f"{prefix}{output.name}"
        self._inputs = list(inputs)
        self._output = output
        self._width = output.width

    def __repr__(self) -> str:
        """Return a string representation of the multiplexer."""
        if len(self.inputs) == 0:
            return f"Mux({self.output.name} <- [no inputs] (cfg: -))"
        input_names = [f"{i.name}" for i in self.inputs]
        return (
            f"Mux({self.output.name} <- [{', '.join(input_names)}] "
            f"(cfg: {self.config_bits} bits))"
        )

    @property
    def name(self) -> str:
        """Get the name of the multiplexer."""
        return self._name

    @property
    def inputs(self) -> tuple[GenericPort, ...]:
        """Get the tuple of input ports."""
        return tuple(self._inputs)

    @property
    def output(self) -> GenericPort:
        """Get the output port."""
        return self._output

    @property
    def width(self) -> int:
        """Get the bit width of the ports."""
        return self._width

    @property
    def config_bits(self) -> int:
        """Get the number of configuration bits needed.

        Returns
        -------
        int
            Number of bits needed to select from N inputs: ceil(log2(N))

        Raises
        ------
        ValueError
            If the mux has no inputs
        """
        if len(self.inputs) == 0:
            raise ValueError("Invalid Mux, no inputs")
        return (len(self.inputs) - 1).bit_length()

    def extend_inputs(self, inputs: Iterable[GenericPort]) -> None:
        """Add more input ports to the multiplexer.

        Parameters
        ----------
        inputs : Iterable[GenericPort]
            Input ports to add

        Raises
        ------
        TypeError
            If an input is not a Port type
        ValueError
            If input width doesn't match output width
        """
        for i in inputs:
            if not isinstance(i, GenericPort):
                raise TypeError("Input must be a Port")

            if i.width != self.output.width:
                raise ValueError(
                    f"All inputs and output must have the same width "
                    f"input port {i} != output port {self.output}"
                )
            self._inputs.append(i)

    def get_flatten_mux(self) -> list[tuple[str, tuple[str, ...]]]:
        """Get the flattened mux inputs and output.

        Returns
        -------
        list[tuple[str, tuple[str, ...]]]
            List of (output_name, (input_names...)) tuples for each bit.
        """
        expanded_input_lists = [input_port.expand() for input_port in self.inputs]

        # Group items by position using zip_longest
        grouped_inputs: list[tuple[str, ...]] = []
        for group in zip_longest(*expanded_input_lists):
            # Filter out None values that zip_longest adds for shorter lists
            grouped_inputs.append(tuple([item for item in group if item is not None]))
        if isinstance(self.output, SharedPort):
            return list(zip(self.output.share_expand(), grouped_inputs, strict=False))
        return list(zip(self.output.expand(), grouped_inputs, strict=False))

    def serialize(self) -> dict:
        """Serialize the mux to a dictionary."""
        return {
            "output": self.output.serialize(),
            "inputs": [input_port.serialize() for input_port in self.inputs],
        }


class MuxPack:
    """High-level interface for building multiplexers with slicing support.

    MuxPack provides a convenient interface for constructing switch matrix
    connections using Verilog-style slicing notation and the //= operator.

    Parameters
    ----------
    port : GenericPort
        The port to create a mux pack for

    Attributes
    ----------
    port : list[Mux]
        The per-bit multiplexers backing this mux pack
    og_port : GenericPort
        The original port the mux pack was created for

    Examples
    --------
    >>> output_pack = MuxPack(output_port)
    >>> input_pack = MuxPack(input_port)
    >>> output_pack //= input_pack  # Connect all bits
    >>> output_pack[3:0] //= input_pack[7:4]  # Connect slices
    """

    port: list[Mux]
    og_port: GenericPort
    _last_get: "MuxPack"

    def __init__(self, port: GenericPort) -> None:
        self.port = []
        self.og_port = port
        for i in range(port.width):
            self.port.append(Mux(SlicedPort(self.og_port, high=i, low=i), []))

    def __getitem__(self, key: slice | int) -> "MuxPack":
        """Return a MuxPack view for the given slice or index."""
        if isinstance(key, slice):
            if key.step is not None:
                raise ValueError("Cannot slice with step")
            if key.start is None:
                raise ValueError(
                    "You must specify a start index. If you are trying to do "
                    "sig[0:4] you should write sig[4:0]"
                )
            if key.start < key.stop:
                raise ValueError(
                    "Start index must be less than stop index, the slicing is "
                    "following the Verilog convention"
                )
            if abs(key.start - key.stop) > self.og_port.width:
                raise ValueError("Slice width is greater than bit width")
            self._last_get = MuxPack(self.og_port)
            # Verilog descending slice [hi:lo] is inclusive of both ends; the
            # backing list is ascending by bit index, so take bits lo..hi.
            self._last_get.port = self.port[key.stop : key.start + 1]
            return self._last_get
        if isinstance(key, int):
            if key >= self.og_port.width:
                raise ValueError("Index out of range")
            self._last_get = MuxPack(self.og_port)
            self._last_get.port = [self.port[key]]
            return self._last_get
        raise ValueError("Invalid slicing for MuxPack")

    def __setitem__(self, key: slice | int, value: "MuxPack") -> None:
        """Reject direct assignment in favour of the //= operator."""
        if self._last_get is value:
            return
        raise TypeError(
            "Cannot perform direct assignment on MuxPort. "
            "Use the //= operator for connecting ports"
        )

    def __ifloordiv__(
        self, other: "MuxPack | list[MuxPack] | tuple[MuxPack, ...]"
    ) -> Self:
        """Connect ports into the muxes using the //= operator."""
        if isinstance(other, (list, tuple)):
            try:
                r = list(
                    zip(*[i.port for i in other if isinstance(i, MuxPack)], strict=True)
                )
            except ValueError:
                raise ValueError(
                    f"not all the object in the list have the same width {other}"
                ) from None
            for o, i in zip(self.port, r, strict=False):
                o.extend_inputs([j.output for j in i])
        elif isinstance(other, MuxPack):
            for k, o in enumerate(self.port):
                o.extend_inputs([other.port[k].output])
        else:
            raise ValueError("Invalid type for Mux construction")  # noqa: TRY004

        return self


@dataclass(frozen=True)
class SwitchMatrix:
    """Encapsulates a tile's switch matrix as its `Mux` objects.

    Read once and immutable: the muxes are fixed at construction and are the
    single source of truth, so the same object can be safely shared or
    deep-copied across fabric-grid placements. `connections` and
    `total_config_bits` are derived views over the muxes; the muxes preserve the
    canonical order the parser produced, so those views reproduce it exactly.

    Attributes
    ----------
    matrix_file : Path
        Source file for the switch matrix (`.csv`, `.list`, or hand-written
        HDL).
    muxes_dict : dict[GenericPort, Mux]
        Output port -> its multiplexer, in canonical order. Holds every
        connection including single-input (direct), zero-input (unused), and
        constant muxes. Empty for hand-written HDL.
    preserve_list_order : bool
        Whether the mux-input order is significant (MSB-first `.list` order)
        rather than the canonical dest-column order. Recorded once at read time
        and reused when exporting so a round trip is faithful. Default False.
    hdl_config_bits : int | None
        Config-bit count declared by a hand-written HDL matrix. None for parsed
        matrices, whose `total_config_bits` is derived from the muxes instead.
    """

    matrix_file: Path
    muxes_dict: dict[GenericPort, Mux] = field(
        default_factory=dict, compare=False, repr=False
    )
    preserve_list_order: bool = False
    hdl_config_bits: int | None = None

    @property
    def muxes(self) -> list[Mux]:
        """Return every multiplexer in canonical order."""
        return list(self.muxes_dict.values())

    @property
    def connections(self) -> dict[str, list[str]]:
        """Derive the `{mux_output: [mux_inputs]}` name map from the muxes.

        This is the flat, name-keyed view the RTL, bitstream-spec, and
        nextpnr-model generators consume; it is regenerated from the muxes on
        each access and preserves their canonical order.

        Returns
        -------
        dict[str, list[str]]
            Mux output name -> ordered list of mux input names.
        """
        return {
            mux.output.name: [i.name for i in mux.inputs]
            for mux in self.muxes_dict.values()
        }

    @property
    def total_config_bits(self) -> int:
        """Number of configuration bits required by this switch matrix.

        Derived on demand from the muxes (so it tracks any change to them); a
        hand-written HDL matrix has no parsed muxes and instead reports the
        count declared in its header (`hdl_config_bits`).

        Returns
        -------
        int
            Total configuration bits across all muxes.
        """
        if self.hdl_config_bits is not None:
            return self.hdl_config_bits
        return sum(
            mux.config_bits for mux in self.muxes_dict.values() if len(mux.inputs) >= 2
        )

    @classmethod
    def from_connections(
        cls,
        matrix_file: Path,
        connections: dict[str, list[str]],
        preserve_list_order: bool = False,
        hdl_config_bits: int | None = None,
    ) -> "SwitchMatrix":
        """Build a SwitchMatrix from a `{mux_output: [mux_inputs]}` name map.

        Each output name becomes a width-1 `Mux` whose inputs are width-1 ports,
        in the map's iteration order, so the resulting muxes carry the exact
        canonical order of `connections`.

        Parameters
        ----------
        matrix_file : Path
            Source file the connections were read from.
        connections : dict[str, list[str]]
            Mux output name -> ordered list of mux input names.
        preserve_list_order : bool, optional
            Whether the mux-input order is the significant MSB-first `.list`
            order. Defaults to False.
        hdl_config_bits : int | None, optional
            Config-bit count for a hand-written HDL matrix. Defaults to None.

        Returns
        -------
        SwitchMatrix
            The constructed switch matrix.
        """
        muxes_dict: dict[GenericPort, Mux] = {}
        for dest, sources in connections.items():
            output_port = Port(name=dest, io_direction=IO.OUTPUT, width=1)
            input_ports: list[GenericPort] = [
                Port(name=src, io_direction=IO.INPUT, width=1) for src in sources
            ]
            muxes_dict[output_port] = Mux(output_port, input_ports)
        return cls(
            matrix_file=matrix_file,
            muxes_dict=muxes_dict,
            preserve_list_order=preserve_list_order,
            hdl_config_bits=hdl_config_bits,
        )

    def __getitem__(self, key: GenericPort) -> Mux:
        """Return the multiplexer driving the given output port."""
        if key in self.muxes_dict:
            return self.muxes_dict[key]
        raise KeyError(f"Output port {key} does not exist in the switch matrix")

    def get_outputs(self) -> list[GenericPort]:
        """Get all output ports in the switch matrix."""
        return [mux.output for mux in self.muxes_dict.values()]

    def get_inputs(self) -> list[GenericPort]:
        """Get all unique input ports in the switch matrix."""
        deduplicating_input: set[GenericPort] = set()

        result_list: list[GenericPort] = []
        for mux in self.muxes_dict.values():
            for i in mux.inputs:
                if i not in deduplicating_input:
                    deduplicating_input.add(i)
                    result_list.append(i)
        return result_list

    def get_port_users(self, port: GenericPort) -> list[GenericPort]:
        """Get all mux outputs that use the given port as an input.

        Parameters
        ----------
        port : GenericPort
            The port to find users for

        Returns
        -------
        list[GenericPort]
            List of output ports that use the given port as input
        """
        sink_list: set[GenericPort] = set()
        for mux in self.muxes_dict.values():
            for i in mux.inputs:
                if i == port:
                    sink_list.add(mux.output)
        return list(sink_list)

    def get_port_drivers(self, port: GenericPort) -> list[GenericPort]:
        """Get all input ports that can drive the given output port.

        Parameters
        ----------
        port : GenericPort
            The output port to find drivers for

        Returns
        -------
        list[GenericPort]
            List of input ports that can drive the given port
        """
        source_list: set[GenericPort] = set()
        for mux in self.muxes_dict.values():
            if mux.output == port:
                for i in mux.inputs:
                    source_list.add(i)
        return list(source_list)

    def serialize(self) -> dict:
        """Serialize the switch matrix to a dictionary."""
        return {
            "muxes": [mux.serialize() for mux in self.muxes],
            "config_bits": self.total_config_bits,
        }

    @classmethod
    def from_file(
        cls,
        path: Path,
        tile_name: str,
        ports: list[Port] | None = None,
        bels: list[Bel] | None = None,
        preserve_list_order: bool = False,
    ) -> "SwitchMatrix":
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
                return cls.from_connections(
                    matrix_file=path,
                    connections={},
                    preserve_list_order=preserve_list_order,
                    hdl_config_bits=cls._extract_config_bits_from_hdl(path),
                )
            case _:
                raise InvalidFileType(
                    f"Unrecognised switch matrix file extension: {path.suffix}"
                )
        return cls.from_connections(
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
