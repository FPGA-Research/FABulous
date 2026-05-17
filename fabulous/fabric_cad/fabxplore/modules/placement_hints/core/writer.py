"""Apply placement hint assignments to a live pyosys design."""

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.models import (
    AttributeValue,
    PlacementHintsResult,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class PlacementHintsWriter:
    """Write placement hint attributes to existing cells."""

    def apply(self, design: PyosysBridge, result: PlacementHintsResult) -> None:
        """Apply placement hint assignments to a pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        result : PlacementHintsResult
            Placement hint assignments to write.
        """
        module = _find_module(design, result.top_name)
        for assignment in result.assignments:
            cell = _find_cell(module, assignment.cell_id)
            _set_attributes(cell, assignment.attributes)


def _set_attributes(cell: ys.Cell, attributes: dict[str, AttributeValue]) -> None:
    """Set attributes on a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Target cell.
    attributes : dict[str, AttributeValue]
        Attributes to set.
    """
    for name, value in attributes.items():
        _set_attribute(cell, name, value)


def _set_attribute(cell: ys.Cell, name: str, value: AttributeValue) -> None:
    """Set one placement hint attribute on a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Target cell.
    name : str
        Attribute name without a leading Yosys escape.
    value : AttributeValue
        Attribute value to write.
    """
    attr_id = _id(f"\\{name}")
    if isinstance(value, bool):
        cell.set_bool_attribute(attr_id, value)
    elif isinstance(value, int):
        cell.set_intvec_attribute(attr_id, [value])
    else:
        cell.set_string_attribute(attr_id, str(value))


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
        If no module matches.
    """
    for module in design.design.modules_.values():
        if _clean_name(module.name) == top_name:
            return module
    raise RuntimeError(f"Top module '{top_name}' not found")


def _find_cell(module: ys.Module, cell_id: str) -> ys.Cell:
    """Find a cell by clean name.

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
        If no cell matches.
    """
    clean_cell_id = _clean_name(cell_id)
    for cell in module.cells_.values():
        if _clean_name(cell.name) == clean_cell_id:
            return cell
    raise RuntimeError(f"Cell '{cell_id}' not found in module '{module.name}'")


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
    """Return a name without a leading Yosys escape.

    Parameters
    ----------
    name : object
        Yosys identifier-like object.

    Returns
    -------
    str
        Clean name.
    """
    text = str(name)
    return text.removeprefix("\\")
