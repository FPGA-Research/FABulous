"""Apply LUT decomposition plans to a live pyosys design."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pyosys.libyosys as ys

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.models import (
        LutDecomposerResult,
        LutDecomposition,
    )
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
        ReplacementPortRef,
    )
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge

_INDEXED_PORT_RE = re.compile(r"^(?P<base>.+)\[(?P<index>\d+)\]$")


class LutDecomposerWriter:
    """Apply LUT decomposition plans to a pyosys module.

    Parameters
    ----------
    mux_top_name : str
        Mux primitive module type to instantiate.
    mux_inputs : list[str]
        Mux input port names used for optional unused-input tying.
    include_unused_mux_inputs : bool
        Whether unused mux inputs are tied to zero.
    """

    def __init__(
        self,
        mux_top_name: str,
        mux_inputs: list[str],
        include_unused_mux_inputs: bool = False,
    ) -> None:
        self.mux_top_name = mux_top_name
        self.mux_inputs = mux_inputs
        self.include_unused_mux_inputs = include_unused_mux_inputs

    def apply(self, design: PyosysBridge, result: LutDecomposerResult) -> None:
        """Apply all decompositions in ``result`` to ``design``.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        result : LutDecomposerResult
            Decomposition plan.
        """
        module = _find_module(design, result.top_name)
        for decomposition in result.decompositions:
            self._apply_one(module, decomposition)
        module.fixup_ports()

    def _apply_one(
        self,
        module: ys.Module,
        decomposition: LutDecomposition,
    ) -> None:
        """Apply one decomposition to a pyosys module.

        Parameters
        ----------
        module : ys.Module
            Module containing the original LUT.
        decomposition : LutDecomposition
            Decomposition to apply.
        """
        old_cell = _find_cell(module, decomposition.original_cell_id)
        cofactor_outputs = self._add_leaf_luts(module, old_cell, decomposition)
        mux_cell = module.addCell(
            _id(f"\\{decomposition.mux_cell_id}"),
            _id(f"\\{self.mux_top_name}"),
        )
        self._connect_mux_inputs(mux_cell, old_cell, decomposition, cofactor_outputs)
        _add_config_ports(mux_cell, decomposition.mux_config_bits)
        for mux_output, ref in decomposition.mux_output_ports.items():
            mux_cell.setPort(_id(f"\\{mux_output}"), _ref_to_signal(old_cell, ref))
        module.remove(old_cell)

    def _add_leaf_luts(
        self,
        module: ys.Module,
        old_cell: ys.Cell,
        decomposition: LutDecomposition,
    ) -> dict[int, ys.SigSpec]:
        """Add generated cofactor LUT cells.

        Parameters
        ----------
        module : ys.Module
            Module being mutated.
        old_cell : ys.Cell
            Original high-width LUT.
        decomposition : LutDecomposition
            Decomposition containing generated cofactors.

        Returns
        -------
        dict[int, ys.SigSpec]
            Cofactor index to generated output signal.
        """
        old_inputs = old_cell.getPort(_id("\\A"))
        leaf_input = _slice_signal(old_inputs, decomposition.leaf_lut_width)
        outputs: dict[int, ys.SigSpec] = {}
        for cofactor in decomposition.cofactors:
            wire = module.addWire(_id(f"\\{cofactor.output_wire_id}"), 1)
            wire_signal = ys.SigSpec(wire)
            leaf = module.addCell(_id(f"\\{cofactor.cell_id}"), _id("$lut"))
            leaf.setParam(_id("\\WIDTH"), ys.Const(decomposition.leaf_lut_width, 32))
            leaf.setParam(
                _id("\\LUT"),
                ys.Const(cofactor.init, 1 << decomposition.leaf_lut_width),
            )
            leaf.setPort(_id("\\A"), leaf_input)
            leaf.setPort(_id("\\Y"), wire_signal)
            outputs[cofactor.index] = wire_signal
        return outputs

    def _connect_mux_inputs(
        self,
        mux_cell: ys.Cell,
        old_cell: ys.Cell,
        decomposition: LutDecomposition,
        cofactor_outputs: dict[int, ys.SigSpec],
    ) -> None:
        """Connect solved mux input routes.

        Parameters
        ----------
        mux_cell : ys.Cell
            Generated mux cell.
        old_cell : ys.Cell
            Original LUT cell.
        decomposition : LutDecomposition
            Decomposition containing mux routes.
        cofactor_outputs : dict[int, ys.SigSpec]
            Generated cofactor output signals.
        """
        grouped: dict[str, dict[int, ys.SigSpec]] = {}
        scalar: dict[str, ys.SigSpec] = {}
        for mux_input, ref in decomposition.mux_input_ports.items():
            signal = _ref_to_signal(old_cell, ref, cofactor_outputs)
            match = _INDEXED_PORT_RE.match(mux_input)
            if match is None:
                scalar[mux_input] = signal
                continue
            grouped.setdefault(match.group("base"), {})[int(match.group("index"))] = (
                signal
            )

        for port, signal in scalar.items():
            mux_cell.setPort(_id(f"\\{port}"), signal)
        for port, indexed in grouped.items():
            mux_cell.setPort(_id(f"\\{port}"), _indexed_signal(indexed))

        if self.include_unused_mux_inputs:
            for mux_input in self.mux_inputs:
                if not mux_cell.hasPort(_id(f"\\{mux_input}")):
                    mux_cell.setPort(_id(f"\\{mux_input}"), _const_signal(0, 1))


def _find_module(design: PyosysBridge, top_name: str) -> ys.Module:
    """Find a module by clean name.

    Parameters
    ----------
    design : PyosysBridge
        Design containing the module.
    top_name : str
        Clean module name.

    Returns
    -------
    ys.Module
        Matching module.

    Raises
    ------
    RuntimeError
        If the module is absent.
    """
    for module in design.design.modules_.values():
        if _clean_name(module.name) == top_name:
            return module
    raise RuntimeError(f"Top module '{top_name}' not found")


def _find_cell(module: ys.Module, cell_id: str) -> ys.Cell:
    """Find one cell by clean name.

    Parameters
    ----------
    module : ys.Module
        Module containing the cell.
    cell_id : str
        Clean cell name.

    Returns
    -------
    ys.Cell
        Matching cell.

    Raises
    ------
    RuntimeError
        If the cell is absent.
    """
    for cell in module.cells_.values():
        if _clean_name(cell.name) == cell_id:
            return cell
    raise RuntimeError(f"Cell '{cell_id}' not found in module '{module.name}'")


def _ref_to_signal(
    cell: ys.Cell,
    ref: ReplacementPortRef,
    cofactor_outputs: dict[int, ys.SigSpec] | None = None,
) -> ys.SigSpec:
    """Convert a replacement reference to a pyosys signal.

    Parameters
    ----------
    cell : ys.Cell
        Original LUT cell.
    ref : ReplacementPortRef
        Replacement signal reference.
    cofactor_outputs : dict[int, ys.SigSpec] | None
        Optional generated cofactor outputs.

    Returns
    -------
    ys.SigSpec
        One-bit signal.

    Raises
    ------
    RuntimeError
        If the reference is invalid.
    """
    if ref.constant is not None:
        return _const_signal(ref.constant, 1)
    if ref.cell_port is None:
        raise RuntimeError("replacement reference must contain a signal source")
    port = ref.cell_port.port
    if port.startswith("__cofactor_"):
        index = int(port.removeprefix("__cofactor_"))
        if cofactor_outputs is None or index not in cofactor_outputs:
            raise RuntimeError(f"Missing cofactor output {index}")
        return cofactor_outputs[index]

    signal = cell.getPort(_id(f"\\{port}"))
    if ref.cell_port.index >= signal.size():
        raise RuntimeError(
            f"Cell '{_clean_name(cell.name)}' port '{port}' "
            f"does not have bit {ref.cell_port.index}"
        )
    return ys.SigSpec(signal.at(ref.cell_port.index), 1)


def _add_config_ports(
    cell: ys.Cell,
    config_bits: dict[str, bool | None],
) -> None:
    """Add solved config ports to a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Mux cell receiving config constants.
    config_bits : dict[str, bool | None]
        Config values keyed by scalar or indexed port name.
    """
    grouped: dict[str, dict[int, int]] = {}
    for name, value in config_bits.items():
        bit = 1 if bool(value) else 0
        match = _INDEXED_PORT_RE.match(name)
        if match is None:
            cell.setPort(_id(f"\\{name}"), _const_signal(bit, 1))
            continue
        grouped.setdefault(match.group("base"), {})[int(match.group("index"))] = bit

    for base, indexed in grouped.items():
        cell.setPort(
            _id(f"\\{base}"),
            _const_signal(_indexed_value(indexed), max(indexed) + 1),
        )


def _slice_signal(signal: ys.SigSpec, width: int) -> ys.SigSpec:
    """Return the low ``width`` bits from a signal.

    Parameters
    ----------
    signal : ys.SigSpec
        Source signal.
    width : int
        Number of bits to keep.

    Returns
    -------
    ys.SigSpec
        Sliced signal.
    """
    out = ys.SigSpec()
    for index in range(width):
        out.append(ys.SigSpec(signal.at(index), 1))
    return out


def _indexed_signal(indexed: dict[int, ys.SigSpec]) -> ys.SigSpec:
    """Build a vector signal from indexed scalar signals.

    Parameters
    ----------
    indexed : dict[int, ys.SigSpec]
        Signals keyed by bit index.

    Returns
    -------
    ys.SigSpec
        Vector signal with missing bits tied to zero.
    """
    out = ys.SigSpec()
    for index in range(max(indexed) + 1):
        out.append(indexed.get(index, _const_signal(0, 1)))
    return out


def _indexed_value(indexed: dict[int, int]) -> int:
    """Pack indexed scalar bits into an integer.

    Parameters
    ----------
    indexed : dict[int, int]
        Bit values keyed by bit index.

    Returns
    -------
    int
        Packed integer.
    """
    value = 0
    for index, bit in indexed.items():
        value |= bit << index
    return value


def _const_signal(value: int, width: int) -> ys.SigSpec:
    """Return a constant signal.

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
        Identifier text.

    Returns
    -------
    ys.IdString
        pyosys identifier.
    """
    return ys.IdString(name)


def _clean_name(name: object) -> str:
    """Return a Yosys name without the leading escape.

    Parameters
    ----------
    name : object
        Yosys identifier-like object.

    Returns
    -------
    str
        Clean name.
    """
    return str(name).removeprefix("\\")
