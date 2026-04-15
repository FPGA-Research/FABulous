"""Parse Yosys JSON into an internal LUT-only netlist representation.

This module loads JSON netlists from multiple input forms and extracts LUT cells from a
selected top module. The parsed data is normalized into model objects used by packing
and reporting stages.
"""

from fabulous.fabric_cad.fabxplore.lut_combinator.core.models import (
    LogicalLutCell,
    LutSpec,
    NetlistModel,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.truth_table import (
    parse_init_literal,
)


def parse_model_json(model_json: dict, top_name: str) -> NetlistModel:
    """Parse a Yosys JSON module into a ``NetlistModel`` of LUT cells.

    Only LUT cells with names matching ``LUT<width>`` are extracted. Inputs,
    output, and INIT values are read from each cell and converted to normalized
    ``LogicalLutCell`` instances.

    Parameters
    ----------
    model_json : dict
        Full Yosys JSON dictionary containing a ``modules`` section.
    top_name : str
        Name of the top module to parse.

    Returns
    -------
    NetlistModel
        Parsed LUT-only model for the requested top module.

    Raises
    ------
    RuntimeError
        If ``top_name`` does not exist in ``model_json["modules"]``.
    """
    modules: dict = model_json.get("modules", {})
    if top_name not in modules:
        available: str = ", ".join(sorted(modules.keys()))
        raise RuntimeError(f"Top module '{top_name}' not found. Available: {available}")

    top: dict = modules[top_name]
    cells_raw: dict = top.get("cells", {})

    luts: list[LogicalLutCell] = []

    for cell_id, cell in cells_raw.items():
        cell_type: str = str(cell.get("type", "")).lstrip("\\")
        match = LutSpec.LUT_RE.value.match(cell_type)

        if match is None:
            continue

        width: int = int(match.group(1))
        conns: dict = cell.get("connections", {})

        in_ports: list[str] = [i for i in conns if LutSpec.INPUT_RE.value.match(i)]

        input_nets: tuple[str, ...] = tuple(
            str(conns[p][0] if isinstance(conns[p], list) else conns[p])
            for p in in_ports[:width]
        )

        out_port: list[str] = [p for p in conns if p in LutSpec.OUTPUT_PORTS.value]
        out_port = out_port[0]

        out_net: str = str(
            conns[out_port][0] if isinstance(conns[out_port], list) else conns[out_port]
        )

        params: dict = cell.get("parameters", {})
        init: int = parse_init_literal(
            str(params.get(LutSpec.INIT_NAME.value, "0")), width
        )

        luts.append(
            LogicalLutCell(
                cell_id=cell_id,
                cell_type=cell_type,
                input_nets=input_nets,
                output_net=out_net,
                init=init,
                width=len(input_nets),
            )
        )

    return NetlistModel(top_name=top_name, lut_cells=tuple(luts))
