"""Apply morph-tile replacement plans to a live pyosys design.

The writer is the only morph-tile layer that mutates the pyosys C++ object
graph. It consumes the pure Python replacement result produced by the mapper
and translates each replacement into ``ys.Module``/``ys.Cell`` operations.
"""

import re

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileReplacement,
    MorphTileResult,
    ReplacementPortRef,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.process_tracker import (
    MorphTileProcessTracker,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge

_CONFIG_INDEX_RE = re.compile(r"^(?P<base>.+)\[(?P<index>\d+)\]$")


class MorphTileWriter:
    """Apply solved morph-tile replacements to a live pyosys module.

    Parameters
    ----------
    tile_top_name : str
        Module type used for replacement instances.
    tile_inputs : list[str]
        Tile input ports that may need explicit zero ties when unused.
    include_unused_inputs : bool
        Whether unused tile input ports are tied to zero.
    tracker : MorphTileProcessTracker | None
        Optional progress tracker.
    """

    def __init__(
        self,
        tile_top_name: str,
        tile_inputs: list[str],
        include_unused_inputs: bool = False,
        tracker: MorphTileProcessTracker | None = None,
    ) -> None:
        self.tile_top_name = tile_top_name
        self.tile_inputs = tile_inputs
        self.include_unused_inputs = include_unused_inputs
        self.tracker = tracker

    def apply(self, design: PyosysBridge, result: MorphTileResult) -> None:
        """Apply all replacements in ``result`` to ``design``.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        result : MorphTileResult
            Replacement plan produced by the mapper.
        """
        module = _find_module(design, result.top_name)
        cell_index = _build_cell_index(module)
        if self.tracker is not None:
            self.tracker.start_apply(len(result.replacements))
        for replacement in result.replacements:
            self._apply_one(module, replacement, cell_index)
            if self.tracker is not None:
                self.tracker.applied()
        module.fixup_ports()
        if self.tracker is not None:
            self.tracker.finish_apply()

    def _apply_one(
        self,
        module: ys.Module,
        replacement: MorphTileReplacement,
        cell_index: dict[str, ys.Cell],
    ) -> None:
        """Apply one replacement to a pyosys module.

        Parameters
        ----------
        module : ys.Module
            Module containing the original LUT.
        replacement : MorphTileReplacement
            Replacement to apply.
        cell_index : dict[str, ys.Cell]
            Original cells keyed by clean name.
        """
        old_cell = _find_indexed_cell(
            module,
            cell_index,
            replacement.original_cell_id,
        )
        new_cell = module.addCell(
            _id(f"\\{replacement.replacement_cell_id}"),
            _id(f"\\{self.tile_top_name}"),
        )
        for tile_input, ref in replacement.input_ports.items():
            new_cell.setPort(_id(f"\\{tile_input}"), _ref_to_signal(old_cell, ref))

        if self.include_unused_inputs:
            zero = _const_signal(0, 1)
            for tile_input in self.tile_inputs:
                port_id = _id(f"\\{tile_input}")
                if not new_cell.hasPort(port_id):
                    new_cell.setPort(port_id, zero)

        for tile_output, ref in replacement.output_ports.items():
            new_cell.setPort(_id(f"\\{tile_output}"), _ref_to_signal(old_cell, ref))

        _add_config_ports(new_cell, replacement.config_bits)
        module.remove(old_cell)
        del cell_index[replacement.original_cell_id]


def _find_module(design: PyosysBridge, top_name: str) -> ys.Module:
    """Find a module by clean name.

    Parameters
    ----------
    design : PyosysBridge
        Design containing the module.
    top_name : str
        Clean module name without a leading backslash.

    Returns
    -------
    ys.Module
        Matching pyosys module.

    Raises
    ------
    RuntimeError
        If no module matches.
    """
    for module in design.design.modules_.values():
        if _clean_name(module.name) == top_name:
            return module
    raise RuntimeError(f"Top module '{top_name}' not found")


def _build_cell_index(module: ys.Module) -> dict[str, ys.Cell]:
    """Build a clean-name lookup for cells in a module.

    Parameters
    ----------
    module : ys.Module
        Module containing cells.

    Returns
    -------
    dict[str, ys.Cell]
        Cells keyed by clean Yosys cell name.
    """
    return {_clean_name(cell.name): cell for cell in module.cells_.values()}


def _find_indexed_cell(
    module: ys.Module,
    cell_index: dict[str, ys.Cell],
    cell_id: str,
) -> ys.Cell:
    """Find a cell in a prebuilt clean-name index.

    Parameters
    ----------
    module : ys.Module
        Module containing the cell.
    cell_index : dict[str, ys.Cell]
        Cells keyed by clean Yosys cell name.
    cell_id : str
        Clean cell name without a leading backslash.

    Returns
    -------
    ys.Cell
        Matching pyosys cell.

    Raises
    ------
    RuntimeError
        If no cell matches.
    """
    try:
        return cell_index[cell_id]
    except KeyError as exc:
        raise RuntimeError(
            f"Cell '{cell_id}' not found in module '{module.name}'"
        ) from exc


def _ref_to_signal(cell: ys.Cell, ref: ReplacementPortRef) -> ys.SigSpec:
    """Convert a replacement reference to a pyosys signal.

    Parameters
    ----------
    cell : ys.Cell
        Original cell being replaced.
    ref : ReplacementPortRef
        Replacement signal reference.

    Returns
    -------
    ys.SigSpec
        Single-bit pyosys signal.

    Raises
    ------
    RuntimeError
        If the referenced original-cell port bit is invalid.
    """
    if ref.constant is not None:
        return _const_signal(ref.constant, 1)
    if ref.cell_port is None:
        raise RuntimeError("replacement reference must contain a signal source")
    signal = cell.getPort(_id(f"\\{ref.cell_port.port}"))
    if ref.cell_port.index >= signal.size():
        raise RuntimeError(
            f"Cell '{_clean_name(cell.name)}' port '{ref.cell_port.port}' "
            f"does not have bit {ref.cell_port.index}"
        )
    return ys.SigSpec(signal.at(ref.cell_port.index), 1)


def _add_config_ports(
    cell: ys.Cell,
    config_bits: dict[str, bool | None],
) -> None:
    """Add scalar and indexed config ports to a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Replacement cell that receives solved config ports.
    config_bits : dict[str, bool | None]
        Solved config values keyed by scalar names or indexed names such as
        ``ConfigBits[0]``.
    """
    grouped: dict[str, dict[int, int]] = {}
    for name, value in config_bits.items():
        bit = 1 if bool(value) else 0
        match = _CONFIG_INDEX_RE.match(name)
        if match is None:
            cell.setPort(_id(f"\\{name}"), _const_signal(bit, 1))
            continue
        base = match.group("base")
        index = int(match.group("index"))
        grouped.setdefault(base, {})[index] = bit

    for base, indexed_bits in grouped.items():
        width = max(indexed_bits) + 1
        value = 0
        for index, bit in indexed_bits.items():
            value |= bit << index
        cell.setPort(_id(f"\\{base}"), _const_signal(value, width))


def _const_signal(value: int, width: int) -> ys.SigSpec:
    """Return a constant pyosys signal.

    Parameters
    ----------
    value : int
        Constant value.
    width : int
        Signal width.

    Returns
    -------
    ys.SigSpec
        Constant signal.
    """
    return ys.SigSpec(ys.Const(value, width))


def _id(name: str) -> ys.IdString:
    """Return a pyosys identifier.

    Parameters
    ----------
    name : str
        Yosys identifier text.

    Returns
    -------
    ys.IdString
        pyosys identifier.
    """
    return ys.IdString(name)


def _clean_name(name: object) -> str:
    """Return a Python-friendly Yosys identifier name.

    Parameters
    ----------
    name : object
        pyosys identifier-like object.

    Returns
    -------
    str
        Identifier without a leading Yosys escape backslash.
    """
    text = str(name)
    return text.removeprefix("\\")
