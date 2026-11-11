"""Tests for parsing BEL HDL files."""

import re
from pathlib import Path

import pytest

from fabulous.custom_exception import InvalidBelDefinition
from fabulous.fabric_definition.define import IO
from fabulous.fabric_generator.parser.parse_hdl import parseBelFile
from fabulous.fabulous_settings import init_context

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


VHDL_BEL = """package attr_pack_vhdl_bel is
  attribute FABulous : string;
  attribute BelMap   : string;
  attribute INV      : integer;
  attribute EXTERNAL : string;
end package attr_pack_vhdl_bel;

library IEEE;
  use IEEE.STD_LOGIC_1164.all;
  use work.attr_pack_vhdl_bel.all;

{belmap_comment}
entity vhdl_bel is
  generic (
    NoConfigBits : integer := 1
  );
  port (
    I          : in    std_logic;
    PAD        : out   std_logic; {pad_comment}
    ConfigBits : in    std_logic_vector(NoConfigBits - 1 downto 0)
  );
  {attributes}
end entity vhdl_bel;

architecture Behavioral of vhdl_bel is
begin
  PAD <= I xor ConfigBits(0);
end architecture Behavioral;
"""

NATIVE_BELMAP = """attribute FABulous of vhdl_bel : entity is "TRUE";
  attribute BelMap of vhdl_bel   : entity is "TRUE";
  attribute INV of vhdl_bel      : entity is 0;"""


@pytest.mark.parametrize(
    ("belmap_comment", "pad_comment", "attributes", "error"),
    [
        pytest.param(
            "",
            "",
            NATIVE_BELMAP + '\n  attribute EXTERNAL of PAD : signal is "TRUE";',
            None,
            id="native",
        ),
        pytest.param(
            "-- (* FABulous, BelMap, INV=0 *)",
            "-- (* FABulous, EXTERNAL *)",
            NATIVE_BELMAP + '\n  attribute EXTERNAL of PAD : signal is "TRUE";',
            None,
            id="comments_repeat_native",
        ),
        pytest.param(
            "",
            "-- EXTERNAL",
            NATIVE_BELMAP,
            "EXTERNAL of port PAD",
            id="plain_comment",
        ),
        pytest.param(
            "",
            "-- (* FABulous, EXTERNAL *)",
            NATIVE_BELMAP,
            "EXTERNAL of port PAD",
            id="attribute_comment",
        ),
        pytest.param(
            "-- (* FABulous, BelMap, INV=0 *)",
            "",
            'attribute EXTERNAL of PAD : signal is "TRUE";',
            "BelMap of the entity",
            id="belmap_comment",
        ),
    ],
)
def test_parse_bel_file_rejects_vhdl_comment_directives(
    project_vhdl: Path,
    belmap_comment: str,
    pad_comment: str,
    attributes: str,
    error: str | None,
) -> None:
    """A directive only declared in a VHDL comment is an error, not ignored."""
    init_context(project_vhdl)
    bel_file = project_vhdl / "Tile" / "vhdl_bel.vhdl"
    bel_file.write_text(
        VHDL_BEL.format(
            belmap_comment=belmap_comment,
            pad_comment=pad_comment,
            attributes=attributes,
        )
    )

    if error is None:
        bel = parseBelFile(bel_file, "A_")
        assert [p.name for p in bel.external_output_ports] == ["A_PAD"]
        assert list(bel.belFeatureMap) == ["INV"]
    else:
        with pytest.raises(InvalidBelDefinition, match=re.escape(error)):
            parseBelFile(bel_file, "A_")
