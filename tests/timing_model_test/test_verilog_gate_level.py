from pathlib import Path

import networkx as nx
import pytest

import fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base as base_mod
from fabulous.fabric_cad.timing_model.hdlnx.hdlnx_timing_model import HdlnxTimingModel
from fabulous.fabric_cad.timing_model.hdlnx.verilog_gate_level import (
    VerilogGateLevelTimingGraph,
)
from fabulous.fabric_cad.timing_model.models import DelayType, SDFGobject

TEST_NETLIST = r"""
/* block comment with fake module
module Fake (input A); endmodule
*/

module LeafWrap (IN, OUT);
    BUF leafbuf ( .A(IN), .Y(OUT) ); // line comment
endmodule

module Mid (A, B, C);
    wire n1;
    LeafWrap u_leaf1 ( .IN(A), .OUT(n1) );
    NAND2   u_nand1 ( .A(n1), .B(B), .Y(C) );
endmodule

module Top (IN1, IN2, OUT1, OUT2);
    wire n_top;
    wire n_mid;

    Mid      u_mid   ( .A(IN1), .B(IN2), .C(n_top) );
    LeafWrap u_leaf2 ( .IN(n_top), .OUT(n_mid) );
    BUF      u_buf0  ( .A(n_mid), .Y(OUT1) );
    BUF      u_buf1  ( .A(IN2),   .Y(OUT2) );
endmodule
"""


class DummySynthTool:
    """Synthesis tool stand-in that hands back an already written netlist."""

    def __init__(self, netlist_file: Path) -> None:
        self.synth_netlist_file = netlist_file
        self.synth_design_name = "Top"
        self.synth_liberty_files: list[Path] = []

    def synth_synthesize(self) -> None:
        """Do nothing; the netlist file is written by the fixture."""

    def synth_clean_up(self) -> None:
        """Do nothing; `tmp_path` owns the netlist file."""


class DummyStaTool:
    """STA tool stand-in that hands back an already written SDF file."""

    def __init__(self, sdf_file: Path) -> None:
        self.sta_sdf_file = sdf_file
        self.sta_netlist_file: Path | None = None
        self.sta_design_name: str | None = None
        self.sta_liberty_files: list[Path] | None = None

    def sta_analyze(self) -> None:
        """Do nothing; the SDF file is written by the fixture."""

    def sta_clean_up(self) -> None:
        """Do nothing; `tmp_path` owns the SDF file."""


@pytest.fixture
def vg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> VerilogGateLevelTimingGraph:
    """Build the timing graph through the real constructor chain.

    The netlist content is read back from a file on disc, so every reader test
    exercises the parsing rather than a planted attribute. Only the SDF parser is
    faked out, since the tests here never look at delays.
    """
    netlist_file = tmp_path / "Top.v"
    netlist_file.write_text(TEST_NETLIST)
    sdf_file = tmp_path / "Top.sdf"
    sdf_file.write_text("(DELAYFILE)")

    sdf_gobject = SDFGobject(
        nx_graph=nx.DiGraph(),
        hier_sep="/",
        header_info={},
        sdf_data={},
        cells=[],
        instances={},
        io_paths=[],
        interconnects=[],
    )
    monkeypatch.setattr(
        base_mod,
        "gen_timing_digraph",
        lambda _path, _delay_type: sdf_gobject,
    )

    return HdlnxTimingModel(
        DummyStaTool(sdf_file),
        DummySynthTool(netlist_file),
        DelayType.MAX_ALL,
    )


def test_get_raw_verilog_netlist_data(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.get_raw_verilog_netlist_data() == TEST_NETLIST


def test_find_verilog_modules_regex_all(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.find_verilog_modules_regex(r".*") == ["LeafWrap", "Mid", "Top"]


def test_find_verilog_modules_regex_filtered(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.find_verilog_modules_regex(r"^L") == ["LeafWrap"]


def test_find_verilog_modules_regex_no_match(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.find_verilog_modules_regex(r"^XYZ$") == []


def test_find_instance_paths_by_regex_matches_recursive_paths(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    paths = vg.find_instance_paths_by_regex(r"u_")
    assert "u_mid" in paths
    assert "u_mid/u_leaf1" in paths
    assert "u_mid/u_leaf1/leafbuf" in paths
    assert "u_mid/u_nand1" in paths
    assert "u_leaf2" in paths
    assert "u_leaf2/leafbuf" in paths
    assert "u_buf0" in paths
    assert "u_buf1" in paths


def test_find_instance_paths_by_regex_with_filter(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    paths = vg.find_instance_paths_by_regex(r"u_", filter_regex=r"leaf")
    assert "u_mid/u_leaf1" in paths
    assert "u_mid/u_leaf1/leafbuf" in paths
    assert "u_leaf2" in paths
    assert "u_leaf2/leafbuf" in paths
    assert "u_buf0" not in paths


def test_find_instances_with_all_nets(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.find_instances_with_all_nets("Top", ["n_mid", "OUT1"]) == ["u_buf0"]


def test_find_instances_with_all_nets_no_match(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.find_instances_with_all_nets("Top", ["foo", "bar"]) == []


def test_find_instances_with_all_nets_missing_module(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    with pytest.raises(ValueError, match=r"Module 'Nope' not found in netlist content"):
        vg.find_instances_with_all_nets("Nope", ["A"])


def test_find_instances_paths_with_all_nets(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.find_instances_paths_with_all_nets("Top", ["n_mid", "OUT1"]) == ["u_buf0"]


def test_net_to_pin_paths_for_instance_leaf(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.net_to_pin_paths_for_instance("u_buf0") == {
        "n_mid": "u_buf0/A",
        "OUT1": "u_buf0/Y",
    }


def test_net_to_pin_paths_for_instance_nested(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.net_to_pin_paths_for_instance("u_mid/u_nand1") == {
        "n1": "u_mid/u_nand1/A",
        "B": "u_mid/u_nand1/B",
        "C": "u_mid/u_nand1/Y",
    }


def test_resolve_hier_pin_leaf_std_cell_returns_same_leaf(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.resolve_hier_pin("u_buf0/A") == ["u_buf0/A"]


def test_resolve_hier_pin_descends_into_submodule(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.resolve_hier_pin("u_leaf2/IN") == ["u_leaf2/leafbuf/A"]


def test_resolve_hier_pin_nested_submodule(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.resolve_hier_pin("u_mid/u_leaf1/IN") == ["u_mid/u_leaf1/leafbuf/A"]


def test_resolve_hier_pin_missing_target_pin(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    with pytest.raises(KeyError):
        vg.resolve_hier_pin("u_buf0/ZZ")


def test_resolve_hier_pin_missing_instance(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    with pytest.raises(KeyError):
        vg.resolve_hier_pin("u_mid/nope/A")


def test_resolve_hier_pin_rejects_short_path(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"Hierarchical pin path must be",
    ):
        vg.resolve_hier_pin("u_buf0")


def test_get_instance_pins_leaf(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.get_instance_pins("u_buf0") == ["A", "Y"]


def test_get_instance_pins_nested(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.get_instance_pins("u_mid/u_nand1") == ["A", "B", "Y"]


def test_get_module_instance_nets_top(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    result = vg.get_module_instance_nets("Top")
    assert result["u_mid"] == ["IN1", "IN2", "n_top"]
    assert result["u_leaf2"] == ["n_top", "n_mid"]
    assert result["u_buf0"] == ["n_mid", "OUT1"]
    assert result["u_buf1"] == ["IN2", "OUT2"]


def test_get_module_instance_nets_missing_module(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"Module 'Nope' not found in provided Verilog source",
    ):
        vg.get_module_instance_nets("Nope")


def test_net_to_pin_paths_for_instance_resolved(
    vg: VerilogGateLevelTimingGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vg,
        "net_to_pin_paths_for_instance",
        lambda _path: {"N1": "u0/A", "N2": "u0/B"},
    )
    monkeypatch.setattr(
        vg,
        "resolve_hier_pin",
        lambda pin: [pin + "_leaf1", pin + "_leaf2"],
    )
    assert vg.net_to_pin_paths_for_instance_resolved("u0") == {
        "N1": ["u0/A_leaf1", "u0/A_leaf2"],
        "N2": ["u0/B_leaf1", "u0/B_leaf2"],
    }


def test_nearest_port_from_pin_rejects_invalid_num_ports(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"num_ports must be at least 1",
    ):
        vg.nearest_port_from_pin("X", num_ports=0)


def test_nearest_port_from_pin_single_port(
    vg: VerilogGateLevelTimingGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _path_to_nearest_target_sentinel(
        _pin: str, _targets: set[str], reverse: bool = False
    ) -> tuple[list[str], str]:
        _ = reverse
        return ["dummy"], "OUT1"

    monkeypatch.setattr(
        vg,
        "path_to_nearest_target_sentinel",
        _path_to_nearest_target_sentinel,
    )
    assert vg.nearest_port_from_pin("u_buf0/A", reverse=False, num_ports=1) == ["OUT1"]


def test_nearest_port_from_pin_single_port_none(
    vg: VerilogGateLevelTimingGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _path_to_nearest_target_sentinel(
        _pin: str, _targets: set[str], reverse: bool = False
    ) -> tuple[list[str], None]:
        _ = reverse
        return [], None

    monkeypatch.setattr(
        vg,
        "path_to_nearest_target_sentinel",
        _path_to_nearest_target_sentinel,
    )
    assert vg.nearest_port_from_pin("u_buf0/A", num_ports=1) == []


def test_nearest_port_from_pin_multiple_forward(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    vg.graph.add_edges_from(
        [
            ("PIN", "N1"),
            ("N1", "OUT1"),
            ("PIN", "N2"),
            ("N2", "OUT2"),
        ]
    )
    vg.output_ports = {"OUT1", "OUT2"}
    assert vg.nearest_port_from_pin("PIN", reverse=False, num_ports=2) == [
        "OUT1",
        "OUT2",
    ]


def test_nearest_port_from_pin_multiple_reverse(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    vg.reverse_graph.add_edges_from(
        [
            ("PIN", "N1"),
            ("N1", "IN1"),
            ("PIN", "N2"),
            ("N2", "IN2"),
        ]
    )
    vg.input_ports = {"IN1", "IN2"}
    assert vg.nearest_port_from_pin("PIN", reverse=True, num_ports=2) == ["IN1", "IN2"]


def test_nearest_port_from_pin_multiple_no_ports(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    vg.graph.add_edge("PIN", "N1")
    vg.output_ports = {"OUT1", "OUT2"}
    assert vg.nearest_port_from_pin("PIN", reverse=False, num_ports=2) == []


def test_nearest_ports_from_instance_pin_nets(
    vg: VerilogGateLevelTimingGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vg,
        "net_to_pin_paths_for_instance_resolved",
        lambda _inst: {
            "N1": ["p1"],
            "N2": ["p2"],
            "N3": [],
        },
    )

    def fake_nearest(
        _pin: str,
        reverse: bool = False,
        num_ports: int = 1,
    ) -> list[str]:
        _ = (reverse, num_ports)
        if _pin == "p1":
            return ["OUT1", "OUT2"]
        if _pin == "p2":
            return ["OUT2"]
        return []

    monkeypatch.setattr(vg, "nearest_port_from_pin", fake_nearest)

    mapping, flat = vg.nearest_ports_from_instance_pin_nets(
        "u0", reverse=False, num_ports=2
    )

    assert mapping == {
        "N1": ["OUT1", "OUT2"],
        "N2": ["OUT2"],
    }
    assert flat == ["OUT1", "OUT2"]
