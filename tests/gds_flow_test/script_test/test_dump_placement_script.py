"""Tests for dump_placement: the block-to-JSON extraction."""

from types import SimpleNamespace

import pytest

from fabulous.fabric_generator.gds_generator.script.dump_placement import dump_block


def _box(x0: int, y0: int, x1: int, y1: int) -> SimpleNamespace:
    return SimpleNamespace(
        xMin=lambda: x0, yMin=lambda: y0, xMax=lambda: x1, yMax=lambda: y1
    )


def _inst(
    name: str, master: str, box: SimpleNamespace, placed: bool = True
) -> SimpleNamespace:
    return SimpleNamespace(
        getName=lambda: name,
        getMaster=lambda: SimpleNamespace(getName=lambda: master),
        getBBox=lambda: box,
        isPlaced=lambda: placed,
    )


def _bterm(
    name: str, io: str, boxes: list[SimpleNamespace], sig: str = "SIGNAL"
) -> SimpleNamespace:
    return SimpleNamespace(
        getName=lambda: name,
        getIoType=lambda: io,
        getSigType=lambda: sig,
        getBPins=lambda: [SimpleNamespace(getBBox=lambda b=b: b) for b in boxes],
    )


def _iterm(
    inst: SimpleNamespace, pin: str, io: str, sig: str = "SIGNAL"
) -> SimpleNamespace:
    return SimpleNamespace(
        getInst=lambda: inst,
        getMTerm=lambda: SimpleNamespace(getName=lambda: pin),
        getIoType=lambda: io,
        getSigType=lambda: sig,
    )


def _net(
    name: str,
    bterms: list[SimpleNamespace],
    iterms: list[SimpleNamespace],
    sig: str = "SIGNAL",
) -> SimpleNamespace:
    return SimpleNamespace(
        getName=lambda: name,
        getSigType=lambda: sig,
        getBTerms=lambda: bterms,
        getITerms=lambda: iterms,
    )


def _block(
    insts: list[SimpleNamespace],
    bterms: list[SimpleNamespace],
    nets: list[SimpleNamespace],
) -> SimpleNamespace:
    return SimpleNamespace(
        getDieArea=lambda: _box(0, 0, 200_000, 100_000),
        getInsts=lambda: insts,
        getBTerms=lambda: bterms,
        getNets=lambda: nets,
    )


def test_dump_block_extracts_geometry_and_signal_connectivity() -> None:
    latch = _inst("lat0", "dlhq", _box(10_000, 20_000, 14_000, 24_000))
    port_in = _bterm("FrameData[0]", "INPUT", [_box(0, 29_000, 1_000, 31_000)])
    vdd = _bterm("VDD", "INOUT", [_box(0, 0, 1, 1)], sig="POWER")
    nets = [
        _net(
            "FrameData[0]",
            [port_in],
            [_iterm(latch, "D", "INPUT"), _iterm(latch, "VDD", "INOUT", sig="POWER")],
        ),
        _net("VDD", [vdd], [_iterm(latch, "VDD", "INOUT", sig="POWER")], sig="POWER"),
    ]

    payload = dump_block(_block([latch], [port_in, vdd], nets), dbu=1000)

    assert payload["die"] == [0, 0, 200, 100]
    assert payload["instances"] == {"lat0": {"master": "dlhq", "x": 12, "y": 22}}
    assert payload["pins"] == {"FrameData[0]": {"io": "INPUT", "x": 0.5, "y": 30}}
    assert payload["nets"] == {
        "FrameData[0]": {"bterms": ["FrameData[0]"], "iterms": [["lat0", "D", "INPUT"]]}
    }


@pytest.mark.parametrize(
    ("insts", "bterms", "message"),
    [
        (
            [_inst("fill", "fill", _box(0, 0, 1, 1), placed=False)],
            [],
            "Instance fill is not placed",
        ),
        ([], [_bterm("N1BEG[0]", "OUTPUT", [])], "Port N1BEG\\[0\\] has no placed pin"),
    ],
)
def test_dump_block_rejects_unplaced_design(
    insts: list[SimpleNamespace], bterms: list[SimpleNamespace], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        dump_block(_block(insts, bterms, []), dbu=1000)
