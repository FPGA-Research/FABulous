"""The Python half of the antenna pre-check: spans in, verdicts out.

The measurement lives in `script/odb_antenna_precheck.py`, which asks OpenROAD's
own antenna checker. What stays here is the part OpenROAD cannot do for itself:
working out how far each declared wire travels, and turning the resulting JSON
into something the flow can act on.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import Port
from fabulous.fabric_generator.gds_generator.steps.antenna_precheck import (
    FABulousAntennaPrecheck,
    FABulousAntennaPrecheckChecker,
    diode_targets,
    parse_summary,
    wire_spans,
)
from tests.conftest import make_empty_tile

FABRIC_ROWS = 10
FABRIC_COLS = 4
LONG_WIRE_PORT = "N10BEG"


@pytest.fixture
def long_wire_port() -> Port:
    """The long wire declared with a span of `FABRIC_ROWS` tiles."""
    return Port(
        wireDirection=Direction.NORTH,
        sourceName=LONG_WIRE_PORT,
        xOffset=0,
        yOffset=FABRIC_ROWS,
        destinationName="N10END",
        wireCount=24,
        name=LONG_WIRE_PORT,
        inOut=IO.OUTPUT,
        sideOfTile=Side.NORTH,
    )


@pytest.fixture
def fabric(long_wire_port: Port) -> Fabric:
    """A fabric holding just the terminator tile type."""
    tile = make_empty_tile("TERM", ports=[long_wire_port])
    return Fabric(
        fabric_dir=Path(),
        tile=[],
        numberOfRows=FABRIC_ROWS,
        numberOfColumns=FABRIC_COLS,
        tileDic={"TERM": tile},
    )


@pytest.fixture
def summary_file(tmp_path: Path) -> Path:
    """A predicted-violation summary as the ODB script writes it."""
    records = [
        {
            "net": f"{LONG_WIRE_PORT}[3]",
            "span": 10,
            "layer": "Metal3",
            "predicted_headroom": 4.38,
            "targets": ["_013_/I"],
        },
        {
            "net": f"{LONG_WIRE_PORT}[3]",
            "span": 10,
            "layer": "Metal2",
            "predicted_headroom": 1.02,
            "targets": ["_013_/I"],
        },
        {
            "net": "FrameStrobe[1]",
            "span": 4,
            "layer": "Metal3",
            "predicted_headroom": 2.11,
            "targets": ["_027_/I", "_031_/A"],
        },
    ]
    path = tmp_path / "antenna_precheck.json"
    path.write_text(json.dumps(records))
    return path


def test_wire_spans_covers_the_ports_and_the_config_buses(fabric: Fabric) -> None:
    """Every declared name the checker could meet must carry its own span."""
    spans = wire_spans(fabric, fabric.tileDic["TERM"])

    assert spans[LONG_WIRE_PORT] == FABRIC_ROWS
    assert spans["N10END"] == FABRIC_ROWS
    assert spans["FrameData"] == FABRIC_COLS, "config data runs along a row"
    assert spans["FrameStrobe"] == FABRIC_ROWS, "config strobe runs down a column"
    assert list(spans.values()) == sorted(spans.values(), reverse=True)


def test_wire_spans_honours_a_uniform_override(fabric: Fabric) -> None:
    """With no fabric model the caller applies one conservative span."""
    spans = wire_spans(fabric, fabric.tileDic["TERM"], span_override=7)

    assert set(spans.values()) == {7}


def test_parse_summary_orders_by_headroom(summary_file: Path) -> None:
    """The worst offender must lead the report."""
    violations = parse_summary(summary_file, "TERM")

    assert [v.headroom for v in violations] == [
        Decimal("4.38"),
        Decimal("2.11"),
        Decimal("1.02"),
    ]
    assert violations[0].tile == "TERM"
    assert violations[0].net == f"{LONG_WIRE_PORT}[3]"
    assert violations[0].layer == "Metal3"
    assert violations[0].span == FABRIC_ROWS


def test_headroom_is_the_number_the_checker_wrote(tmp_path: Path) -> None:
    """Read as a binary float, this ratio would not compare equal to itself."""
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            [
                {
                    "net": "N4BEG[0]",
                    "span": 4,
                    "layer": "Metal3",
                    "predicted_headroom": 2.675,
                    "targets": [],
                }
            ]
        )
    )

    headroom = parse_summary(path, "TERM")[0].headroom

    assert headroom == Decimal("2.675")
    assert str(headroom) == "2.675", "no binary-float artefact in the reported ratio"


def test_diode_targets_are_shaped_for_the_eco_diode_step(summary_file: Path) -> None:
    """`Odb.InsertECODiodes` takes `instance/pin` sinks, not net names."""
    targets = diode_targets(parse_summary(summary_file, "TERM"))

    assert targets == [
        {"target": "_013_/I"},
        {"target": "_027_/I"},
        {"target": "_031_/A"},
    ]


def test_diode_targets_asks_for_one_diode_per_sink(summary_file: Path) -> None:
    """A net violating on two layers still only needs a single diode."""
    violations = parse_summary(summary_file, "TERM")

    assert [v.net for v in violations].count(f"{LONG_WIRE_PORT}[3]") == 2
    assert sum(t == {"target": "_013_/I"} for t in diode_targets(violations)) == 1


def test_the_checker_switch_is_a_real_config_variable() -> None:
    """Declared only as `error_on_var`, it would be rejected as unknown when set."""
    declared = {
        v.name for v in FABulousAntennaPrecheckChecker.get_all_config_variables()
    }

    assert "ERROR_ON_PREDICTED_ANTENNA" in declared


def test_span_reads_the_tile_object_without_parsing_any_csv(
    fabric: Fabric, mocker: MockerFixture
) -> None:
    """The tile flow already holds the Tile, so no CSV should be re-parsed."""
    parse = mocker.patch(
        "fabulous.fabric_generator.gds_generator.steps.antenna_precheck.parseFabricCSV"
    )
    step = FABulousAntennaPrecheck.__new__(FABulousAntennaPrecheck)
    step.config = {
        "DESIGN_NAME": "TERM",
        "FABULOUS_TILE": fabric.tileDic["TERM"],
        "FABULOUS_FABRIC": fabric,
    }

    tile, resolved = step.span_context()

    assert tile is fabric.tileDic["TERM"]
    assert resolved is fabric
    parse.assert_not_called()
