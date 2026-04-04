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
):
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
def fake_sdf_gobject():
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
def sdf_graph(tmp_path, fake_sdf_gobject, monkeypatch):
    sdf_file = tmp_path / "dummy.sdf"
    sdf_file.write_text("dummy sdf content")

    monkeypatch.setattr(
        base_mod,
        "gen_timing_digraph",
        lambda path, delay_type: fake_sdf_gobject,
    )

    return SDFTimingGraph(sdf_file, DelayType.MAX_ALL)


def test_inherits_base_initialization(sdf_graph):
    assert sdf_graph.sdf_file.name == "dummy.sdf"
    assert sdf_graph.sdf_file_content == "dummy sdf content"
    assert sdf_graph.delay_type_str == DelayType.MAX_ALL
    assert isinstance(sdf_graph.graph, nx.DiGraph)
    assert isinstance(sdf_graph.reverse_graph, nx.DiGraph)
    assert sdf_graph.header_info == {"divider": "/"}
    assert sdf_graph.cells == ["BUF_X1", "BUF_X2"]


def test_has_path_true_and_false(sdf_graph):
    assert sdf_graph.has_path("A", "E") is True
    assert sdf_graph.has_path("F", "H") is True
    assert sdf_graph.has_path("B", "C") is False
    assert sdf_graph.has_path("A", "H") is False


def test_single_delay_returns_shortest_weighted_path_and_info(sdf_graph):
    length = sdf_graph.single_delay("A", "E")

    assert length == 7.0


def test_single_delay_prefers_lower_total_delay_not_fewer_edges(sdf_graph):
    length = sdf_graph.single_delay("A", "D")
    assert length == 3.0

def test_single_delay_raises_when_no_path_exists(sdf_graph):
    with pytest.raises(nx.NetworkXNoPath):
        sdf_graph.single_delay("A", "H")


def test_earliest_common_nodes_invalid_mode_raises(sdf_graph):
    with pytest.raises(ValueError, match="mode must be 'max' or 'sum'"):
        sdf_graph.earliest_common_nodes(["A", "B"], mode="bad")


def test_earliest_common_nodes_missing_sources_raise(sdf_graph):
    with pytest.raises(ValueError, match="Source node\\(s\\) not in graph"):
        sdf_graph.earliest_common_nodes(["A", "NOPE"], mode="max")


def test_earliest_common_nodes_empty_sources_returns_empty_result(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes([])

    assert best_nodes == []
    assert best_cost is None
    assert dists == {}


def test_earliest_common_nodes_single_source_returns_source(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(["A"])

    assert best_nodes == ["A"]
    assert best_cost == 0.0
    assert dists["A"]["A"] == 0


def test_earliest_common_nodes_single_source_prefers_sentinel_and_follows_zero_steps(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=0,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0
    assert dists["A"]["E"] == 3


def test_earliest_common_nodes_single_source_prefers_sentinel_and_follows_steps(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["D"]
    assert best_cost == 2
    assert dists["A"]["D"] == 2


def test_earliest_common_nodes_single_source_follow_steps_are_clamped_to_path_end(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=99,
    )

    assert best_nodes == ["E"]
    assert best_cost == 3
    assert dists["A"]["E"] == 3


def test_earliest_common_nodes_single_source_negative_follow_steps_clamp_to_zero(sdf_graph):
    best_nodes, best_cost, _ = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=-5,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0


def test_earliest_common_nodes_single_source_sentinel_not_reachable_returns_source(sdf_graph):
    best_nodes, best_cost, _ = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="H",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0.0


def test_earliest_common_nodes_single_source_sentinel_not_in_graph_returns_source(sdf_graph):
    best_nodes, best_cost, _ = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="NOT_IN_GRAPH",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0.0


def test_earliest_common_nodes_max_multi_source(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["B", "C"], mode="max"
    )

    assert best_nodes == ["D"]
    assert best_cost == 1
    assert dists["B"]["D"] == 1
    assert dists["C"]["D"] == 1
    assert dists["B"]["E"] == 2
    assert dists["C"]["E"] == 2


def test_earliest_common_nodes_sum_multi_source(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["B", "C"], mode="sum"
    )

    assert best_nodes == ["D"]
    assert best_cost == 2
    assert dists["B"]["D"] + dists["C"]["D"] == 2


def test_earliest_common_nodes_with_cutoff_can_remove_common_nodes(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["B", "C"], mode="max", stop=0
    )

    assert best_nodes == []
    assert best_cost is None
    assert dists["B"] == {"B": 0}
    assert dists["C"] == {"C": 0}


def test_earliest_common_nodes_no_common_reachable_node_returns_empty(sdf_graph):
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A", "F"], mode="max"
    )

    assert best_nodes == []
    assert best_cost is None
    assert "A" in dists
    assert "F" in dists


def test_earliest_common_nodes_can_return_multiple_scc_candidates_but_choose_one_by_cost():
    graph = nx.DiGraph()
    comp = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="dummy",
        from_cell_instance="",
        to_cell_instance="",
        from_cell_pin="X",
        to_cell_pin="Y",
        delay=1.0,
    )

    graph.add_edge("S1", "A", weight=1.0, component=comp)
    graph.add_edge("S2", "B", weight=1.0, component=comp)
    graph.add_edge("A", "X", weight=1.0, component=comp)
    graph.add_edge("B", "X", weight=1.0, component=comp)
    graph.add_edge("A", "Y", weight=1.0, component=comp)
    graph.add_edge("B", "Y", weight=2.0, component=comp)

    obj = SDFTimingGraph.__new__(SDFTimingGraph)
    obj.graph = graph
    obj.reverse_graph = graph.reverse(copy=True)

    best_nodes, best_cost, dists = obj.earliest_common_nodes(["S1", "S2"], mode="max")

    assert best_nodes == ["X"]
    assert best_cost == 2
    assert dists["S1"]["X"] == 2
    assert dists["S2"]["X"] == 2


def test_earliest_common_nodes_tie_break_by_common_reach_score():
    graph = nx.DiGraph()
    comp = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="dummy",
        from_cell_instance="",
        to_cell_instance="",
        from_cell_pin="X",
        to_cell_pin="Y",
        delay=1.0,
    )

    graph.add_edge("S1", "A", weight=1.0, component=comp)
    graph.add_edge("S2", "A", weight=1.0, component=comp)
    graph.add_edge("S1", "B", weight=1.0, component=comp)
    graph.add_edge("S2", "B", weight=1.0, component=comp)
    graph.add_edge("A", "C", weight=1.0, component=comp)
    graph.add_edge("C", "D", weight=1.0, component=comp)

    obj = SDFTimingGraph.__new__(SDFTimingGraph)
    obj.graph = graph
    obj.reverse_graph = graph.reverse(copy=True)

    best_nodes, best_cost, _ = obj.earliest_common_nodes(["S1", "S2"], mode="max")

    assert best_nodes == ["A"]
    assert best_cost == 1


def test_earliest_common_nodes_tie_break_by_total_reach_score_then_lexicographic():
    graph = nx.DiGraph()
    comp = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="dummy",
        from_cell_instance="",
        to_cell_instance="",
        from_cell_pin="X",
        to_cell_pin="Y",
        delay=1.0,
    )

    graph.add_edge("S1", "A", weight=1.0, component=comp)
    graph.add_edge("S2", "A", weight=1.0, component=comp)
    graph.add_edge("S1", "B", weight=1.0, component=comp)
    graph.add_edge("S2", "B", weight=1.0, component=comp)

    obj = SDFTimingGraph.__new__(SDFTimingGraph)
    obj.graph = graph
    obj.reverse_graph = graph.reverse(copy=True)

    best_nodes, best_cost, _ = obj.earliest_common_nodes(["S1", "S2"], mode="max")

    assert best_nodes == ["A"]
    assert best_cost == 1


def test_follow_first_fanout_from_pins_one_hop(sdf_graph):
    assert sdf_graph.follow_first_fanout_from_pins("A", num_follow=1) == "B"


def test_follow_first_fanout_from_pins_multiple_hops(sdf_graph):
    assert sdf_graph.follow_first_fanout_from_pins("A", num_follow=3) == "E"


def test_follow_first_fanout_from_pins_stops_when_no_successor(sdf_graph):
    assert sdf_graph.follow_first_fanout_from_pins("E", num_follow=3) == "E"


def test_follow_first_fanout_from_pins_zero_hops_returns_same_pin(sdf_graph):
    assert sdf_graph.follow_first_fanout_from_pins("A", num_follow=0) == "A"


def test_path_to_nearest_target_sentinel_unweighted_forward(sdf_graph):
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["D", "E"], weight=None
    )

    assert path == ["A", "B", "D"]
    assert closest == "D"
    assert all("_sentinel_" not in node for node in path)
    assert not any("_sentinel_" in str(node) for node in sdf_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_weighted_forward(sdf_graph):
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["D", "E"], weight="weight"
    )

    assert path == ["A", "C", "D"]
    assert closest == "D"
    assert not any("_sentinel_" in str(node) for node in sdf_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_reverse_uses_reverse_graph(sdf_graph):
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "E", ["A", "B"], weight="weight", reverse=True
    )

    assert path == ["E", "D", "B"]
    assert closest == "B"
    assert not any("_sentinel_" in str(node) for node in sdf_graph.reverse_graph.nodes)


def test_path_to_nearest_target_sentinel_no_reachable_target_returns_none(sdf_graph):
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["H"], weight="weight"
    )

    assert path is None
    assert closest is None
    assert not any("_sentinel_" in str(node) for node in sdf_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_empty_targets_raises_valueerror(sdf_graph):
    with pytest.raises(ValueError, match="targets must be a non-empty iterable of nodes"):
        sdf_graph.path_to_nearest_target_sentinel("A", [], weight="weight")


def test_path_to_nearest_target_sentinel_custom_prefix_is_cleaned_up(sdf_graph):
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["D"], sentinel_prefix="custom_prefix", weight=None
    )

    assert path == ["A", "B", "D"]
    assert closest == "D"
    assert not any("custom_prefix" in str(node) for node in sdf_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_ignores_missing_target_nodes(sdf_graph):
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["DOES_NOT_EXIST", "D"], weight="weight"
    )

    assert path == ["A", "C", "D"]
    assert closest == "D"