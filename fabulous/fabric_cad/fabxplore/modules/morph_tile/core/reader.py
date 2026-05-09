"""Read LUT information for morph-tile mapping.

The reader is the only morph-tile layer that depends on the project Yosys JSON object
model. It converts the selected top module into a compact internal view that is stable
even if the underlying pyosys traversal strategy changes later.
"""

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.truth_table import (
    parse_init_literal,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileDesign,
    MorphTileLutCell,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_definition.yosys_obj import YosysCellDetails


class MorphTileReader:
    """Extract LUT cells from a pyosys bridge into morph-tile objects."""

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
            Internal design view containing parsed LUT cells.

        Raises
        ------
        RuntimeError
            If ``top_name`` does not exist or a malformed ``$lut`` is found.
        """
        design_object = design.to_py_object()
        if top_name not in design_object.modules:
            available = ", ".join(sorted(design_object.modules))
            raise RuntimeError(
                f"Top module '{top_name}' not found. Available: {available}"
            )

        module = design_object.modules[top_name]
        lut_cells: list[MorphTileLutCell] = []
        for cell_id, cell in module.cells.items():
            parsed = self._parse_lut_cell(cell_id, cell)
            if parsed is not None:
                lut_cells.append(parsed)

        return MorphTileDesign(top_name=top_name, lut_cells=tuple(lut_cells))

    def _parse_lut_cell(
        self,
        cell_id: str,
        cell: YosysCellDetails,
    ) -> MorphTileLutCell | None:
        """Parse one Yosys object-model cell.

        Parameters
        ----------
        cell_id : str
            Cell name in the object model.
        cell : YosysCellDetails
            Candidate cell to inspect.

        Returns
        -------
        MorphTileLutCell | None
            Parsed LUT cell, or ``None`` for non-LUT cells.

        Raises
        ------
        RuntimeError
            If a ``$lut`` cell has an invalid output connection.
        """
        if str(cell.type).lstrip("\\") != "$lut":
            return None

        input_bits = list(cell.connections.get("A", []))
        output_bits = list(cell.connections.get("Y", []))
        if len(output_bits) != 1:
            raise RuntimeError(f"$lut '{cell_id}' must have exactly one Y bit")

        width = len(input_bits)
        init = parse_init_literal(str(cell.parameters.get("LUT", "0")), width)
        return MorphTileLutCell(cell_id=cell_id, width=width, init=init)
