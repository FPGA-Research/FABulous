"""Extract LUT graphs from morph-tile design views.

The extractor consumes the generic ``MorphTileDesign`` model so multi-map does
not depend on pyosys internals while building candidate groups.
"""

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.truth_table import (
    parse_init_literal,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileDesign,
    MorphTileNetlistCell,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
    LutGraph,
    LutNode,
    PortBitRef,
)


def extract_lut_graph(design: MorphTileDesign) -> LutGraph:
    """Extract all Yosys ``$lut`` cells as a graph.

    Parameters
    ----------
    design : MorphTileDesign
        Generic source-design view.

    Returns
    -------
    LutGraph
        Extracted LUT nodes and net connectivity.

    Raises
    ------
    RuntimeError
        If a LUT has malformed ports or duplicate output drivers.
    """
    nodes: dict[str, LutNode] = {}
    driver_by_token: dict[str, str] = {}
    users_by_token: dict[str, list[str]] = {}
    non_lut_cells: list[MorphTileNetlistCell] = []
    for cell in design.cells:
        node = _parse_lut_node(cell)
        if node is None:
            non_lut_cells.append(cell)
            continue
        if node.output_token in driver_by_token:
            raise RuntimeError(
                f"multiple LUTs drive token {node.output_token!r}: "
                f"{driver_by_token[node.output_token]!r} and {node.cell_id!r}"
            )
        nodes[node.cell_id] = node
        driver_by_token[node.output_token] = node.cell_id
        for token in node.input_tokens:
            users_by_token.setdefault(token, []).append(node.cell_id)

    external_user_tokens = _external_lut_output_uses(
        non_lut_cells,
        driver_by_token,
    )
    return LutGraph(
        nodes=nodes,
        driver_by_token=driver_by_token,
        users_by_token={
            token: tuple(cell_ids) for token, cell_ids in users_by_token.items()
        },
        external_user_tokens=frozenset(external_user_tokens),
    )


def _external_lut_output_uses(
    cells: list[MorphTileNetlistCell],
    driver_by_token: dict[str, str],
) -> set[str]:
    """Return LUT-driven tokens touched by non-LUT cells.

    Parameters
    ----------
    cells : list[MorphTileNetlistCell]
        Non-LUT cells from the selected source module.
    driver_by_token : dict[str, str]
        LUT output token to driving LUT cell id.

    Returns
    -------
    set[str]
        LUT output tokens that must be treated as externally used.

    Examples
    --------
    If ``lut_a`` drives ``net_x`` and a flip-flop consumes ``net_x``, then
    ``net_x`` is returned. A later multi-map group may still replace
    ``lut_a`` and downstream LUTs, but the replacement must expose ``net_x`` as
    a boundary output if the output boundary permits it.
    """
    external_tokens: set[str] = set()
    for cell in cells:
        for tokens in cell.connections.values():
            for token in tokens:
                if token in driver_by_token:
                    external_tokens.add(token)
    return external_tokens


def _parse_lut_node(cell: MorphTileNetlistCell) -> LutNode | None:
    """Parse one generic cell as a LUT node.

    Parameters
    ----------
    cell : MorphTileNetlistCell
        Generic source cell.

    Returns
    -------
    LutNode | None
        Parsed LUT node, or ``None`` for non-LUT cells.

    Raises
    ------
    RuntimeError
        If a LUT cell has invalid output wiring.
    """
    if cell.cell_type != "$lut":
        return None
    input_bits = tuple(cell.connections.get("A", ()))
    output_bits = tuple(cell.connections.get("Y", ()))
    if len(output_bits) != 1:
        raise RuntimeError(f"$lut '{cell.cell_id}' must have exactly one Y bit")
    width = len(input_bits)
    init = parse_init_literal(str(cell.parameters.get("LUT", "0")), width)
    return LutNode(
        cell_id=cell.cell_id,
        width=width,
        init=init,
        input_tokens=input_bits,
        output_token=output_bits[0],
        input_refs=tuple(
            PortBitRef(cell_id=cell.cell_id, port="A", index=index)
            for index in range(width)
        ),
        output_ref=PortBitRef(cell_id=cell.cell_id, port="Y", index=0),
    )
