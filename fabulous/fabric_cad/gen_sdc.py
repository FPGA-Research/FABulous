"""Generate SDC constraints that break combinational loops in switch matrices.

The loop graph is built by `Tile.as_graph`, which combines switch-matrix routing
(from a tile's `.list` file) with the tile's BEL combinational arcs (read from
each BEL's parsed netlist via `Bel.get_comb_arcs`) and its intra-tile jump wires.
A combinational loop alternates routing and logic, so the BEL arcs are required
for any loop that closes through a cell (e.g. a LUT feeding its own input). Loops
are broken at node granularity by selecting a small feedback-vertex set (see
`select_break_nodes`) and disabling the driver pin of each chosen net. BEL pins
are excluded from that set so a cut never disables a cell's own combinational
arc; loops break on the switch-matrix and jump-wire feedback instead, which
leaves every BEL forward delay analyzable. The chosen net names are emitted as
portable `set_disable_timing` constraints.
"""

from pathlib import Path

import networkx as nx
from jinja2 import Environment, PackageLoader
from loguru import logger

from fabulous.custom_exception import InvalidState
from fabulous.fabric_definition.tile import Tile

_SDC_ENV = Environment(
    loader=PackageLoader("fabulous.fabric_cad", "templates"),
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
)
_SDC_TEMPLATE = _SDC_ENV.get_template("loop_break.sdc.j2")


# Strongly connected components up to this size are reduced one vertex per round,
# which is near-minimum and exact on the per-tile switch matrices. Larger
# components remove the top `FVS_BATCH_FRACTION` of vertices per round so the
# whole-fabric graph (one large inter-tile component) stays fast.
FVS_SINGLE_MAX = 300
FVS_BATCH_FRACTION = 0.02


def select_break_nodes(
    graph: nx.DiGraph,
    protected: set[str],
    *,
    single_max: int = FVS_SINGLE_MAX,
    batch_fraction: float = FVS_BATCH_FRACTION,
) -> list[str]:
    """Select a feedback-vertex set whose removal makes `graph` acyclic.

    Nodes in `protected` stay in the graph but are never chosen as a cut, so a
    `set_disable_timing` never lands on a cell's own pin.

    Parameters
    ----------
    graph : nx.DiGraph
        Directed connectivity graph. Nodes are net names.
    protected : set[str]
        Net names that must never be chosen as a cut (typically BEL pins). They
        remain in the graph and may still lie on a cycle that is broken elsewhere.
    single_max : int, optional
        Strongly connected components up to this size are reduced one vertex per
        round, which is near-minimum and exact on the per-tile switch matrices.
    batch_fraction : float, optional
        Larger components remove this fraction of their vertices per round so the
        whole-fabric graph (one large inter-tile component) stays fast.

    Returns
    -------
    list[str]
        Sorted list of node names to disable. Empty if `graph` is acyclic.

    Raises
    ------
    InvalidState
        A protected net carries a self-loop, or a strongly connected component
        contains only protected nets, so no loop can be broken without disabling a
        protected pin.
    """
    self_loops = set(nx.nodes_with_selfloops(graph))
    protected_self_loops = self_loops & protected
    if protected_self_loops:
        raise InvalidState(
            f"Protected net(s) {sorted(protected_self_loops)} carry a self-loop; "
            f"cannot break it without disabling a protected pin."
        )
    chosen: set[str] = set(self_loops)
    remaining = graph.copy()
    remaining.remove_nodes_from(chosen)

    work = [
        remaining.subgraph(component).copy()
        for component in nx.strongly_connected_components(remaining)
        if len(component) > 1
    ]
    while work:
        scc = work.pop()
        candidates = [node for node in scc.nodes() if node not in protected]
        if not candidates:
            raise InvalidState(
                f"Strongly connected component of {scc.number_of_nodes()} nets is "
                f"entirely protected; no routing net to break the loop on."
            )
        ranked = sorted(
            candidates,
            key=lambda node: (scc.in_degree(node) * scc.out_degree(node), node),
            reverse=True,
        )
        if scc.number_of_nodes() <= single_max:
            count = 1
        else:
            count = max(1, int(scc.number_of_nodes() * batch_fraction))
        victims = ranked[:count]
        chosen.update(victims)
        scc.remove_nodes_from(victims)
        for component in nx.strongly_connected_components(scc):
            if len(component) > 1:
                work.append(scc.subgraph(component).copy())

    return sorted(chosen)


def render_sdc(break_nodes: list[str], scope: str, *, resolved: bool) -> str:
    """Render SDC text that breaks loops by disabling each node's driver pin.

    Emits one `set_disable_timing` constraint per node, in sorted order, using
    the common-denominator syntax accepted by OpenSTA, Cadence Tempus, and
    Synopsys PrimeTime.

    Parameters
    ----------
    break_nodes : list[str]
        Net names whose driver pins should be disabled.
    scope : str
        Human-readable scope label recorded in the header (e.g. `tile LUT4AB`).
    resolved : bool
        Whether `break_nodes` are real synthesized-netlist net names. When
        `False` (names taken from the `.list` files), a warning is added that
        the names are logical and may not match a synthesized netlist.

    Returns
    -------
    str
        The complete SDC file contents.
    """
    return _SDC_TEMPLATE.render(
        scope=scope,
        resolved=resolved,
        break_nodes=sorted(break_nodes),
    )


def export_tile_sdc(
    tile: Tile,
    out_path: Path,
    *,
    single_max: int = FVS_SINGLE_MAX,
    batch_fraction: float = FVS_BATCH_FRACTION,
) -> Path:
    """Write a loop-break SDC for a single tile.

    The tile graph is the switch-matrix routing graph plus the tile's BEL
    combinational arcs and its intra-tile jump wires (those with zero offset,
    whose `BEG -> END` return path closes loops inside the tile). `tile` must be
    a placed instance from the fabric grid so its `wireList` is populated.

    Parameters
    ----------
    tile : Tile
        Placed tile to analyze.
    out_path : Path
        Destination SDC file path. Parent directories are created.
    single_max : int, optional
        Feedback-vertex-set tuning knob forwarded to `select_break_nodes`.
    batch_fraction : float, optional
        Feedback-vertex-set tuning knob forwarded to `select_break_nodes`.

    Returns
    -------
    Path
        `out_path`.
    """
    graph = tile.as_graph()
    # Protect BEL pins so a cut never disables a cell's own combinational arc.
    protected = {pin for bel in tile.bels for pin in (*bel.inputs, *bel.outputs)}
    break_nodes = select_break_nodes(
        graph, protected, single_max=single_max, batch_fraction=batch_fraction
    )
    text = render_sdc(break_nodes, scope=f"tile {tile.name}", resolved=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    logger.info(f"Wrote loop-break SDC for tile {tile.name} to {out_path}")
    return out_path
