"""Tests for `graph_algorithms`: corner projection and timing-graph queries.

Covers the corner-projection policy (`DelayType` / `project_delay`), the
delay-aware `single_delay` critical-path query, and the structural graph queries
that run on a plain `networkx` directed graph: earliest-common-node convergence,
fan-out following, and nearest-target search via the sentinel trick.
"""

import networkx as nx
import pytest
from sdf_toolkit import TimingGraph, parse
from sdf_toolkit.core.model import DelayPaths, Values

from fabulous.routing_model.graph_algorithms import (
    DelayType,
    earliest_common_nodes,
    follow_first_fanout_from_pins,
    path_to_nearest_target_sentinel,
    project_delay,
    single_delay,
)


@pytest.fixture
def timing_graph() -> nx.DiGraph:
    """Build a small timing graph for the core algorithm tests.

    Topology (edge weights in parentheses):

        A -(1)-> B -(3)-> D -(4)-> E
        A -(2)-> C -(1)-> D
        F -(1)-> G -(1)-> H
    """
    g = nx.DiGraph()
    g.add_edge("A", "B", weight=1.0)
    g.add_edge("A", "C", weight=2.0)
    g.add_edge("B", "D", weight=3.0)
    g.add_edge("C", "D", weight=1.0)
    g.add_edge("D", "E", weight=4.0)
    g.add_edge("F", "G", weight=1.0)
    g.add_edge("G", "H", weight=1.0)
    return g


def test_earliest_common_nodes_invalid_mode_raises(timing_graph: nx.DiGraph) -> None:
    with pytest.raises(ValueError, match="mode must be 'max' or 'sum'"):
        earliest_common_nodes(timing_graph, ["A", "B"], mode="bad")


def test_earliest_common_nodes_missing_sources_raise(
    timing_graph: nx.DiGraph,
) -> None:
    with pytest.raises(ValueError, match="Source node\\(s\\) not in graph"):
        earliest_common_nodes(timing_graph, ["A", "NOPE"], mode="max")


def test_earliest_common_nodes_empty_sources_returns_empty_result(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(timing_graph, [])

    assert best_nodes == []
    assert best_cost is None
    assert dists == {}


def test_earliest_common_nodes_single_source_returns_source(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(timing_graph, ["A"])

    assert best_nodes == ["A"]
    assert best_cost == 0.0
    assert dists["A"]["A"] == 0


def test_earliest_common_nodes_single_source_prefers_sentinel_and_follows_zero_steps(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(
        timing_graph,
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=0,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0
    assert dists["A"]["E"] == 3


def test_earliest_common_nodes_single_source_prefers_sentinel_and_follows_steps(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(
        timing_graph,
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["D"]
    assert best_cost == 2
    assert dists["A"]["D"] == 2


def test_earliest_common_nodes_single_source_follow_steps_are_clamped_to_path_end(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(
        timing_graph,
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=99,
    )

    assert best_nodes == ["E"]
    assert best_cost == 3
    assert dists["A"]["E"] == 3


def test_earliest_common_nodes_single_source_negative_follow_steps_clamp_to_zero(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, _ = earliest_common_nodes(
        timing_graph,
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=-5,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0


def test_earliest_common_nodes_single_source_sentinel_not_reachable_returns_source(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, _ = earliest_common_nodes(
        timing_graph,
        ["A"],
        sentinel="H",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0.0


def test_earliest_common_nodes_single_source_sentinel_not_in_graph_returns_source(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, _ = earliest_common_nodes(
        timing_graph,
        ["A"],
        sentinel="NOT_IN_GRAPH",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0.0


def test_earliest_common_nodes_max_multi_source(timing_graph: nx.DiGraph) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(
        timing_graph, ["B", "C"], mode="max"
    )

    assert best_nodes == ["D"]
    assert best_cost == 1
    assert dists["B"]["D"] == 1
    assert dists["C"]["D"] == 1
    assert dists["B"]["E"] == 2
    assert dists["C"]["E"] == 2


def test_earliest_common_nodes_sum_multi_source(timing_graph: nx.DiGraph) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(
        timing_graph, ["B", "C"], mode="sum"
    )

    assert best_nodes == ["D"]
    assert best_cost == 2
    assert dists["B"]["D"] + dists["C"]["D"] == 2


def test_earliest_common_nodes_with_cutoff_can_remove_common_nodes(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(
        timing_graph, ["B", "C"], mode="max", stop=0
    )

    assert best_nodes == []
    assert best_cost is None
    assert dists["B"] == {"B": 0}
    assert dists["C"] == {"C": 0}


def test_earliest_common_nodes_no_common_reachable_node_returns_empty(
    timing_graph: nx.DiGraph,
) -> None:
    best_nodes, best_cost, dists = earliest_common_nodes(
        timing_graph, ["A", "F"], mode="max"
    )

    assert best_nodes == []
    assert best_cost is None
    assert "A" in dists
    assert "F" in dists


def test_earliest_common_nodes_choose_one_by_cost() -> None:
    g = nx.DiGraph()
    g.add_edge("S1", "A", weight=1.0)
    g.add_edge("S2", "B", weight=1.0)
    g.add_edge("A", "X", weight=1.0)
    g.add_edge("B", "X", weight=1.0)
    g.add_edge("A", "Y", weight=1.0)
    g.add_edge("B", "Y", weight=2.0)

    best_nodes, best_cost, dists = earliest_common_nodes(g, ["S1", "S2"], mode="max")

    assert best_nodes == ["X"]
    assert best_cost == 2
    assert dists["S1"]["X"] == 2
    assert dists["S2"]["X"] == 2


def test_earliest_common_nodes_tie_break_by_common_reach_score() -> None:
    g = nx.DiGraph()
    g.add_edge("S1", "A", weight=1.0)
    g.add_edge("S2", "A", weight=1.0)
    g.add_edge("S1", "B", weight=1.0)
    g.add_edge("S2", "B", weight=1.0)
    g.add_edge("A", "C", weight=1.0)
    g.add_edge("C", "D", weight=1.0)

    best_nodes, best_cost, _ = earliest_common_nodes(g, ["S1", "S2"], mode="max")

    assert best_nodes == ["A"]
    assert best_cost == 1


def test_earliest_common_nodes_total_reach_score_tie_break() -> None:
    g = nx.DiGraph()
    g.add_edge("S1", "A", weight=1.0)
    g.add_edge("S2", "A", weight=1.0)
    g.add_edge("S1", "B", weight=1.0)
    g.add_edge("S2", "B", weight=1.0)

    best_nodes, best_cost, _ = earliest_common_nodes(g, ["S1", "S2"], mode="max")

    assert best_nodes == ["A"]
    assert best_cost == 1


def test_follow_first_fanout_from_pins_one_hop(timing_graph: nx.DiGraph) -> None:
    assert follow_first_fanout_from_pins(timing_graph, "A", num_follow=1) == "B"


def test_follow_first_fanout_from_pins_multiple_hops(timing_graph: nx.DiGraph) -> None:
    assert follow_first_fanout_from_pins(timing_graph, "A", num_follow=3) == "E"


def test_follow_first_fanout_from_pins_stops_when_no_successor(
    timing_graph: nx.DiGraph,
) -> None:
    assert follow_first_fanout_from_pins(timing_graph, "E", num_follow=3) == "E"


def test_follow_first_fanout_from_pins_zero_hops_returns_same_pin(
    timing_graph: nx.DiGraph,
) -> None:
    assert follow_first_fanout_from_pins(timing_graph, "A", num_follow=0) == "A"


def test_path_to_nearest_target_sentinel_unweighted_forward(
    timing_graph: nx.DiGraph,
) -> None:
    path, closest = path_to_nearest_target_sentinel(
        timing_graph, "A", ["D", "E"], weight=None
    )

    assert path == ["A", "B", "D"]
    assert closest == "D"
    assert all("_sentinel_" not in node for node in path)
    assert not any("_sentinel_" in str(node) for node in timing_graph.nodes)


def test_path_to_nearest_target_sentinel_weighted_forward(
    timing_graph: nx.DiGraph,
) -> None:
    path, closest = path_to_nearest_target_sentinel(
        timing_graph, "A", ["D", "E"], weight="weight"
    )

    assert path == ["A", "C", "D"]
    assert closest == "D"
    assert not any("_sentinel_" in str(node) for node in timing_graph.nodes)


def test_path_to_nearest_target_sentinel_reverse_uses_reversed_graph(
    timing_graph: nx.DiGraph,
) -> None:
    reverse_graph = timing_graph.reverse(copy=True)
    path, closest = path_to_nearest_target_sentinel(
        reverse_graph, "E", ["A", "B"], weight="weight"
    )

    assert path == ["E", "D", "B"]
    assert closest == "B"
    assert not any("_sentinel_" in str(node) for node in reverse_graph.nodes)


def test_path_to_nearest_target_sentinel_no_reachable_target_returns_none(
    timing_graph: nx.DiGraph,
) -> None:
    path, closest = path_to_nearest_target_sentinel(
        timing_graph, "A", ["H"], weight="weight"
    )

    assert path is None
    assert closest is None
    assert not any("_sentinel_" in str(node) for node in timing_graph.nodes)


def test_path_to_nearest_target_sentinel_empty_targets_raises_valueerror(
    timing_graph: nx.DiGraph,
) -> None:
    with pytest.raises(
        ValueError, match="targets must be a non-empty iterable of nodes"
    ):
        path_to_nearest_target_sentinel(timing_graph, "A", [], weight="weight")


def test_path_to_nearest_target_sentinel_custom_prefix_is_cleaned_up(
    timing_graph: nx.DiGraph,
) -> None:
    path, closest = path_to_nearest_target_sentinel(
        timing_graph, "A", ["D"], sentinel_prefix="custom_prefix", weight=None
    )

    assert path == ["A", "B", "D"]
    assert closest == "D"
    assert not any("custom_prefix" in str(node) for node in timing_graph.nodes)


def test_path_to_nearest_target_sentinel_ignores_missing_target_nodes(
    timing_graph: nx.DiGraph,
) -> None:
    path, closest = path_to_nearest_target_sentinel(
        timing_graph, "A", ["DOES_NOT_EXIST", "D"], weight="weight"
    )

    assert path == ["A", "C", "D"]
    assert closest == "D"


# ------------------------------ project_delay -----------------------------


def test_project_delay_prefers_nominal_regardless_of_delay_type() -> None:
    delay = DelayPaths(nominal=Values(min=1.0, avg=2.0, max=3.0))
    # Nominal shortcut returns max(min, max) and ignores the corner selector.
    assert project_delay(delay, DelayType.MAX_ALL) == 3.0
    assert project_delay(delay, DelayType.MIN_ALL) == 3.0
    assert project_delay(delay, DelayType.AVG_FAST) == 3.0


@pytest.mark.parametrize(
    ("delay_type", "expected"),
    [
        (DelayType.MAX_ALL, 4.0),
        (DelayType.MIN_ALL, 1.0),
        (DelayType.AVG_ALL, 2.5),
        (DelayType.AVG_FAST, 1.5),
        (DelayType.AVG_SLOW, 3.5),
        (DelayType.MAX_FAST, 2.0),
        (DelayType.MAX_SLOW, 4.0),
        (DelayType.MIN_FAST, 1.0),
        (DelayType.MIN_SLOW, 3.0),
    ],
)
def test_project_delay_fast_slow_corners(
    delay_type: DelayType, expected: float
) -> None:
    delay = DelayPaths(
        fast=Values(min=1.0, avg=1.5, max=2.0),
        slow=Values(min=3.0, avg=3.5, max=4.0),
    )
    assert project_delay(delay, delay_type) == pytest.approx(expected)


def test_project_delay_ignores_unspecified_endpoints() -> None:
    # Only fast.max is given; the missing fast.min is skipped, not read as zero.
    delay = DelayPaths(fast=Values(min=None, max=2.0))
    assert project_delay(delay, DelayType.MAX_ALL) == 2.0
    assert project_delay(delay, DelayType.MIN_ALL) == 2.0
    assert project_delay(delay, DelayType.AVG_FAST) == 2.0


def test_project_delay_raises_when_selected_corner_unspecified() -> None:
    # Only the fast corner exists, so a slow-corner query has nothing to project.
    delay = DelayPaths(fast=Values(min=1.0, max=2.0))
    with pytest.raises(ValueError, match="specifies no value"):
        project_delay(delay, DelayType.AVG_SLOW)


def test_project_delay_raises_when_delay_fully_unspecified() -> None:
    with pytest.raises(ValueError, match="specifies no value"):
        project_delay(DelayPaths(), DelayType.MAX_ALL)


def test_project_delay_unknown_delay_type_raises() -> None:
    delay = DelayPaths(fast=Values(min=1.0, max=2.0))
    with pytest.raises(ValueError, match="Unknown delay type"):
        project_delay(delay, "not_a_delay_type")


# ------------------------------- single_delay -----------------------------

# A small SDF: a top-level input `din` feeds buffer b0 (IOPATH A->Y), whose
# output drives the top-level output `dout`. The IOPATH carries two corners
# (fast and slow), the interconnects a single nominal corner.
SDF_TEXT = """(DELAYFILE
 (DIVIDER /)
 (TIMESCALE 1ns)
 (CELL (CELLTYPE "BUF") (INSTANCE b0)
   (DELAY (ABSOLUTE (IOPATH A Y (0.1:0.2:0.3) (0.1:0.2:0.3)))))
 (CELL (CELLTYPE "top") (INSTANCE)
   (DELAY (ABSOLUTE
     (INTERCONNECT din b0/A (0.05:0.05:0.05))
     (INTERCONNECT b0/Y dout (0.4:0.5:0.6)))))
)"""


@pytest.fixture
def sdf_timing_graph() -> TimingGraph:
    """Parse the sample SDF into sdf_toolkit's native timing graph."""
    return TimingGraph(parse(SDF_TEXT))


def test_single_delay_sums_projected_arc_delays(sdf_timing_graph: TimingGraph) -> None:
    # 0.05 (nominal) + 0.3 (IOPATH MAX_ALL) + 0.6 (nominal) = 0.95.
    assert single_delay(
        sdf_timing_graph, "din", "dout", DelayType.MAX_ALL
    ) == pytest.approx(0.95)


def test_single_delay_respects_delay_type(sdf_timing_graph: TimingGraph) -> None:
    # MIN_ALL collapses the IOPATH corners to 0.1; nominal interconnects are
    # unchanged, so 0.05 + 0.1 + 0.6 = 0.75.
    assert single_delay(
        sdf_timing_graph, "din", "dout", DelayType.MIN_ALL
    ) == pytest.approx(0.75)


def test_single_delay_defaults_to_max_all(sdf_timing_graph: TimingGraph) -> None:
    assert single_delay(sdf_timing_graph, "din", "dout") == pytest.approx(
        single_delay(sdf_timing_graph, "din", "dout", DelayType.MAX_ALL)
    )
