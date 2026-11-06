"""BEL timing regression tests using real netlist and SDF parsers."""

from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest

from fabulous.fabric_cad.timing_model.FABulous_timing_model import (
    FABulousTileTimingModel,
)
from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph import SDFTimingGraph
from fabulous.fabric_cad.timing_model.hdlnx.verilog_gate_level import (
    VerilogGateLevelTimingGraph,
)
from fabulous.fabric_cad.timing_model.models import (
    BelClockTiming,
    BelClockToOutTiming,
    BelDelayTiming,
    BelSetupHoldTiming,
    SDFPathType,
    TimingModelMode,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO


def make_graph(
    tmp_path: Path,
    netlist: str,
    cells: list[str],
    interconnects: list[tuple[str, str]],
) -> VerilogGateLevelTimingGraph:
    """Build the real SDF graph and attach its matching structural netlist."""
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
    graph = VerilogGateLevelTimingGraph.__new__(VerilogGateLevelTimingGraph)
    SDFTimingGraph.__init__(graph, sdf)
    graph.top_name = "Top"
    graph.verilog_netlist_content = netlist
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


def make_model(graph: VerilogGateLevelTimingGraph) -> FABulousTileTimingModel:
    """Attach a prebuilt graph without invoking external EDA tools."""
    model = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    model.tile_name = "demo_tile"
    model.hdlnx_tm_synth = graph
    model.tm_config = SimpleNamespace(
        mode=TimingModelMode.STRUCTURAL, delay_scaling_factor=1.0
    )
    return model


def registered_bel(
    tmp_path: Path, clock: str, buffered: bool = False
) -> tuple[Bel, FABulousTileTimingModel]:
    """Build a register with combinational bypass, like the LC output stage."""
    internal = {"D": (IO.INPUT, 1), "O": (IO.OUTPUT, 1)}
    shared = {}
    if clock == "UserCLK":
        shared[clock] = (IO.INPUT, 1)
    else:
        internal[clock] = (IO.INPUT, 1)
    bel = make_bel("Register", internal, shared=shared, features=("FF",))
    clock_net = "buffered_clock" if buffered else clock
    buffer = f"BUF cbuf (.A({clock}), .Y(buffered_clock));" if buffered else ""
    netlist = f"""
    module Register (D, O, {clock}, ConfigBits);
      {buffer}
      DFF ff (.D(D), .CLK({clock_net}), .Q(q));
      MUX mux (.A(D), .B(q), .S(ConfigBits[0]), .Y(O));
    endmodule
    module Top (D, O, CLK, CFG);
      Register Inst_A_Register (.D(D), .O(O), .{clock}(CLK), .ConfigBits(CFG));
    endmodule
    """
    prefix = "Inst_A_Register/"
    cells = [dff(prefix + "ff"), mux(prefix + "mux")]
    connections = [(prefix + "ff/Q", prefix + "mux/B")]
    if buffered:
        cells.append(f"""(CELL (CELLTYPE "BUF") (INSTANCE {prefix}cbuf)
          (DELAY (ABSOLUTE (IOPATH A Y (0.1:0.1:0.1)))))""")
        connections.append((prefix + "cbuf/Y", prefix + "ff/CLK"))
    return bel, make_model(make_graph(tmp_path, netlist, cells, connections))


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
    tmp_path: Path, clock: str, buffered: bool, expected_checks: int
) -> None:
    """Resolve routed and shared clocks, including internal clock propagation."""
    bel, model = registered_bel(tmp_path, clock, buffered)
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
    arcs = model.bel_timing(bel).arcs
    assert any(isinstance(arc, BelClockTiming) for arc in arcs)
    assert any(isinstance(arc, BelDelayTiming) for arc in arcs)
    assert sum(isinstance(arc, BelSetupHoldTiming) for arc in arcs) == expected_checks
    assert sum(isinstance(arc, BelClockToOutTiming) for arc in arcs) == expected_checks


def test_iobuf_characterizes_registers_across_external_ports(tmp_path: Path) -> None:
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
      DFF in_ff (.D(IN), .CLK(CLK), .Q(in_q));
      DFF en_ff (.D(EN), .CLK(CLK), .Q(en_q));
      DFF out_ff (.D(OUT_top), .CLK(CLK), .Q(out_q));
      MUX in_mux (.A(IN), .B(in_q), .S(ConfigBits[1]), .Y(IN_top));
      MUX en_mux (.A(EN), .B(en_q), .S(ConfigBits[0]), .Y(EN_top));
      MUX out_mux (.A(OUT_top), .B(out_q), .S(ConfigBits[2]), .Y(OUT));
    endmodule
    module Top (CLK, IN, EN, OUT, IN_top, EN_top, OUT_top, CFG);
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
    graph = make_graph(tmp_path, netlist, cells, connections)
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
    assert make_model(graph).bel_timing(bel).arcs == (
        BelClockTiming("CLK"),
        BelSetupHoldTiming("IN", "CLK", 0.3, 0.03, condition="IN_REG=1"),
        BelSetupHoldTiming("EN", "CLK", 0.3, 0.03, condition="EN_REG=1"),
        BelClockToOutTiming("OUT", "CLK", 0.8, condition="OUT_REG=1"),
    )


def test_bel_timing_excludes_paths_through_switch_matrix(tmp_path: Path) -> None:
    """Feedback through tile routing must not become a BEL setup path."""
    bel, model = registered_bel(tmp_path, "CLK")
    baseline = model.bel_timing(bel)
    prefix = "Inst_A_Register/"
    graph = make_graph(
        tmp_path,
        model.hdlnx_tm_synth.verilog_netlist_content,
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
    assert model.bel_timing(bel) == baseline
    assert graph.clock_graph is clock_graph
    assert graph.combinational_graph is combinational_graph
    assert graph.has_path(prefix + "mux/Y", prefix + "ff/D")


def test_vector_hierarchy_connections_resolve_bits() -> None:
    """Follow each vector bit through a child port concatenation."""
    graph = VerilogGateLevelTimingGraph.__new__(VerilogGateLevelTimingGraph)
    graph.top_name = "Top"
    graph.hier_sep = "/"
    graph.verilog_netlist_content = """
    module Child (I, O);
      input [3:0] I;
      output O;
      MUX mux (.A(I[0]), .B(I[1]), .S(I[3]), .Y(O));
    endmodule
    module LC (I, Ci, O);
      input [3:0] I;
      input Ci;
      output O;
      MUX input_mux (.A(I[0]), .B(Ci), .S(I[1]), .Y(index0));
      Child lut (.I({ I[3:1], index0 }), .O(O));
    endmodule
    module Top (I, Ci, O);
      LC Inst_A_LC (.I(I), .Ci(Ci), .O(O));
    endmodule
    """
    assert graph.resolve_hier_pin("Inst_A_LC/I[0]") == ["Inst_A_LC/input_mux/A"]
    assert graph.resolve_hier_pin("Inst_A_LC/I[3]") == ["Inst_A_LC/lut/mux/S"]


@pytest.mark.parametrize("mode", list(TimingModelMode))
def test_bel_timing_uses_synthesis_in_all_modes_and_applies_scaling(
    tmp_path: Path, mode: TimingModelMode
) -> None:
    bel, model = registered_bel(tmp_path, "CLK")
    physical_dir = tmp_path / "physical"
    physical_dir.mkdir()
    _, physical_model = registered_bel(physical_dir, "CLK", buffered=True)
    model.hdlnx_tm_phys = physical_model.hdlnx_tm_synth
    model.tm_config.mode = mode
    model.tm_config.delay_scaling_factor = 2.0
    arcs = model.bel_timing(bel).arcs
    assert BelDelayTiming("D", "O", 0.2, condition="FF=0") in arcs
    assert (
        BelSetupHoldTiming(
            "D",
            "CLK",
            0.6,
            0.06,
            condition="FF=1",
        )
        in arcs
    )
    assert BelClockToOutTiming("O", "CLK", 1.6, condition="FF=1") in arcs


def test_bel_timing_does_not_require_a_physical_model(tmp_path: Path) -> None:
    bel, model = registered_bel(tmp_path, "CLK")
    expected = model.bel_timing(bel)
    model.tm_config.mode = TimingModelMode.PHYSICAL
    model.hdlnx_tm_phys = None
    assert model.bel_timing(bel) == expected


def test_bel_timing_requires_a_synthesis_model(tmp_path: Path) -> None:
    bel, model = registered_bel(tmp_path, "CLK")
    model.hdlnx_tm_synth = None
    with pytest.raises(RuntimeError, match="synthesis timing model is not initialized"):
        model.bel_timing(bel)


def test_missing_bel_reports_the_instance_and_tile(tmp_path: Path) -> None:
    bel, model = registered_bel(tmp_path, "CLK")
    bel.prefix = "missing_"
    with pytest.raises(ValueError, match="missing_Register.*demo_tile"):
        model.bel_timing(bel)


def test_multiple_bel_instances_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bel, model = registered_bel(tmp_path, "CLK")
    graph = model.hdlnx_tm_synth
    graph.verilog_netlist_content = graph.verilog_netlist_content.replace(
        ".ConfigBits(CFG));",
        ".ConfigBits(CFG)); Register Other_A_Register "
        "(.D(D), .O(O), .CLK(CLK), .ConfigBits(CFG));",
    )
    assert model.bel_timing(bel).arcs
    assert "Found multiple hierarchical instance paths" in caplog.text


@pytest.mark.parametrize(
    "name", ["Register", "FABULOUS_LC", "LUT4c_frame_config_dffesr"]
)
def test_lc_clock_to_output_uses_nextpnr_q(tmp_path: Path, name: str) -> None:
    bel, model = registered_bel(tmp_path, "CLK")
    model.hdlnx_tm_synth.verilog_netlist_content = (
        model.hdlnx_tm_synth.verilog_netlist_content.replace("Register", name)
    )
    # Keep SDF instance names and Verilog names identical after renaming the fixture.
    sdf = tmp_path / "demo.sdf"
    sdf.write_text(sdf.read_text().replace("Register", name))
    SDFTimingGraph.__init__(model.hdlnx_tm_synth, sdf)
    bel.name = name
    bel.module_name = name
    expected_port = "O" if name == "Register" else "Q"
    assert (
        BelClockToOutTiming(expected_port, "CLK", 0.8, condition="FF=1")
        in model.bel_timing(bel).arcs
    )


def test_sky130_lc_and_iobuf_from_yosys_opensta() -> None:
    """Exercise real clock gating, escaped parameter modules, and external I/O.

    Fixtures were generated from fabulous-tiles commit
    53cc215ce5f7bdba3375d2cad7a0fc1ce35c1f7d's FABULOUS_LC and IOBUF, using
    OSS CAD Suite 20251210 (Yosys 0.60+15, OpenSTA 2.7.0) and Sky130 HD
    tt_025C_1v80. The wrapper exposes all primitive inputs/configuration bits.
    Synthesis uses the timing model's hierarchical synth/renames/clockgate/
    dfflibmap/splitnets/insbuf/abc sequence, followed by OpenSTA write_sdf.
    """
    fixtures = Path(__file__).parent / "fixtures"
    graph = VerilogGateLevelTimingGraph.__new__(VerilogGateLevelTimingGraph)
    SDFTimingGraph.__init__(graph, fixtures / "sky130_lc_iobuf.sdf")
    graph.top_name = "Top"
    graph.verilog_netlist_content = (fixtures / "sky130_lc_iobuf.v").read_text()
    model = make_model(graph)
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
    arcs = model.bel_timing(lc).arcs
    assert {arc.port for arc in arcs if isinstance(arc, BelSetupHoldTiming)} == {
        "I0",
        "I1",
        "I2",
        "I3",
        "Ci",
        "SR",
        "EN",
    }
    assert any(isinstance(arc, BelClockToOutTiming) and arc.port == "Q" for arc in arcs)
    assert any(isinstance(arc, BelDelayTiming) and arc.source == "I3" for arc in arcs)
    assert all(
        arc.condition is None
        for arc in arcs
        if isinstance(arc, BelDelayTiming) and arc.sink == "Co"
    )
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
    io_arcs = model.bel_timing(io).arcs
    assert {arc.port for arc in io_arcs if isinstance(arc, BelSetupHoldTiming)} == {
        "IN",
        "EN",
    }
    assert {arc.port for arc in io_arcs if isinstance(arc, BelClockToOutTiming)} == {
        "OUT"
    }
    assert {arc.condition for arc in io_arcs} == {
        None,
        "IN_REG=1",
        "EN_REG=1",
        "OUT_REG=1",
    }


def test_input_only_bel_aggregates_register_constraints(tmp_path: Path) -> None:
    bel = make_bel("InputOnly", {"D": (IO.INPUT, 1), "CLK": (IO.INPUT, 1)})
    netlist = """
module InputOnly (D, CLK);
    DFF first (.D(D), .CLK(CLK), .Q(first_q));
    DFF second (.D(D), .CLK(CLK), .Q(second_q));
endmodule
module Top (D, CLK);
    InputOnly Inst_A_InputOnly (.D(D), .CLK(CLK));
endmodule
"""
    graph = make_graph(
        tmp_path,
        netlist,
        [
            dff("Inst_A_InputOnly/first"),
            dff("Inst_A_InputOnly/second").replace("0.1:0.2:0.3", "0.6:0.7:0.8"),
        ],
        [],
    )
    assert make_model(graph).bel_timing(bel).arcs == (
        BelClockTiming("CLK"),
        BelSetupHoldTiming("D", "CLK", 0.8, 0.03),
    )


def test_independent_register_clocks_are_not_merged(tmp_path: Path) -> None:
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
    DFF first (.D(D_A), .CLK(CLK_A), .Q(Q_A));
    DFF second (.D(D_B), .CLK(CLK_B), .Q(Q_B));
endmodule
module Top (D_A, D_B, CLK_A, CLK_B, Q_A, Q_B);
    DualClock Inst_A_DualClock (.D_A(D_A), .D_B(D_B), .CLK_A(CLK_A),
      .CLK_B(CLK_B), .Q_A(Q_A), .Q_B(Q_B));
endmodule
"""
    graph = make_graph(
        tmp_path,
        netlist,
        [dff("Inst_A_DualClock/first"), dff("Inst_A_DualClock/second")],
        [],
    )
    arcs = make_model(graph).bel_timing(bel).arcs
    assert set(arcs) == {
        BelClockTiming("CLK_A"),
        BelClockTiming("CLK_B"),
        BelSetupHoldTiming("D_A", "CLK_A", 0.3, 0.03),
        BelSetupHoldTiming("D_B", "CLK_B", 0.3, 0.03),
        BelClockToOutTiming("Q_A", "CLK_A", 0.6),
        BelClockToOutTiming("Q_B", "CLK_B", 0.6),
    }
