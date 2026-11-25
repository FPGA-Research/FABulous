"""Mutation tests of the reference RTL equivalence checker.

Each case edits a copy of a 2.2.0 reference project. The checker must report every
functional fault and accept every edit that preserves behaviour.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_settings import init_context
from tests.reference_test.rtl_equivalence_test import check_rtl_equivalence

pytestmark = pytest.mark.slow

PROJECTS = {
    HDLType.VERILOG: Path("2.2/ref/demo_2.2.0_verilog"),
    HDLType.VHDL: Path("2.2/ref/demo_2.2.0_vhdl"),
}
MODELS_PACKS = {
    HDLType.VERILOG: Path("Fabric/models_pack.v"),
    HDLType.VHDL: Path("Fabric/models_pack.vhdl"),
}
SWITCH_MATRIX = "Tile/LUT4AB/LUT4AB_switch_matrix.v"
CONFIG_MEM = "Tile/LUT4AB/LUT4AB_ConfigMem.v"
BEL = "Tile/LUT4AB/LUT4c_frame_config_dffesr.v"
TILE = "Tile/LUT4AB/LUT4AB.v"
FABRIC = "Fabric/eFPGA.v"
MODELS_PACK = "Fabric/models_pack.v"
BLOCK_RAM = "Fabric/BlockRAM_1KB.v"
VHDL_SWITCH_MATRIX = "Tile/LUT4AB/LUT4AB_switch_matrix.vhdl"
VHDL_CONFIG_MEM = "Tile/LUT4AB/LUT4AB_ConfigMem.vhdl"
VHDL_BEL = "Tile/LUT4AB/LUT4c_frame_config_dffesr.vhdl"

MUX_PORTS = """    .A0(N1BEG0_input[0]),
    .A1(N1BEG0_input[1]),
    .A2(N1BEG0_input[2]),
    .A3(N1BEG0_input[3]),
    .S0(ConfigBits[0+0]),
    .S0N(ConfigBits_N[0+0]),
    .S1(ConfigBits[0+1]),
    .S1N(ConfigBits_N[0+1]),
    .X(N1BEG0)
"""
MUX_PORTS_REVERSED = (
    ",\n".join(reversed(MUX_PORTS.replace(",", "").splitlines())) + "\n"
)
MUX_INSTANCE = f"cus_mux41 inst_cus_mux41_N1BEG0 (\n{MUX_PORTS});"
MUX_AS_LOGIC = (
    "assign N1BEG0 = ConfigBits[0+1]"
    " ? (ConfigBits[0+0] ? N1BEG0_input[3] : N1BEG0_input[2])"
    " : (ConfigBits[0+0] ? N1BEG0_input[1] : N1BEG0_input[0]);"
)
LATCH_BIT24 = """config_latch Inst_Frame0_bit24 (
    .D(FrameData[24]),
    .E(FrameStrobe[0]),
    .Q(ConfigBits[242]),
    .QN(ConfigBits_N[242])
);
"""
LATCH_BIT23 = """config_latch Inst_Frame0_bit23 (
    .D(FrameData[23]),
    .E(FrameStrobe[0]),
    .Q(ConfigBits[243]),
    .QN(ConfigBits_N[243])
);
"""
FLOP = """    always @(posedge UserCLK) begin
        if (EN) begin
            if (SR) LUT_flop <= c_reset_value;
            else LUT_flop <= LUT_out;
        end
    end
"""


@dataclass(frozen=True)
class Edit:
    """Replace `old` with `new` in `file`, once unless `replace_all` is set."""

    file: str
    old: str
    new: str
    replace_all: bool = False


@dataclass(frozen=True)
class Mutation:
    """Edits to the `language` reference project and whether they change behaviour."""

    name: str
    language: HDLType
    functional: bool
    edits: tuple[Edit, ...]


def swap(file: str, first: str, second: str) -> tuple[Edit, ...]:
    """Return edits that exchange the unique strings `first` and `second`."""
    placeholder = "@@swap@@"
    return (
        Edit(file=file, old=first, new=placeholder),
        Edit(file=file, old=second, new=first),
        Edit(file=file, old=placeholder, new=second),
    )


MUTATIONS = [
    Mutation(
        name="mux_input_order",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=SWITCH_MATRIX,
                old="{J_l_CD_END1,JW2END3,",
                new="{JW2END3,J_l_CD_END1,",
            ),
        ),
    ),
    Mutation(
        name="mux_select_bits_swapped",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=SWITCH_MATRIX,
                old=".S0(ConfigBits[0+0]),",
                new=".S0(ConfigBits[0+1]),",
            ),
            Edit(
                file=SWITCH_MATRIX,
                old=".S1(ConfigBits[0+1]),",
                new=".S1(ConfigBits[0+0]),",
            ),
        ),
    ),
    Mutation(
        name="output_tied_low",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=SWITCH_MATRIX,
                old="assign N2BEG0 = JN2END0;",
                new="assign N2BEG0 = 1'b0;",
            ),
        ),
    ),
    Mutation(
        name="latch_bits_swapped",
        language=HDLType.VERILOG,
        functional=True,
        edits=swap(CONFIG_MEM, ".Q(ConfigBits[242]),", ".Q(ConfigBits[243]),"),
    ),
    Mutation(
        name="latch_wrong_frame_strobe",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=CONFIG_MEM,
                old=".D(FrameData[24]),\n    .E(FrameStrobe[0]),",
                new=".D(FrameData[24]),\n    .E(FrameStrobe[1]),",
            ),
        ),
    ),
    Mutation(
        name="bel_wrong_reset_bit",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=BEL,
                old="assign c_reset_value = ConfigBits[18];",
                new="assign c_reset_value = ConfigBits[17];",
            ),
        ),
    ),
    Mutation(
        name="bel_clock_edge",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=BEL,
                old="always @(posedge UserCLK)",
                new="always @(negedge UserCLK)",
            ),
        ),
    ),
    Mutation(
        name="bel_reset_over_enable",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=BEL,
                old=FLOP,
                new="""    always @(posedge UserCLK) begin
        if (SR) LUT_flop <= c_reset_value;
        else if (EN) LUT_flop <= LUT_out;
    end
""",
            ),
        ),
    ),
    Mutation(
        name="child_wiring_inverted",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=FABRIC,
                old="Tile_X1Y1_LUT4AB\n    (\n    .N1END(Tile_X1Y2_N1BEG),",
                new="Tile_X1Y1_LUT4AB\n    (\n    .N1END(~Tile_X1Y2_N1BEG),",
            ),
        ),
    ),
    Mutation(
        name="child_type_renamed",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=BEL,
                old="module LUT4c_frame_config_dffesr ",
                new="module LUT4c_dffesr ",
            ),
            Edit(
                file=TILE,
                old="LUT4c_frame_config_dffesr Inst_",
                new="LUT4c_dffesr Inst_",
                replace_all=True,
            ),
        ),
    ),
    Mutation(
        name="child_parameter_overridden",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=TILE,
                old="LUT4AB_switch_matrix Inst_LUT4AB_switch_matrix (",
                new="LUT4AB_switch_matrix #(.NoConfigBits(461)) "
                "Inst_LUT4AB_switch_matrix (",
            ),
        ),
    ),
    Mutation(
        name="models_pack_mux_behaviour",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=MODELS_PACK,
                old="wire B1 = S0 ? A3 : A2;",
                new="wire B1 = S0 ? A2 : A3;",
            ),
        ),
    ),
    Mutation(
        name="blackbox_port_width",
        language=HDLType.VERILOG,
        functional=True,
        edits=(
            Edit(
                file=BLOCK_RAM,
                old="input  wire                  csb0  ,",
                new="input  wire [1:0]            csb0  ,",
            ),
        ),
    ),
    Mutation(
        name="comments_and_whitespace",
        language=HDLType.VERILOG,
        functional=False,
        edits=(
            Edit(
                file=SWITCH_MATRIX,
                old="assign N2BEG0 = JN2END0;",
                new="// pass\n\n   assign    N2BEG0   =\n  JN2END0 ;  /* x */",
            ),
        ),
    ),
    Mutation(
        name="wire_renamed",
        language=HDLType.VERILOG,
        functional=False,
        edits=(
            Edit(
                file=SWITCH_MATRIX,
                old="N1BEG0_input",
                new="n1beg0_sel_in",
                replace_all=True,
            ),
        ),
    ),
    Mutation(
        name="port_connections_reordered",
        language=HDLType.VERILOG,
        functional=False,
        edits=(Edit(file=SWITCH_MATRIX, old=MUX_PORTS, new=MUX_PORTS_REVERSED),),
    ),
    Mutation(
        name="latch_instances_reordered",
        language=HDLType.VERILOG,
        functional=False,
        edits=(
            Edit(
                file=CONFIG_MEM,
                old=f"{LATCH_BIT24}\n{LATCH_BIT23}",
                new=f"{LATCH_BIT23}\n{LATCH_BIT24}",
            ),
        ),
    ),
    Mutation(
        name="latch_instances_renamed",
        language=HDLType.VERILOG,
        functional=False,
        edits=(
            Edit(
                file=CONFIG_MEM,
                old="config_latch Inst_Frame",
                new="config_latch cfg_frame",
                replace_all=True,
            ),
        ),
    ),
    Mutation(
        name="state_register_renamed",
        language=HDLType.VERILOG,
        functional=False,
        edits=(Edit(file=BEL, old="LUT_flop", new="lut_state_q", replace_all=True),),
    ),
    Mutation(
        name="flop_as_ternary",
        language=HDLType.VERILOG,
        functional=False,
        edits=(
            Edit(
                file=BEL,
                old=FLOP,
                new="""    always @(posedge UserCLK)
        if (EN) LUT_flop <= SR ? c_reset_value : LUT_out;
""",
            ),
        ),
    ),
    Mutation(
        name="models_pack_cell_as_logic",
        language=HDLType.VERILOG,
        functional=False,
        edits=(Edit(file=SWITCH_MATRIX, old=MUX_INSTANCE, new=MUX_AS_LOGIC),),
    ),
    Mutation(
        name="vhdl_mux_input_order",
        language=HDLType.VHDL,
        functional=True,
        edits=(
            Edit(
                file=VHDL_SWITCH_MATRIX,
                old="N1BEG0_input <= J_l_CD_END1 & JW2END3 &",
                new="N1BEG0_input <= JW2END3 & J_l_CD_END1 &",
            ),
        ),
    ),
    Mutation(
        name="vhdl_latch_bits_swapped",
        language=HDLType.VHDL,
        functional=True,
        edits=swap(VHDL_CONFIG_MEM, "Q => ConfigBits(242),", "Q => ConfigBits(243),"),
    ),
    Mutation(
        name="vhdl_signal_renamed",
        language=HDLType.VHDL,
        functional=False,
        edits=(
            Edit(
                file=VHDL_SWITCH_MATRIX,
                old="N1BEG0_input",
                new="n1beg0_sel_in",
                replace_all=True,
            ),
        ),
    ),
    Mutation(
        name="vhdl_state_register_renamed",
        language=HDLType.VHDL,
        functional=False,
        edits=(
            Edit(file=VHDL_BEL, old="LUT_flop", new="lut_state_q", replace_all=True),
        ),
    ),
]


def apply_edits(project: Path, edits: tuple[Edit, ...]) -> None:
    """Apply `edits` to `project`, failing if a target string is absent or ambiguous."""
    for edit in edits:
        path = project / edit.file
        text = path.read_text()
        count = text.count(edit.old)
        assert count == 1 or (edit.replace_all and count > 0), (
            f"{edit.old!r} occurs {count} times in {path}"
        )
        path.write_text(text.replace(edit.old, edit.new))


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda mutation: mutation.name)
def test_checker_verdict(
    mutation: Mutation,
    projects_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checker reports `mutation` exactly when it changes behaviour."""
    language = mutation.language
    reference = projects_dir / PROJECTS[language]
    mutated = tmp_path / reference.name
    shutil.copytree(reference, mutated, symlinks=True)
    apply_edits(mutated, mutation.edits)
    monkeypatch.setenv("FAB_PROJ_DIR", str(mutated))
    monkeypatch.setenv("FAB_PROJ_LANG", language.upper())
    init_context(mutated)

    failures = check_rtl_equivalence(
        reference=reference,
        regenerated=mutated,
        models_pack=MODELS_PACKS[language],
        language=language,
        top="eFPGA_top",
        work_dir=tmp_path / "equivalence",
    )

    assert bool(failures) == mutation.functional, failures
