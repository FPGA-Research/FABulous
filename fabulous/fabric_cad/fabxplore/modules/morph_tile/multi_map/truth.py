"""Build multi-output truth tables for LUT groups.

The truth builder simulates the grouped LUT subgraph over the group's boundary inputs,
so groups with internal LUT-to-LUT edges are handled correctly.
"""

from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
    LutGraph,
    LutGroupCandidate,
    LutGroupTruth,
)


class CyclicGroupError(ValueError):
    """Raised when a selected LUT group contains a combinational cycle."""


def build_group_truth(
    graph: LutGraph,
    candidate: LutGroupCandidate,
) -> LutGroupTruth:
    """Build fixed truth tables for a LUT group.

    Parameters
    ----------
    graph : LutGraph
        Source LUT graph.
    candidate : LutGroupCandidate
        Group to simulate.

    Returns
    -------
    LutGroupTruth
        Spec inputs and output INITs for sat_fab.

    Examples
    --------
    If a selected group contains ``lut_a -> lut_b``, the output of ``lut_a`` is
    simulated internally for each boundary-input assignment before ``lut_b`` is
    evaluated. Only the group's boundary outputs are written into
    ``output_inits``.
    """
    input_names = [f"N{index}" for index in range(len(candidate.boundary_tokens))]
    token_to_input = {
        token: input_names[index]
        for index, token in enumerate(candidate.boundary_tokens)
    }
    order = _topological_order(graph, candidate.lut_ids)
    output_inits = {name: 0 for name in candidate.output_refs}

    for assignment_index in range(1 << len(input_names)):
        env = {
            name: bool((assignment_index >> bit_index) & 1)
            for bit_index, name in enumerate(input_names)
        }
        values: dict[str, bool] = {}
        for lut_id in order:
            node = graph.nodes[lut_id]
            lut_index = 0
            for bit_index, token in enumerate(node.input_tokens):
                if _value_for_token(token, token_to_input, env, values):
                    lut_index |= 1 << bit_index
            values[node.output_token] = bool((node.init >> lut_index) & 1)

        for output_name, output_ref in candidate.output_refs.items():
            output_token = graph.nodes[output_ref.cell_id].output_token
            if values[output_token]:
                output_inits[output_name] |= 1 << assignment_index

    return LutGroupTruth(input_names=input_names, output_inits=output_inits)


def _topological_order(graph: LutGraph, lut_ids: tuple[str, ...]) -> list[str]:
    """Return grouped LUTs in dependency order.

    Parameters
    ----------
    graph : LutGraph
        Source LUT graph.
    lut_ids : tuple[str, ...]
        LUT ids in the selected group.

    Returns
    -------
    list[str]
        LUT ids ordered so internal drivers appear before their users.
    """
    group = set(lut_ids)
    visiting: set[str] = set()
    visited: set[str] = set()
    ordered: list[str] = []

    def visit(lut_id: str) -> None:
        if lut_id in visited:
            return
        if lut_id in visiting:
            raise CyclicGroupError(f"group contains a cycle at LUT {lut_id!r}")
        visiting.add(lut_id)
        for token in graph.nodes[lut_id].input_tokens:
            driver = graph.driver_by_token.get(token)
            if driver in group:
                visit(driver)
        visiting.remove(lut_id)
        visited.add(lut_id)
        ordered.append(lut_id)

    for lut_id in lut_ids:
        visit(lut_id)
    return ordered


def _value_for_token(
    token: str,
    token_to_input: dict[str, str],
    env: dict[str, bool],
    values: dict[str, bool],
) -> bool:
    """Return one net token value during group simulation.

    Parameters
    ----------
    token : str
        Net token or literal constant to resolve.
    token_to_input : dict[str, str]
        Mapping from boundary net token to generated spec input name.
    env : dict[str, bool]
        Current boundary-input assignment.
    values : dict[str, bool]
        Internal LUT output values computed so far.

    Returns
    -------
    bool
        Boolean value for ``token`` under the current simulation assignment.
    """
    if token == "0":
        return False
    if token == "1":
        return True
    input_name = token_to_input.get(token)
    if input_name is not None:
        return env[input_name]
    return values[token]
