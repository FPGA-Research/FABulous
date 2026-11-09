"""Tests for the Yosys JSON netlist index."""

import pytest

from fabulous.fabric_cad.timing_model.netlist import (
    HierPath,
    NetlistIndex,
    PortBit,
    sdf_identifier,
)
from tests.timing_model_test.conftest import ReadNetlist

NETLIST = r"""
module Leaf (I, O, U);
    input [1:0] I;
    output O;
    output U;
    BUF lo (.A(I[0]), .Y(O));
    BUF hi (.A(I[1]), .Y(U));
endmodule

module \Child$  (I, O, U);
    input [0:3] I;
    output O;
    output U;
    BUF low (.A(I[3]), .Y(O));
    BUF high (.A(I[0]), .Y(U));
endmodule

module Mid (A, B, Y, Z, U0, U1);
    input A;
    input [7:4] B;
    output Y;
    output Z;
    output U0;
    output U1;
    wire [3:0] alias;
    assign alias = B;
    Leaf leaf (.I({B[5], A}), .O(Y), .U(U0));
    \Child$  child (.I({alias[3:2], alias[1:0]}), .O(Z), .U(U1));
endmodule

module Reg (D, CLK, Q);
    input D;
    input CLK;
    output Q;
    DFF \Q[0]$_DFF_P_  (.D(D), .CLK(CLK), .Q(Q));
endmodule

module Top (A, B, D, CLK, Y, Z, Q, U0, U1);
    input A;
    input [7:4] B;
    input D;
    input CLK;
    output Y;
    output Z;
    output Q;
    output U0;
    output U1;
    wire a_buf;
    BUF u_buf (.A(A), .Y(a_buf));
    Mid u_mid (.A(a_buf), .B(B), .Y(Y), .Z(Z), .U0(U0), .U1(U1));
    Reg \r$1  (.D(D), .CLK(CLK), .Q(Q));
endmodule
"""


@pytest.fixture
def netlist(read_netlist: ReadNetlist) -> NetlistIndex:
    """Index the shared test netlist."""
    return read_netlist(NETLIST, "Top")


@pytest.mark.parametrize(
    ("instance", "port", "expected"),
    [
        pytest.param(("u_buf",), PortBit("A", None), ["u_buf/A"], id="leaf-cell"),
        pytest.param(
            ("u_mid",), PortBit("A", None), ["u_mid/leaf/lo/A"], id="scalar-port"
        ),
        pytest.param(("u_mid",), PortBit("B", 5), ["u_mid/leaf/hi/A"], id="bus-bit"),
        pytest.param(
            ("u_mid",),
            PortBit("B", 4),
            ["u_mid/child/low/A"],
            id="alias-into-ascending-range",
        ),
        pytest.param(
            ("u_mid",),
            PortBit("B", 7),
            ["u_mid/child/high/A"],
            id="alias-into-ascending-range-msb",
        ),
        pytest.param(
            ("u_mid", "leaf"),
            PortBit("I", 1),
            ["u_mid/leaf/hi/A"],
            id="through-hierarchy",
        ),
        pytest.param(
            ("u_mid",), PortBit("Y", None), ["u_mid/leaf/lo/Y"], id="output-port"
        ),
        pytest.param(
            ("r$1",),
            PortBit("Q", None),
            [r"r\$1/Q\[0\]\$_DFF_P_/Q"],
            id="escaped-identifier",
        ),
    ],
)
def test_leaf_pins_resolve_port_bits_to_sdf_pins(
    netlist: NetlistIndex, instance: HierPath, port: PortBit, expected: list[str]
) -> None:
    """A port bit resolves to the leaf cell pins on its net, in SDF spelling."""
    assert netlist.leaf_pins(instance, port) == expected


@pytest.mark.parametrize(
    ("instance", "port", "error"),
    [
        pytest.param(("nope",), PortBit("A", None), KeyError, id="missing-instance"),
        pytest.param(
            ("u_buf", "x"), PortBit("A", None), KeyError, id="below-leaf-cell"
        ),
        pytest.param(("u_mid",), PortBit("ZZ", None), KeyError, id="missing-port"),
        pytest.param(("u_mid",), PortBit("B", 3), KeyError, id="missing-bit"),
        pytest.param(("u_mid",), PortBit("B", None), ValueError, id="bus-no-index"),
    ],
)
def test_leaf_pins_reject_absent_ports(
    netlist: NetlistIndex,
    instance: HierPath,
    port: PortBit,
    error: type[Exception],
) -> None:
    """An absent instance or port bit raises instead of returning no pins."""
    with pytest.raises(error):
        netlist.leaf_pins(instance, port)


@pytest.mark.parametrize(
    ("instance", "expected"),
    [
        (("u_mid", "leaf"), True),
        (("r$1",), True),
        (("u_mid", "nope"), False),
        (("u_buf", "x"), False),
        ((), False),
    ],
)
def test_contains_names_instance_paths(
    netlist: NetlistIndex, instance: HierPath, expected: bool
) -> None:
    """Membership holds exactly for instance paths of the hierarchy."""
    assert (instance in netlist) is expected


def test_child_nets_names_every_net_on_each_child(netlist: NetlistIndex) -> None:
    """Each child lists the parent's names of its nets, aliases included."""
    children = netlist.child_nets(("u_mid",))
    assert {name: set(nets) for name, nets in children.items()} == {
        "leaf": {"A", "B[5]", "alias[1]", "Y", "U0"},
        "child": {
            *("B[4]", "B[5]", "B[6]", "B[7]"),
            *("alias[0]", "alias[1]", "alias[2]", "alias[3]"),
            *("Z", "U1"),
        },
    }


@pytest.mark.parametrize(
    ("instance", "expected"),
    [
        pytest.param(
            ("u_buf",), {"A": ["u_buf/A"], "a_buf": ["u_buf/Y"]}, id="leaf-cell"
        ),
        pytest.param(
            ("u_mid", "leaf"),
            {
                "A": ["u_mid/leaf/lo/A"],
                "B[5]": ["u_mid/leaf/hi/A"],
                "alias[1]": ["u_mid/leaf/hi/A"],
                "Y": ["u_mid/leaf/lo/Y"],
                "U0": ["u_mid/leaf/hi/Y"],
            },
            id="module",
        ),
    ],
)
def test_net_leaf_pins_follow_each_connected_net(
    netlist: NetlistIndex, instance: HierPath, expected: dict[str, list[str]]
) -> None:
    """Each net on an instance maps to the leaf pins reached through it."""
    assert netlist.net_leaf_pins(instance) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ordinary_instance", "ordinary_instance"),
        ("Q$_DFF_P_", r"Q\$_DFF_P_"),
        ("Q[0]$_DFF_P_", r"Q\[0\]\$_DFF_P_"),
        (r"\$paramod\LUTK", r"\$paramod\\LUTK"),
        ("f:g/h", r"f\:g\/h"),
    ],
)
def test_sdf_identifier_escapes_like_opensta(name: str, expected: str) -> None:
    """Every character but letters, digits and `_` is escaped, as OpenSTA does."""
    assert sdf_identifier(name) == expected
