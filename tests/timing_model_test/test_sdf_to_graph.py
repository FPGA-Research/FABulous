from pathlib import Path

import networkx as nx
import pytest

import fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base as base_mod
from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph import SDFTimingGraph
from fabulous.fabric_cad.timing_model.models import (
    Component,
    DelayType,
    SDFCellType,
    SDFGobject,
)


def make_component(
    *,
    c_type: SDFCellType,
    cell_name: str,
    connection_string: str,
    from_cell_instance: str,
    to_cell_instance: str,
    from_cell_pin: str,
    to_cell_pin: str,
    delay: float,
) -> Component:
    return Component(
        c_type=c_type,
        cell_name=cell_name,
        connection_string=connection_string,
        from_cell_instance=from_cell_instance,
        to_cell_instance=to_cell_instance,
        from_cell_pin=from_cell_pin,
        to_cell_pin=to_cell_pin,
        delay=delay,
        delay_paths={"fast": {"min": delay, "max": delay}},
        is_one_cell_instance=(from_cell_instance == to_cell_instance),
        is_timing_check=False,
        is_timing_env=False,
        is_absolute=True,
        is_incremental=False,
        is_cond=False,
        cond_equation=None,
        from_pin_edge=None,
        to_pin_edge=None,
    )


@pytest.fixture
def fake_sdf_gobject() -> SDFGobject:
    graph = nx.DiGraph()

    comp_a_b = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="A->B",
        from_cell_instance="",
        to_cell_instance="U1",
        from_cell_pin="A",
        to_cell_pin="B",
        delay=1.0,
    )
    comp_a_c = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="A->C",
        from_cell_instance="",
        to_cell_instance="U2",
        from_cell_pin="A",
        to_cell_pin="C",
        delay=2.0,
    )
    comp_b_d = make_component(
        c_type=SDFCellType.IOPATH,
        cell_name="BUF_X1",
        connection_string="B->D",
        from_cell_instance="U1",
        to_cell_instance="U1",
        from_cell_pin="B",
        to_cell_pin="D",
        delay=3.0,
    )
    comp_c_d = make_component(
        c_type=SDFCellType.IOPATH,
        cell_name="BUF_X2",
        connection_string="C->D",
        from_cell_instance="U2",
        to_cell_instance="U2",
        from_cell_pin="C",
        to_cell_pin="D",
        delay=1.0,
    )
    comp_d_e = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="D->E",
        from_cell_instance="U3",
        to_cell_instance="",
        from_cell_pin="D",
        to_cell_pin="E",
        delay=4.0,
    )
    comp_f_g = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="F->G",
        from_cell_instance="",
        to_cell_instance="",
        from_cell_pin="F",
        to_cell_pin="G",
        delay=1.0,
    )
    comp_g_h = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="G->H",
        from_cell_instance="",
        to_cell_instance="",
        from_cell_pin="G",
        to_cell_pin="H",
        delay=1.0,
    )

    graph.add_edge("A", "B", weight=1.0, component=comp_a_b)
    graph.add_edge("A", "C", weight=2.0, component=comp_a_c)
    graph.add_edge("B", "D", weight=3.0, component=comp_b_d)
    graph.add_edge("C", "D", weight=1.0, component=comp_c_d)
    graph.add_edge("D", "E", weight=4.0, component=comp_d_e)
    graph.add_edge("F", "G", weight=1.0, component=comp_f_g)
    graph.add_edge("G", "H", weight=1.0, component=comp_g_h)

    return SDFGobject(
        nx_graph=graph,
        hier_sep="/",
        header_info={"divider": "/"},
        sdf_data={"dummy": True},
        cells=["BUF_X1", "BUF_X2"],
        instances={},
        io_paths=[comp_b_d, comp_c_d],
        interconnects=[comp_a_b, comp_a_c, comp_d_e, comp_f_g, comp_g_h],
    )


@pytest.fixture
def sdf_graph(
    tmp_path: Path,
    fake_sdf_gobject: SDFGobject,
    monkeypatch: pytest.MonkeyPatch,
) -> SDFTimingGraph:
    sdf_file = tmp_path / "dummy.sdf"
    sdf_file.write_text("dummy sdf content")

    monkeypatch.setattr(
        base_mod,
        "gen_timing_digraph",
        lambda *_args: fake_sdf_gobject,
    )

    return SDFTimingGraph(sdf_file, DelayType.MAX_ALL)


def test_has_path_true_and_false(sdf_graph: SDFTimingGraph) -> None:
    assert sdf_graph.has_path("A", "E") is True
    assert sdf_graph.has_path("F", "H") is True
    assert sdf_graph.has_path("B", "C") is False
    assert sdf_graph.has_path("A", "H") is False


@pytest.mark.parametrize(
    ("target", "expected"),
    [("E", 7.0), ("D", 3.0)],
    ids=["through_lighter_branch", "lower_delay_not_fewer_edges"],
)
def test_single_delay_returns_shortest_weighted_path(
    sdf_graph: SDFTimingGraph, target: str, expected: float
) -> None:
    assert sdf_graph.single_delay("A", target) == expected


def test_single_delay_raises_when_no_path_exists(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.raises(nx.NetworkXNoPath):
        sdf_graph.single_delay("A", "H")


def test_earliest_common_nodes_invalid_mode_raises(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.raises(ValueError, match="mode must be 'max' or 'sum'"):
        sdf_graph.earliest_common_nodes(["A", "B"], mode="bad")


def test_earliest_common_nodes_missing_sources_raise(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.raises(ValueError, match="Source node\\(s\\) not in graph"):
        sdf_graph.earliest_common_nodes(["A", "NOPE"], mode="max")


def test_earliest_common_nodes_empty_sources_returns_empty_result(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes([])

    assert best_nodes == []
    assert best_cost is None
    assert dists == {}


@pytest.mark.parametrize(
    (
        "sentinel",
        "prefer_sentinel",
        "follow_steps",
        "expected_nodes",
        "expected_cost",
    ),
    [
        (None, False, 0, ["A"], 0),
        ("E", False, 2, ["A"], 0),
        ("E", True, 0, ["A"], 0),
        ("E", True, 2, ["D"], 2),
        ("E", True, 99, ["E"], 3),
        ("E", True, -5, ["A"], 0),
        ("H", True, 2, ["A"], 0),
        ("NOT_IN_GRAPH", True, 2, ["A"], 0),
    ],
    ids=[
        "no_sentinel",
        "sentinel_not_preferred",
        "zero_steps",
        "two_steps",
        "steps_clamped_to_path_end",
        "negative_steps_clamped_to_zero",
        "sentinel_unreachable",
        "sentinel_not_in_graph",
    ],
)
def test_earliest_common_nodes_single_source(
    sdf_graph: SDFTimingGraph,
    sentinel: str | None,
    prefer_sentinel: bool,
    follow_steps: int,
    expected_nodes: list[str],
    expected_cost: int,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel=sentinel,
        prefer_sentinel_for_single_source=prefer_sentinel,
        follow_steps_to_sentinel=follow_steps,
    )

    assert best_nodes == expected_nodes
    assert best_cost == expected_cost
    # distances are hop counts, not delays
    assert dists == {"A": {"A": 0, "B": 1, "C": 1, "D": 2, "E": 3}}


@pytest.mark.parametrize(
    ("mode", "expected_cost"),
    [("max", 1), ("sum", 2)],
)
def test_earliest_common_nodes_multi_source_mode(
    sdf_graph: SDFTimingGraph, mode: str, expected_cost: int
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["B", "C"], mode=mode
    )

    assert best_nodes == ["D"]
    assert best_cost == expected_cost
    assert dists == {"B": {"B": 0, "D": 1, "E": 2}, "C": {"C": 0, "D": 1, "E": 2}}


def test_earliest_common_nodes_with_cutoff_can_remove_common_nodes(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["B", "C"], mode="max", stop=0
    )

    assert best_nodes == []
    assert best_cost is None
    assert dists["B"] == {"B": 0}
    assert dists["C"] == {"C": 0}


def test_earliest_common_nodes_no_common_reachable_node_returns_empty(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A", "F"], mode="max"
    )

    assert best_nodes == []
    assert best_cost is None
    assert dists == {
        "A": {"A": 0, "B": 1, "C": 1, "D": 2, "E": 3},
        "F": {"F": 0, "G": 1, "H": 2},
    }


# Each graph is built so that the selection stage named by the id picks a
# different node than every later stage, ending in the lexicographic fallback.
# Without a cutoff the two reach scores coincide, so only `stop` separates them.
@pytest.mark.parametrize(
    ("edges", "stop", "expected_node", "expected_cost"),
    [
        (
            [
                ("S1", "A"),
                ("S2", "B"),
                ("A", "X"),
                ("B", "X"),
                ("A", "W"),
                ("B", "Z"),
                ("Z", "W"),
            ],
            None,
            "X",
            2,
        ),
        (
            [
                ("S1", "P"),
                ("P", "X"),
                ("S2", "Q"),
                ("Q", "X"),
                ("X", "Y"),
                ("S1", "Y"),
                ("S2", "Y"),
            ],
            None,
            "X",
            2,
        ),
        (
            [
                ("S1", "A"),
                ("S2", "A"),
                ("S1", "B"),
                ("S2", "B"),
                ("B", "C"),
                ("B", "C2"),
                ("A", "D"),
                ("D", "E"),
                ("E", "F"),
            ],
            2,
            "B",
            1,
        ),
        (
            [("S1", "A"), ("S2", "A"), ("S1", "B"), ("S2", "B"), ("B", "C")],
            1,
            "B",
            1,
        ),
        (
            [("S1", "B"), ("S2", "B"), ("S1", "A"), ("S2", "A")],
            None,
            "A",
            1,
        ),
    ],
    ids=[
        "lowest_cost",
        "earliest_scc_only",
        "common_reach_tie_break_under_cutoff",
        "total_reach_tie_break_under_cutoff",
        "lexicographic_fallback",
    ],
)
def test_earliest_common_nodes_multi_source_selection(
    edges: list[tuple[str, str]],
    stop: float | None,
    expected_node: str,
    expected_cost: int,
) -> None:
    obj = SDFTimingGraph.__new__(SDFTimingGraph)
    obj.graph = nx.DiGraph(edges)

    best_nodes, best_cost, _ = obj.earliest_common_nodes(
        ["S1", "S2"], mode="max", stop=stop
    )

    assert best_nodes == [expected_node]
    assert best_cost == expected_cost


@pytest.mark.parametrize(
    ("start", "num_follow", "expected"),
    [("A", 1, "B"), ("A", 3, "E"), ("E", 3, "E"), ("A", 0, "A")],
    ids=["one_hop", "multiple_hops", "stops_without_successor", "zero_hops"],
)
def test_follow_first_fanout_from_pins(
    sdf_graph: SDFTimingGraph, start: str, num_follow: int, expected: str
) -> None:
    assert sdf_graph.follow_first_fanout_from_pins(start, num_follow) == expected


@pytest.mark.parametrize(
    ("source", "targets", "kwargs", "expected_path", "expected_closest"),
    [
        ("A", ["D", "E"], {"weight": None}, ["A", "B", "D"], "D"),
        ("A", ["D", "E"], {"weight": "weight"}, ["A", "C", "D"], "D"),
        (
            "E",
            ["A", "B"],
            {"weight": "weight", "reverse": True},
            ["E", "D", "B"],
            "B",
        ),
        ("A", ["H"], {"weight": "weight"}, None, None),
        (
            "A",
            ["D"],
            {"weight": None, "sentinel_prefix": "custom_prefix"},
            ["A", "B", "D"],
            "D",
        ),
    ],
    ids=[
        "unweighted_forward",
        "weighted_forward",
        "reverse_graph",
        "no_reachable_target",
        "custom_sentinel_prefix",
    ],
)
def test_path_to_nearest_target_sentinel(
    sdf_graph: SDFTimingGraph,
    source: str,
    targets: list[str],
    kwargs: dict[str, object],
    expected_path: list[str] | None,
    expected_closest: str | None,
) -> None:
    edges_before = set(sdf_graph.graph.edges)
    reverse_edges_before = set(sdf_graph.reverse_graph.edges)

    path, closest = sdf_graph.path_to_nearest_target_sentinel(source, targets, **kwargs)

    assert path == expected_path
    assert closest == expected_closest
    # the temporary sentinel and its edges are removed again
    assert set(sdf_graph.graph.edges) == edges_before
    assert set(sdf_graph.reverse_graph.edges) == reverse_edges_before


def test_path_to_nearest_target_sentinel_empty_targets_raises_valueerror(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.raises(
        ValueError, match="targets must be a non-empty iterable of nodes"
    ):
        sdf_graph.path_to_nearest_target_sentinel("A", [], weight="weight")


def test_path_to_nearest_target_sentinel_ignores_missing_target_nodes(
    sdf_graph: SDFTimingGraph,
) -> None:
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["DOES_NOT_EXIST", "D"], weight="weight"
    )

    assert path == ["A", "C", "D"]
    assert closest == "D"


def test_path_to_nearest_target_sentinel_leaves_graph_nodes_unchanged(
    sdf_graph: SDFTimingGraph,
) -> None:
    nodes_before = set(sdf_graph.graph.nodes)

    sdf_graph.path_to_nearest_target_sentinel(
        "A", ["DOES_NOT_EXIST", "D"], weight="weight"
    )

    assert set(sdf_graph.graph.nodes) == nodes_before
