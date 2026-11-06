"""Tests for the pip delays read from the timing of a tile macro."""

from decimal import Decimal
from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_db import Pip, SwitchPip, WirePip
from fabulous.fabric_cad.timing_model.macro import (
    PhysicalMacro,
    StructuralMacro,
    TileMacro,
    TimedNetlist,
)
from fabulous.fabric_cad.timing_model.netlist import NetlistIndex
from fabulous.fabric_cad.timing_model.pips import characterize_tile_pips
from fabulous.fabric_cad.timing_model.sdf_timing_graph import SdfTimingGraph
from tests.conftest import make_empty_tile
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


@pytest.fixture
def macro() -> TileMacro:
    """Return tile `T`, synthesised as its own macro."""
    return TileMacro(tile=make_empty_tile("T", pinOrderConfig={}), top="T", scope=())


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
    tmp_path: Path, netlist: NetlistIndex, macro: TileMacro, reverse: bool
) -> None:
    """Each pip kind reads its delay; external pips find muxes listed after them."""
    timing = StructuralMacro(TimedNetlist(netlist=netlist, graph=synth_graph(tmp_path)))
    pips = list(STRUCTURAL_PIPS)[:: -1 if reverse else 1]

    delays = characterize_tile_pips(timing, macro=macro, pips=pips, scale=Decimal(1))

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
    macro: TileMacro,
    wire: str,
    buf: str,
    expected: str,
) -> None:
    """A followed mux-to-mux wire faster than 1e-5 ns gets the default delay."""
    graph = synth_graph(tmp_path, wire=wire, buf=buf)
    timing = StructuralMacro(TimedNetlist(netlist=netlist, graph=graph))
    pip = WirePip("JN0", "JS0")

    delays = characterize_tile_pips(
        timing, macro=macro, pips=[SwitchPip("N1END0", "JN0"), pip], scale=Decimal(1)
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
    macro: TileMacro,
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

    delays = characterize_tile_pips(
        timing, macro=macro, pips=pips, scale=Decimal(scale)
    )

    assert [str(delays[pip]) for pip in pips] == expected


def test_physical_pip_delays_read_the_layout(
    tmp_path: Path, netlist: NetlistIndex, macro: TileMacro
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
    expected = {
        SwitchPip("N1END0", "S1BEG0"): "0.6",
        SwitchPip("N1END1", "S1BEG0"): "0.7",
        WirePip("N1END1", "N1BEG1"): "0.9",
    }

    delays = characterize_tile_pips(
        PhysicalMacro(synth=synth, layout=layout),
        macro=macro,
        pips=list(expected),
        scale=Decimal(1),
    )

    assert {pip: str(delay) for pip, delay in delays.items()} == expected


def test_missing_switch_matrix_raises(tmp_path: Path, netlist: NetlistIndex) -> None:
    """A macro without the tile's switch matrix instance cannot be timed."""
    timing = StructuralMacro(TimedNetlist(netlist=netlist, graph=synth_graph(tmp_path)))
    macro = TileMacro(tile=make_empty_tile("U", pinOrderConfig={}), top="T", scope=())

    with pytest.raises(ValueError, match="Inst_U_switch_matrix"):
        characterize_tile_pips(timing, macro=macro, pips=[], scale=Decimal(1))
