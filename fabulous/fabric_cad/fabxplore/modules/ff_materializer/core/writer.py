"""Apply FF materialization rewrites to a live pyosys design."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.models import (
    FfLaneBinding,
    FfMaterialization,
    FfMaterializerResult,
    FfMaterializerTileModel,
    split_indexed_name,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class FfMaterializerWriter:
    """Apply FF materialization plans to pyosys modules.

    Parameters
    ----------
    tile : FfMaterializerTileModel
        Replacement tile model.
    """

    def __init__(self, tile: FfMaterializerTileModel) -> None:
        self.tile = tile

    def apply(self, design: PyosysBridge, result: FfMaterializerResult) -> None:
        """Apply all materializations in ``result``.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        result : FfMaterializerResult
            Materialization plan.
        """
        module = _find_module(design, result.top_name)
        cell_index = _build_cell_index(module)
        for materialization in result.materializations:
            self._apply_one(module, materialization, cell_index)
        module.fixup_ports()

    def _apply_one(
        self,
        module: ys.Module,
        materialization: FfMaterialization,
        cell_index: dict[str, ys.Cell],
    ) -> None:
        """Apply one materialization.

        Parameters
        ----------
        module : ys.Module
            Module containing the FFs.
        materialization : FfMaterialization
            Materialization to apply.
        cell_index : dict[str, ys.Cell]
            Clean cell-name index for fast lookup.
        """
        new_cell = module.addCell(
            _id(f"\\{materialization.replacement_cell_id}"),
            _id(f"\\{materialization.tile_type}"),
        )
        cell_index[_clean_name(materialization.replacement_cell_id)] = new_cell
        for binding in materialization.bindings:
            first_ff = _indexed_cell(cell_index, binding.ff_cell_ids[0], module)
            last_ff = _indexed_cell(cell_index, binding.ff_cell_ids[-1], module)
            self._connect_binding(new_cell, first_ff, last_ff, binding)
        _add_config_ports(new_cell, materialization.config, self.tile)
        _add_attributes(new_cell, materialization.attributes)
        for binding in materialization.bindings:
            for ff_cell_id in binding.ff_cell_ids:
                ff_cell = _indexed_cell(cell_index, ff_cell_id, module)
                module.remove(ff_cell)
                cell_index.pop(_clean_name(ff_cell_id), None)

    def _connect_binding(
        self,
        new_cell: ys.Cell,
        first_ff: ys.Cell,
        last_ff: ys.Cell,
        binding: FfLaneBinding,
    ) -> None:
        """Connect one FF binding to a replacement tile cell.

        Parameters
        ----------
        new_cell : ys.Cell
            Replacement tile cell.
        first_ff : ys.Cell
            First FF stage consumed by the binding.
        last_ff : ys.Cell
            Last FF stage consumed by the binding.
        binding : FfLaneBinding
            Lane binding.
        """
        lane = binding.lane
        new_cell.setPort(
            _id(f"\\{lane.data_port}"),
            first_ff.getPort(_id(f"\\{binding.ff_data_port}")),
        )
        new_cell.setPort(
            _id(f"\\{lane.output_port}"),
            last_ff.getPort(_id(f"\\{binding.ff_output_port}")),
        )
        if lane.clock_port is not None:
            new_cell.setPort(
                _id(f"\\{lane.clock_port}"),
                first_ff.getPort(_id(f"\\{binding.ff_clock_port}")),
            )
        _connect_optional_control(
            new_cell=new_cell,
            ff=first_ff,
            tile_port=lane.enable_tile_port,
            ff_port=binding.ff_enable_port,
            neutral=lane.enable_neutral,
        )
        _connect_optional_control(
            new_cell=new_cell,
            ff=first_ff,
            tile_port=lane.reset_tile_port,
            ff_port=binding.ff_reset_port,
            neutral=lane.reset_neutral,
        )


def _connect_optional_control(
    new_cell: ys.Cell,
    ff: ys.Cell,
    tile_port: str | None,
    ff_port: str | None,
    neutral: int | bool | None,
) -> None:
    """Connect or neutralize one optional tile control port.

    Parameters
    ----------
    new_cell : ys.Cell
        Replacement tile cell.
    ff : ys.Cell
        FF being removed.
    tile_port : str | None
        Optional tile control port.
    ff_port : str | None
        Optional source FF control port.
    neutral : int | bool | None
        Neutral constant when the FF has no matching control.
    """
    if tile_port is None:
        return
    if ff_port is not None:
        new_cell.setPort(_id(f"\\{tile_port}"), ff.getPort(_id(f"\\{ff_port}")))
        return
    if neutral is not None:
        new_cell.setPort(_id(f"\\{tile_port}"), _const_signal(int(bool(neutral)), 1))


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


def _build_cell_index(module: ys.Module) -> dict[str, ys.Cell]:
    """Build a clean cell-name lookup for one module.

    Parameters
    ----------
    module : ys.Module
        Module containing cells.

    Returns
    -------
    dict[str, ys.Cell]
        Cell lookup keyed by clean cell name.
    """
    return {_clean_name(cell.name): cell for cell in module.cells_.values()}


def _indexed_cell(
    cell_index: dict[str, ys.Cell],
    cell_id: str,
    module: ys.Module,
) -> ys.Cell:
    """Return one cell from a clean cell-name lookup.

    Parameters
    ----------
    cell_index : dict[str, ys.Cell]
        Cell lookup keyed by clean cell name.
    cell_id : str
        Cell name to find.
    module : ys.Module
        Module used for error context.

    Returns
    -------
    ys.Cell
        Matching cell.

    Raises
    ------
    RuntimeError
        If the cell is absent.
    """
    clean_cell_id = _clean_name(cell_id)
    if clean_cell_id in cell_index:
        return cell_index[clean_cell_id]
    raise RuntimeError(f"Cell '{cell_id}' not found in module '{module.name}'")


def _add_config_ports(
    cell: ys.Cell,
    config_bits: dict[str, int | bool],
    tile: FfMaterializerTileModel,
) -> None:
    """Merge config-bit updates into a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Cell receiving config ports.
    config_bits : dict[str, int | bool]
        Config updates keyed by scalar or indexed port names.
    tile : FfMaterializerTileModel
        Tile model used to infer config bus widths.
    """
    widths = _config_widths(tile)
    grouped: dict[str, dict[int, int]] = {}
    scalar: dict[str, int] = {}
    for name, value in config_bits.items():
        base, index = split_indexed_name(name)
        if index is None:
            scalar[base] = int(value)
        else:
            grouped.setdefault(base, {})[index] = 1 if bool(value) else 0

    for port, value in scalar.items():
        cell.setPort(_id(f"\\{port}"), _const_signal(value, widths.get(port, 1)))
    for port, indexed_bits in grouped.items():
        width = max(widths.get(port, 0), *(index + 1 for index in indexed_bits))
        bits = [ys.SigBit(ys.State.S0) for _ in range(width)]
        for index, bit in indexed_bits.items():
            bits[index] = ys.SigBit(ys.State.S1 if bit else ys.State.S0)
        cell.setPort(_id(f"\\{port}"), _indexed_signal(bits))


def _add_params(cell: ys.Cell, params: dict[str, str | int | bool]) -> None:
    """Set parameter updates on a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Cell receiving parameter updates.
    params : dict[str, str | int | bool]
        Parameter updates.
    """
    for name, value in params.items():
        cell.setParam(_id(f"\\{name}"), ys.Const(value))


def _add_attributes(cell: ys.Cell, attrs: dict[str, str | int | bool]) -> None:
    """Set attribute updates on a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Cell receiving attribute updates.
    attrs : dict[str, str | int | bool]
        Attribute updates.
    """
    updated_attrs = cell.attributes.copy()
    for name, value in attrs.items():
        updated_attrs[_id(f"\\{name}")] = ys.Const(value)
    cell.attributes = updated_attrs


def _config_widths(tile: FfMaterializerTileModel) -> dict[str, int]:
    """Return config port widths from scalar config names.

    Parameters
    ----------
    tile : FfMaterializerTileModel
        Tile model.

    Returns
    -------
    dict[str, int]
        Config base port to width.
    """
    widths: dict[str, int] = {}
    for name in tile.config_bits:
        base, index = split_indexed_name(name)
        widths[base] = max(widths.get(base, 0), 1 if index is None else index + 1)
    return widths


def _indexed_signal(bits: list[ys.SigBit]) -> ys.SigSpec:
    """Return a vector signal from individual bits.

    Parameters
    ----------
    bits : list[ys.SigBit]
        Bits in LSB-first order.

    Returns
    -------
    ys.SigSpec
        Vector signal.
    """
    signal = ys.SigSpec()
    for bit in bits:
        signal.append(bit)
    return signal


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
        Yosys identifier text.

    Returns
    -------
    ys.IdString
        pyosys identifier.
    """
    return ys.IdString(name)


def _clean_name(name: object) -> str:
    """Return a name without a leading Yosys escape backslash.

    Parameters
    ----------
    name : object
        Yosys name-like object.

    Returns
    -------
    str
        Clean name.
    """
    return str(name).removeprefix("\\")
