"""Tests for the SDF timing graph, built from real SDF text."""

from pathlib import Path

import networkx as nx
import pytest

from fabulous.fabric_cad.timing_model.models import (
    DelayType,
    SDFCellType,
    SDFPathType,
    SDFTimingTriplet,
)
from fabulous.fabric_cad.timing_model.sdf_timing_graph import SdfTimingGraph

HEADER = '(SDFVERSION "3.0") (DESIGN "Top") (TIMESCALE 1ns)'

# Interconnect delays of the shared graph: A-B-D-E is the shortest path by edge
# count from A to E, A-C-D-E the shortest by delay. F-G-H is not connected to it.
SHARED_EDGES = (
    ("A", "B", 1.0),
    ("A", "C", 2.0),
    ("B", "D", 3.0),
    ("C", "D", 1.0),
    ("D", "E", 4.0),
    ("F", "G", 1.0),
    ("G", "H", 1.0),
)


def write_sdf(
    tmp_path: Path, cells: str, divider: str | None = "/", header: str = HEADER
) -> Path:
    """Write an SDF file holding `cells` and return its path."""
    divider_item = "" if divider is None else f"(DIVIDER {divider})"
    sdf_file = tmp_path / "test.sdf"
    sdf_file.write_text(f"(DELAYFILE {header} {divider_item} {cells})")
    return sdf_file


def top_cell(interconnects: str) -> str:
    """Return the top-level cell holding the given INTERCONNECT entries."""
    return f'(CELL (CELLTYPE "Top") (INSTANCE) (DELAY (ABSOLUTE {interconnects})))'


def interconnects(edges: tuple[tuple[str, str, float], ...]) -> str:
    """Return one INTERCONNECT entry per edge, with a single delay triple."""
    return " ".join(
        f"(INTERCONNECT {source} {sink} ({delay}::{delay}))"
        for source, sink, delay in edges
    )


def graph_of(
    tmp_path: Path,
    cells: str,
    *,
    divider: str | None = "/",
    delay_type: DelayType = DelayType.MAX_ALL,
) -> SdfTimingGraph:
    """Parse `cells` as an SDF file into a timing graph."""
    return SdfTimingGraph(write_sdf(tmp_path, cells, divider), delay_type)


def dff_cell(
    instance: str, clock_to_q: str = "(0.4:0.5:0.6) (0.7:0.8:0.9)", checks: str = ""
) -> str:
    """Return a register cell with a clock-to-output arc and its checks."""
    checks = checks or (
        "(SETUP D (posedge CLK) (0.1:0.2:0.3)) (HOLD D (posedge CLK) (0.01:0.02:0.03))"
    )
    return (
        f'(CELL (CELLTYPE "DFF") (INSTANCE {instance}) '
        f"(DELAY (ABSOLUTE (IOPATH (posedge CLK) Q {clock_to_q}))) "
        f"(TIMINGCHECK {checks}))"
    )


@pytest.fixture
def shared_graph(tmp_path: Path) -> SdfTimingGraph:
    """Build the shared top-level interconnect graph."""
    return graph_of(tmp_path, top_cell(interconnects(SHARED_EDGES)))


def values(
    timing: SDFTimingTriplet | None,
) -> tuple[float | None, float | None, float | None]:
    """Return a triple as a tuple, so `pytest.approx` can compare it."""
    assert timing is not None
    return (timing.minimum, timing.typical, timing.maximum)


@pytest.mark.parametrize(
    ("delays", "kind", "expected"),
    [
        pytest.param("(1::2) (3::4)", DelayType.MIN_ALL, 1.0, id="min-all"),
        pytest.param("(1::2) (3::4)", DelayType.MAX_ALL, 4.0, id="max-all"),
        pytest.param("(1::2) (3::4)", DelayType.AVG_ALL, 2.5, id="avg-all"),
        pytest.param("(1::2) (3::4)", DelayType.AVG_FAST, 1.5, id="avg-fast"),
        pytest.param("(1::2) (3::4)", DelayType.AVG_SLOW, 3.5, id="avg-slow"),
        pytest.param("(1::2) (3::4)", DelayType.MAX_FAST, 2.0, id="max-fast"),
        pytest.param("(1::2) (3::4)", DelayType.MAX_SLOW, 4.0, id="max-slow"),
        pytest.param("(1::2) (3::4)", DelayType.MIN_FAST, 1.0, id="min-fast"),
        pytest.param("(1::2) (3::4)", DelayType.MIN_SLOW, 3.0, id="min-slow"),
        pytest.param(
            "(100::200) (2::8) (300::400)",
            DelayType.MIN_ALL,
            8.0,
            id="nominal-overrides-min",
        ),
        pytest.param(
            "(100::200) (2::8) (300::400)",
            DelayType.MAX_ALL,
            8.0,
            id="nominal-overrides-max",
        ),
        pytest.param("(::1.5) (2.5::)", DelayType.MIN_ALL, 0.0, id="missing-min"),
        pytest.param("(::1.5) (2.5::)", DelayType.MAX_ALL, 2.5, id="missing-max"),
        pytest.param("(::1.5) (2.5::)", DelayType.AVG_ALL, 1.0, id="missing-avg"),
    ],
)
def test_edge_weight_reduces_delays_by_delay_type(
    tmp_path: Path, delays: str, kind: DelayType, expected: float
) -> None:
    cell = (
        '(CELL (CELLTYPE "BUF") (INSTANCE U1) '
        f"(DELAY (ABSOLUTE (IOPATH A Y {delays}))))"
    )

    graph = graph_of(tmp_path, cell, delay_type=kind)

    assert graph.graph["U1/A"]["U1/Y"]["weight"] == pytest.approx(expected)


def test_unknown_delay_type_raises(tmp_path: Path) -> None:
    cell = top_cell("(INTERCONNECT A Y (1::2) (3::4))")
    with pytest.raises(ValueError, match="Unknown delay type"):
        graph_of(tmp_path, cell, delay_type="not-a-delay-type")  # ty: ignore[invalid-argument-type]


def test_graph_holds_cell_and_interconnect_components(tmp_path: Path) -> None:
    graph = graph_of(
        tmp_path,
        top_cell("(INTERCONNECT IN U1/A (0.1::0.2))")
        + '(CELL (CELLTYPE "BUF_X1") (INSTANCE U1) (DELAY (ABSOLUTE '
        "(IOPATH A Y (1::2) (3::4)))))"
        '(CELL (CELLTYPE "DFF_X1") (INSTANCE U2) (DELAY (INCREMENT '
        "(INTERCONNECT U1/Y U2/A (0.1::0.2) (0.3::0.4))"
        "(COND EN == 1'b1 (INTERCONNECT U2/Q OUT (:0.6:) (0.7::)))"
        "(IOPATH D Q (5::7.5)))))",
    )

    assert set(graph.graph.edges) == {
        ("U1/A", "U1/Y"),
        ("U2/D", "U2/Q"),
        ("IN", "U1/A"),
        ("U1/Y", "U2/A"),
        ("U2/Q", "OUT"),
    }
    iopath = graph.graph["U1/A"]["U1/Y"]
    assert iopath["weight"] == 4.0
    assert iopath["component"].c_type == SDFCellType.IOPATH
    assert iopath["component"].cell_name == "BUF_X1"
    assert iopath["component"].is_one_cell_instance is True
    assert iopath["component"].is_absolute is True
    interconnect = graph.graph["U1/Y"]["U2/A"]["component"]
    assert interconnect.c_type == SDFCellType.INTERCONNECT
    assert (interconnect.from_cell_instance, interconnect.from_cell_pin) == ("U1", "Y")
    assert (interconnect.to_cell_instance, interconnect.to_cell_pin) == ("U2", "A")
    assert interconnect.is_one_cell_instance is False
    assert interconnect.is_incremental is True
    assert graph.graph["U1/Y"]["U2/A"]["weight"] == 0.4
    output = graph.graph["U2/Q"]["OUT"]["component"]
    assert (output.to_cell_instance, output.to_cell_pin) == ("", "OUT")
    assert output.is_cond is True
    assert output.cond_equation == "EN == 1'b1"
    assert graph.graph["U2/Q"]["OUT"]["weight"] == 0.7
    assert [c.c_type for c in graph.instances["U2"]] == [SDFCellType.IOPATH]
    assert graph.instances["U2"][0].delay == 7.5
    assert graph.input_ports == ["IN"]
    assert graph.output_ports == ["OUT"]


@pytest.mark.parametrize(
    ("divider", "expected_separator", "edge"),
    [
        pytest.param("/", "/", ("U1/A", "U1/Y"), id="slash"),
        pytest.param(".", ".", ("U1.A", "U1.Y"), id="dot"),
        pytest.param(None, "/", ("U1/A", "U1/Y"), id="default"),
    ],
)
def test_node_names_use_the_sdf_divider(
    tmp_path: Path,
    divider: str | None,
    expected_separator: str,
    edge: tuple[str, str],
) -> None:
    cell = (
        '(CELL (CELLTYPE "BUF") (INSTANCE U1) (DELAY (ABSOLUTE (IOPATH A Y (1::2)))))'
    )

    graph = graph_of(tmp_path, cell, divider=divider)

    assert graph.hier_sep == expected_separator
    assert graph.graph.has_edge(*edge)


def test_escaped_instance_name_is_kept_in_node_names(tmp_path: Path) -> None:
    instance = r"registered_leaf/Q\$_DFF_P_"
    cell = (
        f'(CELL (CELLTYPE "DFF") (INSTANCE {instance}) '
        "(DELAY (ABSOLUTE (IOPATH CLK Q (1::2)))))"
    )

    graph = graph_of(tmp_path, cell)

    assert graph.graph.has_edge(f"{instance}/CLK", f"{instance}/Q")


def test_timing_checks_add_data_to_clock_edges(tmp_path: Path) -> None:
    graph = graph_of(tmp_path, dff_cell("U_FF"))

    edge = graph.graph["U_FF/D"]["U_FF/CLK"]
    assert edge["weight"] == 0.0
    assert edge["component"].is_timing_check is True
    assert edge["component"].delay_paths is None
    assert [c.c_type for c in graph.instances["U_FF"]] == [
        SDFCellType.IOPATH,
        SDFCellType.SETUP,
        SDFCellType.HOLD,
    ]


def test_ports_are_top_level_sources_and_sinks(shared_graph: SdfTimingGraph) -> None:
    assert sorted(shared_graph.input_ports) == ["A", "F"]
    assert sorted(shared_graph.output_ports) == ["E", "H"]


def test_hierarchical_pins_are_not_ports(tmp_path: Path) -> None:
    graph = graph_of(tmp_path, top_cell("(INTERCONNECT U1/Y U2/A (1::1))"))

    assert graph.input_ports == []
    assert graph.output_ports == []


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [("A", "E", True), ("F", "H", True), ("B", "C", False), ("A", "H", False)],
)
def test_has_path(
    shared_graph: SdfTimingGraph, source: str, target: str, expected: bool
) -> None:
    assert shared_graph.has_path(source, target) is expected


@pytest.mark.parametrize(
    ("target", "expected"), [("E", 7.0), ("D", 3.0)], ids=["to-sink", "fewer-edges"]
)
def test_single_delay_returns_the_lowest_total_delay(
    shared_graph: SdfTimingGraph,
    caplog: pytest.LogCaptureFixture,
    target: str,
    expected: float,
) -> None:
    assert shared_graph.single_delay("A", target) == expected
    assert "single_delay() is deprecated" in caplog.text


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(lambda graph: graph.single_delay("A", "H"), id="single-delay"),
        pytest.param(lambda graph: graph.query_timing_paths("A", "H"), id="paths"),
    ],
)
def test_queries_raise_when_no_path_exists(
    shared_graph: SdfTimingGraph, query: object
) -> None:
    with pytest.raises(nx.NetworkXNoPath):
        query(shared_graph)  # ty: ignore[call-non-callable]


@pytest.mark.parametrize(
    ("delays", "rise", "fall", "high_impedance"),
    [
        pytest.param(
            "(1:4:9)",
            SDFTimingTriplet(minimum=1.0, typical=4.0, maximum=9.0),
            SDFTimingTriplet(minimum=1.0, typical=4.0, maximum=9.0),
            SDFTimingTriplet(minimum=1.0, typical=4.0, maximum=9.0),
            id="single-transition-value",
        ),
        pytest.param(
            "(1:2:3) (4:5:6)",
            SDFTimingTriplet(minimum=1.0, typical=2.0, maximum=3.0),
            SDFTimingTriplet(minimum=4.0, typical=5.0, maximum=6.0),
            None,
            id="rise-and-fall",
        ),
        pytest.param(
            "(1:2:3) (4:5:6) (7:8:9)",
            SDFTimingTriplet(minimum=1.0, typical=2.0, maximum=3.0),
            SDFTimingTriplet(minimum=4.0, typical=5.0, maximum=6.0),
            SDFTimingTriplet(minimum=7.0, typical=8.0, maximum=9.0),
            id="rise-fall-and-high-impedance",
        ),
        pytest.param(
            "(:2:3) (4::6)",
            SDFTimingTriplet(minimum=None, typical=2.0, maximum=3.0),
            SDFTimingTriplet(minimum=4.0, typical=None, maximum=6.0),
            None,
            id="missing-triplet-values",
        ),
    ],
)
def test_query_timing_paths_reads_sdf_transition_lists(
    tmp_path: Path,
    delays: str,
    rise: SDFTimingTriplet,
    fall: SDFTimingTriplet,
    high_impedance: SDFTimingTriplet | None,
) -> None:
    graph = graph_of(tmp_path, top_cell(f"(INTERCONNECT A Z {delays})"))

    path_timing = graph.query_timing_paths("A", "Z")[0]

    assert path_timing.rise == rise
    assert path_timing.fall == fall
    assert path_timing.high_impedance == high_impedance
    assert path_timing.path_type == SDFPathType.COMBINATIONAL
    assert path_timing.nodes == ("A", "Z")
    assert len(path_timing.components) == 1


def test_query_timing_paths_orders_paths_by_edges_not_delay(tmp_path: Path) -> None:
    graph = graph_of(
        tmp_path,
        top_cell(
            "(INTERCONNECT A B (4:5:6)) (INTERCONNECT B Z (4:5:6)) "
            "(INTERCONNECT A C (0.1:0.2:0.3)) (INTERCONNECT C D (0.1:0.2:0.3)) "
            "(INTERCONNECT D Z (0.1:0.2:0.3))"
        ),
    )

    path_timings = graph.query_timing_paths("A", "Z", max_paths=2)

    assert [timing.nodes for timing in path_timings] == [
        ("A", "B", "Z"),
        ("A", "C", "D", "Z"),
    ]
    assert values(path_timings[0].rise) == pytest.approx((8.0, 10.0, 12.0))
    assert values(path_timings[1].rise) == pytest.approx((0.3, 0.6, 0.9))


def test_query_timing_paths_returns_sequential_checks_and_conditions(
    tmp_path: Path,
) -> None:
    graph = graph_of(
        tmp_path,
        dff_cell(
            "U_FF",
            checks="(SETUP D (COND ENABLE == 1'b1 (posedge CLK)) (0.1:0.2:0.3)) "
            "(HOLD D (posedge CLK) (0.01:0.02:0.03))",
        ),
    )

    path_timing = graph.query_timing_paths("U_FF/D", "U_FF/Q")[0]

    assert path_timing.path_type == SDFPathType.SEQUENTIAL
    assert path_timing.rise == SDFTimingTriplet(minimum=0.4, typical=0.5, maximum=0.6)
    assert path_timing.fall == SDFTimingTriplet(minimum=0.7, typical=0.8, maximum=0.9)
    assert path_timing.setup == (
        SDFTimingTriplet(minimum=0.1, typical=0.2, maximum=0.3),
    )
    assert path_timing.hold == (
        SDFTimingTriplet(minimum=0.01, typical=0.02, maximum=0.03),
    )
    assert [check.c_type for check in path_timing.timing_checks] == [
        SDFCellType.SETUP,
        SDFCellType.HOLD,
    ]
    assert path_timing.conditions == ("ENABLE == 1'b1",)
    assert path_timing.register_clock_pin == "U_FF/CLK"
    assert path_timing.effective_setup == ()
    assert path_timing.effective_hold == ()
    assert path_timing.clock_to_output_rise is None
    assert path_timing.clock_to_output_fall is None


def test_query_timing_paths_keeps_every_check_of_a_pin_pair(tmp_path: Path) -> None:
    graph = graph_of(
        tmp_path,
        dff_cell(
            "U_FF",
            checks="(HOLD (posedge D) (posedge CLK) (-0.028::-0.028)) "
            "(HOLD (negedge D) (posedge CLK) (-0.045::-0.045)) "
            "(SETUP (posedge D) (posedge CLK) (0.050::0.050)) "
            "(SETUP (negedge D) (posedge CLK) (0.101::0.101))",
        ),
    )

    path_timing = graph.query_timing_paths("U_FF/D", "U_FF/Q")[0]

    assert [setup.maximum for setup in path_timing.setup] == [0.050, 0.101]
    assert [hold.maximum for hold in path_timing.hold] == [-0.028, -0.045]


def test_query_timing_paths_calculates_effective_sequential_timing(
    tmp_path: Path,
) -> None:
    graph = graph_of(
        tmp_path,
        top_cell(
            "(INTERCONNECT DATA_IN U_FF/D (1.0:2.0:3.0) (1.5:2.5:4.0)) "
            "(INTERCONNECT CLK_IN U_FF/CLK (0.2:0.3:0.4) (0.25:0.35:0.5)) "
            "(INTERCONNECT U_FF/Q OUT (0.1:0.2:0.3))"
        )
        + dff_cell("U_FF"),
    )

    path_timing = graph.query_timing_paths("DATA_IN", "OUT", clock_pin="CLK_IN")[0]

    assert path_timing.register_clock_pin == "U_FF/CLK"
    assert [values(setup) for setup in path_timing.effective_setup] == [
        pytest.approx((0.6, 2.4, 4.1))
    ]
    assert [values(hold) for hold in path_timing.effective_hold] == [
        pytest.approx((-3.79, -1.63, -0.47))
    ]
    assert values(path_timing.clock_to_output_rise) == pytest.approx((0.7, 1.0, 1.3))
    assert values(path_timing.clock_to_output_fall) == pytest.approx((1.05, 1.35, 1.7))


def test_query_timing_paths_uses_each_sequential_paths_clock_to_output_suffix(
    tmp_path: Path,
) -> None:
    registers = (("U_FF_1", 0.1, 1.0), ("U_FF_2", 2.0, 4.0))
    graph = graph_of(
        tmp_path,
        top_cell(
            " ".join(
                f"(INTERCONNECT DATA {register}/D (0:0:0)) "
                f"(INTERCONNECT BEL_CLK {register}/CLK ({clock}:{clock}:{clock})) "
                f"(INTERCONNECT {register}/Q OUT (0.3:0.3:0.3))"
                for register, clock, _ in registers
            )
        )
        + " ".join(
            dff_cell(
                register,
                clock_to_q=f"({delay}:{delay}:{delay})",
                checks="(SETUP D (posedge CLK) (0.2:0.2:0.2))",
            )
            for register, _, delay in registers
        ),
    )
    expected_delays = {
        f"{register}/CLK": clock + delay + 0.3 for register, clock, delay in registers
    }

    path_timings = graph.query_timing_paths(
        "DATA", "OUT", max_paths=2, clock_pin="BEL_CLK"
    )

    assert len(path_timings) == 2
    for path_timing in path_timings:
        assert path_timing.register_clock_pin is not None
        expected = expected_delays[path_timing.register_clock_pin]
        assert values(path_timing.clock_to_output_rise) == pytest.approx(
            (expected, expected, expected)
        )
        assert path_timing.clock_to_output_fall == path_timing.clock_to_output_rise


def test_query_timing_paths_classifies_clock_to_output_as_sequential(
    tmp_path: Path,
) -> None:
    graph = graph_of(
        tmp_path,
        dff_cell(
            "U_FF",
            clock_to_q="(0.4:0.5:0.6)",
            checks="(SETUP D (posedge CLK) (0.1:0.2:0.3))",
        ),
    )

    path_timing = graph.query_timing_paths("U_FF/CLK", "U_FF/Q")[0]

    assert path_timing.path_type == SDFPathType.SEQUENTIAL
    assert path_timing.setup == ()
    assert path_timing.hold == ()
    assert path_timing.register_clock_pin == "U_FF/CLK"


def test_query_timing_paths_limits_default_to_ten(tmp_path: Path) -> None:
    graph = graph_of(
        tmp_path,
        top_cell(
            " ".join(
                f"(INTERCONNECT A P{index} (1:2:3)) (INTERCONNECT P{index} Z (1:2:3))"
                for index in range(11)
            )
        ),
    )

    assert len(graph.query_timing_paths("A", "Z")) == 10


def test_query_timing_paths_source_equals_target_has_zero_delay(
    shared_graph: SdfTimingGraph,
) -> None:
    path_timing = shared_graph.query_timing_paths("A", "A")[0]

    assert path_timing.nodes == ("A",)
    assert path_timing.components == ()
    assert path_timing.rise == SDFTimingTriplet(minimum=0, typical=0, maximum=0)
    assert path_timing.fall == path_timing.rise


def test_query_timing_paths_rejects_invalid_max_paths(
    shared_graph: SdfTimingGraph,
) -> None:
    with pytest.raises(ValueError, match="max_paths must be at least 1"):
        shared_graph.query_timing_paths("A", "E", max_paths=0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        pytest.param({"sources": ["A", "B"], "mode": "bad"}, "mode must be", id="mode"),
        pytest.param(
            {"sources": ["A", "NOPE"]}, r"Source node\(s\) not in graph", id="missing"
        ),
    ],
)
def test_earliest_common_nodes_rejects_invalid_input(
    shared_graph: SdfTimingGraph, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        shared_graph.earliest_common_nodes(**kwargs)  # ty: ignore[invalid-argument-type]


def test_earliest_common_nodes_empty_sources_returns_empty_result(
    shared_graph: SdfTimingGraph,
) -> None:
    assert shared_graph.earliest_common_nodes([]) == ([], None, {})


@pytest.mark.parametrize(
    ("sentinel", "follow_steps", "expected_node", "expected_cost"),
    [
        pytest.param(None, 0, "A", 0.0, id="no-sentinel"),
        pytest.param("E", 0, "A", 0, id="zero-steps"),
        pytest.param("E", 2, "D", 2, id="two-steps"),
        pytest.param("E", 99, "E", 3, id="clamped-to-path-end"),
        pytest.param("E", -5, "A", 0, id="negative-clamped-to-zero"),
        pytest.param("H", 2, "A", 0.0, id="sentinel-unreachable"),
        pytest.param("NOT_IN_GRAPH", 2, "A", 0.0, id="sentinel-not-in-graph"),
    ],
)
def test_earliest_common_nodes_single_source(
    shared_graph: SdfTimingGraph,
    sentinel: str | None,
    follow_steps: int,
    expected_node: str,
    expected_cost: float,
) -> None:
    best_nodes, best_cost, dists = shared_graph.earliest_common_nodes(
        ["A"],
        sentinel=sentinel,
        prefer_sentinel_for_single_source=sentinel is not None,
        follow_steps_to_sentinel=follow_steps,
    )

    assert best_nodes == [expected_node]
    assert best_cost == expected_cost
    assert dists["A"]["A"] == 0
    assert dists["A"]["E"] == 3


@pytest.mark.parametrize(
    ("mode", "expected_cost"), [("max", 1), ("sum", 2)], ids=["max", "sum"]
)
def test_earliest_common_nodes_multi_source(
    shared_graph: SdfTimingGraph, mode: str, expected_cost: int
) -> None:
    best_nodes, best_cost, dists = shared_graph.earliest_common_nodes(
        ["B", "C"], mode=mode
    )

    assert best_nodes == ["D"]
    assert best_cost == expected_cost
    assert dists["B"]["D"] == dists["C"]["D"] == 1
    assert dists["B"]["E"] == dists["C"]["E"] == 2


@pytest.mark.parametrize(
    ("sources", "stop"), [(["B", "C"], 0), (["A", "F"], None)], ids=["cutoff", "none"]
)
def test_earliest_common_nodes_without_common_node_returns_empty(
    shared_graph: SdfTimingGraph, sources: list[str], stop: int | None
) -> None:
    best_nodes, best_cost, dists = shared_graph.earliest_common_nodes(
        sources, mode="max", stop=stop
    )

    assert best_nodes == []
    assert best_cost is None
    assert list(dists) == sources


@pytest.mark.parametrize(
    ("edges", "expected_node", "expected_cost"),
    [
        pytest.param(
            (
                ("S1", "A", 1.0),
                ("S2", "B", 1.0),
                ("A", "X", 1.0),
                ("B", "X", 1.0),
                ("A", "Y", 1.0),
                ("B", "Y", 2.0),
            ),
            "X",
            2,
            id="by-cost",
        ),
        pytest.param(
            (
                ("S1", "A", 1.0),
                ("S2", "A", 1.0),
                ("S1", "B", 1.0),
                ("S2", "B", 1.0),
                ("A", "C", 1.0),
                ("C", "D", 1.0),
            ),
            "A",
            1,
            id="by-common-reach",
        ),
        pytest.param(
            (
                ("S1", "A", 1.0),
                ("S2", "A", 1.0),
                ("S1", "B", 1.0),
                ("S2", "B", 1.0),
            ),
            "A",
            1,
            id="by-node-name",
        ),
    ],
)
def test_earliest_common_nodes_tie_breaks(
    tmp_path: Path,
    edges: tuple[tuple[str, str, float], ...],
    expected_node: str,
    expected_cost: int,
) -> None:
    graph = graph_of(tmp_path, top_cell(interconnects(edges)))

    best_nodes, best_cost, _ = graph.earliest_common_nodes(["S1", "S2"], mode="max")

    assert best_nodes == [expected_node]
    assert best_cost == expected_cost


@pytest.mark.parametrize(
    ("pin", "hops", "expected"),
    [("A", 1, "B"), ("A", 3, "E"), ("E", 3, "E"), ("A", 0, "A")],
    ids=["one-hop", "three-hops", "no-successor", "zero-hops"],
)
def test_follow_first_fanout_from_pins(
    shared_graph: SdfTimingGraph, pin: str, hops: int, expected: str
) -> None:
    assert shared_graph.follow_first_fanout_from_pins(pin, num_follow=hops) == expected


@pytest.mark.parametrize(
    ("source", "targets", "weight", "reverse", "expected_path"),
    [
        pytest.param("A", ["D", "E"], None, False, ["A", "B", "D"], id="unweighted"),
        pytest.param("A", ["D", "E"], "weight", False, ["A", "C", "D"], id="weighted"),
        pytest.param("E", ["A", "B"], "weight", True, ["E", "D", "B"], id="reverse"),
        pytest.param(
            "A", ["DOES_NOT_EXIST", "D"], "weight", False, ["A", "C", "D"], id="missing"
        ),
    ],
)
def test_path_to_nearest_target_sentinel(
    shared_graph: SdfTimingGraph,
    source: str,
    targets: list[str],
    weight: str | None,
    reverse: bool,
    expected_path: list[str],
) -> None:
    path, closest = shared_graph.path_to_nearest_target_sentinel(
        source, targets, weight=weight, reverse=reverse
    )

    assert path == expected_path
    assert closest == expected_path[-1]
    for graph in (shared_graph.graph, shared_graph.reverse_graph):
        assert not any("_sentinel_" in node for node in graph.nodes)


def test_path_to_nearest_target_sentinel_no_reachable_target_returns_none(
    shared_graph: SdfTimingGraph,
) -> None:
    assert shared_graph.path_to_nearest_target_sentinel("A", ["H"]) == (None, None)
    assert not any("_sentinel_" in node for node in shared_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_custom_prefix_is_cleaned_up(
    shared_graph: SdfTimingGraph,
) -> None:
    path, closest = shared_graph.path_to_nearest_target_sentinel(
        "A", ["D"], sentinel_prefix="custom_prefix"
    )

    assert (path, closest) == (["A", "B", "D"], "D")
    assert not any("custom_prefix" in node for node in shared_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_empty_targets_raises(
    shared_graph: SdfTimingGraph,
) -> None:
    with pytest.raises(ValueError, match="targets must be a non-empty"):
        shared_graph.path_to_nearest_target_sentinel("A", [])
