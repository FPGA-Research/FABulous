"""Tests for the gate-level loop-break SDC generator."""

from pathlib import Path

import networkx as nx
import pytest

from fabulous.custom_exception import InvalidState
from fabulous.fabric_cad.gen_sdc import (
    loop_break_nets,
    render_sdc,
    select_break_nodes,
)
from fabulous.fabric_definition.yosys_obj import YosysJson

_LIBERTY = """library(tiny) {
  cell(INV) {
    pin(A) { direction : input; }
    pin(Y) { direction : output; function : "!A"; }
  }
  cell(MUX2) {
    pin(A0) { direction : input; }
    pin(A1) { direction : input; }
    pin(S) { direction : input; }
    pin(X) { direction : output; function : "(A0&!S)|(A1&S)"; }
  }
}
"""

_BEL = (
    "module bel(input I0, input I1, input C, output O);\n"
    "  MUX2 u (.A0(I0), .A1(I1), .S(C), .X(O));\n"
    "endmodule\n"
)

# The BEL output routes back to its input through the routing net `j`.
_ROUTING_TILE = (
    "module tile(input E, input S0, input S1, output N);\n"
    "  wire bi, bo, j;\n"
    "  MUX2 m0 (.A0(E), .A1(j), .S(S0), .X(bi));\n"
    "  bel b (.I0(bi), .I1(E), .C(E), .O(bo));\n"
    "  MUX2 m1 (.A0(E), .A1(bo), .S(S1), .X(j));\n"
    "  INV n (.A(j), .Y(N));\n"
    "endmodule\n"
)


def _netlist_json(tmp_path: Path, netlist: str) -> YosysJson:
    liberty = tmp_path / "tiny.lib"
    liberty.write_text(_LIBERTY)
    netlist_path = tmp_path / "tile.nl.v"
    netlist_path.write_text(netlist)
    return YosysJson.from_netlist(
        netlist_path, liberty=[liberty], top="tile", json_output=tmp_path / "tile.json"
    )


def _hub(hub: int) -> list[tuple[int, int]]:
    """Four two-node loops 1..4 that all pass through `hub`."""
    return [edge for leaf in (1, 2, 3, 4) for edge in ((hub, leaf), (leaf, hub))]


@pytest.mark.parametrize(
    ("edges", "protected", "last_resort", "expected"),
    [
        pytest.param([(1, 2), (2, 3)], set(), set(), set(), id="dag"),
        pytest.param([(1, 1), (1, 2)], set(), set(), {1}, id="self-loop"),
        pytest.param(_hub(0), set(), set(), {0}, id="shared-hub"),
        pytest.param(_hub(0), {0}, set(), {1, 2, 3, 4}, id="protected-hub"),
        pytest.param(_hub(0), set(), {0}, {1, 2, 3, 4}, id="last-resort-hub"),
        pytest.param([(1, 2), (2, 1)], {2}, {1}, {1}, id="last-resort-only"),
    ],
)
def test_select_break_nodes(
    edges: list[tuple[int, int]],
    protected: set[int],
    last_resort: set[int],
    expected: set[int],
) -> None:
    """The cut set breaks every loop and avoids protected and last-resort nodes."""
    graph = nx.DiGraph(edges)

    chosen = select_break_nodes(graph, protected=protected, last_resort=last_resort)

    assert chosen == expected
    graph.remove_nodes_from(chosen)
    assert nx.is_directed_acyclic_graph(graph)


@pytest.mark.parametrize(
    ("edges", "protected", "error"),
    [
        pytest.param([(1, 2), (2, 1)], {1, 2}, "entirely protected", id="scc"),
        pytest.param([(1, 1), (1, 2)], {1}, "self-loop", id="self-loop"),
    ],
)
def test_select_break_nodes_raises_without_unprotected_cut(
    edges: list[tuple[int, int]], protected: set[int], error: str
) -> None:
    """A loop made only of protected nodes cannot be broken."""
    with pytest.raises(InvalidState, match=error):
        select_break_nodes(nx.DiGraph(edges), protected=protected, last_resort=set())


@pytest.mark.parametrize(
    ("tile", "expected"),
    [
        pytest.param(_ROUTING_TILE, ["j"], id="routing-net"),
        # The only routing net on the loop is the BEL input itself.
        pytest.param(
            "module tile(input E, input S0, output N);\n"
            "  wire bi, bo;\n"
            "  MUX2 m0 (.A0(E), .A1(bo), .S(S0), .X(bi));\n"
            "  bel b (.I0(bi), .I1(E), .C(E), .O(bo));\n"
            "  INV n (.A(bo), .Y(N));\n"
            "endmodule\n",
            ["bi"],
            id="bel-input",
        ),
        # The BEL output is the loop's busiest net, so only its protection keeps
        # the cuts on the two routing nets `j1` and `j2`.
        pytest.param(
            "module tile(input E, input S0, input S1, input S2, output N);\n"
            "  wire bi0, bi1, bo, j1, j2;\n"
            "  MUX2 m0 (.A0(j1), .A1(j2), .S(S0), .X(bi0));\n"
            "  MUX2 m1 (.A0(j1), .A1(j2), .S(S1), .X(bi1));\n"
            "  bel b (.I0(bi0), .I1(bi1), .C(S2), .O(bo));\n"
            "  MUX2 m2 (.A0(E), .A1(bo), .S(S0), .X(j1));\n"
            "  MUX2 m3 (.A0(E), .A1(bo), .S(S1), .X(j2));\n"
            "  INV n (.A(bo), .Y(N));\n"
            "endmodule\n",
            ["j1", "j2"],
            id="bel-output-hub",
        ),
        pytest.param(
            "module tile(input E, output N);\n"
            "  wire bo;\n"
            "  bel b (.I0(E), .I1(E), .C(E), .O(bo));\n"
            "  INV n (.A(bo), .Y(N));\n"
            "endmodule\n",
            [],
            id="no-loop",
        ),
    ],
)
def test_loop_break_nets(tmp_path: Path, tile: str, expected: list[str]) -> None:
    """Cuts land on routing nets of the gate-level netlist, never inside a BEL."""
    yosys_json = _netlist_json(tmp_path, _BEL + tile)

    assert loop_break_nets(yosys_json, top="tile", bel_modules={"bel"}) == expected


@pytest.mark.parametrize(
    ("module_name", "pattern"),
    [
        pytest.param("bel", "bel", id="exact"),
        pytest.param("bel_Barch_3", "bel_B*", id="ghdl-elaborated"),
    ],
)
def test_loop_break_nets_matches_bel_pattern(
    tmp_path: Path, module_name: str, pattern: str
) -> None:
    """A BEL is recognised by a selection pattern on its elaborated module name."""
    netlist = (_BEL + _ROUTING_TILE).replace("bel", module_name)

    yosys_json = _netlist_json(tmp_path, netlist)

    assert loop_break_nets(yosys_json, top="tile", bel_modules={pattern}) == ["j"]


@pytest.mark.parametrize(
    "netlist",
    [
        pytest.param(
            "module tile(input E, output N); INV u (.A(E), .Y(N)); endmodule\n",
            id="flattened",
        ),
        pytest.param(
            (_BEL + _ROUTING_TILE).replace("bel", "bel_Barch_3"), id="ghdl-elaborated"
        ),
    ],
)
def test_loop_break_nets_rejects_unmatched_bel(tmp_path: Path, netlist: str) -> None:
    """A BEL pattern matching no module leaves no way to keep cuts out of the BEL."""
    yosys_json = _netlist_json(tmp_path, netlist)

    with pytest.raises(InvalidState, match="match no module"):
        loop_break_nets(yosys_json, top="tile", bel_modules={"bel"})


@pytest.mark.parametrize(
    "nets",
    [
        pytest.param(["a", "b[1]"], id="cuts"),
        pytest.param([], id="no-loops"),
    ],
)
def test_render_sdc(nets: list[str]) -> None:
    """The base SDC comes first, then one driver-pin cut per net in order."""
    base_sdc = "create_clock -name clk -period 10 [get_ports clk]"

    sdc = render_sdc(base_sdc=base_sdc, nets=nets, design_name="tile")

    assert sdc.startswith(base_sdc)
    cuts = [line for line in sdc.splitlines() if line.startswith("set_disable_timing")]
    assert cuts == [
        f"set_disable_timing [fabulous_loop_break_driver {{{net}}}]" for net in nets
    ]
