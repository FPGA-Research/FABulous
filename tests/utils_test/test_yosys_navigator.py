"""Tests for the YosysJson hierarchy-navigation API and YosysModule helpers.

The structural queries run against modules parsed from a committed Yosys JSON
fixture (generated once with `write_json`), so the tests exercise a real Yosys
netlist without invoking Yosys at test time.
"""

import json
from pathlib import Path

import pytest

from fabulous.fabric_definition.yosys_obj import (
    YosysJson,
    YosysModule,
)

# Yosys JSON for a small three-module hierarchy:
#
#   module LeafWrap (IN, OUT);  BUF leafbuf (.A(IN), .Y(OUT));
#   module Mid (A, B, C);       LeafWrap u_leaf1 (.IN(A), .OUT(n1));
#                               NAND2    u_nand1 (.A(n1), .B(B), .Y(C));
#   module Top (IN1, IN2, OUT1, OUT2):
#       Mid      u_mid  (.A(IN1), .B(IN2), .C(n_top));
#       LeafWrap u_leaf2(.IN(n_top), .OUT(n_mid));
#       BUF      u_buf0 (.A(n_mid), .Y(OUT1));
#       BUF      u_buf1 (.A(IN2),   .Y(OUT2));
_FIXTURE = Path(__file__).parent / "data" / "gate_level_netlist.json"


def _load_yosys_modules() -> dict[str, YosysModule]:
    """Load the committed Yosys JSON fixture into YosysModule objects."""
    raw = json.loads(_FIXTURE.read_text())
    return {
        name: YosysModule(
            attributes=m.get("attributes", {}),
            parameter_default_values=m.get("parameter_default_values", {}),
            ports=m.get("ports", {}),
            cells=m.get("cells", {}),
            memories=m.get("memories", {}),
            netnames=m.get("netnames", {}),
        )
        for name, m in raw["modules"].items()
    }


@pytest.fixture
def nav() -> YosysJson:
    """A YosysJson over the committed three-module netlist, top = ``Top``."""
    return YosysJson.from_modules(_load_yosys_modules(), "Top", "/")


# ----------------------- YosysModule.pin_nets resolution ------------------


def test_pin_nets_resolves_cell_connections_to_net_names() -> None:
    modules = _load_yosys_modules()

    # Each pin maps to a list of per-bit net names; these scalar pins are
    # one-element lists.
    top = modules["Top"]
    assert top.pin_nets("u_mid") == {"A": ["IN1"], "B": ["IN2"], "C": ["n_top"]}
    assert top.pin_nets("u_leaf2") == {"IN": ["n_top"], "OUT": ["n_mid"]}
    assert top.pin_nets("u_buf0") == {"A": ["n_mid"], "Y": ["OUT1"]}

    # Inside a leaf-wrapping module, the std-cell pins resolve to local nets.
    assert modules["LeafWrap"].pin_nets("leafbuf") == {"A": ["IN"], "Y": ["OUT"]}


# ------------------------------ top-level ports ---------------------------


def test_module_port_names_read_directly_from_ports() -> None:
    # Directions and bit-blasting come straight from the module's declared
    # ports, not from any graph search.
    top = _load_yosys_modules()["Top"]
    assert top.port_names("input") == ["IN1", "IN2"]
    assert top.port_names("output") == ["OUT1", "OUT2"]


def test_top_level_ports_read_from_netlist(nav: YosysJson) -> None:
    # The navigator surfaces the top module's port directions verbatim.
    assert nav.input_ports == ["IN1", "IN2"]
    assert nav.output_ports == ["OUT1", "OUT2"]


# ----------------------------- module queries -----------------------------


def test_find_verilog_modules_regex_all(nav: YosysJson) -> None:
    assert nav.find_verilog_modules_regex(r".*") == ["LeafWrap", "Mid", "Top"]


def test_find_verilog_modules_regex_filtered(nav: YosysJson) -> None:
    assert nav.find_verilog_modules_regex(r"^L") == ["LeafWrap"]


def test_find_verilog_modules_regex_no_match(nav: YosysJson) -> None:
    assert nav.find_verilog_modules_regex(r"^XYZ$") == []


# ---------------------------- instance queries ----------------------------


def _ref(nav: YosysJson, path: str):  # noqa: ANN202
    """The InstanceRef whose hierarchical path is ``path``."""
    return next(r for r in nav.walk_instances() if r.path == path)


def test_find_instances_by_regex_matches_recursive_paths(
    nav: YosysJson,
) -> None:
    paths = [r.path for r in nav.find_instances_by_regex(r"u_")]
    assert "u_mid" in paths
    assert "u_mid/u_leaf1" in paths
    assert "u_mid/u_leaf1/leafbuf" in paths
    assert "u_mid/u_nand1" in paths
    assert "u_leaf2" in paths
    assert "u_leaf2/leafbuf" in paths
    assert "u_buf0" in paths
    assert "u_buf1" in paths


def test_find_instances_by_regex_with_filter(nav: YosysJson) -> None:
    paths = [r.path for r in nav.find_instances_by_regex(r"u_", filter_regex=r"leaf")]
    assert "u_mid/u_leaf1" in paths
    assert "u_mid/u_leaf1/leafbuf" in paths
    assert "u_leaf2" in paths
    assert "u_leaf2/leafbuf" in paths
    assert "u_buf0" not in paths


def test_walk_instances_pre_order_paths(nav: YosysJson) -> None:
    refs = list(nav.walk_instances())
    paths = [r.path for r in refs]
    assert paths == [
        "u_buf0",
        "u_buf1",
        "u_leaf2",
        "u_leaf2/leafbuf",
        "u_mid",
        "u_mid/u_leaf1",
        "u_mid/u_leaf1/leafbuf",
        "u_mid/u_nand1",
    ]
    # The ref carries its parent module type and a pin_nets() helper.
    u_buf0 = next(r for r in refs if r.path == "u_buf0")
    assert u_buf0.module_name == "Top"
    assert u_buf0.inst_name == "u_buf0"
    assert u_buf0.pin_nets() == {"A": ["n_mid"], "Y": ["OUT1"]}


# ----------------------- net-to-pin resolution (with descent) ----------------


def test_net_to_pin_paths_for_instance_resolved_leaf_std_cell(nav: YosysJson) -> None:
    # A leaf std-cell instance (BUF): each pin resolves to itself.
    assert nav.net_to_pin_paths_for_instance_resolved(_ref(nav, "u_buf0")) == {
        "n_mid": ["u_buf0/A"],
        "OUT1": ["u_buf0/Y"],
    }


def test_net_to_pin_paths_for_instance_resolved_descends_into_submodule(
    nav: YosysJson,
) -> None:
    # A submodule instance (LeafWrap): each port is followed into the child down
    # to the wrapped leaf std-cell pin.
    assert nav.net_to_pin_paths_for_instance_resolved(_ref(nav, "u_leaf2")) == {
        "n_top": ["u_leaf2/leafbuf/A"],
        "n_mid": ["u_leaf2/leafbuf/Y"],
    }


def test_net_to_pin_paths_for_instance_resolved_nested_submodule(
    nav: YosysJson,
) -> None:
    # A two-level submodule instance (Mid -> LeafWrap -> BUF): the net is followed
    # across each module boundary (a port name becomes the child net name).
    assert nav.net_to_pin_paths_for_instance_resolved(_ref(nav, "u_mid")) == {
        "IN1": ["u_mid/u_leaf1/leafbuf/A"],
        "IN2": ["u_mid/u_nand1/B"],
        "n_top": ["u_mid/u_nand1/Y"],
    }
