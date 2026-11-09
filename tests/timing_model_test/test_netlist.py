"""Tests for the Yosys JSON netlist index."""

import pytest

from fabulous.fabric_cad.timing_model.netlist import (
    HierPath,
    NetlistIndex,
    PortBit,
    PortDirection,
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
    ("source", "top", "expected"),
    [
        pytest.param(
            NETLIST,
            "Top",
            [
                PortBit("A", None),
                *(PortBit("B", index) for index in (4, 5, 6, 7)),
                *(PortBit(name, None) for name in ("D", "CLK", "Y", "Z", "Q")),
                *(PortBit(name, None) for name in ("U0", "U1")),
            ],
            id="descending-range",
        ),
        pytest.param(
            "module P (I, O); input [0:2] I; output [0:0] O; endmodule",
            "P",
            [*(PortBit("I", index) for index in (2, 1, 0)), PortBit("O", None)],
            id="ascending-range",
        ),
    ],
)
def test_top_port_bits_list_each_bit_lsb_first(
    read_netlist: ReadNetlist, source: str, top: str, expected: list[PortBit]
) -> None:
    """Bits keep their HDL index; a one-bit port, `[0:0]` included, has none."""
    assert read_netlist(source, top).top_port_bits() == expected


@pytest.mark.parametrize(
    ("instance", "direction", "expected"),
    [
        pytest.param(
            ("u_mid",),
            "input",
            [PortBit("A", None), *(PortBit("B", index) for index in (4, 5, 6, 7))],
            id="inputs",
        ),
        pytest.param(
            ("u_mid",),
            "output",
            [PortBit(name, None) for name in ("Y", "Z", "U0", "U1")],
            id="outputs",
        ),
        pytest.param(
            ("u_mid", "child"),
            "input",
            [PortBit("I", index) for index in (3, 2, 1, 0)],
            id="nested-ascending-range",
        ),
    ],
)
def test_port_bits_list_one_direction_of_an_instance(
    netlist: NetlistIndex,
    instance: HierPath,
    direction: PortDirection,
    expected: list[PortBit],
) -> None:
    """The bits of the instance's module ports, LSB first, in one direction."""
    assert netlist.port_bits(instance, direction=direction) == expected


@pytest.mark.parametrize("instance", [("u_buf",), ("nope",)], ids=["leaf", "absent"])
def test_port_bits_reject_leaf_and_absent_instances(
    netlist: NetlistIndex, instance: HierPath
) -> None:
    """Only a module instance has module ports to list."""
    with pytest.raises(KeyError):
        netlist.port_bits(instance, direction="input")


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


@pytest.mark.parametrize(
    ("instance", "port", "expected"),
    [
        pytest.param(("u_buf",), PortBit("A", None), ["A"], id="top-port"),
        pytest.param(("u_mid",), PortBit("A", None), ["a_buf"], id="wire"),
        pytest.param(("u_mid",), PortBit("B", 5), ["B[5]"], id="bus-bit"),
        pytest.param(
            ("u_mid", "leaf"), PortBit("I", 1), ["B[5]", "alias[1]"], id="aliases"
        ),
        pytest.param(
            ("u_mid", "child"), PortBit("I", 0), ["B[7]", "alias[3]"], id="upto"
        ),
    ],
)
def test_parent_net_names_name_the_net_on_an_instance_pin(
    netlist: NetlistIndex, instance: HierPath, port: PortBit, expected: list[str]
) -> None:
    """The parent module's names of the net on one port bit of an instance."""
    assert sorted(netlist.parent_net_names(instance, port)) == expected


def test_parent_net_names_of_a_constant_bit_are_empty(
    read_netlist: ReadNetlist,
) -> None:
    """A port bit tied to a constant is on no net."""
    tied = read_netlist(
        "module Top (Y); output Y; BUF u (.A(1'b0), .Y(Y)); endmodule", "Top"
    )
    assert tied.parent_net_names(("u",), PortBit("A", None)) == []


# A flat post-layout netlist as OpenROAD writes it: member cells keep their
# member instance as a `/` prefix, a wire between members is a scalar escaped
# net, and the supertile ports stay vectors.
FLAT_NETLIST = r"""
module ST (Tile_X0Y1_W1END, Tile_X0Y0_E1BEG);
    input [1:0] Tile_X0Y1_W1END;
    output [1:0] Tile_X0Y0_E1BEG;
    wire \Tile_X0Y1_N1BEG[0] ;
    wire \Tile_X0Y1_BOT/inner.net ;
    BUF \Tile_X0Y1_BOT/_5_  (.A(Tile_X0Y1_W1END[0]), .Y(\Tile_X0Y1_BOT/inner.net ));
    BUF \Tile_X0Y1_BOT/_6_  (.A(\Tile_X0Y1_BOT/inner.net ), .Y(\Tile_X0Y1_N1BEG[0] ));
    BUF \Tile_X0Y0_TOP/_7_  (.A(\Tile_X0Y1_N1BEG[0] ), .Y(Tile_X0Y0_E1BEG[0]));
    BUF \Tile_X0Y0_TOP/_8_  (.A(\Tile_X0Y1_N1BEG[0] ), .Y(Tile_X0Y0_E1BEG[1]));
endmodule
"""


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param(
            "Tile_X0Y1_N1BEG[0]",
            [r"Tile_X0Y0_TOP\/_7_/A", r"Tile_X0Y0_TOP\/_8_/A", r"Tile_X0Y1_BOT\/_6_/Y"],
            id="escaped-scalar-wire",
        ),
        pytest.param(
            "Tile_X0Y1_W1END[0]", [r"Tile_X0Y1_BOT\/_5_/A"], id="vector-port-bit"
        ),
        pytest.param(
            "Tile_X0Y1_BOT/inner.net",
            [r"Tile_X0Y1_BOT\/_5_/Y", r"Tile_X0Y1_BOT\/_6_/A"],
            id="member-net",
        ),
        pytest.param("Tile_X0Y1_W1END[1]", [], id="port-bit-without-load"),
        pytest.param("Tile_X0Y1_N1BEG[1]", None, id="absent"),
    ],
)
def test_top_net_leaf_pins_find_a_net_by_its_spelled_name(
    read_netlist: ReadNetlist, name: str, expected: list[str] | None
) -> None:
    """A top-module net, scalar or vector bit, resolves to its leaf pins."""
    flat = read_netlist(FLAT_NETLIST, "ST")
    pins = flat.top_net_leaf_pins(name)
    assert (pins if pins is None else sorted(pins)) == expected
