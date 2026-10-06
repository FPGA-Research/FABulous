from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_model.hdlnx.hdlnx_timing_model import HdlnxTimingModel
from fabulous.fabric_cad.timing_model.hdlnx.verilog_gate_level import (
    VerilogGateLevelTimingGraph,
)
from fabulous.fabric_cad.timing_model.models import DelayType

TEST_NETLIST = r"""
/* block comment with fake module
module Fake (input A); endmodule
*/

module LeafWrap (IN, OUT, NC);
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
    wire n_nc;

    Mid      u_mid    ( .A(IN1), .B(IN2), .C(n_top) );
    LeafWrap u_leaf2  ( .IN(n_top), .OUT(n_mid), .NC(IN1) );
    BUF      u_buf0   ( .A(n_mid), .Y(OUT1) );
    BUF      u_buf1   ( .A(IN2),   .Y(OUT2) );
    BUF      u_dangle ( .A(IN2),   .Y(n_nc) );
endmodule
"""


def _iopath_cell(cell_type: str, instance: str, arcs: list[str]) -> str:
    """Return an SDF `CELL` block with one 0.1 ns `IOPATH` per `from to` arc."""
    paths = "".join(f"    (IOPATH {arc} (0.1::0.1))\n" for arc in arcs)
    return (
        f'(CELL (CELLTYPE "{cell_type}") (INSTANCE {instance})\n'
        f" (DELAY (ABSOLUTE\n{paths} )))\n"
    )


# The STA view of TEST_NETLIST: OpenSTA names leaf cells by hierarchical path.
TEST_SDF = (
    '(DELAYFILE (SDFVERSION "3.0") (DESIGN "Top") (DIVIDER /)\n'
    '(CELL (CELLTYPE "Top") (INSTANCE)\n'
    " (DELAY (ABSOLUTE\n"
    "    (INTERCONNECT IN1 u_mid/u_leaf1/leafbuf/A (0.1::0.1))\n"
    "    (INTERCONNECT u_mid/u_leaf1/leafbuf/Y u_mid/u_nand1/A (0.1::0.1))\n"
    "    (INTERCONNECT IN2 u_mid/u_nand1/B (0.1::0.1))\n"
    "    (INTERCONNECT u_mid/u_nand1/Y u_leaf2/leafbuf/A (0.1::0.1))\n"
    "    (INTERCONNECT u_leaf2/leafbuf/Y u_buf0/A (0.1::0.1))\n"
    "    (INTERCONNECT u_buf0/Y OUT1 (0.1::0.1))\n"
    "    (INTERCONNECT IN2 u_buf1/A (0.1::0.1))\n"
    "    (INTERCONNECT u_buf1/Y OUT2 (0.1::0.1))\n"
    "    (INTERCONNECT IN2 u_dangle/A (0.1::0.1))\n"
    " )))\n"
    + _iopath_cell("BUF", "u_mid/u_leaf1/leafbuf", ["A Y"])
    + _iopath_cell("NAND2", "u_mid/u_nand1", ["A Y", "B Y"])
    + _iopath_cell("BUF", "u_leaf2/leafbuf", ["A Y"])
    + _iopath_cell("BUF", "u_buf0", ["A Y"])
    + _iopath_cell("BUF", "u_buf1", ["A Y"])
    + _iopath_cell("BUF", "u_dangle", ["A Y"])
    + ")\n"
)


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
def vg(tmp_path: Path) -> VerilogGateLevelTimingGraph:
    """Build the timing graph through the real constructor chain.

    Only the external synthesis and STA runs are stood in for: the netlist and the
    SDF they would produce are written to disc and parsed for real.
    """
    netlist_file = tmp_path / "Top.v"
    netlist_file.write_text(TEST_NETLIST)
    sdf_file = tmp_path / "Top.sdf"
    sdf_file.write_text(TEST_SDF)

    return HdlnxTimingModel(
        DummyStaTool(sdf_file),
        DummySynthTool(netlist_file),
        DelayType.MAX_ALL,
    )


def test_get_raw_verilog_netlist_data(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    assert vg.get_raw_verilog_netlist_data() == TEST_NETLIST


@pytest.mark.parametrize(
    ("name_pattern", "expected"),
    [(r".*", ["LeafWrap", "Mid", "Top"]), (r"^L", ["LeafWrap"]), (r"^XYZ$", [])],
    ids=["all", "filtered", "no_match"],
)
def test_find_verilog_modules_regex(
    vg: VerilogGateLevelTimingGraph, name_pattern: str, expected: list[str]
) -> None:
    assert vg.find_verilog_modules_regex(name_pattern) == expected


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
    assert result["u_leaf2"] == ["n_top", "n_mid", "IN1"]
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


@pytest.mark.parametrize(
    ("hier_inst_path", "expected"),
    [
        (
            "u_mid/u_leaf1",
            {"A": ["u_mid/u_leaf1/leafbuf/A"], "n1": ["u_mid/u_leaf1/leafbuf/Y"]},
        ),
        # NC is a LeafWrap port with nothing behind it
        (
            "u_leaf2",
            {
                "n_top": ["u_leaf2/leafbuf/A"],
                "n_mid": ["u_leaf2/leafbuf/Y"],
                "IN1": [],
            },
        ),
        ("u_buf0", {"n_mid": ["u_buf0/A"], "OUT1": ["u_buf0/Y"]}),
    ],
    ids=["nested_submodule", "unconnected_port", "leaf_cell"],
)
def test_net_to_pin_paths_for_instance_resolved(
    vg: VerilogGateLevelTimingGraph,
    hier_inst_path: str,
    expected: dict[str, list[str]],
) -> None:
    assert vg.net_to_pin_paths_for_instance_resolved(hier_inst_path) == expected


def test_nearest_port_from_pin_rejects_invalid_num_ports(
    vg: VerilogGateLevelTimingGraph,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"num_ports must be at least 1",
    ):
        vg.nearest_port_from_pin("X", num_ports=0)


@pytest.mark.parametrize(
    ("hier_pin_path", "reverse", "num_ports", "expected"),
    [
        ("u_buf0/A", False, 1, ["OUT1"]),
        ("u_leaf2/leafbuf/A", True, 1, ["IN2"]),
        ("u_dangle/A", False, 1, []),
        ("IN2", False, 2, ["OUT2", "OUT1"]),
        ("u_leaf2/leafbuf/A", True, 2, ["IN2", "IN1"]),
        ("u_dangle/A", False, 2, []),
    ],
    ids=[
        "single_forward",
        "single_reverse",
        "single_none_reachable",
        "nearest_first_forward",
        "nearest_first_reverse",
        "multiple_none_reachable",
    ],
)
def test_nearest_port_from_pin(
    vg: VerilogGateLevelTimingGraph,
    hier_pin_path: str,
    reverse: bool,
    num_ports: int,
    expected: list[str],
) -> None:
    assert (
        vg.nearest_port_from_pin(hier_pin_path, reverse=reverse, num_ports=num_ports)
        == expected
    )


@pytest.mark.parametrize(
    ("inst_path", "num_ports", "expected_mapping", "expected_flat"),
    [
        (
            "u_mid/u_nand1",
            2,
            {"n1": ["IN1"], "B": ["IN2"], "C": ["IN2", "IN1"]},
            ["IN1", "IN2"],
        ),
        # the unconnected NC port resolves to no pin and gets no entry
        ("u_leaf2", 1, {"n_top": ["IN2"], "n_mid": ["IN2"]}, ["IN2"]),
    ],
    ids=["deduplicated_flat_list", "skips_unresolved_net"],
)
def test_nearest_ports_from_instance_pin_nets(
    vg: VerilogGateLevelTimingGraph,
    inst_path: str,
    num_ports: int,
    expected_mapping: dict[str, list[str]],
    expected_flat: list[str],
) -> None:
    mapping, flat = vg.nearest_ports_from_instance_pin_nets(
        inst_path, reverse=True, num_ports=num_ports
    )

    assert mapping == expected_mapping
    assert flat == expected_flat
