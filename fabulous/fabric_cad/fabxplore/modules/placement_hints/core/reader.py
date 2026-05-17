"""Read pyosys designs into placement-hints models.

The reader uses the shared ``yosys_obj`` representation from ``PyosysBridge`` so
placement hint analysis follows the same structured path as other fabxplore passes.
"""

from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.models import (
    PlacementHintCell,
    PlacementHintDesign,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_definition.yosys_obj import YosysCellDetails


class PlacementHintsReader:
    """Read a top module for placement hint detection."""

    def read_design(
        self,
        design: PyosysBridge,
        top_name: str | None = None,
    ) -> PlacementHintDesign:
        """Read a pyosys design into a pure-Python model.

        Parameters
        ----------
        design : PyosysBridge
            Design wrapper to inspect.
        top_name : str | None
            Optional top module. If ``None``, use the bridge's current top.

        Returns
        -------
        PlacementHintDesign
            Parsed design model.

        Raises
        ------
        RuntimeError
            If the selected top module does not exist.
        """
        selected_top = top_name or design.top_name()
        design_object = design.to_py_object()
        if selected_top not in design_object.modules:
            available = ", ".join(sorted(design_object.modules))
            raise RuntimeError(
                f"Top module '{selected_top}' not found. Available: {available}"
            )
        module = design_object.modules[selected_top]
        cells = tuple(
            self._parse_cell(cell_id, cell) for cell_id, cell in module.cells.items()
        )
        return PlacementHintDesign(top_name=selected_top, cells=cells)

    def _parse_cell(
        self,
        cell_id: str,
        cell: YosysCellDetails,
    ) -> PlacementHintCell:
        """Parse one Yosys object-model cell.

        Parameters
        ----------
        cell_id : str
            Cell name in the object model.
        cell : YosysCellDetails
            Cell to parse.

        Returns
        -------
        PlacementHintCell
            Parsed placement-hints cell.
        """
        return PlacementHintCell(
            cell_id=_clean_name(cell_id),
            cell_type=str(cell.type).lstrip("\\"),
            attributes={
                str(name): _stringify_attribute(value)
                for name, value in cell.attributes.items()
            },
            connections={
                str(port): tuple(str(bit) for bit in bits)
                for port, bits in cell.connections.items()
            },
        )


def _stringify_attribute(value: object) -> str:
    """Return a stable string representation for a JSON attribute.

    Parameters
    ----------
    value : object
        Raw attribute value from Yosys JSON.

    Returns
    -------
    str
        Stringified attribute.
    """
    if isinstance(value, str):
        return value.strip('"')
    return str(value)


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
    return str(name).removeprefix("\\")
