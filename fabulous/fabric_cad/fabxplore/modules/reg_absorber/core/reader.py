"""Read pyosys designs into register-absorber models."""

from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
    RegAbsorberCell,
    RegAbsorberDesign,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_definition.yosys_obj import YosysCellDetails


class RegAbsorberReader:
    """Extract cells needed by register absorption."""

    def read_design(self, design: PyosysBridge, top_name: str) -> RegAbsorberDesign:
        """Read one top module from a pyosys bridge.

        Parameters
        ----------
        design : PyosysBridge
            Source design.
        top_name : str
            Top module to inspect.

        Returns
        -------
        RegAbsorberDesign
            Internal design view.

        Raises
        ------
        RuntimeError
            If ``top_name`` is not present.
        """
        design_object = design.to_py_object()
        if top_name not in design_object.modules:
            available = ", ".join(sorted(design_object.modules))
            raise RuntimeError(
                f"Top module '{top_name}' not found. Available: {available}"
            )

        module = design_object.modules[top_name]
        cells = tuple(
            self._parse_cell(cell_id, cell) for cell_id, cell in module.cells.items()
        )
        output_bits = frozenset(
            str(bit)
            for port in module.ports.values()
            if port.direction == "output"
            for bit in port.bits
        )
        return RegAbsorberDesign(
            top_name=top_name,
            cells=cells,
            module_output_bits=output_bits,
        )

    def _parse_cell(
        self,
        cell_id: str,
        cell: YosysCellDetails,
    ) -> RegAbsorberCell:
        """Parse one Yosys object-model cell.

        Parameters
        ----------
        cell_id : str
            Cell instance name.
        cell : YosysCellDetails
            Cell details from the object model.

        Returns
        -------
        RegAbsorberCell
            Internal cell view.
        """
        return RegAbsorberCell(
            cell_id=_clean_name(cell_id),
            cell_type=str(cell.type).lstrip("\\"),
            parameters={key: str(value) for key, value in cell.parameters.items()},
            connections={
                key: tuple(str(bit) for bit in bits)
                for key, bits in cell.connections.items()
            },
            port_directions={
                key: str(value) for key, value in cell.port_directions.items()
            },
        )


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
