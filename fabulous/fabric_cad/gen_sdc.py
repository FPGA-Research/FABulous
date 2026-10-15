"""Generate SDC constraints that break the combinational loops of a tile netlist.

OpenSTA breaks every combinational loop it finds at an edge of its own choosing,
which can drop a real critical path from the timing graph. The cuts here are
chosen on the synthesised gate-level netlist, the graph STA times, because
flattening lets synthesis copy switch-matrix logic so that loops route round any
net picked from the RTL. The tile flow keeps each BEL module as its own module
through synthesis, so BEL logic never merges into switch-matrix gates. A BEL
instance therefore contributes only its port-to-port arcs, its outputs are never
cut and its inputs are cut only when a loop has no other routing net. Every other
top-level net is routing and a valid cut. Loops are broken at net granularity by
selecting a small feedback-vertex set (see `select_break_nodes`) and disabling the
driver pin of each chosen net.
"""

from collections import defaultdict
from fnmatch import fnmatchcase

import networkx as nx

from fabulous.custom_exception import InvalidState
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.yosys_obj import YosysJson
from fabulous.tools.tool import template_env


def select_break_nodes(
    graph: nx.DiGraph, protected: set[int], last_resort: set[int]
) -> set[int]:
    """Select a feedback-vertex set whose removal makes `graph` acyclic.

    Each round removes the vertex with the largest in-degree x out-degree
    product from one strongly connected component, which is near-minimum on
    switch-matrix graphs. Nodes in `protected` stay in the graph but are never
    chosen as a cut, so a `set_disable_timing` never lands on a cell's own pin.
    Nodes in `last_resort` are chosen only from a component with no other
    unprotected node.

    Parameters
    ----------
    graph : nx.DiGraph
        Directed connectivity graph. Nodes are net bit ids.
    protected : set[int]
        Nodes that must never be chosen as a cut (BEL outputs). They remain in
        the graph and may still lie on a cycle that is broken elsewhere.
    last_resort : set[int]
        Nodes cut only when nothing else breaks their component (BEL inputs).

    Returns
    -------
    set[int]
        Nodes to disable. Empty if `graph` is acyclic.

    Raises
    ------
    InvalidState
        A protected node carries a self-loop, or a strongly connected component
        contains only protected nodes, so no loop can be broken without disabling
        a protected pin.
    """
    self_loops = set(nx.nodes_with_selfloops(graph))
    protected_self_loops = self_loops & protected
    if protected_self_loops:
        raise InvalidState(
            f"Protected net bit(s) {sorted(protected_self_loops)} carry a "
            f"self-loop; cannot break it without disabling a protected pin."
        )
    chosen: set[int] = set(self_loops)
    remaining = graph.copy()
    remaining.remove_nodes_from(chosen)

    work = [
        remaining.subgraph(component).copy()
        for component in nx.strongly_connected_components(remaining)
        if len(component) > 1
    ]
    while work:
        scc = work.pop()
        candidates = [
            node
            for node in scc.nodes()
            if node not in protected and node not in last_resort
        ] or [node for node in scc.nodes() if node in last_resort]
        if not candidates:
            raise InvalidState(
                f"Strongly connected component of {scc.number_of_nodes()} nets is "
                f"entirely protected; no routing net to break the loop on."
            )
        victim = max(
            candidates,
            key=lambda node: (scc.in_degree(node) * scc.out_degree(node), node),
        )
        chosen.add(victim)
        scc.remove_node(victim)
        for component in nx.strongly_connected_components(scc):
            if len(component) > 1:
                work.append(scc.subgraph(component).copy())

    return chosen


def loop_break_nets(
    netlist: YosysJson, *, top: str, bel_modules: set[str]
) -> list[str]:
    """Name the nets whose driver pins break every combinational loop of `top`.

    Parameters
    ----------
    netlist : YosysJson
        Gate-level netlist with its standard cells modelled (see
        `YosysJson.from_netlist`).
    top : str
        Name of the top module to analyse.
    bel_modules : set[str]
        Yosys module selection patterns of the BELs, the same strings passed to
        `SYNTH_KEEP_HIERARCHY_MODULES`. Each must match a module instantiated in
        `top`.

    Returns
    -------
    list[str]
        Net names in `top`, sorted.

    Raises
    ------
    InvalidState
        A BEL pattern matches no module instantiated in `top`, so its logic was
        flattened into the routing, or a chosen net bit does not have exactly one
        public name.
    """
    module = netlist.modules[top]
    bel_cells = [
        cell
        for cell in module.cells.values()
        if any(fnmatchcase(cell.type, pattern) for pattern in bel_modules)
    ]
    flattened = {
        pattern
        for pattern in bel_modules
        if not any(fnmatchcase(cell.type, pattern) for cell in bel_cells)
    }
    if flattened:
        raise InvalidState(
            f"BEL module(s) {sorted(flattened)} match no module in {top}, so "
            f"their logic cannot be told apart from routing. Keep them as their "
            f"own modules through synthesis with `SYNTH_KEEP_HIERARCHY_MODULES`."
        )
    cuts = select_break_nodes(
        netlist.bit_graph(top),
        protected={bit for cell in bel_cells for bit in cell.port_bits(IO.OUTPUT)},
        last_resort={bit for cell in bel_cells for bit in cell.port_bits(IO.INPUT)},
    )

    names: defaultdict[int, list[str]] = defaultdict(list)
    for net_name, net in module.netnames.items():
        if net.hide_name:
            continue
        for bit, bit_name in zip(net.bits, net.bit_names(net_name), strict=True):
            if isinstance(bit, int):
                names[bit].append(bit_name)
    for cut in cuts:
        if len(names[cut]) != 1:
            raise InvalidState(
                f"Loop-break net bit {cut} in {top} has public names "
                f"{names[cut]}; a cut needs exactly one."
            )
    return sorted(names[cut][0] for cut in cuts)


def render_sdc(*, base_sdc: str, nets: list[str], design_name: str) -> str:
    """Render the base SDC followed by one loop-break cut per net.

    Each cut disables the timing arcs of the single output pin driving the net.
    The SDC raises a Tcl error if a net does not resolve to exactly one driver
    pin, so a stale or renamed net fails the step reading it.

    Parameters
    ----------
    base_sdc : str
        SDC text the cuts are appended to, such as clock definitions.
    nets : list[str]
        Net names whose driver pins are disabled.
    design_name : str
        Design recorded in the header.

    Returns
    -------
    str
        The complete SDC file contents.
    """
    return (
        template_env()
        .get_template("loop_break.sdc.j2")
        .render(base_sdc=base_sdc, nets=nets, design_name=design_name)
    )
