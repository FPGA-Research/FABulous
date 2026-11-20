"""Tests for writing BELs as Yosys blackbox primitives."""

from pathlib import Path

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_generator.gen_fabric.fabric_automation import addBelsToPrim

SPLIT_PORTS = """module my_bel (
    input D0,
    input D1,
    input EN,
    output Q0,
    output Q1,
    (* iopad_external_pin *)
    output PAD0,
    (* iopad_external_pin *)
    output PAD1,
    input CLK
);"""

VECTOR_PORTS = """module my_bel (
    input [1:0] D,
    input EN,
    output [1:0] Q,
    (* iopad_external_pin *)
    output [1:0] PAD,
    input CLK
);"""


@pytest.mark.parametrize(
    ("keep_vector_ports", "expected_ports"),
    [
        pytest.param(False, SPLIT_PORTS, id="split"),
        pytest.param(True, VECTOR_PORTS, id="vector"),
    ],
)
def test_add_bels_to_prim_declares_vector_ports(
    tmp_path: Path, keep_vector_ports: bool, expected_ports: str
) -> None:
    """A BEL that keeps its vector ports gets a primitive with vector ports.

    The primitive has to match the pins the nextpnr model gives the BEL, which
    follow the same attribute.
    """
    bel = Bel(
        src=Path("my_bel.v"),
        prefix="A_",
        module_name="my_bel",
        internal=[
            ("A_D0", IO.INPUT),
            ("A_D1", IO.INPUT),
            ("A_EN", IO.INPUT),
            ("A_Q0", IO.OUTPUT),
            ("A_Q1", IO.OUTPUT),
        ],
        external=[("A_PAD0", IO.OUTPUT), ("A_PAD1", IO.OUTPUT)],
        configPort=[],
        sharedPort=[("UserCLK", IO.INPUT)],
        configBit=0,
        belMap={},
        userCLK=True,
        ports_vectors={
            "internal": {
                "D": (IO.INPUT, 2),
                "EN": (IO.INPUT, 1),
                "Q": (IO.OUTPUT, 2),
            },
            "external": {"PAD": (IO.OUTPUT, 2)},
            "config": {},
            "shared": {"UserCLK": (IO.INPUT, 1)},
        },
        carry={},
        localShared={},
        keep_vector_ports=keep_vector_ports,
    )
    prims_file = tmp_path / "custom_prims.v"
    prims_file.touch()

    addBelsToPrim(prims_file, [bel])

    assert expected_ports in prims_file.read_text()
