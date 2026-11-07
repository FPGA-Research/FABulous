"""Tests for composing the per-macro characterisation onto the fabric."""

from copy import deepcopy
from pathlib import Path

import pytest
from pytest_mock import MockerFixture, MockType

from fabulous.fabric_cad.gen_npnr_model import tile_copies
from fabulous.fabric_cad.timing_db import SwitchPip
from fabulous.fabric_cad.timing_model.characterize import characterize
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.timing import BelArcs, BelPin, DelayArc, ns
from tests.conftest import make_empty_tile, make_fabric_from_grid

CHARACTERIZE = "fabulous.fabric_cad.timing_model.characterize"


def _bel(prefix: str) -> Bel:
    """Build one LUT BEL instance with the given prefix."""
    return Bel(
        src=Path("LUT4c_frame_config_dffesr.v"),
        prefix=prefix,
        module_name="LUT4c_frame_config_dffesr",
        internal=[(f"{prefix}I0", IO.INPUT), (f"{prefix}O", IO.OUTPUT)],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )


@pytest.fixture
def two_lut_tiles() -> Fabric:
    """Place one LUT4AB tile type, holding two BELs, twice, as parser copies."""
    tile = make_empty_tile("LUT4AB", pinOrderConfig={})
    tile.bels = [_bel("LA_"), _bel("LONG_")]
    tile.switch_matrix = SwitchMatrix(
        matrix_file=Path(), connections={"LA_I0": ["J_BEG", "LONG_O"]}
    )
    fabric = make_fabric_from_grid([[deepcopy(tile), deepcopy(tile)]])
    fabric.tileDic = {tile.name: tile}
    return fabric


@pytest.fixture
def tools(mocker: MockerFixture) -> MockType:
    """Replace the tool runs and the source lookup of each macro."""
    mocker.patch(f"{CHARACTERIZE}.resolve_sources")
    return mocker.patch(f"{CHARACTERIZE}.run_macro_tools")


def test_characterize_times_each_pip_and_bel_of_a_tile_type_once(
    two_lut_tiles: Fabric, tools: MockType, mocker: MockerFixture
) -> None:
    """Repeated placements reuse the tile type's results; BEL prefixes stay apart."""
    pip = SwitchPip(src="LONG_O", dst="LA_I0")
    pips = mocker.patch(
        f"{CHARACTERIZE}.characterize_pips", return_value={pip: ns(6.0)}
    )
    bel_timing = mocker.patch(
        f"{CHARACTERIZE}.characterize_bel",
        side_effect=lambda _synth, bel, **_: BelArcs(
            delays=(DelayArc(BelPin("I0"), BelPin("O"), ns(len(bel.prefix))),)
        ),
    )

    timing = characterize(two_lut_tiles, mocker.Mock())

    tools.assert_called_once()
    pips.assert_called_once()
    assert timing.pips.tile_delay("LUT4AB", pip) == ns(6.0)
    la, long = two_lut_tiles.tile[0][0].bels
    assert [call.kwargs["instance"] for call in bel_timing.call_args_list] == [
        (la.instance_name,),
        (long.instance_name,),
    ]
    for tile in tile_copies(two_lut_tiles):
        la, long = tile.bels
        assert la.arcs is not None
        assert la.arcs.delays[0].delay == ns(3)
        assert long.arcs is not None
        assert long.arcs.delays[0].delay == ns(5)


@pytest.mark.usefixtures("tools")
def test_characterize_leaves_bels_untimed_when_a_bel_fails(
    two_lut_tiles: Fabric, mocker: MockerFixture
) -> None:
    """No BEL gets arcs unless every BEL of the fabric was characterised."""
    mocker.patch(f"{CHARACTERIZE}.characterize_pips", return_value={})
    mocker.patch(
        f"{CHARACTERIZE}.characterize_bel",
        side_effect=[BelArcs(), ValueError("no timing graph")],
    )

    with pytest.raises(ValueError, match="no timing graph"):
        characterize(two_lut_tiles, mocker.Mock())

    assert all(
        bel.arcs is None for tile in tile_copies(two_lut_tiles) for bel in tile.bels
    )


def test_characterize_gives_each_macro_its_own_temporary_work_dir(
    tools: MockType, mocker: MockerFixture
) -> None:
    """Macros do not share tool outputs, and no files outlive the run."""
    mocker.patch(f"{CHARACTERIZE}.characterize_pips", return_value={})
    work_dirs: list[Path] = []

    def run_tools(_config: object, *, top: str, work_dir: Path, **_: object) -> None:
        assert work_dir.name == top
        assert work_dir.is_dir()
        assert not any(work_dir.iterdir())
        work_dirs.append(work_dir)

    tools.side_effect = run_tools
    lut = make_empty_tile("LUT4AB", pinOrderConfig={})
    io = make_empty_tile("W_IO", pinOrderConfig={})

    characterize(make_fabric_from_grid([[io, lut]]), mocker.Mock())

    assert len(work_dirs) == 2
    assert work_dirs[0].parent == work_dirs[1].parent
    assert not work_dirs[0].parent.exists()


def test_characterize_times_a_supertile_once_in_its_member_scopes(
    tools: MockType, mocker: MockerFixture
) -> None:
    """Members and the supertile switch matrix and BELs share one supertile run."""
    tools.side_effect = lambda _config, *, top, **_: mocker.Mock(synth=top)
    top, bot, lut = (
        make_empty_tile(name, pinOrderConfig={}) for name in ("TOP", "BOT", "LUT")
    )
    fabric = make_fabric_from_grid([[top, lut], [bot, lut]])
    super_pip = SwitchPip(src="BOT_SJ0", dst="ST_I0")
    st_bel = _bel("ST_")
    fabric.superTileDic = {
        "ST": SuperTile(
            name="ST",
            tileDir=Path(),
            tiles=[top, bot],
            tileMap=[[top], [bot]],
            bels=[st_bel],
            switch_matrix=SwitchMatrix(
                matrix_file=Path(), connections={"ST_I0": ["BOT_SJ0"]}
            ),
        )
    }
    pips = mocker.patch(
        f"{CHARACTERIZE}.characterize_pips",
        side_effect=lambda _timing, *, pips, **_: dict.fromkeys(pips, ns(1.5)),
    )
    bel_timing = mocker.patch(
        f"{CHARACTERIZE}.characterize_bel", return_value=BelArcs()
    )

    timing = characterize(fabric, mocker.Mock())

    assert [call.kwargs["top"] for call in tools.call_args_list] == ["ST", "LUT"]
    assert [
        (call.args[0].synth, call.kwargs["scope"], call.kwargs["switch_matrix"])
        for call in pips.call_args_list
    ] == [
        ("ST", ("Tile_X0Y0_TOP",), "Inst_TOP_switch_matrix"),
        ("LUT", (), "Inst_LUT_switch_matrix"),
        ("ST", ("Tile_X0Y1_BOT",), "Inst_BOT_switch_matrix"),
        ("ST", (), "Inst_ST_switch_matrix"),
    ]
    assert timing.pips.super_tile_delay("ST", super_pip) == ns(1.5)
    assert [
        (call.args[0], call.kwargs["instance"]) for call in bel_timing.call_args_list
    ] == [("ST", ("Inst_ST_ST_LUT4c_frame_config_dffesr",))]
    assert st_bel.arcs == BelArcs()
