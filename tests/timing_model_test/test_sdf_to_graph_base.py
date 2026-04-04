from pathlib import Path

import networkx as nx
import pytest

import fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base as base_mod
from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base import SDFTimingGraphBase
from fabulous.fabric_cad.timing_model.models import (
    Component,
    DelayType,
    SDFCellType,
    SDFGobject,
)


def make_component(
    *,
    c_type: SDFCellType,
    cell_name: str,
    connection_string: str,
    from_cell_instance: str,
    to_cell_instance: str,
    from_cell_pin: str,
    to_cell_pin: str,
    delay: float,
):
    return Component(
        c_type=c_type,
        cell_name=cell_name,
        connection_string=connection_string,
        from_cell_instance=from_cell_instance,
        to_cell_instance=to_cell_instance,
        from_cell_pin=from_cell_pin,
        to_cell_pin=to_cell_pin,
        delay=delay,
        delay_paths={"fast": {"min": delay, "max": delay}},
        is_one_cell_instance=(from_cell_instance == to_cell_instance),
        is_timing_check=False,
        is_timing_env=False,
        is_absolute=True,
        is_incremental=False,
        is_cond=False,
        cond_equation=None,
        from_pin_edge=None,
        to_pin_edge=None,
    )


@pytest.fixture
def fake_sdf_graph_object():
    graph = nx.DiGraph()

    comp_in_u1 = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="INTERCONNECT IN U1/A",
        from_cell_instance="",
        to_cell_instance="U1",
        from_cell_pin="IN",
        to_cell_pin="A",
        delay=0.1,
    )
    comp_u1_iopath = make_component(
        c_type=SDFCellType.IOPATH,
        cell_name="BUF_X1",
        connection_string="IOPATH A Y",
        from_cell_instance="U1",
        to_cell_instance="U1",
        from_cell_pin="A",
        to_cell_pin="Y",
        delay=0.2,
    )
    comp_u1_hold = make_component(
        c_type=SDFCellType.HOLD,
        cell_name="BUF_X1",
        connection_string="HOLD A Y",
        from_cell_instance="U1",
        to_cell_instance="U1",
        from_cell_pin="A",
        to_cell_pin="Y",
        delay=0.3,
    )
    comp_u1_u2 = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="INTERCONNECT U1/Y U2/B",
        from_cell_instance="U1",
        to_cell_instance="U2",
        from_cell_pin="Y",
        to_cell_pin="B",
        delay=0.4,
    )
    comp_u2_iopath = make_component(
        c_type=SDFCellType.IOPATH,
        cell_name="INV_X1",
        connection_string="IOPATH B Z",
        from_cell_instance="U2",
        to_cell_instance="U2",
        from_cell_pin="B",
        to_cell_pin="Z",
        delay=0.5,
    )
    comp_u2_out = make_component(
        c_type=SDFCellType.INTERCONNECT,
        cell_name="TOP",
        connection_string="INTERCONNECT U2/Z OUT",
        from_cell_instance="U2",
        to_cell_instance="",
        from_cell_pin="Z",
        to_cell_pin="OUT",
        delay=0.6,
    )

    graph.add_edge("IN", "U1/A", weight=0.1, component=comp_in_u1)
    graph.add_edge("U1/A", "U1/Y", weight=0.2, component=comp_u1_iopath)
    graph.add_edge("U1/Y", "U2/B", weight=0.4, component=comp_u1_u2)
    graph.add_edge("U2/B", "U2/Z", weight=0.5, component=comp_u2_iopath)
    graph.add_edge("U2/Z", "OUT", weight=0.6, component=comp_u2_out)

    instances = {
        "U1": [comp_u1_iopath, comp_u1_hold],
        "U2": [comp_u2_iopath],
    }

    return SDFGobject(
        nx_graph=graph,
        hier_sep="/",
        header_info={"divider": "/", "timescale": "1ns"},
        sdf_data={"header": {"divider": "/"}, "cells": {"BUF_X1": {}, "INV_X1": {}}},
        cells=["BUF_X1", "INV_X1"],
        instances=instances,
        io_paths=[comp_u1_iopath, comp_u2_iopath],
        interconnects=[comp_in_u1, comp_u1_u2, comp_u2_out],
    )


@pytest.fixture
def sdf_base(tmp_path, fake_sdf_graph_object, monkeypatch):
    sdf_file = tmp_path / "dummy.sdf"
    sdf_file.write_text("dummy sdf file content")

    def fake_gen_timing_digraph(path, delay_type):
        assert path == sdf_file
        assert delay_type == DelayType.MAX_ALL
        return fake_sdf_graph_object

    monkeypatch.setattr(base_mod, "gen_timing_digraph", fake_gen_timing_digraph)

    return SDFTimingGraphBase(sdf_file, DelayType.MAX_ALL)


def test_init_populates_attributes_from_sdf_object(sdf_base, fake_sdf_graph_object):
    assert sdf_base.sdf_file.name == "dummy.sdf"
    assert sdf_base.sdf_file_content == "dummy sdf file content"
    assert sdf_base.delay_type_str == DelayType.MAX_ALL
    assert sdf_base.sdf_gobject is fake_sdf_graph_object

    assert sdf_base.graph is fake_sdf_graph_object.nx_graph
    assert isinstance(sdf_base.reverse_graph, nx.DiGraph)
    assert sdf_base.reverse_graph.has_edge("U1/A", "IN")
    assert sdf_base.reverse_graph.has_edge("U1/Y", "U1/A")

    assert sdf_base.header_info == {"divider": "/", "timescale": "1ns"}
    assert sdf_base.sdf_data_dict == {"header": {"divider": "/"}, "cells": {"BUF_X1": {}, "INV_X1": {}}}
    assert sdf_base.cells == ["BUF_X1", "INV_X1"]
    assert sdf_base.instances == fake_sdf_graph_object.instances
    assert sdf_base.io_paths == fake_sdf_graph_object.io_paths
    assert sdf_base.interconnects == fake_sdf_graph_object.interconnects
    assert sdf_base.hier_sep == "/"


def test_init_detects_input_and_output_ports(sdf_base):
    assert set(sdf_base.input_ports) == {"IN"}
    assert set(sdf_base.output_ports) == {"OUT"}


def test_get_input_and_output_ports_property(sdf_base):
    ports = sdf_base.get_input_and_output_ports
    assert set(ports) == {"IN", "OUT"}


def test_get_sdf_header_info_property(sdf_base):
    header_dict, header_str = sdf_base.get_SDF_header_info

    assert header_dict == {"divider": "/", "timescale": "1ns"}
    assert "divider: /" in header_str
    assert "timescale: 1ns" in header_str


def test_get_cell_instance_returns_components_for_instance(sdf_base):
    comps = sdf_base.get_cell_instance_components("U1")

    assert len(comps) == 2
    assert comps[0].c_type == SDFCellType.IOPATH
    assert comps[1].c_type == SDFCellType.HOLD


def test_get_cell_instance_missing_instance_raises_keyerror(sdf_base):
    with pytest.raises(KeyError):
        sdf_base.get_cell_instance_components("NO_SUCH_INSTANCE")


def test_get_cell_instance_inputs_to_outputs_for_existing_instance(sdf_base):
    input_pins, output_pins = sdf_base.get_cell_instance_input_and_output_pins("U1")

    assert input_pins == ["A"]
    assert output_pins == ["Y"]


def test_get_cell_instance_inputs_to_outputs_ignores_non_iopath_components(sdf_base):
    input_pins, output_pins = sdf_base.get_cell_instance_input_and_output_pins("U1")

    assert "A" in input_pins
    assert "Y" in output_pins
    assert len(input_pins) == 1
    assert len(output_pins) == 1


def test_get_cell_instance_inputs_to_outputs_missing_instance_returns_empty_and_prints(
    sdf_base, capsys
):
    input_pins, output_pins = sdf_base.get_cell_instance_input_and_output_pins("NO_SUCH_INSTANCE")
    out = capsys.readouterr().out

    assert input_pins == []
    assert output_pins == []


def test_get_cell_instance_component_by_type_returns_matching_component(sdf_base):
    comp = sdf_base.get_cell_instance_component_by_type(
        "U1", SDFCellType.IOPATH, "A", "Y"
    )

    assert comp is not None
    assert comp.c_type == SDFCellType.IOPATH
    assert comp.cell_name == "BUF_X1"
    assert comp.from_cell_pin == "A"
    assert comp.to_cell_pin == "Y"
    assert comp.delay == 0.2


def test_get_cell_instance_component_by_type_returns_none_if_no_match(sdf_base):
    comp = sdf_base.get_cell_instance_component_by_type(
        "U1", SDFCellType.SETUP, "A", "Y"
    )

    assert comp is None


def test_get_cell_instance_component_by_type_can_find_non_iopath_component(sdf_base):
    comp = sdf_base.get_cell_instance_component_by_type(
        "U1", SDFCellType.HOLD, "A", "Y"
    )

    assert comp is not None
    assert comp.c_type == SDFCellType.HOLD
    assert comp.delay == 0.3


def test_get_cell_instance_component_by_type_missing_instance_raises_keyerror(sdf_base):
    with pytest.raises(KeyError, match="Instance NO_SUCH_INSTANCE not found in SDF instances."):
        sdf_base.get_cell_instance_component_by_type(
            "NO_SUCH_INSTANCE", SDFCellType.IOPATH, "A", "Y"
        )


def test_init_with_graph_having_only_hierarchical_nodes_has_no_top_level_ports(tmp_path, monkeypatch):
    graph = nx.DiGraph()

    comp = make_component(
        c_type=SDFCellType.IOPATH,
        cell_name="BUF_X1",
        connection_string="IOPATH A Y",
        from_cell_instance="U1",
        to_cell_instance="U1",
        from_cell_pin="A",
        to_cell_pin="Y",
        delay=0.2,
    )
    graph.add_edge("U1/A", "U1/Y", weight=0.2, component=comp)

    sdf_gobject = SDFGobject(
        nx_graph=graph,
        hier_sep="/",
        header_info={},
        sdf_data={},
        cells=["BUF_X1"],
        instances={"U1": [comp]},
        io_paths=[comp],
        interconnects=[],
    )

    sdf_file = tmp_path / "only_hier.sdf"
    sdf_file.write_text("content")

    monkeypatch.setattr(base_mod, "gen_timing_digraph", lambda path, delay: sdf_gobject)

    obj = SDFTimingGraphBase(sdf_file, DelayType.MAX_ALL)

    assert obj.input_ports == []
    assert obj.output_ports == []
    assert obj.get_input_and_output_ports == []