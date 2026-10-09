from pathlib import Path

import networkx as nx
import pytest
from pytest_mock import MockerFixture

import fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base as base_mod
from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph import SDFTimingGraph
from fabulous.fabric_cad.timing_model.models import (
    Component,
    DelayType,
    SDFCellType,
    SDFGobject,
    SDFPathType,
    SDFTimingTriplet,
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


def make_path_component(
    *,
    connection_string: str,
    from_cell_instance: str,
    to_cell_instance: str,
    from_cell_pin: str,
    to_cell_pin: str,
    delay_paths: dict[str, dict[str, float | None]] | None,
    c_type: SDFCellType = SDFCellType.IOPATH,
    is_timing_check: bool = False,
    is_cond: bool = False,
    cond_equation: str | None = None,
) -> Component:
    """Create a fully controlled component for timing-path query tests.

    Parameters
    ----------
    connection_string : str
        Human-readable component identifier.
    from_cell_instance : str
        Source instance name.
    to_cell_instance : str
        Destination instance name.
    from_cell_pin : str
        Source pin name.
    to_cell_pin : str
        Destination pin name.
    delay_paths : dict[str, dict[str, float | None]] | None
        Raw delay paths produced by the SDF parser.
    c_type : SDFCellType
        SDF component type.
    is_timing_check : bool
        Whether the component is a synthetic timing-check edge.
    is_cond : bool
        Whether the component is conditional.
    cond_equation : str | None
        Optional SDF condition.

    Returns
    -------
    Component
        Component suitable for insertion into a timing graph.
    """
    return Component(
        c_type=c_type,
        cell_name="TEST_CELL",
        connection_string=connection_string,
        from_cell_instance=from_cell_instance,
        to_cell_instance=to_cell_instance,
        from_cell_pin=from_cell_pin,
        to_cell_pin=to_cell_pin,
        delay=0.0,
        delay_paths=delay_paths,
        is_one_cell_instance=(from_cell_instance == to_cell_instance),
        is_timing_check=is_timing_check,
        is_timing_env=False,
        is_absolute=True,
        is_incremental=False,
        is_cond=is_cond,
        cond_equation=cond_equation,
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


def test_inherits_base_initialization(sdf_graph: SDFTimingGraph) -> None:
    assert sdf_graph.sdf_file.name == "dummy.sdf"
    assert sdf_graph.sdf_file_content == "dummy sdf content"
    assert sdf_graph.delay_type_str == DelayType.MAX_ALL
    assert isinstance(sdf_graph.graph, nx.DiGraph)
    assert isinstance(sdf_graph.reverse_graph, nx.DiGraph)
    assert sdf_graph.header_info == {"divider": "/"}
    assert sdf_graph.cells == ["BUF_X1", "BUF_X2"]


def test_has_path_true_and_false(sdf_graph: SDFTimingGraph) -> None:
    assert sdf_graph.has_path("A", "E") is True
    assert sdf_graph.has_path("F", "H") is True
    assert sdf_graph.has_path("B", "C") is False
    assert sdf_graph.has_path("A", "H") is False


def test_single_delay_returns_shortest_weighted_path_and_info(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.warns(DeprecationWarning, match="query_timing_paths"):
        length = sdf_graph.single_delay("A", "E")

    assert length == 7.0


def test_single_delay_prefers_lower_total_delay_not_fewer_edges(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.warns(DeprecationWarning, match="query_timing_paths"):
        length = sdf_graph.single_delay("A", "D")
    assert length == 3.0


def test_single_delay_raises_when_no_path_exists(
    sdf_graph: SDFTimingGraph,
) -> None:
    with (
        pytest.warns(DeprecationWarning, match="query_timing_paths"),
        pytest.raises(nx.NetworkXNoPath),
    ):
        sdf_graph.single_delay("A", "H")


@pytest.mark.parametrize(
    ("delay_paths", "expected_rise", "expected_fall", "expected_high_impedance"),
    [
        pytest.param(
            {"nominal": {"min": 1.0, "avg": 4.0, "max": 9.0}},
            SDFTimingTriplet(minimum=1.0, typical=4.0, maximum=9.0),
            SDFTimingTriplet(minimum=1.0, typical=4.0, maximum=9.0),
            SDFTimingTriplet(minimum=1.0, typical=4.0, maximum=9.0),
            id="single-transition-value",
        ),
        pytest.param(
            {
                "fast": {"min": 1.0, "avg": 2.0, "max": 3.0},
                "slow": {"min": 4.0, "avg": 5.0, "max": 6.0},
            },
            SDFTimingTriplet(minimum=1.0, typical=2.0, maximum=3.0),
            SDFTimingTriplet(minimum=4.0, typical=5.0, maximum=6.0),
            None,
            id="rise-and-fall",
        ),
        pytest.param(
            {
                "fast": {"min": 1.0, "avg": 2.0, "max": 3.0},
                "nominal": {"min": 4.0, "avg": 5.0, "max": 6.0},
                "slow": {"min": 7.0, "avg": 8.0, "max": 9.0},
            },
            SDFTimingTriplet(minimum=1.0, typical=2.0, maximum=3.0),
            SDFTimingTriplet(minimum=4.0, typical=5.0, maximum=6.0),
            SDFTimingTriplet(minimum=7.0, typical=8.0, maximum=9.0),
            id="rise-fall-and-high-impedance",
        ),
        pytest.param(
            {
                "fast": {"min": None, "avg": 2.0, "max": 3.0},
                "slow": {"min": 4.0, "avg": None, "max": 6.0},
            },
            SDFTimingTriplet(minimum=None, typical=2.0, maximum=3.0),
            SDFTimingTriplet(minimum=4.0, typical=None, maximum=6.0),
            None,
            id="missing-triplet-values",
        ),
    ],
)
def test_query_timing_paths_normalizes_parser_transition_shapes(
    sdf_graph: SDFTimingGraph,
    delay_paths: dict[str, dict[str, float | None]],
    expected_rise: SDFTimingTriplet,
    expected_fall: SDFTimingTriplet,
    expected_high_impedance: SDFTimingTriplet | None,
) -> None:
    sdf_graph.graph.clear()
    component = make_path_component(
        connection_string="A->Z",
        from_cell_instance="",
        to_cell_instance="",
        from_cell_pin="A",
        to_cell_pin="Z",
        delay_paths=delay_paths,
        c_type=SDFCellType.INTERCONNECT,
    )
    sdf_graph.graph.add_edge("A", "Z", weight=100.0, component=component)

    path_timing = sdf_graph.query_timing_paths("A", "Z")[0]

    assert path_timing.rise == expected_rise
    assert path_timing.fall == expected_fall
    assert path_timing.high_impedance == expected_high_impedance
    assert path_timing.path_type == SDFPathType.COMBINATIONAL
    assert path_timing.nodes == ("A", "Z")
    assert path_timing.components == (component,)


def test_query_timing_paths_orders_paths_by_edges_not_delay(
    sdf_graph: SDFTimingGraph,
) -> None:
    sdf_graph.graph.clear()
    long_delay_paths = {"nominal": {"min": 4.0, "avg": 5.0, "max": 6.0}}
    short_delay_paths = {"nominal": {"min": 0.1, "avg": 0.2, "max": 0.3}}

    for source, target in [("A", "B"), ("B", "Z")]:
        component = make_path_component(
            connection_string=f"{source}->{target}",
            from_cell_instance="",
            to_cell_instance="",
            from_cell_pin=source,
            to_cell_pin=target,
            delay_paths=long_delay_paths,
            c_type=SDFCellType.INTERCONNECT,
        )
        sdf_graph.graph.add_edge(
            source,
            target,
            weight=100.0,
            component=component,
        )

    for source, target in [("A", "C"), ("C", "D"), ("D", "Z")]:
        component = make_path_component(
            connection_string=f"{source}->{target}",
            from_cell_instance="",
            to_cell_instance="",
            from_cell_pin=source,
            to_cell_pin=target,
            delay_paths=short_delay_paths,
            c_type=SDFCellType.INTERCONNECT,
        )
        sdf_graph.graph.add_edge(
            source,
            target,
            weight=0.01,
            component=component,
        )

    path_timings = sdf_graph.query_timing_paths("A", "Z", max_paths=2)

    assert [timing.nodes for timing in path_timings] == [
        ("A", "B", "Z"),
        ("A", "C", "D", "Z"),
    ]
    assert path_timings[0].rise == SDFTimingTriplet(
        minimum=8.0,
        typical=10.0,
        maximum=12.0,
    )
    assert path_timings[1].rise == SDFTimingTriplet(
        minimum=pytest.approx(0.3),
        typical=pytest.approx(0.6),
        maximum=pytest.approx(0.9),
    )


def test_query_timing_paths_returns_sequential_checks_and_conditions(
    sdf_graph: SDFTimingGraph,
) -> None:
    sdf_graph.graph.clear()
    setup = make_path_component(
        connection_string="SETUP D CLK",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="D",
        delay_paths={"nominal": {"min": 0.1, "avg": 0.2, "max": 0.3}},
        c_type=SDFCellType.SETUP,
        is_timing_check=True,
        is_cond=True,
        cond_equation="ENABLE == 1'b1",
    )
    hold = make_path_component(
        connection_string="HOLD D CLK",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="D",
        delay_paths={"nominal": {"min": 0.01, "avg": 0.02, "max": 0.03}},
        c_type=SDFCellType.HOLD,
        is_timing_check=True,
    )
    synthetic_data_to_clock = make_path_component(
        connection_string="D CLK",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="D",
        to_cell_pin="CLK",
        delay_paths=None,
        is_timing_check=True,
        is_cond=True,
        cond_equation="REGISTERED == 1'b1",
    )
    clock_to_q = make_path_component(
        connection_string="IOPATH CLK Q",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="Q",
        delay_paths={
            "fast": {"min": 0.4, "avg": 0.5, "max": 0.6},
            "slow": {"min": 0.7, "avg": 0.8, "max": 0.9},
        },
    )
    sdf_graph.instances = {"U_FF": [clock_to_q, setup, hold]}
    sdf_graph.graph.add_edge(
        "U_FF/D",
        "U_FF/CLK",
        weight=0.0,
        component=synthetic_data_to_clock,
    )
    sdf_graph.graph.add_edge(
        "U_FF/CLK",
        "U_FF/Q",
        weight=0.9,
        component=clock_to_q,
    )

    path_timing = sdf_graph.query_timing_paths("U_FF/D", "U_FF/Q")[0]

    assert path_timing.path_type == SDFPathType.SEQUENTIAL
    assert path_timing.rise == SDFTimingTriplet(
        minimum=0.4,
        typical=0.5,
        maximum=0.6,
    )
    assert path_timing.fall == SDFTimingTriplet(
        minimum=0.7,
        typical=0.8,
        maximum=0.9,
    )
    assert path_timing.setup == (
        SDFTimingTriplet(minimum=0.1, typical=0.2, maximum=0.3),
    )
    assert path_timing.hold == (
        SDFTimingTriplet(minimum=0.01, typical=0.02, maximum=0.03),
    )
    assert path_timing.timing_checks == (setup, hold)
    assert path_timing.conditions == (
        "REGISTERED == 1'b1",
        "ENABLE == 1'b1",
    )
    assert path_timing.register_clock_pin == "U_FF/CLK"
    assert path_timing.effective_setup == ()
    assert path_timing.effective_hold == ()
    assert path_timing.clock_to_output_rise is None
    assert path_timing.clock_to_output_fall is None


def test_query_timing_paths_calculates_effective_sequential_timing(
    sdf_graph: SDFTimingGraph,
) -> None:
    """Adjust cell checks for data/clock paths when a clock pin is supplied."""
    sdf_graph.graph.clear()
    setup = make_path_component(
        connection_string="SETUP D CLK",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="D",
        delay_paths={"nominal": {"min": 0.1, "avg": 0.2, "max": 0.3}},
        c_type=SDFCellType.SETUP,
        is_timing_check=True,
    )
    hold = make_path_component(
        connection_string="HOLD D CLK",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="D",
        delay_paths={"nominal": {"min": 0.01, "avg": 0.02, "max": 0.03}},
        c_type=SDFCellType.HOLD,
        is_timing_check=True,
    )
    data_path = make_path_component(
        connection_string="DATA_IN D",
        from_cell_instance="U_DATA",
        to_cell_instance="U_FF",
        from_cell_pin="Y",
        to_cell_pin="D",
        delay_paths={
            "fast": {"min": 1.0, "avg": 2.0, "max": 3.0},
            "slow": {"min": 1.5, "avg": 2.5, "max": 4.0},
        },
        c_type=SDFCellType.INTERCONNECT,
    )
    clock_path = make_path_component(
        connection_string="CLK_IN CLK",
        from_cell_instance="U_CLK",
        to_cell_instance="U_FF",
        from_cell_pin="Y",
        to_cell_pin="CLK",
        delay_paths={
            "fast": {"min": 0.2, "avg": 0.3, "max": 0.4},
            "slow": {"min": 0.25, "avg": 0.35, "max": 0.5},
        },
        c_type=SDFCellType.INTERCONNECT,
    )
    synthetic_data_to_clock = make_path_component(
        connection_string="D CLK",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="D",
        to_cell_pin="CLK",
        delay_paths=None,
        is_timing_check=True,
    )
    clock_to_q = make_path_component(
        connection_string="IOPATH CLK Q",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="Q",
        delay_paths={
            "fast": {"min": 0.4, "avg": 0.5, "max": 0.6},
            "slow": {"min": 0.7, "avg": 0.8, "max": 0.9},
        },
    )
    output_path = make_path_component(
        connection_string="Q OUT",
        from_cell_instance="U_FF",
        to_cell_instance="U_OUT",
        from_cell_pin="Q",
        to_cell_pin="A",
        delay_paths={"nominal": {"min": 0.1, "avg": 0.2, "max": 0.3}},
        c_type=SDFCellType.INTERCONNECT,
    )
    sdf_graph.instances = {"U_FF": [clock_to_q, setup, hold]}
    for source, target, component in (
        ("DATA_IN", "U_FF/D", data_path),
        ("CLK_IN", "U_FF/CLK", clock_path),
        ("U_FF/D", "U_FF/CLK", synthetic_data_to_clock),
        ("U_FF/CLK", "U_FF/Q", clock_to_q),
        ("U_FF/Q", "OUT", output_path),
    ):
        sdf_graph.graph.add_edge(source, target, weight=0.0, component=component)

    path_timing = sdf_graph.query_timing_paths(
        "DATA_IN",
        "OUT",
        clock_pin="CLK_IN",
    )[0]

    assert path_timing.register_clock_pin == "U_FF/CLK"
    assert path_timing.effective_setup == (
        SDFTimingTriplet(
            minimum=pytest.approx(0.6),
            typical=pytest.approx(2.4),
            maximum=pytest.approx(4.1),
        ),
    )
    assert path_timing.effective_hold == (
        SDFTimingTriplet(
            minimum=pytest.approx(-3.79),
            typical=pytest.approx(-1.63),
            maximum=pytest.approx(-0.47),
        ),
    )
    assert path_timing.clock_to_output_rise == SDFTimingTriplet(
        minimum=pytest.approx(0.7),
        typical=pytest.approx(1.0),
        maximum=pytest.approx(1.3),
    )
    assert path_timing.clock_to_output_fall == SDFTimingTriplet(
        minimum=pytest.approx(1.05),
        typical=pytest.approx(1.35),
        maximum=pytest.approx(1.7),
    )


def test_query_timing_paths_uses_each_sequential_paths_clock_to_output_suffix(
    sdf_graph: SDFTimingGraph,
) -> None:
    """Keep clock-to-output timing associated with its sequential path.

    Parameters
    ----------
    sdf_graph : SDFTimingGraph
        Timing graph fixture populated with two distinct register paths.
    """
    sdf_graph.graph.clear()
    sdf_graph.instances = {}
    expected_delays: dict[str, float] = {}
    for register, clock_delay, clock_to_q_delay in (
        ("U_FF_1", 0.1, 1.0),
        ("U_FF_2", 2.0, 4.0),
    ):
        setup = make_path_component(
            connection_string=f"SETUP {register}/D {register}/CLK",
            from_cell_instance=register,
            to_cell_instance=register,
            from_cell_pin="CLK",
            to_cell_pin="D",
            delay_paths={"nominal": {"min": 0.2, "avg": 0.2, "max": 0.2}},
            c_type=SDFCellType.SETUP,
            is_timing_check=True,
        )
        data_path = make_path_component(
            connection_string=f"DATA {register}/D",
            from_cell_instance="",
            to_cell_instance=register,
            from_cell_pin="DATA",
            to_cell_pin="D",
            delay_paths={"nominal": {"min": 0.0, "avg": 0.0, "max": 0.0}},
            c_type=SDFCellType.INTERCONNECT,
        )
        clock_path = make_path_component(
            connection_string=f"BEL_CLK {register}/CLK",
            from_cell_instance="",
            to_cell_instance=register,
            from_cell_pin="BEL_CLK",
            to_cell_pin="CLK",
            delay_paths={
                "nominal": {
                    "min": clock_delay,
                    "avg": clock_delay,
                    "max": clock_delay,
                }
            },
            c_type=SDFCellType.INTERCONNECT,
        )
        synthetic_data_to_clock = make_path_component(
            connection_string=f"{register}/D {register}/CLK",
            from_cell_instance=register,
            to_cell_instance=register,
            from_cell_pin="D",
            to_cell_pin="CLK",
            delay_paths=None,
            is_timing_check=True,
        )
        clock_to_q = make_path_component(
            connection_string=f"IOPATH {register}/CLK {register}/Q",
            from_cell_instance=register,
            to_cell_instance=register,
            from_cell_pin="CLK",
            to_cell_pin="Q",
            delay_paths={
                "nominal": {
                    "min": clock_to_q_delay,
                    "avg": clock_to_q_delay,
                    "max": clock_to_q_delay,
                }
            },
        )
        output_path = make_path_component(
            connection_string=f"{register}/Q OUT",
            from_cell_instance=register,
            to_cell_instance="",
            from_cell_pin="Q",
            to_cell_pin="OUT",
            delay_paths={"nominal": {"min": 0.3, "avg": 0.3, "max": 0.3}},
            c_type=SDFCellType.INTERCONNECT,
        )
        sdf_graph.instances[register] = [clock_to_q, setup]
        for source, target, component in (
            ("DATA", f"{register}/D", data_path),
            ("BEL_CLK", f"{register}/CLK", clock_path),
            (f"{register}/D", f"{register}/CLK", synthetic_data_to_clock),
            (f"{register}/CLK", f"{register}/Q", clock_to_q),
            (f"{register}/Q", "OUT", output_path),
        ):
            sdf_graph.graph.add_edge(source, target, weight=0.0, component=component)
        expected_delays[f"{register}/CLK"] = clock_delay + clock_to_q_delay + 0.3

    path_timings = sdf_graph.query_timing_paths(
        "DATA",
        "OUT",
        max_paths=2,
        clock_pin="BEL_CLK",
    )

    assert len(path_timings) == 2
    for path_timing in path_timings:
        assert path_timing.register_clock_pin is not None
        expected_delay = expected_delays[path_timing.register_clock_pin]
        assert path_timing.clock_to_output_rise == SDFTimingTriplet(
            minimum=pytest.approx(expected_delay),
            typical=pytest.approx(expected_delay),
            maximum=pytest.approx(expected_delay),
        )
        assert path_timing.clock_to_output_fall == path_timing.clock_to_output_rise


def test_query_timing_paths_with_real_sdf_parser(tmp_path: Path) -> None:
    sdf_file = tmp_path / "path_query.sdf"
    sdf_file.write_text(
        """(DELAYFILE
            (SDFVERSION "3.0")
            (DESIGN "path_query")
            (DIVIDER /)
            (VOLTAGE (1:1:1))
            (PROCESS "typical")
            (TEMPERATURE (25:25:25))
            (TIMESCALE 1 ns)
            (CELL
                (CELLTYPE "TRANSITIONS")
                (INSTANCE U_COMB)
                (DELAY (ABSOLUTE
                    (IOPATH A Y (1:4:9))
                    (IOPATH B Z (1:2:3) (4:5:6))
                    (IOPATH C Q (1:2:3) (4:5:6) (7:8:9))
                ))
            )
            (CELL
                (CELLTYPE "DFF")
                (INSTANCE U_FF)
                (DELAY (ABSOLUTE
                    (IOPATH (posedge CLK) Q
                        (0.4:0.5:0.6) (0.7:0.8:0.9))
                ))
                (TIMINGCHECK
                    (SETUP D (posedge CLK) (0.1:0.2:0.3))
                    (HOLD D (posedge CLK) (0.01:0.02:0.03))
                )
            )
        )"""
    )
    graph = SDFTimingGraph(sdf_file)

    single_transition = graph.query_timing_paths("U_COMB/A", "U_COMB/Y")[0]
    rise_and_fall = graph.query_timing_paths("U_COMB/B", "U_COMB/Z")[0]
    three_transitions = graph.query_timing_paths("U_COMB/C", "U_COMB/Q")[0]
    registered = graph.query_timing_paths("U_FF/D", "U_FF/Q")[0]

    assert single_transition.rise == SDFTimingTriplet(
        minimum=1.0,
        typical=4.0,
        maximum=9.0,
    )
    assert single_transition.fall == single_transition.rise
    assert single_transition.high_impedance == single_transition.rise
    assert rise_and_fall.rise == SDFTimingTriplet(
        minimum=1.0,
        typical=2.0,
        maximum=3.0,
    )
    assert rise_and_fall.fall == SDFTimingTriplet(
        minimum=4.0,
        typical=5.0,
        maximum=6.0,
    )
    assert rise_and_fall.high_impedance is None
    assert three_transitions.high_impedance == SDFTimingTriplet(
        minimum=7.0,
        typical=8.0,
        maximum=9.0,
    )
    assert registered.path_type == SDFPathType.SEQUENTIAL
    assert registered.rise == SDFTimingTriplet(
        minimum=0.4,
        typical=0.5,
        maximum=0.6,
    )
    assert registered.fall == SDFTimingTriplet(
        minimum=0.7,
        typical=0.8,
        maximum=0.9,
    )
    assert registered.setup == (
        SDFTimingTriplet(minimum=0.1, typical=0.2, maximum=0.3),
    )
    assert registered.hold == (
        SDFTimingTriplet(minimum=0.01, typical=0.02, maximum=0.03),
    )


def test_query_timing_paths_classifies_clock_to_output_as_sequential(
    sdf_graph: SDFTimingGraph,
) -> None:
    sdf_graph.graph.clear()
    clock_to_q = make_path_component(
        connection_string="IOPATH CLK Q",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="Q",
        delay_paths={"nominal": {"min": 0.4, "avg": 0.5, "max": 0.6}},
    )
    setup = make_path_component(
        connection_string="SETUP D CLK",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="D",
        delay_paths={"nominal": {"min": 0.1, "avg": 0.2, "max": 0.3}},
        c_type=SDFCellType.SETUP,
        is_timing_check=True,
    )
    sdf_graph.instances = {"U_FF": [clock_to_q, setup]}
    sdf_graph.graph.add_edge(
        "U_FF/CLK",
        "U_FF/Q",
        weight=0.6,
        component=clock_to_q,
    )

    path_timing = sdf_graph.query_timing_paths("U_FF/CLK", "U_FF/Q")[0]

    assert path_timing.path_type == SDFPathType.SEQUENTIAL
    assert path_timing.setup == ()
    assert path_timing.hold == ()


def test_sequential_instances_are_cached(
    sdf_graph: SDFTimingGraph,
    mocker: MockerFixture,
) -> None:
    """Reuse sequential-instance discovery across timing-path queries.

    Parameters
    ----------
    sdf_graph : SDFTimingGraph
        Timing graph fixture whose instance components are controlled by the test.
    mocker : MockerFixture
        Pytest fixture used to observe instance-map scans.
    """
    setup = make_path_component(
        connection_string="SETUP D CLK",
        from_cell_instance="U_FF",
        to_cell_instance="U_FF",
        from_cell_pin="CLK",
        to_cell_pin="D",
        delay_paths={"nominal": {"min": 0.1, "avg": 0.2, "max": 0.3}},
        c_type=SDFCellType.SETUP,
        is_timing_check=True,
    )
    sdf_graph.instances = mocker.Mock()
    sdf_graph.instances.items.return_value = [("U_FF", [setup])]
    sdf_graph.graph.clear()
    path_component = make_path_component(
        connection_string="A Z",
        from_cell_instance="",
        to_cell_instance="",
        from_cell_pin="A",
        to_cell_pin="Z",
        delay_paths={"nominal": {"min": 0.1, "avg": 0.2, "max": 0.3}},
        c_type=SDFCellType.INTERCONNECT,
    )
    sdf_graph.graph.add_edge("A", "Z", weight=0.3, component=path_component)

    sdf_graph.query_timing_paths("A", "Z")
    sdf_graph.query_timing_paths("A", "Z")

    sdf_graph.instances.items.assert_called_once_with()


def test_query_timing_paths_limits_default_to_ten(
    sdf_graph: SDFTimingGraph,
) -> None:
    sdf_graph.graph.clear()
    delay_paths = {"nominal": {"min": 1.0, "avg": 2.0, "max": 3.0}}
    for index in range(11):
        middle = f"P{index}"
        for source, target in [("A", middle), (middle, "Z")]:
            component = make_path_component(
                connection_string=f"{source}->{target}",
                from_cell_instance="",
                to_cell_instance="",
                from_cell_pin=source,
                to_cell_pin=target,
                delay_paths=delay_paths,
                c_type=SDFCellType.INTERCONNECT,
            )
            sdf_graph.graph.add_edge(
                source,
                target,
                weight=1.0,
                component=component,
            )

    path_timings = sdf_graph.query_timing_paths("A", "Z")

    assert len(path_timings) == 10


def test_query_timing_paths_source_equals_target_has_zero_delay(
    sdf_graph: SDFTimingGraph,
) -> None:
    path_timing = sdf_graph.query_timing_paths("A", "A")[0]

    assert path_timing.nodes == ("A",)
    assert path_timing.components == ()
    assert path_timing.rise == SDFTimingTriplet(
        minimum=0,
        typical=0,
        maximum=0,
    )
    assert path_timing.fall == path_timing.rise


def test_query_timing_paths_rejects_invalid_max_paths(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.raises(ValueError, match="max_paths must be at least 1"):
        sdf_graph.query_timing_paths("A", "E", max_paths=0)


def test_query_timing_paths_raises_when_no_path_exists(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.raises(nx.NetworkXNoPath):
        sdf_graph.query_timing_paths("A", "H")


def test_query_timing_paths_rejects_unsupported_parser_shape(
    sdf_graph: SDFTimingGraph,
) -> None:
    sdf_graph.graph.clear()
    component = make_path_component(
        connection_string="A->Z",
        from_cell_instance="",
        to_cell_instance="",
        from_cell_pin="A",
        to_cell_pin="Z",
        delay_paths={"unexpected": {"min": 1.0, "avg": 2.0, "max": 3.0}},
        c_type=SDFCellType.INTERCONNECT,
    )
    sdf_graph.graph.add_edge("A", "Z", weight=1.0, component=component)

    with pytest.raises(ValueError, match="Unsupported SDF delay-path shape"):
        sdf_graph.query_timing_paths("A", "Z")


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


def test_earliest_common_nodes_single_source_returns_source(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(["A"])

    assert best_nodes == ["A"]
    assert best_cost == 0.0
    assert dists["A"]["A"] == 0


def test_earliest_common_nodes_single_source_prefers_sentinel_and_follows_zero_steps(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=0,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0
    assert dists["A"]["E"] == 3


def test_earliest_common_nodes_single_source_prefers_sentinel_and_follows_steps(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["D"]
    assert best_cost == 2
    assert dists["A"]["D"] == 2


def test_earliest_common_nodes_single_source_follow_steps_are_clamped_to_path_end(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=99,
    )

    assert best_nodes == ["E"]
    assert best_cost == 3
    assert dists["A"]["E"] == 3


def test_earliest_common_nodes_single_source_negative_follow_steps_clamp_to_zero(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, _ = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="E",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=-5,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0


def test_earliest_common_nodes_single_source_sentinel_not_reachable_returns_source(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, _ = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="H",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0.0


def test_earliest_common_nodes_single_source_sentinel_not_in_graph_returns_source(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, _ = sdf_graph.earliest_common_nodes(
        ["A"],
        sentinel="NOT_IN_GRAPH",
        prefer_sentinel_for_single_source=True,
        follow_steps_to_sentinel=2,
    )

    assert best_nodes == ["A"]
    assert best_cost == 0.0


def test_earliest_common_nodes_max_multi_source(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["B", "C"], mode="max"
    )

    assert best_nodes == ["D"]
    assert best_cost == 1
    assert dists["B"]["D"] == 1
    assert dists["C"]["D"] == 1
    assert dists["B"]["E"] == 2
    assert dists["C"]["E"] == 2


def test_earliest_common_nodes_sum_multi_source(
    sdf_graph: SDFTimingGraph,
) -> None:
    best_nodes, best_cost, dists = sdf_graph.earliest_common_nodes(
        ["B", "C"], mode="sum"
    )

    assert best_nodes == ["D"]
    assert best_cost == 2
    assert dists["B"]["D"] + dists["C"]["D"] == 2


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
    assert "A" in dists
    assert "F" in dists


def test_earliest_common_nodes_choose_one_by_cost() -> None:
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


def test_earliest_common_nodes_tie_break_by_common_reach_score() -> None:
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


def test_earliest_common_nodes_total_reach_score_tie_break() -> None:
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


def test_follow_first_fanout_from_pins_one_hop(
    sdf_graph: SDFTimingGraph,
) -> None:
    assert sdf_graph.follow_first_fanout_from_pins("A", num_follow=1) == "B"


def test_follow_first_fanout_from_pins_multiple_hops(
    sdf_graph: SDFTimingGraph,
) -> None:
    assert sdf_graph.follow_first_fanout_from_pins("A", num_follow=3) == "E"


def test_follow_first_fanout_from_pins_stops_when_no_successor(
    sdf_graph: SDFTimingGraph,
) -> None:
    assert sdf_graph.follow_first_fanout_from_pins("E", num_follow=3) == "E"


def test_follow_first_fanout_from_pins_zero_hops_returns_same_pin(
    sdf_graph: SDFTimingGraph,
) -> None:
    assert sdf_graph.follow_first_fanout_from_pins("A", num_follow=0) == "A"


def test_path_to_nearest_target_sentinel_unweighted_forward(
    sdf_graph: SDFTimingGraph,
) -> None:
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["D", "E"], weight=None
    )

    assert path == ["A", "B", "D"]
    assert closest == "D"
    assert all("_sentinel_" not in node for node in path)
    assert not any("_sentinel_" in str(node) for node in sdf_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_weighted_forward(
    sdf_graph: SDFTimingGraph,
) -> None:
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["D", "E"], weight="weight"
    )

    assert path == ["A", "C", "D"]
    assert closest == "D"
    assert not any("_sentinel_" in str(node) for node in sdf_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_reverse_uses_reverse_graph(
    sdf_graph: SDFTimingGraph,
) -> None:
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "E", ["A", "B"], weight="weight", reverse=True
    )

    assert path == ["E", "D", "B"]
    assert closest == "B"
    assert not any("_sentinel_" in str(node) for node in sdf_graph.reverse_graph.nodes)


def test_path_to_nearest_target_sentinel_no_reachable_target_returns_none(
    sdf_graph: SDFTimingGraph,
) -> None:
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["H"], weight="weight"
    )

    assert path is None
    assert closest is None
    assert not any("_sentinel_" in str(node) for node in sdf_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_empty_targets_raises_valueerror(
    sdf_graph: SDFTimingGraph,
) -> None:
    with pytest.raises(
        ValueError, match="targets must be a non-empty iterable of nodes"
    ):
        sdf_graph.path_to_nearest_target_sentinel("A", [], weight="weight")


def test_path_to_nearest_target_sentinel_custom_prefix_is_cleaned_up(
    sdf_graph: SDFTimingGraph,
) -> None:
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["D"], sentinel_prefix="custom_prefix", weight=None
    )

    assert path == ["A", "B", "D"]
    assert closest == "D"
    assert not any("custom_prefix" in str(node) for node in sdf_graph.graph.nodes)


def test_path_to_nearest_target_sentinel_ignores_missing_target_nodes(
    sdf_graph: SDFTimingGraph,
) -> None:
    path, closest = sdf_graph.path_to_nearest_target_sentinel(
        "A", ["DOES_NOT_EXIST", "D"], weight="weight"
    )

    assert path == ["A", "C", "D"]
    assert closest == "D"
