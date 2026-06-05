"""Apply selected multi-map replacements to a pyosys design.

The writer replaces several original LUT cells with one candidate tile cell. It reuses
original cell port signals as references, then removes all grouped LUT cells after the
new tile instance is wired.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pyosys.libyosys as ys

if TYPE_CHECKING:
    from collections.abc import Callable

    from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
        InputPortSource,
        MultiMapReplacement,
    )
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge

_CONFIG_INDEX_RE = re.compile(r"^(?P<base>.+)\[(?P<index>\d+)\]$")


class MultiMapWriter:
    """Apply multi-LUT replacement records to a live pyosys design.

    Parameters
    ----------
    tile_top_name : str
        Replacement tile module name.
    tile_inputs : list[str]
        Candidate tile input ports.
    include_unused_inputs : bool
        Whether unused tile input ports should be tied to zero.
    """

    def __init__(
        self,
        tile_top_name: str,
        tile_inputs: list[str],
        include_unused_inputs: bool = False,
    ) -> None:
        self.tile_top_name = tile_top_name
        self.tile_inputs = tile_inputs
        self.include_unused_inputs = include_unused_inputs

    def apply(
        self,
        design: PyosysBridge,
        top_name: str,
        replacements: tuple[MultiMapReplacement, ...],
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        """Apply all multi-map replacements to a design.

        Parameters
        ----------
        design : PyosysBridge
            Live pyosys design to mutate.
        top_name : str
            Top module name.
        replacements : tuple[MultiMapReplacement, ...]
            Selected replacements.
        progress : Callable[[dict[str, object]], None] | None
            Optional callback receiving writer progress events.
        """
        module = _find_module(design, top_name)
        removed_luts = sum(
            len(replacement.original_cell_ids) for replacement in replacements
        )
        _emit_writer_event(
            progress,
            "start",
            {
                "replacements": len(replacements),
                "removed_luts": removed_luts,
            },
        )
        applied_removed_luts = 0
        for index, replacement in enumerate(replacements, start=1):
            self._apply_one(module, replacement)
            applied_removed_luts += len(replacement.original_cell_ids)
            _emit_writer_event(
                progress,
                "progress",
                {
                    "current": index,
                    "total": len(replacements),
                    "removed_luts": applied_removed_luts,
                },
            )
        _emit_writer_event(progress, "fixup_start", {})
        module.fixup_ports()
        _emit_writer_event(
            progress,
            "finish",
            {
                "replacements": len(replacements),
                "removed_luts": removed_luts,
            },
        )

    def _apply_one(
        self,
        module: ys.Module,
        replacement: MultiMapReplacement,
    ) -> None:
        """Apply one multi-cell replacement.

        Parameters
        ----------
        module : ys.Module
            Live pyosys module to mutate.
        replacement : MultiMapReplacement
            Replacement record containing original cells, tile ports, and
            solved config bits.
        """
        new_cell = module.addCell(
            _id(f"\\{replacement.replacement_cell_id}"),
            _id(f"\\{self.tile_top_name}"),
        )
        for tile_input, ref in replacement.input_ports.items():
            new_cell.setPort(_id(f"\\{tile_input}"), _ref_to_signal(module, ref))

        if self.include_unused_inputs:
            zero = _const_signal(0, 1)
            for tile_input in self.tile_inputs:
                port_id = _id(f"\\{tile_input}")
                if not new_cell.hasPort(port_id):
                    new_cell.setPort(port_id, zero)

        for tile_output, ref in replacement.output_ports.items():
            new_cell.setPort(_id(f"\\{tile_output}"), _ref_to_signal(module, ref))

        _add_config_ports(new_cell, replacement.config_bits)
        for cell_id in replacement.original_cell_ids:
            module.remove(_find_cell(module, cell_id))


def _find_module(design: PyosysBridge, top_name: str) -> ys.Module:
    """Find one module by clean name.

    Parameters
    ----------
    design : PyosysBridge
        Live pyosys design.
    top_name : str
        Module name without a leading Yosys escape.

    Returns
    -------
    ys.Module
        Matching pyosys module.

    Raises
    ------
    RuntimeError
        If the module is not present in the design.
    """
    for module in design.design.modules_.values():
        if _clean_name(module.name) == top_name:
            return module
    raise RuntimeError(f"Top module '{top_name}' not found")


def _emit_writer_event(
    progress: Callable[[dict[str, object]], None] | None,
    event: str,
    payload: dict[str, object],
) -> None:
    """Emit a writer progress event if a callback is available.

    Parameters
    ----------
    progress : Callable[[dict[str, object]], None] | None
        Optional callback.
    event : str
        Event name such as ``"start"``, ``"progress"``, or ``"finish"``.
    payload : dict[str, object]
        Event-specific values.
    """
    if progress is None:
        return
    progress({"event": event, **payload})


def _find_cell(module: ys.Module, cell_id: str) -> ys.Cell:
    """Find one cell by clean name.

    Parameters
    ----------
    module : ys.Module
        Live pyosys module.
    cell_id : str
        Cell name without a leading Yosys escape.

    Returns
    -------
    ys.Cell
        Matching pyosys cell.

    Raises
    ------
    RuntimeError
        If the cell is not present in the module.
    """
    for cell in module.cells_.values():
        if _clean_name(cell.name) == cell_id:
            return cell
    raise RuntimeError(f"Cell '{cell_id}' not found in module '{module.name}'")


def _ref_to_signal(module: ys.Module, ref: InputPortSource) -> ys.SigSpec:
    """Convert a port-bit reference into a one-bit signal.

    Parameters
    ----------
    module : ys.Module
        Live pyosys module containing referenced cells.
    ref : InputPortSource
        Original-cell port reference or integer constant.

    Returns
    -------
    ys.SigSpec
        One-bit pyosys signal.

    Raises
    ------
    RuntimeError
        If the referenced cell port does not contain the requested bit.
    """
    if isinstance(ref, int):
        return _const_signal(ref, 1)
    cell = _find_cell(module, ref.cell_id)
    signal = cell.getPort(_id(f"\\{ref.port}"))
    if ref.index >= signal.size():
        raise RuntimeError(
            f"Cell '{ref.cell_id}' port '{ref.port}' does not have bit {ref.index}"
        )
    return ys.SigSpec(signal.at(ref.index), 1)


def _add_config_ports(
    cell: ys.Cell,
    config_bits: dict[str, bool | None],
) -> None:
    """Add scalar and indexed config ports to a replacement cell.

    Parameters
    ----------
    cell : ys.Cell
        Replacement tile cell to update.
    config_bits : dict[str, bool | None]
        Solved config bits keyed by scalar names such as ``"CE"`` or indexed
        names such as ``"ConfigBits[3]"``.

    Examples
    --------
    ``{"ConfigBits[0]": True, "ConfigBits[2]": True}`` is grouped into one
    vector port ``ConfigBits`` with value ``0b101`` and width ``3``.
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
    """Return a constant signal.

    Parameters
    ----------
    value : int
        Constant integer value.
    width : int
        Signal width in bits.

    Returns
    -------
    ys.SigSpec
        Constant pyosys signal.
    """
    return ys.SigSpec(ys.Const(value, width))


def _id(name: str) -> ys.IdString:
    """Return a pyosys identifier.

    Parameters
    ----------
    name : str
        Escaped or raw identifier string.

    Returns
    -------
    ys.IdString
        pyosys identifier object.
    """
    return ys.IdString(name)


def _clean_name(name: object) -> str:
    r"""Return an identifier without a leading Yosys backslash.

    Parameters
    ----------
    name : object
        pyosys identifier-like object.

    Returns
    -------
    str
        String form without a leading ``"\\"``.
    """
    return str(name).removeprefix("\\")
