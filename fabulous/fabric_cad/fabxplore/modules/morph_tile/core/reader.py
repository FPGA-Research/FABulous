"""Read generic cell information for morph-tile mapping.

The reader is the only morph-tile layer that depends on the project Yosys JSON object
model. It converts the selected top module into a generic internal cell view that is
stable even if the underlying pyosys traversal strategy changes later.
"""

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileDesign,
    MorphTileNetlistCell,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_definition.yosys_obj import YosysCellDetails


class MorphTileReader:
    """Extract generic cells from a pyosys bridge into morph-tile objects."""

    def read_design(self, design: PyosysBridge, top_name: str) -> MorphTileDesign:
        """Read a top module into the morph-tile internal representation.

        Parameters
        ----------
        design : PyosysBridge
            Source pyosys design.
        top_name : str
            Top module to inspect.

        Returns
        -------
        MorphTileDesign
            Internal design view containing generic cells.

        Raises
        ------
        RuntimeError
            If ``top_name`` does not exist.
        """
        design_object = design.to_py_object()
        if top_name not in design_object.modules:
            available = ", ".join(sorted(design_object.modules))
            raise RuntimeError(
                f"Top module '{top_name}' not found. Available: {available}"
            )

        module = design_object.modules[top_name]
        cells: list[MorphTileNetlistCell] = []
        for cell_id, cell in module.cells.items():
            cells.append(self._parse_cell(cell_id, cell))

        return MorphTileDesign(top_name=top_name, cells=tuple(cells))

    def _parse_cell(
        self,
        cell_id: str,
        cell: YosysCellDetails,
    ) -> MorphTileNetlistCell:
        """Parse one Yosys object-model cell.

        Parameters
        ----------
        cell_id : str
            Cell name in the object model.
        cell : YosysCellDetails
            Candidate cell to inspect.

        Returns
        -------
        MorphTileNetlistCell
            Parsed generic cell.
        """
        return MorphTileNetlistCell(
            cell_id=cell_id,
            cell_type=str(cell.type).lstrip("\\"),
            parameters={key: str(value) for key, value in cell.parameters.items()},
            connections={
                key: tuple(str(bit) for bit in bits)
                for key, bits in cell.connections.items()
            },
        )
