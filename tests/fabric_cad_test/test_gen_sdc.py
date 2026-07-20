import shutil
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest
from pytest_mock import MockerFixture

from fabulous.custom_exception import InvalidState
from fabulous.fabric_cad.gen_sdc import (
    export_tile_sdc,
    render_sdc,
    select_break_nodes,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.yosys_obj import YosysJson


def test_select_break_nodes_empty_for_dag() -> None:
    g = nx.DiGraph([("a", "b"), ("b", "c")])
    assert select_break_nodes(g, set()) == []


def test_select_break_nodes_breaks_simple_cycle() -> None:
    g = nx.DiGraph([("a", "b"), ("b", "c"), ("c", "a")])
    chosen = select_break_nodes(g, set())
    assert len(chosen) == 1
    g.remove_nodes_from(chosen)
    assert nx.is_directed_acyclic_graph(g)


def test_select_break_nodes_handles_self_loop() -> None:
    g = nx.DiGraph([("a", "a"), ("a", "b")])
    chosen = select_break_nodes(g, set())
    assert chosen == ["a"]


def test_select_break_nodes_is_deterministic() -> None:
    edges = [("a", "b"), ("b", "a"), ("c", "d"), ("d", "c")]
    first = select_break_nodes(nx.DiGraph(edges), set())
    second = select_break_nodes(nx.DiGraph(edges), set())
    assert first == second
    g = nx.DiGraph(edges)
    g.remove_nodes_from(first)
    assert nx.is_directed_acyclic_graph(g)


def test_select_break_nodes_prefers_shared_hub_over_many_cuts() -> None:
    # A hub h sits on four 2-cycles h<->a..d. The minimum feedback-vertex set is
    # just {h}; cutting one vertex per back edge would disable four. The
    # degree-greedy removes the shared hub first, so a single constraint suffices.
    edges = []
    for spoke in ("a", "b", "c", "d"):
        edges += [("h", spoke), (spoke, "h")]
    g = nx.DiGraph(edges)
    chosen = select_break_nodes(g, set())
    assert chosen == ["h"]
    g.remove_nodes_from(chosen)
    assert nx.is_directed_acyclic_graph(g)


def test_select_break_nodes_breaks_independent_components() -> None:
    # Two disjoint cycles: each is its own SCC and needs exactly one cut.
    g = nx.DiGraph([("a", "b"), ("b", "a"), ("c", "d"), ("d", "c")])
    chosen = select_break_nodes(g, set())
    assert len(chosen) == 2
    g.remove_nodes_from(chosen)
    assert nx.is_directed_acyclic_graph(g)


def test_select_break_nodes_never_cuts_protected_hub() -> None:
    # h is the highest-degree vertex (the unconstrained greedy would pick it), but
    # it is protected, so the cut must fall on the spokes instead. Every spoke is
    # its own 2-cycle through h, so one cut per spoke is required.
    edges = []
    for spoke in ("a", "b", "c", "d"):
        edges += [("h", spoke), (spoke, "h")]
    g = nx.DiGraph(edges)
    chosen = select_break_nodes(g, {"h"})
    assert "h" not in chosen
    assert chosen == ["a", "b", "c", "d"]
    g.remove_nodes_from(chosen)
    assert nx.is_directed_acyclic_graph(g)


def test_select_break_nodes_raises_when_cycle_is_all_protected() -> None:
    # A 2-cycle whose only vertices are protected cannot be broken without
    # disabling a protected pin, so the infeasibility is surfaced.
    g = nx.DiGraph([("a", "b"), ("b", "a")])
    with pytest.raises(InvalidState, match="entirely protected"):
        select_break_nodes(g, {"a", "b"})


def test_select_break_nodes_raises_on_protected_self_loop() -> None:
    g = nx.DiGraph([("a", "a"), ("a", "b")])
    with pytest.raises(InvalidState, match="self-loop"):
        select_break_nodes(g, {"a"})


def test_render_sdc_emits_one_constraint_per_node_sorted() -> None:
    text = render_sdc(["N1BEG0", "E1BEG1"], scope="tile LUT4AB", resolved=False)
    lines = [ln for ln in text.splitlines() if ln.startswith("set_disable_timing")]
    assert lines == [
        "set_disable_timing [get_pins -of_objects [get_nets E1BEG1] "
        '-filter "direction==output"]',
        "set_disable_timing [get_pins -of_objects [get_nets N1BEG0] "
        '-filter "direction==output"]',
    ]


def test_render_sdc_warns_when_not_resolved() -> None:
    text = render_sdc(["N1BEG0"], scope="tile LUT4AB", resolved=False)
    assert "logical" in text.lower()
    assert "tile LUT4AB" in text


def test_render_sdc_no_warning_when_resolved() -> None:
    text = render_sdc(["N1BEG0"], scope="fabric eFPGA", resolved=True)
    assert "logical" not in text.lower()


def test_render_sdc_no_loops_comment_when_empty() -> None:
    text = render_sdc([], scope="tile LUT4AB", resolved=False)
    assert "no combinational loops found" in text
    assert "set_disable_timing" not in text


def _write_list(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "m_switch_matrix.list"
    p.write_text(body)
    return p


@dataclass
class _FakeWire:
    source: str
    destination: str
    xOffset: int
    yOffset: int


@dataclass
class _FakeBel:
    prefix: str
    inputs: list[str]
    outputs: list[str]
    comb_arcs: set[tuple[str, str]] = field(default_factory=set)
    module_name: str = "FAKE"
    name: str = "fake"
    src: Path = Path("fake.v")
    yosys_json: object = None

    def get_comb_arcs(self) -> set[tuple[str, str]]:
        return self.comb_arcs


class _FakeTile(Tile):
    """A Tile that skips the heavy real `__init__` but keeps the real `as_graph`.

    Only the attributes `as_graph`/`export_tile_sdc` read are populated.
    """

    def __init__(
        self,
        matrix_path: Path,
        wires: list[_FakeWire],
        bels: list[_FakeBel] | None = None,
        name: str = "TILE",
    ) -> None:
        self.name = name
        self.switch_matrix = SwitchMatrix.from_file(matrix_path, name)
        self.wireList = wires
        self.bels = bels or []


def test_as_graph_edge_direction_is_driver_to_sink(tmp_path: Path) -> None:
    # A `.list` line is `sink,source`; the connectivity edge must run source->sink.
    tile = _FakeTile(_write_list(tmp_path, "SINK0,SRC0\n"), [])
    g = tile.as_graph()
    assert g.has_edge("SRC0", "SINK0")
    assert not g.has_edge("SINK0", "SRC0")


def test_as_graph_detects_loop(tmp_path: Path) -> None:
    # SRC drives SINK, SINK drives back to SRC -> a 2-cycle.
    tile = _FakeTile(_write_list(tmp_path, "SINK0,SRC0\nSRC0,SINK0\n"), [])
    assert not nx.is_directed_acyclic_graph(tile.as_graph())


def test_export_tile_sdc_writes_file_with_constraints(tmp_path: Path) -> None:
    m = tmp_path / "t.list"
    m.write_text("SINK0,SRC0\nSRC0,SINK0\n")  # 2-cycle
    tile = _FakeTile(m, [])
    tile.name = "LUT4AB"
    out = tmp_path / "out" / "LUT4AB_loop_break.sdc"

    returned = export_tile_sdc(tile, out)

    assert returned == out
    assert out.exists()
    text = out.read_text()
    assert "set_disable_timing" in text
    assert "logical" in text.lower()  # .list source -> unresolved


def test_export_tile_sdc_writes_no_loops_file_for_dag(tmp_path: Path) -> None:
    m = tmp_path / "t.list"
    m.write_text("SINK0,SRC0\n")  # no cycle
    tile = _FakeTile(m, [])
    tile.name = "LUT4AB"
    out = tmp_path / "LUT4AB_loop_break.sdc"

    export_tile_sdc(tile, out)

    assert "no combinational loops found" in out.read_text()


def test_as_graph_maps_bel_pins_and_filters_non_data_ports(tmp_path: Path) -> None:
    # netlist arcs include a config pin (ConfigBits0) that is not a data port.
    bel = _FakeBel(
        prefix="LA_",
        inputs=["LA_I0", "LA_Ci"],
        outputs=["LA_O", "LA_Co"],
        comb_arcs={("I0", "O"), ("Ci", "Co"), ("ConfigBits0", "O")},
    )
    tile = _FakeTile(_write_list(tmp_path, ""), [], bels=[bel])
    g = tile.as_graph()

    assert g.has_edge("LA_I0", "LA_O")
    assert g.has_edge("LA_Ci", "LA_Co")
    # ConfigBits0 -> LA_ConfigBits0 is not a declared data input -> dropped.
    assert "LA_ConfigBits0" not in g


def test_export_tile_sdc_finds_bel_feedback_loop(tmp_path: Path) -> None:
    # Routing: END0 -> LA_I0 (mux input) and LA_O -> BEG0 (mux output).
    # BEL arc LA_I0 -> LA_O plus an intra-tile jump wire BEG0 -> END0 close the
    # loop LA_I0 -> LA_O -> BEG0 -> END0 -> LA_I0.
    m = tmp_path / "t.list"
    m.write_text("LA_I0,END0\nBEG0,LA_O\n")
    bel = _FakeBel(
        prefix="LA_", inputs=["LA_I0"], outputs=["LA_O"], comb_arcs={("I0", "O")}
    )
    wire = _FakeWire(source="BEG0", destination="END0", xOffset=0, yOffset=0)
    tile = _FakeTile(m, [wire], bels=[bel], name="LUT4AB")
    out = tmp_path / "LUT4AB_loop_break.sdc"

    export_tile_sdc(tile, out)

    text = out.read_text()
    assert "set_disable_timing" in text
    # The loop is broken on the routing feedback (BEG0/END0), never on the BEL
    # pins LA_I0/LA_O, so the LUT's combinational arc stays analyzable.
    assert "get_nets BEG0" in text or "get_nets END0" in text
    assert "get_nets LA_O" not in text
    assert "get_nets LA_I0" not in text


def test_export_tile_sdc_no_loop_without_bel_arc(tmp_path: Path) -> None:
    # Same routing and jump wire, but no BEL arc: the LUT input never reaches its
    # output, so no combinational loop exists and no constraint is emitted.
    m = tmp_path / "t.list"
    m.write_text("LA_I0,END0\nBEG0,LA_O\n")
    bel = _FakeBel(prefix="LA_", inputs=["LA_I0"], outputs=["LA_O"], comb_arcs=set())
    wire = _FakeWire(source="BEG0", destination="END0", xOffset=0, yOffset=0)
    tile = _FakeTile(m, [wire], bels=[bel], name="LUT4AB")
    out = tmp_path / "LUT4AB_loop_break.sdc"

    export_tile_sdc(tile, out)

    assert "no combinational loops found" in out.read_text()


@pytest.mark.slow
def test_get_comb_arcs_extracts_lut_arcs_from_demo_netlist(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    # Real extraction from the demo LUT4c BEL netlist: the LUT inputs and carry
    # must reach the outputs combinationally, while the control pins (SR/EN) and
    # the clock must not (they only reach the registered path). Sources are
    # copied to a temp dir so the generated .json files stay out of the repo.
    demo = Path(__file__).parents[2] / "demo"
    src_models_pack = demo / "Fabric" / "models_pack.v"
    src_bel = demo / "Tile" / "LUT4AB" / "LUT4c_frame_config_dffesr.v"
    if not src_models_pack.exists() or not src_bel.exists():
        pytest.skip("demo project Verilog not available")
    models_pack = shutil.copy(src_models_pack, tmp_path / src_models_pack.name)
    bel_src = shutil.copy(src_bel, tmp_path / src_bel.name)

    context = SimpleNamespace(
        models_pack=Path(models_pack), yosys_path="yosys", ghdl_path="ghdl"
    )
    # The BEL netlist now resolves its primitives against models_pack at read
    # time (see YosysJson), so only yosys_obj needs the patched context.
    mocker.patch(
        "fabulous.fabric_definition.yosys_obj.get_context", return_value=context
    )

    bel = Bel(
        src=Path(bel_src),
        prefix="LA_",
        module_name="LUT4c_frame_config_dffesr",
        internal=[],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
        yosys_json=YosysJson(Path(bel_src)),
    )
    arcs = bel.get_comb_arcs()

    assert ("I0", "O") in arcs
    assert ("Ci", "Co") in arcs
    assert not any(src in {"SR", "EN", "UserCLK"} for src, _ in arcs)
