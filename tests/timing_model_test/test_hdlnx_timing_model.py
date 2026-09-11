"""Tests for how the timing-graph classes drive the shared tool wrappers.

`VerilogGateLevelTimingGraph` turns an existing netlist into a graph, so it
only runs OpenSTA. `HdlnxTimingModel` starts from RTL, so it synthesizes first
and owns the netlist it created. Both delete only the temporaries they made.
"""

from pathlib import Path

import networkx as nx
import pytest
from pytest_mock import MockerFixture

import fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base as base_mod
from fabulous.fabric_cad.timing_model.hdlnx.hdlnx_timing_model import HdlnxTimingModel
from fabulous.fabric_cad.timing_model.hdlnx.verilog_gate_level import (
    VerilogGateLevelTimingGraph,
)
from fabulous.fabric_cad.timing_model.models import SDFGobject
from fabulous.tools.opensta import OpenStaTool
from fabulous.tools.yosys import YosysTool


@pytest.fixture
def stub_sdf_parse(mocker: MockerFixture) -> None:
    """Replace the SDF parser so the tests need no parseable SDF text."""
    mocker.patch.object(
        base_mod,
        "gen_timing_digraph",
        return_value=SDFGobject(
            nx_graph=nx.DiGraph(),
            hier_sep="/",
            header_info={},
            sdf_data={},
            cells=[],
            instances={},
            io_paths=[],
            interconnects=[],
        ),
    )


@pytest.fixture
def sdf_file(tmp_path: Path) -> Path:
    sdf = tmp_path / "out.sdf"
    sdf.write_text("(DELAYFILE)")
    return sdf


@pytest.mark.usefixtures("stub_sdf_parse")
def test_gate_level_graph_analyzes_netlist_and_drops_only_the_sdf(
    mocker: MockerFixture, tmp_path: Path, sdf_file: Path
) -> None:
    netlist = tmp_path / "TOP.nl.v"
    netlist.write_text("module TOP(); endmodule")
    liberty = tmp_path / "x.lib"
    spef = tmp_path / "TOP.nom.spef"
    analyze = mocker.patch.object(OpenStaTool, "analyze", return_value=sdf_file)
    sta_clean_up = mocker.patch.object(OpenStaTool, "clean_up")
    synthesize = mocker.patch.object(YosysTool, "synthesize_to_netlist")

    graph = VerilogGateLevelTimingGraph(
        top_name="TOP",
        netlist_file=netlist,
        liberty_files=liberty,
        spef_files=spef,
    )

    synthesize.assert_not_called()
    assert analyze.call_args.kwargs == {
        "verilog_netlist": netlist,
        "liberty_files": liberty,
        "top_name": "TOP",
        "spef_files": spef,
    }
    sta_clean_up.assert_called_once_with(sdf_file)
    assert netlist.exists()
    assert graph.get_raw_verilog_netlist_data() == "module TOP(); endmodule"


@pytest.mark.usefixtures("stub_sdf_parse")
def test_hdlnx_synthesizes_rtl_then_drops_its_own_netlist(
    mocker: MockerFixture, tmp_path: Path, sdf_file: Path
) -> None:
    rtl = [tmp_path / "a.v", tmp_path / "b.v"]
    liberty = tmp_path / "x.lib"
    netlist = tmp_path / "synth_TOP_tmp.v"
    netlist.write_text("module TOP(); endmodule")
    synthesize = mocker.patch.object(
        YosysTool, "synthesize_to_netlist", return_value=netlist
    )
    synth_clean_up = mocker.patch.object(YosysTool, "clean_up")
    mocker.patch.object(OpenStaTool, "analyze", return_value=sdf_file)
    mocker.patch.object(OpenStaTool, "clean_up")

    HdlnxTimingModel(
        top_name="TOP",
        verilog_files=rtl,
        liberty_files=liberty,
        techmap_files=[tmp_path / "tm.v"],
        min_buf_cell_and_ports="BUF A Y",
    )

    assert synthesize.call_args.kwargs == {
        "verilog_files": rtl,
        "liberty_files": liberty,
        "top_name": "TOP",
        "techmap_files": [tmp_path / "tm.v"],
        "tiehi_cell_and_port": None,
        "tielo_cell_and_port": None,
        "min_buf_cell_and_ports": "BUF A Y",
        "flat": False,
    }
    synth_clean_up.assert_called_once_with(netlist)


@pytest.mark.usefixtures("stub_sdf_parse")
def test_hdlnx_drops_its_netlist_when_analysis_fails(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    netlist = tmp_path / "synth_TOP_tmp.v"
    netlist.write_text("module TOP(); endmodule")
    mocker.patch.object(YosysTool, "synthesize_to_netlist", return_value=netlist)
    synth_clean_up = mocker.patch.object(YosysTool, "clean_up")
    mocker.patch.object(OpenStaTool, "analyze", side_effect=RuntimeError("sta died"))

    with pytest.raises(RuntimeError, match="sta died"):
        HdlnxTimingModel(
            top_name="TOP",
            verilog_files=[tmp_path / "a.v"],
            liberty_files=tmp_path / "x.lib",
        )

    synth_clean_up.assert_called_once_with(netlist)
