"""Tests for parsing BEL HDL files."""

from pathlib import Path

import pytest

from fabulous.fabric_definition.define import IO
from fabulous.fabric_generator.parser.parse_hdl import parseBelFile

BEL_BODY = """module vector_bel #(
    parameter NoConfigBits = 1
) (
    input wire [3:0] D,
    input wire EN,
    output wire [3:0] Q,
    (* FABulous, GLOBAL *) input wire [NoConfigBits-1:0] ConfigBits
);
    assign Q = (EN ^ ConfigBits[0]) ? D : 4'b0;
endmodule
"""


@pytest.mark.parametrize(
    ("module_attribute", "keep_vector_ports"),
    [
        pytest.param("(* FABulous, BelMap, INV=0 *)", False, id="split"),
        pytest.param("(* FABulous, BelMap, VECTOR_PORTS, INV=0 *)", True, id="vector"),
        pytest.param("(* FABulous, BelMap, INV=0, vector_ports *)", True, id="case"),
    ],
)
def test_parse_bel_file_reads_vector_ports_attribute(
    tmp_path: Path, module_attribute: str, keep_vector_ports: bool
) -> None:
    """`VECTOR_PORTS` sets `keep_vector_ports` and nothing else.

    The attribute is not a BelMap feature, and the ports are split into the same
    switch-matrix wires with or without it.
    """
    bel_file = tmp_path / "vector_bel.v"
    bel_file.write_text(f"{module_attribute}\n{BEL_BODY}")

    bel = parseBelFile(bel_file, "A_")

    assert bel.keep_vector_ports is keep_vector_ports
    assert list(bel.belFeatureMap) == ["INV"]
    assert [p.name for p in bel.input_ports] == [
        "A_D0",
        "A_D1",
        "A_D2",
        "A_D3",
        "A_EN",
    ]
    assert [p.name for p in bel.output_ports] == ["A_Q0", "A_Q1", "A_Q2", "A_Q3"]
    assert bel.ports_vectors["internal"] == {
        "D": (IO.INPUT, 4),
        "EN": (IO.INPUT, 1),
        "Q": (IO.OUTPUT, 4),
    }
