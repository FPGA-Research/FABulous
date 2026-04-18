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


def parse_model_json(
    model_json: dict, top_name: str, lut_spec: LutSpec
) -> NetlistModel:
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
    lut_spec : LutSpec
        LUT specification defining naming patterns and parameters for LUT cells.

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
        match = lut_spec.lut_re.match(cell_type)

        if match is None:
            continue

        conns: dict = flatten_connections(cell.get("connections", {}))
        width: int = len([p for p in conns if lut_spec.input_re.match(p)])

        in_ports: list[str] = [i for i in conns if lut_spec.input_re.match(i)]

        input_nets: tuple[str, ...] = tuple(
            str(conns[p][0] if isinstance(conns[p], list) else conns[p])
            for p in in_ports[:width]
        )

        out_port: list[str] = [p for p in conns if p in lut_spec.output_ports]
        out_port = out_port[0]

        out_net: str = str(
            conns[out_port][0] if isinstance(conns[out_port], list) else conns[out_port]
        )

        params: dict = cell.get("parameters", {})
        init: int = parse_init_literal(str(params.get(lut_spec.init_name, "0")), width)

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


def flatten_connections(
    connections: dict[str, list[int]],
    keep_single_entries: bool = True,
) -> dict[str, list[int]]:
    """Flatten Yosys connection lists into single-value entries.

    Yosys represents multi-bit connections as lists of individual bits. This function
    converts these into a flat dictionary where each bit is represented as a separate
    entry with an indexed name (e.g., "A0", "A1", ...). Optionally, single-bit
    connections can keep their original name.

    Parameters
    ----------
    connections : dict[str, list[int]]
        Original Yosys connection dictionary.
    keep_single_entries : bool, optional
        If ``True``, single-bit connections keep their original name. If ``False``,
        they are also indexed (e.g., ``"Y0"``), by default ``True``.

    Returns
    -------
    dict[str, list[int]]
        Flattened connection dictionary with single-value entries.
    """
    result: dict[str, list[int]] = {}

    for name, values in connections.items():
        if keep_single_entries and len(values) == 1:
            result[name] = [values[0]]
        else:
            for i, value in enumerate(values):
                result[f"{name}{i}"] = [value]

    return result
