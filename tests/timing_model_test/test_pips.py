"""Tests for the pip delays read from the timing of a tile or supertile macro."""

from decimal import Decimal
from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_db import Pip, SwitchPip, WirePip
from fabulous.fabric_cad.timing_model.macro import (
    PhysicalMacro,
    StructuralMacro,
    TimedNetlist,
)
from fabulous.fabric_cad.timing_model.netlist import HierPath, NetlistIndex
from fabulous.fabric_cad.timing_model.pips import DEFAULT_PIP_DELAY, characterize_pips
from fabulous.fabric_cad.timing_model.sdf_timing_graph import SdfTimingGraph
from tests.timing_model_test.conftest import ReadNetlist

# Tile `T`: mux `mux_S1BEG0` drives a tile output, mux `mux_JN0` drives a
# wire that leaves the switch matrix through buffer `jbuf`.
NETLIST = r"""
module T_switch_matrix (N1END0, N1END1, CFG, S1BEG0, JN0);
    input N1END0;
    input N1END1;
    input CFG;
    output S1BEG0;
    output JN0;
    MUX2 mux_S1BEG0 (.A0(N1END0), .A1(N1END1), .S(CFG), .X(S1BEG0));
    MUX2 mux_JN0 (.A0(N1END0), .A1(N1END1), .S(CFG), .X(JN0));
endmodule

module T (N1END, CFG, UNUSED, S1BEG);
    input [1:0] N1END;
    input CFG;
    input UNUSED;
    output [1:0] S1BEG;
    wire jn0;
    T_switch_matrix Inst_T_switch_matrix (
        .N1END0(N1END[0]), .N1END1(N1END[1]), .CFG(CFG), .S1BEG0(S1BEG[0]), .JN0(jn0)
    );
    BUF jbuf (.A(jn0), .Y(S1BEG[1]));
endmodule
"""

SM = "Inst_T_switch_matrix"


def write_sdf(path: Path, cells: dict[str, list[str]], wires: list[str]) -> Path:
    """Write an SDF file of the cell IOPATHs and top-level INTERCONNECTs."""
    entries = [
        f'(CELL (CELLTYPE "C") (INSTANCE {instance}) (DELAY (ABSOLUTE '
        + " ".join(f"(IOPATH {iopath})" for iopath in iopaths)
        + ")))"
        for instance, iopaths in cells.items()
    ]
    top = " ".join(f"(INTERCONNECT {wire})" for wire in wires)
    entries.append(f'(CELL (CELLTYPE "T") (INSTANCE) (DELAY (ABSOLUTE {top})))')
    path.write_text(
        '(DELAYFILE (SDFVERSION "3.0") (DESIGN "T") (TIMESCALE 1ns) (DIVIDER /) '
        + " ".join(entries)
        + ")"
    )
    return path


def synth_graph(
    tmp_path: Path, *, wire: str = "0.02", buf: str = "0.03"
) -> SdfTimingGraph:
    """Return the timing of the synthesised netlist.

    `wire` and `buf` time the path from the `mux_JN0` output through `jbuf`.
    """
    return SdfTimingGraph(
        write_sdf(
            tmp_path / "synth.sdf",
            cells={
                f"{SM}/mux_S1BEG0": [
                    "A0 X (0.1::0.1)",
                    "A1 X (0.2::0.2)",
                    "S X (0.3::0.3)",
                ],
                f"{SM}/mux_JN0": [
                    "A0 X (0.4::0.4)",
                    "A1 X (0.5::0.5)",
                    "S X (0.6::0.6)",
                ],
                "jbuf": [f"A Y ({buf}::{buf})"],
            },
            wires=[
                f"N1END[0] {SM}/mux_S1BEG0/A0 (0.01::0.01)",
                f"N1END[1] {SM}/mux_S1BEG0/A1 (0.02::0.02)",
                f"N1END[0] {SM}/mux_JN0/A0 (0.01::0.01)",
                f"N1END[1] {SM}/mux_JN0/A1 (0.02::0.02)",
                f"CFG {SM}/mux_S1BEG0/S (0.0::0.0)",
                f"CFG {SM}/mux_JN0/S (0.0::0.0)",
                f"{SM}/mux_S1BEG0/X S1BEG[0] (0.05::0.05)",
                f"{SM}/mux_JN0/X jbuf/A ({wire}::{wire})",
                "jbuf/Y S1BEG[1] (0.0::0.0)",
                "UNUSED dead/A (0.1::0.1)",
            ],
        )
    )


@pytest.fixture
def netlist(read_netlist: ReadNetlist) -> NetlistIndex:
    """Index the synthesised netlist of tile `T`."""
    return read_netlist(NETLIST, "T")


STRUCTURAL_PIPS: dict[Pip, str] = {
    SwitchPip("N1END0", "S1BEG0"): "0.1",
    SwitchPip("N1END1", "S1BEG0"): "0.2",
    SwitchPip("N1END1", "JN0"): "0.5",
    # Tile output stitched to the next tile.
    WirePip("S1BEG0", "N1BEG0"): "0.001",
    # Tile input to its nearest tile output: N1END[1] -> mux_S1BEG0 -> S1BEG[0].
    WirePip("N1END1", "N1BEG1"): "0.27",
    # Tile input that reaches no tile output.
    WirePip("UNUSED", "N1BEG2"): "0.001",
    # Mux output followed through `jbuf` to the next mux input.
    WirePip("JN0", "JS0"): "0.05",
    # Wire whose source no internal pip drives.
    WirePip("N2MID0", "N2END0"): "0.001",
}


@pytest.mark.parametrize("reverse", [False, True], ids=["emission", "reversed"])
def test_structural_pip_delays(
    tmp_path: Path, netlist: NetlistIndex, reverse: bool
) -> None:
    """Each pip kind reads its delay; external pips find muxes listed after them."""
    timing = StructuralMacro(TimedNetlist(netlist=netlist, graph=synth_graph(tmp_path)))
    pips = list(STRUCTURAL_PIPS)[:: -1 if reverse else 1]

    delays = characterize_pips(
        timing, scope=(), switch_matrix=SM, pips=pips, scale=Decimal(1)
    )

    assert {pip: str(delay) for pip, delay in delays.items()} == STRUCTURAL_PIPS


@pytest.mark.parametrize(
    ("wire", "buf", "expected"),
    [
        pytest.param("0.02", "0.03", "0.05", id="wire-delay"),
        pytest.param("0.000001", "0.000002", "0.001", id="below-minimum"),
    ],
)
def test_followed_mux_wire_has_a_minimum_delay(
    tmp_path: Path,
    netlist: NetlistIndex,
    wire: str,
    buf: str,
    expected: str,
) -> None:
    """A followed mux-to-mux wire faster than 1e-5 ns gets the default delay."""
    graph = synth_graph(tmp_path, wire=wire, buf=buf)
    timing = StructuralMacro(TimedNetlist(netlist=netlist, graph=graph))
    pip = WirePip("JN0", "JS0")

    delays = characterize_pips(
        timing,
        scope=(),
        switch_matrix=SM,
        pips=[SwitchPip("N1END0", "JN0"), pip],
        scale=Decimal(1),
    )

    assert str(delays[pip]) == expected


@pytest.mark.parametrize(
    ("scale", "expected"),
    [
        pytest.param("1", ["0.1", "0.27", "0.001"], id="unscaled"),
        pytest.param("2", ["0.2", "0.54", "0.002"], id="doubled"),
        pytest.param("10", ["1.0", "2.7", "0.01"], id="integral"),
    ],
)
def test_pip_delays_scale_exactly(
    tmp_path: Path,
    netlist: NetlistIndex,
    scale: str,
    expected: list[str],
) -> None:
    """Internal, external and default delays all take the scaling factor."""
    timing = StructuralMacro(TimedNetlist(netlist=netlist, graph=synth_graph(tmp_path)))
    pips = [
        SwitchPip("N1END0", "S1BEG0"),
        WirePip("N1END1", "N1BEG1"),
        WirePip("S1BEG0", "N1BEG0"),
    ]

    delays = characterize_pips(
        timing, scope=(), switch_matrix=SM, pips=pips, scale=Decimal(scale)
    )

    assert [str(delays[pip]) for pip in pips] == expected


def test_physical_pip_delays_read_the_layout(
    tmp_path: Path, netlist: NetlistIndex, read_netlist: ReadNetlist
) -> None:
    """In the layout the mux is the node where the paths of its input ports meet."""
    layout = SdfTimingGraph(
        write_sdf(
            tmp_path / "layout.sdf",
            cells={"g": ["A0 X (0.5::0.5)", "A1 X (0.6::0.6)", "S X (0.7::0.7)"]},
            wires=[
                "N1END[0] g/A0 (0.1::0.1)",
                "N1END[1] g/A1 (0.1::0.1)",
                "CFG g/S (0.1::0.1)",
                "g/X S1BEG[0] (0.2::0.2)",
            ],
        )
    )
    synth = TimedNetlist(netlist=netlist, graph=synth_graph(tmp_path))
    layout_netlist = read_netlist(
        "module T (N1END, CFG, S1BEG); input [1:0] N1END; input CFG; "
        "output [1:0] S1BEG; MUX2 g (.A0(N1END[0]), .A1(N1END[1]), .S(CFG), "
        ".X(S1BEG[0])); endmodule",
        "T",
    )
    expected = {
        SwitchPip("N1END0", "S1BEG0"): "0.6",
        SwitchPip("N1END1", "S1BEG0"): "0.7",
        WirePip("N1END1", "N1BEG1"): "0.9",
    }

    delays = characterize_pips(
        PhysicalMacro(synth=synth, layout=layout, layout_netlist=layout_netlist),
        scope=(),
        switch_matrix=SM,
        pips=list(expected),
        scale=Decimal(1),
    )

    assert {pip: str(delay) for pip, delay in delays.items()} == expected


def test_missing_switch_matrix_raises(tmp_path: Path, netlist: NetlistIndex) -> None:
    """A macro without the tile's switch matrix instance cannot be timed."""
    timing = StructuralMacro(TimedNetlist(netlist=netlist, graph=synth_graph(tmp_path)))

    with pytest.raises(ValueError, match="Inst_U_switch_matrix"):
        characterize_pips(
            timing,
            scope=(),
            switch_matrix="Inst_U_switch_matrix",
            pips=[],
            scale=Decimal(1),
        )


# Supertile `ST`: member `BOT` drives member `TOP` through `Tile_X0Y1_N1BEG`, and
# routes `WW4END[1]` through two buffers to `WW4BEG[0]`. The supertile's own
# switch matrix drives `BEL_A`.
SUPER_NETLIST = r"""
module BOT_switch_matrix (W1END0, W1END1, CFG, N1BEG0, E1BEG0);
    input W1END0;
    input W1END1;
    input CFG;
    output N1BEG0;
    output E1BEG0;
    MUX2 mux_N1BEG0 (.A0(W1END0), .A1(W1END1), .S(CFG), .X(N1BEG0));
    MUX2 mux_E1BEG0 (.A0(W1END0), .A1(W1END1), .S(CFG), .X(E1BEG0));
endmodule

module BOT (W1END, WW4END, CFG, N1BEG, E1BEG, WW4BEG);
    input [1:0] W1END;
    input [1:0] WW4END;
    input CFG;
    output [1:0] N1BEG;
    output [1:0] E1BEG;
    output [1:0] WW4BEG;
    wire ww;
    BOT_switch_matrix Inst_BOT_switch_matrix (
        .W1END0(W1END[0]), .W1END1(W1END[1]), .CFG(CFG),
        .N1BEG0(N1BEG[0]), .E1BEG0(E1BEG[0])
    );
    BUF inbuf (.A(WW4END[1]), .Y(ww));
    BUF outbuf (.A(ww), .Y(WW4BEG[0]));
endmodule

module TOP_switch_matrix (N1END0, N1END1, CFG, E1BEG0);
    input N1END0;
    input N1END1;
    input CFG;
    output E1BEG0;
    MUX2 mux_E1BEG0 (.A0(N1END0), .A1(N1END1), .S(CFG), .X(E1BEG0));
endmodule

module TOP (N1END, CFG, E1BEG);
    input [1:0] N1END;
    input CFG;
    output [1:0] E1BEG;
    TOP_switch_matrix Inst_TOP_switch_matrix (
        .N1END0(N1END[0]), .N1END1(N1END[1]), .CFG(CFG), .E1BEG0(E1BEG[0])
    );
endmodule

module ST_switch_matrix (ST_I0, ST_I1, CFG, BEL_A);
    input ST_I0;
    input ST_I1;
    input CFG;
    output BEL_A;
    MUX2 mux_BEL_A (.A0(ST_I0), .A1(ST_I1), .S(CFG), .X(BEL_A));
endmodule

module ST (
    Tile_X0Y1_W1END, Tile_X0Y1_WW4END, ST_I0, ST_I1, CFG,
    Tile_X0Y0_E1BEG, Tile_X0Y1_E1BEG, Tile_X0Y1_WW4BEG, BEL_A
);
    input [1:0] Tile_X0Y1_W1END;
    input [1:0] Tile_X0Y1_WW4END;
    input ST_I0;
    input ST_I1;
    input CFG;
    output [1:0] Tile_X0Y0_E1BEG;
    output [1:0] Tile_X0Y1_E1BEG;
    output [1:0] Tile_X0Y1_WW4BEG;
    output BEL_A;
    wire [1:0] Tile_X0Y1_N1BEG;
    TOP Tile_X0Y0_TOP (.N1END(Tile_X0Y1_N1BEG), .CFG(CFG), .E1BEG(Tile_X0Y0_E1BEG));
    BOT Tile_X0Y1_BOT (
        .W1END(Tile_X0Y1_W1END), .WW4END(Tile_X0Y1_WW4END), .CFG(CFG),
        .N1BEG(Tile_X0Y1_N1BEG), .E1BEG(Tile_X0Y1_E1BEG), .WW4BEG(Tile_X0Y1_WW4BEG)
    );
    ST_switch_matrix Inst_ST_switch_matrix (
        .ST_I0(ST_I0), .ST_I1(ST_I1), .CFG(CFG), .BEL_A(BEL_A)
    );
endmodule
"""

BOT = "Tile_X0Y1_BOT"
BOT_SM = f"{BOT}/Inst_BOT_switch_matrix"
TOP = "Tile_X0Y0_TOP"
TOP_SM = f"{TOP}/Inst_TOP_switch_matrix"
ST_SM = "Inst_ST_switch_matrix"


@pytest.fixture
def super_timing(tmp_path: Path, read_netlist: ReadNetlist) -> StructuralMacro:
    """Return the structural timing of supertile `ST`."""
    graph = SdfTimingGraph(
        write_sdf(
            tmp_path / "st.sdf",
            cells={
                f"{BOT_SM}/mux_N1BEG0": [
                    "A0 X (0.1::0.1)",
                    "A1 X (0.2::0.2)",
                    "S X (0.3::0.3)",
                ],
                f"{BOT_SM}/mux_E1BEG0": [
                    "A0 X (0.4::0.4)",
                    "A1 X (0.5::0.5)",
                    "S X (0.6::0.6)",
                ],
                f"{BOT}/inbuf": ["A Y (0.05::0.05)"],
                f"{BOT}/outbuf": ["A Y (0.06::0.06)"],
                f"{TOP_SM}/mux_E1BEG0": [
                    "A0 X (0.7::0.7)",
                    "A1 X (0.8::0.8)",
                    "S X (0.9::0.9)",
                ],
                f"{ST_SM}/mux_BEL_A": [
                    "A0 X (0.15::0.15)",
                    "A1 X (0.25::0.25)",
                    "S X (0.35::0.35)",
                ],
            },
            wires=[
                *(
                    f"Tile_X0Y1_W1END[{i}] {BOT_SM}/{mux}/A{i} (0.01::0.01)"
                    for i in (0, 1)
                    for mux in ("mux_N1BEG0", "mux_E1BEG0")
                ),
                f"Tile_X0Y1_WW4END[1] {BOT}/inbuf/A (0.03::0.03)",
                f"{BOT}/inbuf/Y {BOT}/outbuf/A (0.0::0.0)",
                f"{BOT}/outbuf/Y Tile_X0Y1_WW4BEG[0] (0.0::0.0)",
                f"{BOT_SM}/mux_E1BEG0/X Tile_X0Y1_E1BEG[0] (0.0::0.0)",
                f"{BOT_SM}/mux_N1BEG0/X {TOP_SM}/mux_E1BEG0/A0 (0.04::0.04)",
                f"{TOP_SM}/mux_E1BEG0/X Tile_X0Y0_E1BEG[0] (0.0::0.0)",
                f"ST_I0 {ST_SM}/mux_BEL_A/A0 (0.01::0.01)",
                f"ST_I1 {ST_SM}/mux_BEL_A/A1 (0.01::0.01)",
                f"{ST_SM}/mux_BEL_A/X BEL_A (0.0::0.0)",
            ],
        )
    )
    return StructuralMacro(
        TimedNetlist(netlist=read_netlist(SUPER_NETLIST, "ST"), graph=graph)
    )


@pytest.mark.parametrize(
    ("scope", "switch_matrix", "expected"),
    [
        pytest.param(
            (BOT,),
            "Inst_BOT_switch_matrix",
            {
                # Mux path inside the member.
                SwitchPip("W1END0", "N1BEG0"): "0.1",
                SwitchPip("W1END1", "E1BEG0"): "0.5",
                # Member output that leaves the supertile.
                WirePip("E1BEG0", "E1END0"): "0.001",
                # Member input to its nearest member output, inside the member.
                WirePip("WW4END1", "WW4BEG1"): "0.11",
                # Member input with no load.
                WirePip("WW4END0", "WW4BEG0"): "0.001",
            },
            id="member-bot",
        ),
        pytest.param(
            (TOP,),
            "Inst_TOP_switch_matrix",
            {
                SwitchPip("N1END0", "E1BEG0"): "0.7",
                WirePip("E1BEG0", "E1END0"): "0.001",
            },
            id="member-top",
        ),
        pytest.param(
            (),
            ST_SM,
            {SwitchPip("ST_I0", "BEL_A"): "0.15", SwitchPip("ST_I1", "BEL_A"): "0.25"},
            id="supertile-switch-matrix",
        ),
    ],
)
def test_supertile_pips_are_timed_in_their_scope(
    super_timing: StructuralMacro,
    scope: HierPath,
    switch_matrix: str,
    expected: dict[Pip, str],
) -> None:
    """Member pips see the member ports; supertile pips see the supertile ports."""
    delays = characterize_pips(
        super_timing,
        scope=scope,
        switch_matrix=switch_matrix,
        pips=list(expected),
        scale=Decimal(1),
    )

    assert {pip: str(delay) for pip, delay in delays.items()} == expected


@pytest.mark.parametrize(
    "pip",
    [
        # The net reaches TOP through a 0.04 ns interconnect.
        pytest.param(WirePip("N1BEG0", "N1END0"), id="to-sibling-member"),
        pytest.param(WirePip("E1BEG0", "E1END0"), id="out-of-supertile"),
    ],
)
def test_member_output_is_stitched_wherever_its_net_goes(
    super_timing: StructuralMacro, pip: WirePip
) -> None:
    """A wire to a sibling member gets the same stitched delay as any tile wire."""
    delays = characterize_pips(
        super_timing,
        scope=(BOT,),
        switch_matrix="Inst_BOT_switch_matrix",
        pips=[pip],
        scale=Decimal(1),
    )

    assert delays == {pip: DEFAULT_PIP_DELAY}


# The post-layout netlist of `ST`, flat as OpenROAD writes it after a synthesis
# that kept the members: member cells carry their instance as a `/` prefix and
# the wires between members keep the wrapper's names. `_8_` drives the second
# wire into `TOP`.
LAYOUT_NETLIST = r"""
module ST (
    Tile_X0Y1_W1END, Tile_X0Y1_WW4END, ST_I0, ST_I1, CFG,
    Tile_X0Y0_E1BEG, Tile_X0Y1_E1BEG, Tile_X0Y1_WW4BEG, BEL_A
);
    input [1:0] Tile_X0Y1_W1END;
    input [1:0] Tile_X0Y1_WW4END;
    input ST_I0;
    input ST_I1;
    input CFG;
    output [1:0] Tile_X0Y0_E1BEG;
    output [1:0] Tile_X0Y1_E1BEG;
    output [1:0] Tile_X0Y1_WW4BEG;
    output BEL_A;
    wire \Tile_X0Y1_N1BEG[0] ;
    wire \Tile_X0Y1_N1BEG[1] ;
    wire \Tile_X0Y1_BOT/ww ;
    MUX2 \Tile_X0Y1_BOT/_1_  (
        .A0(Tile_X0Y1_W1END[0]), .A1(Tile_X0Y1_W1END[1]), .S(CFG),
        .X(\Tile_X0Y1_N1BEG[0] )
    );
    MUX2 \Tile_X0Y1_BOT/_2_  (
        .A0(Tile_X0Y1_W1END[0]), .A1(Tile_X0Y1_W1END[1]), .S(CFG),
        .X(Tile_X0Y1_E1BEG[0])
    );
    BUF \Tile_X0Y1_BOT/_3_  (.A(Tile_X0Y1_WW4END[1]), .Y(\Tile_X0Y1_BOT/ww ));
    BUF \Tile_X0Y1_BOT/_4_  (.A(\Tile_X0Y1_BOT/ww ), .Y(Tile_X0Y1_WW4BEG[0]));
    BUF \Tile_X0Y1_BOT/_8_  (.A(Tile_X0Y1_W1END[1]), .Y(\Tile_X0Y1_N1BEG[1] ));
    MUX2 \Tile_X0Y0_TOP/_5_  (
        .A0(\Tile_X0Y1_N1BEG[0] ), .A1(\Tile_X0Y1_N1BEG[1] ), .S(CFG),
        .X(Tile_X0Y0_E1BEG[0])
    );
    MUX2 _6_ (.A0(ST_I0), .A1(ST_I1), .S(CFG), .X(BEL_A));
endmodule
"""

LAYOUT_BOT = r"Tile_X0Y1_BOT\/"
LAYOUT_TOP = r"Tile_X0Y0_TOP\/"
LAYOUT_CELLS = {
    f"{LAYOUT_BOT}_1_": ["A0 X (0.11::0.11)", "A1 X (0.21::0.21)", "S X (0.31::0.31)"],
    f"{LAYOUT_BOT}_2_": ["A0 X (0.41::0.41)", "A1 X (0.51::0.51)", "S X (0.61::0.61)"],
    f"{LAYOUT_BOT}_3_": ["A Y (0.051::0.051)"],
    f"{LAYOUT_BOT}_4_": ["A Y (0.061::0.061)"],
    f"{LAYOUT_BOT}_8_": ["A Y (0.02::0.02)"],
    f"{LAYOUT_TOP}_5_": ["A0 X (0.71::0.71)", "A1 X (0.81::0.81)", "S X (0.91::0.91)"],
    "_6_": ["A0 X (0.151::0.151)", "A1 X (0.251::0.251)", "S X (0.351::0.351)"],
}
LAYOUT_WIRES = [
    *(
        f"Tile_X0Y1_W1END[{i}] {LAYOUT_BOT}{mux}/A{i} ({delay}::{delay})"
        for i, delay in ((0, "0.01"), (1, "0.02"))
        for mux in ("_1_", "_2_")
    ),
    f"Tile_X0Y1_W1END[1] {LAYOUT_BOT}_8_/A (0.02::0.02)",
    f"Tile_X0Y1_WW4END[1] {LAYOUT_BOT}_3_/A (0.03::0.03)",
    f"{LAYOUT_BOT}_3_/Y {LAYOUT_BOT}_4_/A (0.005::0.005)",
    f"{LAYOUT_BOT}_4_/Y Tile_X0Y1_WW4BEG[0] (0.007::0.007)",
    f"{LAYOUT_BOT}_2_/X Tile_X0Y1_E1BEG[0] (0.008::0.008)",
    # The two wires from BOT into TOP.
    f"{LAYOUT_BOT}_1_/X {LAYOUT_TOP}_5_/A0 (0.04::0.04)",
    f"{LAYOUT_BOT}_8_/Y {LAYOUT_TOP}_5_/A1 (0.06::0.06)",
    f"{LAYOUT_TOP}_5_/X Tile_X0Y0_E1BEG[0] (0.009::0.009)",
    *(
        f"CFG {cell}/S (0.002::0.002)"
        for cell in (f"{LAYOUT_BOT}_1_", f"{LAYOUT_BOT}_2_", f"{LAYOUT_TOP}_5_", "_6_")
    ),
    "ST_I0 _6_/A0 (0.01::0.01)",
    "ST_I1 _6_/A1 (0.01::0.01)",
    "_6_/X BEL_A (0.003::0.003)",
]


def physical_super_timing(
    tmp_path: Path,
    read_netlist: ReadNetlist,
    super_timing: StructuralMacro,
    *,
    netlist_edits: tuple[tuple[str, str], ...] = (),
    sdf_edits: tuple[tuple[str, str], ...] = (),
) -> PhysicalMacro:
    """Return the physical timing of `ST`, with text edits to its layout files."""
    layout_netlist = LAYOUT_NETLIST
    for old, new in netlist_edits:
        layout_netlist = layout_netlist.replace(old, new)
    layout_sdf = write_sdf(tmp_path / "layout.sdf", LAYOUT_CELLS, LAYOUT_WIRES)
    text = layout_sdf.read_text()
    for old, new in sdf_edits:
        text = text.replace(old, new)
    layout_sdf.write_text(text)
    return PhysicalMacro(
        synth=super_timing.synth,
        layout=SdfTimingGraph(layout_sdf),
        layout_netlist=read_netlist(layout_netlist, "ST"),
    )


@pytest.mark.parametrize(
    ("scope", "switch_matrix", "expected"),
    [
        pytest.param(
            (TOP,),
            "Inst_TOP_switch_matrix",
            {
                # The wire from BOT is charged at TOP's input: 0.04 + 0.71.
                SwitchPip("N1END0", "E1BEG0"): "0.75",
                SwitchPip("N1END1", "E1BEG0"): "0.87",
                # Input to the nearest output, which leaves the supertile:
                # 0.04 + 0.71 + the 0.009 wire to the supertile port.
                WirePip("N1END0", "N1BEG0"): "0.759",
                WirePip("E1BEG0", "E1END0"): "0.001",
            },
            id="member-top",
        ),
        pytest.param(
            (BOT,),
            "Inst_BOT_switch_matrix",
            {
                # 0.03 + 0.051 + 0.005 + 0.061 + 0.007.
                WirePip("WW4END1", "WW4BEG1"): "0.154",
                # Member outputs stay stitched: the wire to TOP is TOP's.
                WirePip("N1BEG0", "N1END0"): "0.001",
                WirePip("E1BEG0", "E1END0"): "0.001",
            },
            id="member-bot",
        ),
        pytest.param(
            (),
            ST_SM,
            {SwitchPip("ST_I0", "BEL_A"): "0.161"},
            id="supertile-switch-matrix",
        ),
    ],
)
def test_physical_supertile_pips_read_the_layout_of_their_scope(
    tmp_path: Path,
    read_netlist: ReadNetlist,
    super_timing: StructuralMacro,
    scope: HierPath,
    switch_matrix: str,
    expected: dict[Pip, str],
) -> None:
    """Member ports take each wire between members once, at the receiver."""
    timing = physical_super_timing(tmp_path, read_netlist, super_timing)

    delays = characterize_pips(
        timing,
        scope=scope,
        switch_matrix=switch_matrix,
        pips=list(expected),
        scale=Decimal(1),
    )

    assert {pip: str(delay) for pip, delay in delays.items()} == expected


@pytest.mark.parametrize(
    ("netlist_edits", "sdf_edits", "message"),
    [
        pytest.param(
            ((r"\Tile_X0Y0_TOP/", "\\"),),
            ((LAYOUT_TOP, ""),),
            r"Tile_X0Y0_TOP.*SYNTH_KEEP_HIERARCHY_MODULES",
            id="member-flattened",
        ),
        pytest.param(
            (("Tile_X0Y1_N1BEG", "net_17"),),
            (),
            r"Tile_X0Y0_TOP/N1END\[0\].*Tile_X0Y1_N1BEG\[0\]"
            r".*SYNTH_KEEP_HIERARCHY_MODULES",
            id="wire-renamed",
        ),
        pytest.param(
            (
                (
                    ".A0(\\Tile_X0Y1_N1BEG[0] ), .A1(\\Tile_X0Y1_N1BEG[1] )",
                    ".A0(n9), .A1(\\Tile_X0Y1_N1BEG[1] )",
                ),
                (
                    "    MUX2 _6_",
                    "    wire n9;\n    BUF _9_ (.A(\\Tile_X0Y1_N1BEG[0] ), .Y(n9));\n"
                    "    MUX2 _6_",
                ),
            ),
            (
                (
                    f"{LAYOUT_BOT}_1_/X {LAYOUT_TOP}_5_/A0",
                    f"{LAYOUT_BOT}_1_/X _9_/A (0.04::0.04)) "
                    f"(INTERCONNECT _9_/Y {LAYOUT_TOP}_5_/A0",
                ),
            ),
            r"Tile_X0Y0_TOP/N1END\[0\].*no pin inside.*SYNTH_KEEP_HIERARCHY_MODULES",
            id="cell-at-boundary",
        ),
    ],
)
def test_physical_member_without_its_hierarchy_raises(
    tmp_path: Path,
    read_netlist: ReadNetlist,
    super_timing: StructuralMacro,
    netlist_edits: tuple[tuple[str, str], ...],
    sdf_edits: tuple[tuple[str, str], ...],
    message: str,
) -> None:
    """A member that cannot be found in the layout stops the run, naming it."""
    timing = physical_super_timing(
        tmp_path,
        read_netlist,
        super_timing,
        netlist_edits=netlist_edits,
        sdf_edits=sdf_edits,
    )

    with pytest.raises(ValueError, match=message):
        characterize_pips(
            timing,
            scope=(TOP,),
            switch_matrix="Inst_TOP_switch_matrix",
            pips=[SwitchPip("N1END0", "E1BEG0")],
            scale=Decimal(1),
        )


# A two-member supertile hardened by real tools; see `generate.sh` next to it.
TOY = Path(__file__).parent / "fixtures" / "toy_supertile"
TOY_BOT = "Tile_X0Y1_TOY_bot"
TOY_TOP = "Tile_X0Y0_TOY_top"


@pytest.fixture
def toy_timing(read_netlist: ReadNetlist) -> PhysicalMacro:
    """Return the physical timing of the toy supertile fixture."""
    return PhysicalMacro(
        synth=TimedNetlist(
            netlist=read_netlist(TOY / "synth.v", "TOY"),
            graph=SdfTimingGraph(TOY / "synth.sdf"),
        ),
        layout=SdfTimingGraph(TOY / "layout.sdf"),
        layout_netlist=read_netlist(TOY / "layout.v", "TOY"),
    )


@pytest.mark.parametrize(
    ("scope", "switch_matrix", "expected"),
    [
        pytest.param(
            (TOY_BOT,),
            "Inst_TOY_bot_switch_matrix",
            {
                # Port wire + mux arc: 0.059 + 0.200, 0.074 + 0.210.
                SwitchPip("W1END0", "N1BEG0"): "0.259",
                SwitchPip("W1END1", "N1BEG0"): "0.284",
                SwitchPip("W1END1", "E1BEG0"): "0.338",
                SwitchPip("W1END2", "E1BEG0"): "0.32",
                # 0.072 + 0.138 + 0.006 + 0.222 + 0.099 to the supertile port.
                WirePip("WW4END1", "WW4BEG0"): "0.537",
                WirePip("N1BEG0", "N1END0"): "0.001",
                WirePip("E1BEG", "E1END0"): "0.001",
            },
            id="member-bot",
        ),
        pytest.param(
            (TOY_TOP,),
            "Inst_TOY_top_switch_matrix",
            {
                # The wires from TOY_bot, 0.007 and 0.010, are charged here.
                SwitchPip("N1END0", "E1BEG0"): "0.267",
                SwitchPip("N1END1", "E1BEG0"): "0.275",
                # 0.007 + 0.260 + the 0.104 wire to the supertile port.
                WirePip("N1END0", "N1BEG0"): "0.371",
                WirePip("E1BEG", "E1END0"): "0.001",
            },
            id="member-top",
        ),
    ],
)
def test_physical_member_pips_of_a_hardened_supertile(
    toy_timing: PhysicalMacro,
    scope: HierPath,
    switch_matrix: str,
    expected: dict[Pip, str],
) -> None:
    """Member pips read the flat OpenROAD netlist and its SPEF-annotated SDF."""
    delays = characterize_pips(
        toy_timing,
        scope=scope,
        switch_matrix=switch_matrix,
        pips=list(expected),
        scale=Decimal(1),
    )

    assert {pip: str(delay) for pip, delay in delays.items()} == expected
