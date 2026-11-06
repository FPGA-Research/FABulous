"""BEL timing regression tests using real netlist and SDF parsers."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest

from fabulous.fabric_cad.gen_npnr_model import (
    emit_nextpnr_model,
    nextpnr_bel,
    placeholder_timing,
    render_arcs,
)
from fabulous.fabric_cad.timing_db import (
    BelArcs,
    BelTiming,
    FeatureIs,
)
from fabulous.fabric_cad.timing_model.FABulous_timing_model import (
    FABulousTileTimingModel,
)
from fabulous.fabric_cad.timing_model.hdlnx.hdlnx_timing_model import (
    HdlnxTimingModel,
)
from fabulous.fabric_cad.timing_model.models import (
    SDFPathType,
    TimingModelMode,
)
from fabulous.fabric_cad.timing_model.netlist import NetlistIndex
from fabulous.fabric_cad.timing_model.sdf_timing_graph import SdfTimingGraph
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from tests.conftest import make_empty_tile, make_fabric_from_grid
from tests.timing_model_test.conftest import ReadNetlist

FIXTURES = Path(__file__).parent / "fixtures"


def make_graph(
    tmp_path: Path,
    cells: list[str],
    interconnects: list[tuple[str, str]],
) -> HdlnxTimingModel:
    """Build the real SDF graph without invoking external EDA tools."""
    sdf = tmp_path / "demo.sdf"
    sdf.write_text(
        '(DELAYFILE (SDFVERSION "3.0") (DESIGN "Top") (DIVIDER /) '
        '(VOLTAGE (1:1:1)) (PROCESS "typical") '
        "(TEMPERATURE (25:25:25)) (TIMESCALE 1 ns) "
        '(CELL (CELLTYPE "Top") (INSTANCE) (DELAY (ABSOLUTE '
        + " ".join(
            f"(INTERCONNECT {source} {sink} (0:0:0))" for source, sink in interconnects
        )
        + "))) "
        + " ".join(cells)
        + ")"
    )
    graph = HdlnxTimingModel.__new__(HdlnxTimingModel)
    SdfTimingGraph.__init__(graph, sdf)
    return graph


def dff(instance: str) -> str:
    """Provide actual SETUP, HOLD, and CLK-to-Q SDF arcs."""
    return f"""(CELL (CELLTYPE "DFF") (INSTANCE {instance})
      (DELAY (ABSOLUTE (IOPATH (posedge CLK) Q (0.4:0.5:0.6))))
      (TIMINGCHECK (SETUP D (posedge CLK) (0.1:0.2:0.3))
                   (HOLD D (posedge CLK) (0.01:0.02:0.03))))"""


def mux(instance: str) -> str:
    """Provide two data arcs and one configuration arc."""
    return f"""(CELL (CELLTYPE "MUX") (INSTANCE {instance})
      (DELAY (ABSOLUTE (IOPATH A Y (0.1:0.1:0.1))
                       (IOPATH B Y (0.2:0.2:0.2))
                       (IOPATH S Y (0.1:0.1:0.1)))))"""


def make_bel(
    name: str,
    internal: dict[str, tuple[IO, int]],
    external: dict[str, tuple[IO, int]] | None = None,
    shared: dict[str, tuple[IO, int]] | None = None,
    features: tuple[str, ...] = (),
) -> Bel:
    """Build a real BEL with the declared port categories."""
    external = external or {}
    shared = shared or {}
    return Bel(
        src=Path(f"{name}.v"),
        prefix="A_",
        module_name=name,
        internal=[(f"A_{pin}", direction) for pin, (direction, _) in internal.items()],
        external=[(f"A_{pin}", direction) for pin, (direction, _) in external.items()],
        configPort=[],
        sharedPort=[(pin, direction) for pin, (direction, _) in shared.items()],
        configBit=len(features),
        belMap={feature: {} for feature in features},
        userCLK="UserCLK" in shared,
        ports_vectors={"internal": internal, "external": external, "shared": shared},
        carry={},
        localShared={},
    )


def make_model(
    graph: HdlnxTimingModel, netlist: NetlistIndex
) -> FABulousTileTimingModel:
    """Attach a prebuilt graph and its matching structural netlist."""
    model = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    model.tile_name = "demo_tile"
    model.hdlnx_tm_synth = graph
    model.synth_netlist = netlist
    model.tm_config = SimpleNamespace(
        mode=TimingModelMode.STRUCTURAL, delay_scaling_factor=1.0
    )
    return model


def v3_arcs(model: FABulousTileTimingModel, bel: Bel) -> list[str]:
    """Return the `bel.v3` timing lines of one characterised BEL."""
    return render_arcs(bel_arcs(model, bel), kind=nextpnr_bel(bel.name).kind)


def bel_arcs(model: FABulousTileTimingModel, bel: Bel) -> BelArcs:
    """Characterise a BEL instantiated directly under the top module."""
    return model.bel_timing(bel, instance=(bel.instance_name,))


def registered_bel(
    tmp_path: Path,
    read_netlist: ReadNetlist,
    clock: str,
    buffered: bool = False,
    name: str = "Register",
) -> tuple[Bel, FABulousTileTimingModel]:
    """Build a register with combinational bypass, like the LC output stage."""
    internal = {"D": (IO.INPUT, 1), "O": (IO.OUTPUT, 1)}
    shared = {}
    if clock == "UserCLK":
        shared[clock] = (IO.INPUT, 1)
    else:
        internal[clock] = (IO.INPUT, 1)
    bel = make_bel(name, internal, shared=shared, features=("FF",))
    clock_net = "buffered_clock" if buffered else clock
    buffer = f"BUF cbuf (.A({clock}), .Y(buffered_clock));" if buffered else ""
    netlist = f"""
    module {name} (D, O, {clock}, ConfigBits);
      input D, {clock};
      input [0:0] ConfigBits;
      output O;
      {buffer}
      DFF ff (.D(D), .CLK({clock_net}), .Q(q));
      MUX mux (.A(D), .B(q), .S(ConfigBits[0]), .Y(O));
    endmodule
    module Top (D, O, CLK, CFG);
      input D, CLK, CFG;
      output O;
      {name} Inst_A_{name} (.D(D), .O(O), .{clock}(CLK), .ConfigBits(CFG));
    endmodule
    """
    prefix = f"Inst_A_{name}/"
    cells = [dff(prefix + "ff"), mux(prefix + "mux")]
    connections = [(prefix + "ff/Q", prefix + "mux/B")]
    if buffered:
        cells.append(f"""(CELL (CELLTYPE "BUF") (INSTANCE {prefix}cbuf)
          (DELAY (ABSOLUTE (IOPATH A Y (0.1:0.1:0.1)))))""")
        connections.append((prefix + "cbuf/Y", prefix + "ff/CLK"))
    graph = make_graph(tmp_path, cells, connections)
    return bel, make_model(graph, read_netlist(netlist, "Top"))


@pytest.mark.parametrize(
    ("clock", "buffered", "expected_checks"),
    [
        ("UserCLK", False, 1),
        ("CLK", False, 1),
        ("UserCLK", True, 1),
        ("CLOCK", True, 1),
    ],
)
def test_clock_lookup_follows_internal_shared_and_buffered_clocks(
    tmp_path: Path,
    read_netlist: ReadNetlist,
    clock: str,
    buffered: bool,
    expected_checks: int,
) -> None:
    """Resolve routed and shared clocks, including internal clock propagation."""
    bel, model = registered_bel(tmp_path, read_netlist, clock, buffered)
    graph = model.hdlnx_tm_synth
    prefix = "Inst_A_Register/"
    clock_pin = prefix + ("cbuf/A" if buffered else "ff/CLK")
    raw = graph.query_timing_paths(prefix + "ff/D", prefix + "mux/Y")[0]
    assert raw.path_type == SDFPathType.SEQUENTIAL
    assert raw.setup
    assert raw.hold
    assert not raw.effective_setup
    complete = graph.query_timing_paths(
        prefix + "ff/D", prefix + "mux/Y", clock_pin=clock_pin
    )[0]
    assert complete.effective_setup
    assert complete.effective_hold
    assert complete.clock_to_output_rise.maximum == pytest.approx(
        0.9 if buffered else 0.8
    )
    arcs = bel_arcs(model, bel)
    assert arcs.clocks
    assert arcs.delays
    assert len(arcs.checks) == expected_checks
    assert len(arcs.clock_to_outs) == expected_checks


def test_iobuf_characterizes_registers_across_external_ports(
    tmp_path: Path, read_netlist: ReadNetlist
) -> None:
    """IOBUF data paths cross the external boundary; CLK-to-OUT has no D edge."""
    bel = make_bel(
        "IOBUF",
        {
            "CLK": (IO.INPUT, 1),
            "IN": (IO.INPUT, 1),
            "EN": (IO.INPUT, 1),
            "OUT": (IO.OUTPUT, 1),
        },
        external={
            "IN_top": (IO.OUTPUT, 1),
            "EN_top": (IO.OUTPUT, 1),
            "OUT_top": (IO.INPUT, 1),
        },
        features=("EN_REG", "IN_REG", "OUT_REG"),
    )
    netlist = """
    module IOBUF (CLK, IN, EN, OUT, IN_top, EN_top, OUT_top, ConfigBits);
      input CLK, IN, EN, OUT_top;
      input [2:0] ConfigBits;
      output OUT, IN_top, EN_top;
      DFF in_ff (.D(IN), .CLK(CLK), .Q(in_q));
      DFF en_ff (.D(EN), .CLK(CLK), .Q(en_q));
      DFF out_ff (.D(OUT_top), .CLK(CLK), .Q(out_q));
      MUX in_mux (.A(IN), .B(in_q), .S(ConfigBits[1]), .Y(IN_top));
      MUX en_mux (.A(EN), .B(en_q), .S(ConfigBits[0]), .Y(EN_top));
      MUX out_mux (.A(OUT_top), .B(out_q), .S(ConfigBits[2]), .Y(OUT));
    endmodule
    module Top (CLK, IN, EN, OUT, IN_top, EN_top, OUT_top, CFG);
      input CLK, IN, EN, OUT_top;
      input [2:0] CFG;
      output OUT, IN_top, EN_top;
      IOBUF Inst_A_IOBUF (.CLK(CLK), .IN(IN), .EN(EN), .OUT(OUT),
        .IN_top(IN_top), .EN_top(EN_top), .OUT_top(OUT_top), .ConfigBits(CFG));
    endmodule
    """
    prefix = "Inst_A_IOBUF/"
    cells = []
    connections = []
    for channel in ("in", "en", "out"):
        cells.extend([dff(prefix + channel + "_ff"), mux(prefix + channel + "_mux")])
        connections.append((prefix + channel + "_ff/Q", prefix + channel + "_mux/B"))
    graph = make_graph(tmp_path, cells, connections)
    # There really are valid sequential paths on all three independent channels.
    for channel in ("in", "en", "out"):
        complete = graph.query_timing_paths(
            prefix + channel + "_ff/D",
            prefix + channel + "_mux/Y",
            clock_pin=prefix + channel + "_ff/CLK",
        )[0]
        assert complete.effective_setup
        assert complete.effective_hold
        assert complete.clock_to_output_rise.maximum == pytest.approx(0.8)
    for channel in ("in", "en"):
        with pytest.raises(nx.NetworkXNoPath):
            graph.query_timing_paths(prefix + channel + "_ff/D", prefix + "out_mux/Y")
    clock_path = graph.query_timing_paths(
        prefix + "out_ff/CLK", prefix + "out_mux/Y", clock_pin=prefix + "out_ff/CLK"
    )[0]
    assert clock_path.path_type == SDFPathType.SEQUENTIAL
    assert clock_path.rise.maximum == pytest.approx(0.8)
    assert clock_path.register_clock_pin == prefix + "out_ff/CLK"
    assert clock_path.clock_to_output_rise.maximum == pytest.approx(0.8)
    assert v3_arcs(make_model(graph, read_netlist(netlist, "Top")), bel) == [
        "Clock,CLK",
        "SetupHold,IN,CLK,0.3,0.03,IN_REG=1",
        "SetupHold,EN,CLK,0.3,0.03,EN_REG=1",
        "ClkToOut,OUT,CLK,0.8,OUT_REG=1",
    ]


def test_bel_timing_excludes_paths_through_switch_matrix(
    tmp_path: Path, read_netlist: ReadNetlist
) -> None:
    """Feedback through tile routing must not become a BEL setup path."""
    bel, model = registered_bel(tmp_path, read_netlist, "CLK")
    baseline = bel_arcs(model, bel)
    prefix = "Inst_A_Register/"
    graph = make_graph(
        tmp_path,
        [dff(prefix + "ff"), mux(prefix + "mux"), mux("switch_matrix/feedback")],
        [
            (prefix + "ff/Q", prefix + "mux/B"),
            (prefix + "mux/Y", "switch_matrix/feedback/A"),
            ("switch_matrix/feedback/Y", prefix + "ff/D"),
        ],
    )
    # Shared graph views may already be cached by another timing consumer.
    clock_graph = graph.clock_graph
    combinational_graph = graph.combinational_graph
    model.hdlnx_tm_synth = graph
    assert bel_arcs(model, bel) == baseline
    assert graph.clock_graph is clock_graph
    assert graph.combinational_graph is combinational_graph
    assert graph.has_path(prefix + "mux/Y", prefix + "ff/D")


@pytest.mark.parametrize("mode", list(TimingModelMode))
def test_bel_timing_uses_synthesis_in_all_modes_and_applies_scaling(
    tmp_path: Path, read_netlist: ReadNetlist, mode: TimingModelMode
) -> None:
    bel, model = registered_bel(tmp_path, read_netlist, "CLK")
    physical_dir = tmp_path / "physical"
    physical_dir.mkdir()
    _, physical_model = registered_bel(physical_dir, read_netlist, "CLK", buffered=True)
    model.hdlnx_tm_phys = physical_model.hdlnx_tm_synth
    model.tm_config.mode = mode
    model.tm_config.delay_scaling_factor = 2.0
    lines = v3_arcs(model, bel)
    assert "Delay,D,O,0.2,FF=0" in lines
    assert "SetupHold,D,CLK,0.6,0.06,FF=1" in lines
    assert "ClkToOut,O,CLK,1.6,FF=1" in lines


def test_bel_timing_does_not_require_a_physical_model(
    tmp_path: Path, read_netlist: ReadNetlist
) -> None:
    bel, model = registered_bel(tmp_path, read_netlist, "CLK")
    expected = bel_arcs(model, bel)
    model.tm_config.mode = TimingModelMode.PHYSICAL
    model.hdlnx_tm_phys = None
    assert bel_arcs(model, bel) == expected


def test_bel_timing_requires_a_synthesis_model(
    tmp_path: Path, read_netlist: ReadNetlist
) -> None:
    bel, model = registered_bel(tmp_path, read_netlist, "CLK")
    model.hdlnx_tm_synth = None
    with pytest.raises(RuntimeError, match="synthesis timing model is not initialized"):
        bel_arcs(model, bel)


def test_missing_bel_reports_the_instance_and_tile(
    tmp_path: Path, read_netlist: ReadNetlist
) -> None:
    bel, model = registered_bel(tmp_path, read_netlist, "CLK")
    bel.prefix = "missing_"
    with pytest.raises(ValueError, match="missing_Register.*demo_tile"):
        bel_arcs(model, bel)


@pytest.mark.parametrize(
    "name", ["Register", "FABULOUS_LC", "LUT4c_frame_config_dffesr"]
)
def test_lc_clock_to_output_uses_nextpnr_q(
    tmp_path: Path, read_netlist: ReadNetlist, name: str
) -> None:
    bel, model = registered_bel(tmp_path, read_netlist, "CLK", name=name)
    expected_port = "O" if name == "Register" else "Q"
    assert f"ClkToOut,{expected_port},CLK,0.8,FF=1" in v3_arcs(model, bel)


def sky130_lc_and_iobuf(
    read_netlist: ReadNetlist,
) -> tuple[FABulousTileTimingModel, Bel, Bel]:
    """Build the Sky130 fixture model with its FABULOUS_LC and IOBUF BELs.

    Fixtures were generated from fabulous-tiles commit
    53cc215ce5f7bdba3375d2cad7a0fc1ce35c1f7d's FABULOUS_LC and IOBUF, using
    OSS CAD Suite 20251210 (Yosys 0.60+15, OpenSTA 2.7.0) and Sky130 HD
    tt_025C_1v80. The wrapper exposes all primitive inputs/configuration bits.
    Synthesis uses the timing model's hierarchical synth/renames/clockgate/
    dfflibmap/splitnets/insbuf/abc sequence, followed by OpenSTA write_sdf.
    """
    graph = HdlnxTimingModel.__new__(HdlnxTimingModel)
    SdfTimingGraph.__init__(graph, FIXTURES / "sky130_lc_iobuf.sdf")
    model = make_model(graph, read_netlist(FIXTURES / "sky130_lc_iobuf.v", "Top"))
    lc = make_bel(
        "FABULOUS_LC",
        {
            "I": (IO.INPUT, 4),
            "Ci": (IO.INPUT, 1),
            "SR": (IO.INPUT, 1),
            "EN": (IO.INPUT, 1),
            "CLK": (IO.INPUT, 1),
            "O": (IO.OUTPUT, 1),
            "Co": (IO.OUTPUT, 1),
        },
        features=("FF",),
    )
    lc.prefix = "LA_"
    io = make_bel(
        "IOBUF",
        {
            "CLK": (IO.INPUT, 1),
            "IN": (IO.INPUT, 1),
            "EN": (IO.INPUT, 1),
            "OUT": (IO.OUTPUT, 1),
        },
        external={
            "IN_top": (IO.OUTPUT, 1),
            "EN_top": (IO.OUTPUT, 1),
            "OUT_top": (IO.INPUT, 1),
        },
        features=("IN_REG", "EN_REG", "OUT_REG"),
    )
    return model, lc, io


def test_sky130_lc_and_iobuf_from_yosys_opensta(read_netlist: ReadNetlist) -> None:
    """Exercise real clock gating, escaped parameter modules, and external I/O."""
    model, lc, io = sky130_lc_and_iobuf(read_netlist)
    arcs = bel_arcs(model, lc)
    assert {arc.data.name for arc in arcs.checks} == {
        "I0",
        "I1",
        "I2",
        "I3",
        "Ci",
        "SR",
        "EN",
    }
    assert any(line.startswith("ClkToOut,Q,") for line in v3_arcs(model, lc))
    assert any(arc.src.name == "I3" for arc in arcs.delays)
    assert all(arc.when == () for arc in arcs.delays if arc.dst.name == "Co")
    io_arcs = bel_arcs(model, io)
    assert {arc.data.name for arc in io_arcs.checks} == {"IN", "EN"}
    assert {arc.out.name for arc in io_arcs.clock_to_outs} == {"OUT"}
    groups = (io_arcs.clocks, io_arcs.delays, io_arcs.checks, io_arcs.clock_to_outs)
    assert {arc.when for group in groups for arc in group} == {
        (),
        (FeatureIs("IN_REG", True),),
        (FeatureIs("EN_REG", True),),
        (FeatureIs("OUT_REG", True),),
    }


def test_sky130_lc_and_iobuf_bel_v3_matches_golden(read_netlist: ReadNetlist) -> None:
    """Pin the characterised `bel.v3` blocks of the Sky130 LC and IOBUF."""
    model, lc, io = sky130_lc_and_iobuf(read_netlist)
    tile = make_empty_tile("SKY130", pinOrderConfig={})
    tile.bels = [lc, io]
    fabric = make_fabric_from_grid([[tile]])
    bels = {bel.instance_name: bel_arcs(model, bel) for bel in tile.bels}
    timing = replace(
        placeholder_timing(fabric),
        bels=BelTiming(
            tiles={tile.name: bels},
            super_tiles={},
        ),
    )
    bel_v3 = emit_nextpnr_model(fabric, timing).bel_v3
    golden = (FIXTURES / "sky130_lc_iobuf.bel.v3.txt").read_text()
    assert bel_v3.splitlines()[2:] == golden.splitlines()


def test_input_only_bel_aggregates_register_constraints(
    tmp_path: Path, read_netlist: ReadNetlist
) -> None:
    bel = make_bel("InputOnly", {"D": (IO.INPUT, 1), "CLK": (IO.INPUT, 1)})
    netlist = """
module InputOnly (D, CLK);
    input D, CLK;
    DFF first (.D(D), .CLK(CLK), .Q(first_q));
    DFF second (.D(D), .CLK(CLK), .Q(second_q));
endmodule
module Top (D, CLK);
    input D, CLK;
    InputOnly Inst_A_InputOnly (.D(D), .CLK(CLK));
endmodule
"""
    graph = make_graph(
        tmp_path,
        [
            dff("Inst_A_InputOnly/first"),
            dff("Inst_A_InputOnly/second").replace("0.1:0.2:0.3", "0.6:0.7:0.8"),
        ],
        [],
    )
    assert v3_arcs(make_model(graph, read_netlist(netlist, "Top")), bel) == [
        "Clock,CLK",
        "SetupHold,D,CLK,0.8,0.03",
    ]


def test_independent_register_clocks_are_not_merged(
    tmp_path: Path, read_netlist: ReadNetlist
) -> None:
    bel = make_bel(
        "DualClock",
        {
            "D_A": (IO.INPUT, 1),
            "D_B": (IO.INPUT, 1),
            "CLK_A": (IO.INPUT, 1),
            "CLK_B": (IO.INPUT, 1),
            "Q_A": (IO.OUTPUT, 1),
            "Q_B": (IO.OUTPUT, 1),
        },
    )
    netlist = """
module DualClock (D_A, D_B, CLK_A, CLK_B, Q_A, Q_B);
    input D_A, D_B, CLK_A, CLK_B;
    output Q_A, Q_B;
    DFF first (.D(D_A), .CLK(CLK_A), .Q(Q_A));
    DFF second (.D(D_B), .CLK(CLK_B), .Q(Q_B));
endmodule
module Top (D_A, D_B, CLK_A, CLK_B, Q_A, Q_B);
    input D_A, D_B, CLK_A, CLK_B;
    output Q_A, Q_B;
    DualClock Inst_A_DualClock (.D_A(D_A), .D_B(D_B), .CLK_A(CLK_A),
      .CLK_B(CLK_B), .Q_A(Q_A), .Q_B(Q_B));
endmodule
"""
    graph = make_graph(
        tmp_path,
        [dff("Inst_A_DualClock/first"), dff("Inst_A_DualClock/second")],
        [],
    )
    assert set(v3_arcs(make_model(graph, read_netlist(netlist, "Top")), bel)) == {
        "Clock,CLK_A",
        "Clock,CLK_B",
        "SetupHold,D_A,CLK_A,0.3,0.03",
        "SetupHold,D_B,CLK_B,0.3,0.03",
        "ClkToOut,Q_A,CLK_A,0.6",
        "ClkToOut,Q_B,CLK_B,0.6",
    }
