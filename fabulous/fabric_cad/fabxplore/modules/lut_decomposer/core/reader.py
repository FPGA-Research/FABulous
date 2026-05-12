"""Read Yosys LUT cells into decomposer objects."""

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.truth_table import (
    parse_init_literal,
)
from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.models import (
    LutDecomposerCell,
    LutDecomposerDesign,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_definition.yosys_obj import YosysCellDetails


class LutDecomposerReader:
    """Extract normal Yosys ``$lut`` cells from a pyosys bridge."""

    def read_design(self, design: PyosysBridge, top_name: str) -> LutDecomposerDesign:
        """Read a top module into the internal decomposer representation.

        Parameters
        ----------
        design : PyosysBridge
            Source pyosys design.
        top_name : str
            Top module to inspect.

        Returns
        -------
        LutDecomposerDesign
            Internal design view containing extracted LUT cells.

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
        cells = [
            parsed
            for cell_id, cell in module.cells.items()
            if (parsed := self._parse_lut_cell(cell_id, cell)) is not None
        ]
        return LutDecomposerDesign(top_name=top_name, lut_cells=tuple(cells))

    def _parse_lut_cell(
        self,
        cell_id: str,
        cell: YosysCellDetails,
    ) -> LutDecomposerCell | None:
        """Parse one object-model cell as a LUT.

        Parameters
        ----------
        cell_id : str
            Source cell name.
        cell : YosysCellDetails
            Object-model cell payload.

        Returns
        -------
        LutDecomposerCell | None
            Parsed LUT cell, or ``None`` for non-LUT cells.

        Raises
        ------
        RuntimeError
            If a ``$lut`` has an invalid output connection.
        """
        if str(cell.type).lstrip("\\") != "$lut":
            return None

        input_bits = tuple(str(bit) for bit in cell.connections.get("A", ()))
        output_bits = tuple(str(bit) for bit in cell.connections.get("Y", ()))
        if len(output_bits) != 1:
            raise RuntimeError(f"$lut '{cell_id}' must have exactly one Y bit")

        width = len(input_bits)
        init = parse_init_literal(str(cell.parameters.get("LUT", "0")), width)
        return LutDecomposerCell(
            cell_id=cell_id,
            width=width,
            init=init,
            input_bits=input_bits,
            output_bit=output_bits[0],
        )
