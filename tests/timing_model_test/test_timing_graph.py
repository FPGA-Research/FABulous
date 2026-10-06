from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_model.hdlnx.sdfnx import timing_graph as tg
from fabulous.fabric_cad.timing_model.models import Component, DelayType, SDFCellType

# IN -> U1 (BUF) -> U2 (DFF) -> OUT, with rise/fall triple pairs, a single
# (nominal) triple, and a setup/hold check pair on the flip-flop.
SDF_TEXT = """(DELAYFILE
(SDFVERSION "3.0")
(DESIGN "top")
(DIVIDER /)
(TIMESCALE 1ns)
(CELL
 (CELLTYPE "top")
 (INSTANCE)
 (DELAY
  (ABSOLUTE
   (INTERCONNECT IN U1/A (0.010::0.020) (0.030::0.040))
   (INTERCONNECT U1/Y U2/D (0.050::0.060))
   (INTERCONNECT U2/Q OUT (0.070::0.080) (0.090::0.100))
  )
 )
)
(CELL
 (CELLTYPE "BUF_X1")
 (INSTANCE U1)
 (DELAY
  (ABSOLUTE
   (IOPATH A Y (0.100::0.200) (0.300::0.400))
  )
 )
)
(CELL
 (CELLTYPE "DFF_X1")
 (INSTANCE U2)
 (DELAY
  (ABSOLUTE
   (IOPATH (posedge CLK) Q (0.500::0.600) (0.700::0.800))
  )
 )
 (TIMINGCHECK
  (SETUP D (posedge CLK) (0.110::0.120))
  (HOLD D (posedge CLK) (0.130::0.140))
 )
)
)
"""


def _summary(component: Component) -> tuple[object, ...]:
    """Project a component onto the fields `parse_sdf` derives itself."""
    return (
        component.c_type,
        component.connection_string,
        component.cell_name,
        component.from_cell_instance,
        component.from_cell_pin,
        component.to_cell_instance,
        component.to_cell_pin,
        component.delay,
        component.is_one_cell_instance,
    )


@pytest.fixture
def sdf_file(tmp_path: Path) -> Path:
    path = tmp_path / "top.sdf"
    path.write_text(SDF_TEXT)
    return path


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
def test_delay_type_all_modes_without_nominal(
    kind: DelayType,
    expected: float,
) -> None:
    delay_paths = {
        "fast": {"min": 1.0, "max": 2.0},
        "slow": {"min": 3.0, "max": 4.0},
    }
    assert tg.delay_type(delay_paths, kind) == expected


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (DelayType.MAX_ALL, 8.0),
        (DelayType.MIN_ALL, 2.0),
        (DelayType.AVG_ALL, 5.0),
        (DelayType.MIN_FAST, 2.0),
        (DelayType.MAX_SLOW, 8.0),
    ],
)
def test_delay_type_nominal_overrides_fast_and_slow(
    kind: DelayType, expected: float
) -> None:
    delay_paths = {
        "nominal": {"min": 2.0, "max": 8.0},
        "fast": {"min": 100.0, "max": 200.0},
        "slow": {"min": 300.0, "max": 400.0},
    }
    assert tg.delay_type(delay_paths, kind) == expected


def test_delay_type_missing_values_are_treated_as_zero() -> None:
    delay_paths = {
        "fast": {"min": None, "max": 1.5},
        "slow": {"min": 2.5, "max": None},
    }
    assert tg.delay_type(delay_paths, DelayType.MIN_ALL) == 0.0
    assert tg.delay_type(delay_paths, DelayType.MAX_ALL) == 2.5
    assert tg.delay_type(delay_paths, DelayType.AVG_ALL) == 1.0


def test_delay_type_unknown_kind_raises_value_error() -> None:
    delay_paths = {
        "fast": {"min": 1.0, "max": 2.0},
        "slow": {"min": 3.0, "max": 4.0},
    }
    with pytest.raises(ValueError, match="Unknown delay type"):
        tg.delay_type(delay_paths, "not-a-delay-type")


def test_split_instance_pin_with_hierarchy() -> None:
    assert tg.split_instance_pin("_2988_/Q", "/") == ("_2988_", "Q")
    assert tg.split_instance_pin("top|u1|A", "|") == ("top|u1", "A")


def test_split_instance_pin_without_hierarchy() -> None:
    assert tg.split_instance_pin("CLK", "/") == ("", "CLK")


def test_parse_sdf_extracts_header_cells_instances_and_components(
    sdf_file: Path,
) -> None:
    result = tg.parse_sdf(sdf_file, DelayType.MAX_ALL)

    assert result.hier_sep == "/"
    assert result.header_info == {
        "sdfversion": "3.0",
        "design": "top",
        "divider": "/",
        "timescale": "1ns",
    }
    assert result.cells == ["top", "BUF_X1", "DFF_X1"]
    assert result.nx_graph.number_of_edges() == 0

    iopath, wire = SDFCellType.IOPATH, SDFCellType.INTERCONNECT
    assert [_summary(c) for c in result.io_paths] == [
        (iopath, "iopath_A_Y", "BUF_X1", "U1", "A", "U1", "Y", 0.4, True),
        (iopath, "iopath_CLK_Q", "DFF_X1", "U2", "CLK", "U2", "Q", 0.8, True),
        # setup and hold each become a zero-delay D -> CLK arc
        (iopath, "CLK_D", "DFF_X1", "U2", "D", "U2", "CLK", 0.0, True),
        (iopath, "CLK_D", "DFF_X1", "U2", "D", "U2", "CLK", 0.0, True),
    ]
    assert [_summary(c) for c in result.interconnects] == [
        (wire, "interconnect_IN_U1/A", "top", "", "IN", "U1", "A", 0.04, False),
        (wire, "interconnect_U1/Y_U2/D", "top", "U1", "Y", "U2", "D", 0.06, False),
        (wire, "interconnect_U2/Q_OUT", "top", "U2", "Q", "", "OUT", 0.1, False),
    ]
    assert {
        name: [_summary(c) for c in comps] for name, comps in result.instances.items()
    } == {
        "U1": [(iopath, "iopath_A_Y", "BUF_X1", "U1", "A", "U1", "Y", 0.4, True)],
        "U2": [
            (iopath, "iopath_CLK_Q", "DFF_X1", "U2", "CLK", "U2", "Q", 0.8, True),
            (
                SDFCellType.SETUP,
                "setup_CLK_D",
                "DFF_X1",
                "U2",
                "CLK",
                "U2",
                "D",
                0.12,
                True,
            ),
            (
                SDFCellType.HOLD,
                "hold_CLK_D",
                "DFF_X1",
                "U2",
                "CLK",
                "U2",
                "D",
                0.14,
                True,
            ),
        ],
    }
    # the synthesised arc carries the check's flags but no delay data of its own
    setup_arc = result.io_paths[2]
    assert setup_arc.delay_paths is None
    assert setup_arc.is_timing_check is True
    assert setup_arc.is_absolute is False
    assert setup_arc.from_pin_edge is None
    assert result.io_paths[1].from_pin_edge == "posedge"


def test_parse_sdf_defaults_to_slash_when_header_has_no_divider(
    tmp_path: Path,
) -> None:
    sdf_file = tmp_path / "no_divider.sdf"
    sdf_file.write_text(
        '(DELAYFILE (SDFVERSION "3.0") (DESIGN "top")\n'
        '(CELL (CELLTYPE "INV_X1") (INSTANCE U3)\n'
        " (DELAY (ABSOLUTE (IOPATH A Y (0.9::1.1) (1.2::1.4))))))\n"
    )

    result = tg.parse_sdf(sdf_file, DelayType.MIN_FAST)

    assert result.hier_sep == "/"
    assert "divider" not in result.header_info
    assert [_summary(c) for c in result.io_paths] == [
        (SDFCellType.IOPATH, "iopath_A_Y", "INV_X1", "U3", "A", "U3", "Y", 0.9, True)
    ]
    assert result.interconnects == []


def test_gen_timing_digraph_builds_expected_edges_and_attributes(
    sdf_file: Path,
) -> None:
    result = tg.gen_timing_digraph(sdf_file, DelayType.MAX_ALL)

    assert sorted(result.nx_graph.edges(data="weight")) == [
        ("IN", "U1/A", 0.04),
        ("U1/A", "U1/Y", 0.4),
        ("U1/Y", "U2/D", 0.06),
        ("U2/CLK", "U2/Q", 0.8),
        ("U2/D", "U2/CLK", 0.0),
        ("U2/Q", "OUT", 0.1),
    ]
    edge_components = {
        (u, v): component for u, v, component in result.nx_graph.edges(data="component")
    }
    assert edge_components[("U1/A", "U1/Y")] is result.io_paths[0]
    assert edge_components[("U1/Y", "U2/D")] is result.interconnects[1]


def test_gen_timing_digraph_uses_header_separator_for_node_names(
    tmp_path: Path,
) -> None:
    sdf_file = tmp_path / "dot_divider.sdf"
    sdf_file.write_text(
        SDF_TEXT.replace("(DIVIDER /)", "(DIVIDER .)")
        .replace("U1/", "U1.")
        .replace("U2/", "U2.")
    )

    result = tg.gen_timing_digraph(sdf_file, DelayType.MAX_ALL)

    assert result.hier_sep == "."
    assert sorted(result.nx_graph.edges) == [
        ("IN", "U1.A"),
        ("U1.A", "U1.Y"),
        ("U1.Y", "U2.D"),
        ("U2.CLK", "U2.Q"),
        ("U2.D", "U2.CLK"),
        ("U2.Q", "OUT"),
    ]
