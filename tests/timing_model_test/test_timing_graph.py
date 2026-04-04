from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_model.hdlnx.sdfnx import timing_graph as tg
from fabulous.fabric_cad.timing_model.models import DelayType, SDFCellType


def make_component_data(
    *,
    ctype: str,
    from_pin: str,
    to_pin: str,
    delay_paths: dict,
    is_timing_check: bool = False,
    is_timing_env: bool = False,
    is_absolute: bool = True,
    is_incremental: bool = False,
    is_cond: bool = False,
    cond_equation: str | None = None,
    from_pin_edge: str | None = None,
    to_pin_edge: str | None = None,
):
    return {
        "type": ctype,
        "from_pin": from_pin,
        "to_pin": to_pin,
        "delay_paths": delay_paths,
        "is_timing_check": is_timing_check,
        "is_timing_env": is_timing_env,
        "is_absolute": is_absolute,
        "is_incremental": is_incremental,
        "is_cond": is_cond,
        "cond_equation": cond_equation,
        "from_pin_edge": from_pin_edge,
        "to_pin_edge": to_pin_edge,
    }


def fake_sdf_data_with_divider():
    return {
        "header": {"divider": "/"},
        "cells": {
            "BUF_X1": {
                "U1": {
                    "IOPATH A Y": make_component_data(
                        ctype="iopath",
                        from_pin="A",
                        to_pin="Y",
                        delay_paths={
                            "fast": {"min": 1.0, "max": 2.0},
                            "slow": {"min": 3.0, "max": 4.0},
                        },
                        is_absolute=True,
                    ),
                    "INTERCONNECT U1/Y U2/A": make_component_data(
                        ctype="interconnect",
                        from_pin="U1/Y",
                        to_pin="U2/A",
                        delay_paths={
                            "fast": {"min": 0.1, "max": 0.2},
                            "slow": {"min": 0.3, "max": 0.4},
                        },
                        is_incremental=True,
                    ),
                }
            },
            "DFF_X1": {
                "U2": {
                    "IOPATH D Q": make_component_data(
                        ctype="iopath",
                        from_pin="D",
                        to_pin="Q",
                        delay_paths={
                            "nominal": {"min": 5.0, "max": 7.5},
                        },
                        is_timing_check=False,
                    ),
                    "INTERCONNECT U2/Q OUT": make_component_data(
                        ctype="interconnect",
                        from_pin="U2/Q",
                        to_pin="OUT",
                        delay_paths={
                            "fast": {"min": None, "max": 0.6},
                            "slow": {"min": 0.7, "max": None},
                        },
                        is_cond=True,
                        cond_equation="EN == 1'b1",
                    ),
                }
            },
        },
    }


def fake_sdf_data_without_divider():
    return {
        "header": {},
        "cells": {
            "INV_X1": {
                "U3": {
                    "IOPATH A Y": make_component_data(
                        ctype="iopath",
                        from_pin="A",
                        to_pin="Y",
                        delay_paths={
                            "fast": {"min": 0.9, "max": 1.1},
                            "slow": {"min": 1.2, "max": 1.4},
                        },
                    )
                }
            }
        },
    }


def test_as_float_none_uses_default():
    assert tg._as_float(None) == 0.0
    assert tg._as_float(None, default=2.5) == 2.5


def test_as_float_converts_numeric_values():
    assert tg._as_float(3) == 3.0
    assert tg._as_float(4.25) == 4.25


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (DelayType.MIN_ALL, 1.0),
        (DelayType.MAX_ALL, 4.0),
        (DelayType.AVG_ALL, 2.5),
        (DelayType.AVG_FAST, 1.5),
        (DelayType.AVG_SLOW, 3.5),
        (DelayType.MAX_FAST, 2.0),
        (DelayType.MAX_SLOW, 4.0),
        (DelayType.MIN_FAST, 1.0),
        (DelayType.MIN_SLOW, 3.0),
    ],
)
def test_delay_type_all_modes_without_nominal(kind, expected):
    delay_paths = {
        "fast": {"min": 1.0, "max": 2.0},
        "slow": {"min": 3.0, "max": 4.0},
    }
    assert tg.delay_type(delay_paths, kind) == expected


def test_delay_type_nominal_shortcut_uses_max_of_nominal_min_and_max():
    delay_paths = {
        "nominal": {"min": 2.0, "max": 8.0},
        "fast": {"min": 100.0, "max": 200.0},
        "slow": {"min": 300.0, "max": 400.0},
    }
    assert tg.delay_type(delay_paths, DelayType.MIN_ALL) == 8.0
    assert tg.delay_type(delay_paths, DelayType.MAX_ALL) == 8.0


def test_delay_type_missing_values_are_treated_as_zero():
    delay_paths = {
        "fast": {"min": None, "max": 1.5},
        "slow": {"min": 2.5, "max": None},
    }
    assert tg.delay_type(delay_paths, DelayType.MIN_ALL) == 0.0
    assert tg.delay_type(delay_paths, DelayType.MAX_ALL) == 2.5
    assert tg.delay_type(delay_paths, DelayType.AVG_ALL) == (0.0 + 1.5 + 2.5 + 0.0) / 4.0


def test_delay_type_unknown_kind_raises_value_error():
    delay_paths = {
        "fast": {"min": 1.0, "max": 2.0},
        "slow": {"min": 3.0, "max": 4.0},
    }
    with pytest.raises(ValueError, match="Unknown delay type"):
        tg.delay_type(delay_paths, "not-a-delay-type")


def test_split_instance_pin_with_hierarchy():
    assert tg.split_instance_pin("_2988_/Q", "/") == ("_2988_", "Q")
    assert tg.split_instance_pin("top|u1|A", "|") == ("top|u1", "A")


def test_split_instance_pin_without_hierarchy():
    assert tg.split_instance_pin("CLK", "/") == ("", "CLK")


def test_parse_sdf_extracts_header_cells_instances_and_components(tmp_path, monkeypatch):
    sdf_file = tmp_path / "test.sdf"
    sdf_file.write_text("dummy sdf content")

    monkeypatch.setattr(tg.sdfparse, "parse", lambda text: fake_sdf_data_with_divider())

    result = tg.parse_sdf(sdf_file, DelayType.MAX_ALL)

    assert result.hier_sep == "/"
    assert result.header_info == {"divider": "/"}
    assert result.sdf_data == fake_sdf_data_with_divider()
    assert result.cells == ["BUF_X1", "DFF_X1"]

    assert set(result.instances.keys()) == {"U1", "U2"}
    assert len(result.io_paths) == 2
    assert len(result.interconnects) == 2
    assert result.nx_graph.number_of_nodes() == 0
    assert result.nx_graph.number_of_edges() == 0

    iopath_u1 = result.io_paths[0]
    assert iopath_u1.c_type == SDFCellType.IOPATH
    assert iopath_u1.cell_name == "BUF_X1"
    assert iopath_u1.connection_string == "IOPATH A Y"
    assert iopath_u1.from_cell_instance == "U1"
    assert iopath_u1.to_cell_instance == "U1"
    assert iopath_u1.from_cell_pin == "A"
    assert iopath_u1.to_cell_pin == "Y"
    assert iopath_u1.delay == 4.0
    assert iopath_u1.is_one_cell_instance is True
    assert iopath_u1.is_timing_check is False
    assert iopath_u1.is_timing_env is False
    assert iopath_u1.is_absolute is True
    assert iopath_u1.is_incremental is False
    assert iopath_u1.is_cond is False
    assert iopath_u1.cond_equation is None

    inter_u1_u2 = result.interconnects[0]
    assert inter_u1_u2.c_type == SDFCellType.INTERCONNECT
    assert inter_u1_u2.cell_name == "BUF_X1"
    assert inter_u1_u2.from_cell_instance == "U1"
    assert inter_u1_u2.to_cell_instance == "U2"
    assert inter_u1_u2.from_cell_pin == "Y"
    assert inter_u1_u2.to_cell_pin == "A"
    assert inter_u1_u2.delay == 0.4
    assert inter_u1_u2.is_one_cell_instance is False
    assert inter_u1_u2.is_incremental is True

    inter_u2_out = result.interconnects[1]
    assert inter_u2_out.from_cell_instance == "U2"
    assert inter_u2_out.to_cell_instance == ""
    assert inter_u2_out.from_cell_pin == "Q"
    assert inter_u2_out.to_cell_pin == "OUT"
    assert inter_u2_out.delay == 0.7
    assert inter_u2_out.is_cond is True
    assert inter_u2_out.cond_equation == "EN == 1'b1"

    assert len(result.instances["U1"]) == 1
    assert len(result.instances["U2"]) == 1
    assert result.instances["U1"][0].c_type == SDFCellType.IOPATH
    assert result.instances["U2"][0].c_type == SDFCellType.IOPATH
    assert result.instances["U2"][0].delay == 7.5


def test_parse_sdf_defaults_to_slash_when_header_has_no_divider(tmp_path, monkeypatch):
    sdf_file = tmp_path / "test_no_divider.sdf"
    sdf_file.write_text("dummy sdf content")

    monkeypatch.setattr(tg.sdfparse, "parse", lambda text: fake_sdf_data_without_divider())

    result = tg.parse_sdf(sdf_file, DelayType.MIN_FAST)

    assert result.hier_sep == "/"
    assert result.header_info == {}
    assert result.cells == ["INV_X1"]
    assert list(result.instances.keys()) == ["U3"]
    assert len(result.io_paths) == 1
    assert len(result.interconnects) == 0
    assert result.io_paths[0].delay == 0.9


def test_gen_timing_digraph_builds_expected_edges_and_attributes(tmp_path, monkeypatch):
    sdf_file = tmp_path / "graph.sdf"
    sdf_file.write_text("dummy sdf content")

    monkeypatch.setattr(tg.sdfparse, "parse", lambda text: fake_sdf_data_with_divider())

    result = tg.gen_timing_digraph(sdf_file, DelayType.MAX_ALL)

    graph = result.nx_graph

    assert isinstance(graph, tg.nx.DiGraph)
    assert graph.number_of_edges() == 4

    assert graph.has_edge("U1/A", "U1/Y")
    assert graph.has_edge("U1/Y", "U2/A")
    assert graph.has_edge("U2/D", "U2/Q")
    assert graph.has_edge("U2/Q", "OUT")

    edge_u1_iopath = graph["U1/A"]["U1/Y"]
    assert edge_u1_iopath["weight"] == 4.0
    assert edge_u1_iopath["component"].c_type == SDFCellType.IOPATH
    assert edge_u1_iopath["component"].connection_string == "IOPATH A Y"

    edge_inter = graph["U1/Y"]["U2/A"]
    assert edge_inter["weight"] == 0.4
    assert edge_inter["component"].c_type == SDFCellType.INTERCONNECT
    assert edge_inter["component"].from_cell_instance == "U1"
    assert edge_inter["component"].to_cell_instance == "U2"

    edge_u2_iopath = graph["U2/D"]["U2/Q"]
    assert edge_u2_iopath["weight"] == 7.5

    edge_out = graph["U2/Q"]["OUT"]
    assert edge_out["weight"] == 0.7
    assert edge_out["component"].to_cell_instance == ""


def test_gen_timing_digraph_uses_header_separator_for_node_names(tmp_path, monkeypatch):
    sdf_file = tmp_path / "graph_sep.sdf"
    sdf_file.write_text("dummy sdf content")

    data = {
        "header": {"divider": "|"},
        "cells": {
            "BUF_X1": {
                "U1": {
                    "IOPATH A Y": make_component_data(
                        ctype="iopath",
                        from_pin="A",
                        to_pin="Y",
                        delay_paths={"fast": {"min": 1.0, "max": 2.0}, "slow": {"min": 3.0, "max": 4.0}},
                    ),
                    "INTERCONNECT U1|Y U2|A": make_component_data(
                        ctype="interconnect",
                        from_pin="U1|Y",
                        to_pin="U2|A",
                        delay_paths={"fast": {"min": 0.1, "max": 0.2}, "slow": {"min": 0.3, "max": 0.4}},
                    ),
                }
            }
        },
    }

    monkeypatch.setattr(tg.sdfparse, "parse", lambda text: data)

    result = tg.gen_timing_digraph(sdf_file, DelayType.MAX_ALL)

    assert result.hier_sep == "|"
    assert result.nx_graph.has_edge("U1|A", "U1|Y")
    assert result.nx_graph.has_edge("U1|Y", "U2|A")