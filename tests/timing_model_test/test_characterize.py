"""Tests for composing the per-macro characterisation onto the fabric."""

from copy import deepcopy
from pathlib import Path

import pytest
from pytest_mock import MockerFixture, MockType

from fabulous.fabric_cad.gen_npnr_model import set_placeholder_timing, tile_copies
from fabulous.fabric_cad.timing_model.characterize import characterize
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.timing import (
    BelArcs,
    BelPin,
    DelayArc,
    SwitchPip,
    WirePip,
    ns,
)
from fabulous.fabric_definition.wire import Wire
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
    # Placements of one tile type differ in their wires, like SJUMP wires.
    for x, (source, destination) in enumerate([("A0", "B0"), ("C0", "D0")]):
        fabric.tile[0][x].wireList = [
            Wire(Direction.JUMP, source, 0, 0, destination, "", "")
        ]
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
    pips = mocker.patch(
        f"{CHARACTERIZE}.characterize_pips",
        side_effect=lambda _timing, *, pips, **_: dict.fromkeys(pips, ns(6.0)),
    )
    bel_timing = mocker.patch(
        f"{CHARACTERIZE}.characterize_bel",
        side_effect=lambda _synth, bel, **_: BelArcs(
            delays=(DelayArc(BelPin("I0"), BelPin("O"), ns(len(bel.prefix))),)
        ),
    )

    characterize(two_lut_tiles, mocker.Mock())

    tools.assert_called_once()
    pips.assert_called_once()
    assert {WirePip("A0", "B0"), WirePip("C0", "D0")} <= set(
        pips.call_args.kwargs["pips"]
    )
    for x in (0, 1):
        assert [wire.delay for wire in two_lut_tiles.tile[0][x].wireList] == [ns(6.0)]
    assert two_lut_tiles.clock_arrival == ns(1.0)
    delays = two_lut_tiles.tileDic["LUT4AB"].switch_matrix.pip_delays
    assert delays == {
        SwitchPip(src="J_BEG", dst="LA_I0"): ns(6.0),
        SwitchPip(src="LONG_O", dst="LA_I0"): ns(6.0),
    }
    assert all(
        tile.switch_matrix.pip_delays is delays for tile in tile_copies(two_lut_tiles)
    )
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
    """No timing is set unless every BEL and pip of the fabric was characterised."""
    mocker.patch(f"{CHARACTERIZE}.characterize_pips", return_value={})
    mocker.patch(
        f"{CHARACTERIZE}.characterize_bel",
        side_effect=[BelArcs(), ValueError("no timing graph")],
    )

    with pytest.raises(ValueError, match="no timing graph"):
        characterize(two_lut_tiles, mocker.Mock())

    for tile in tile_copies(two_lut_tiles):
        assert tile.switch_matrix.pip_delays is None
        assert all(wire.delay is None for wire in tile.wireList)
        assert all(bel.arcs is None for bel in tile.bels)
    assert two_lut_tiles.clock_arrival is None


@pytest.mark.usefixtures("tools")
@pytest.mark.parametrize("characterised", [False, True])
def test_a_tile_type_without_placement_is_timed_like_a_placed_one(
    two_lut_tiles: Fabric, mocker: MockerFixture, *, characterised: bool
) -> None:
    """Placeholder and characterised timing both cover every tile type."""
    io = make_empty_tile("W_IO", pinOrderConfig={})
    io.bels = [_bel("A_")]
    io.switch_matrix = SwitchMatrix(
        matrix_file=Path(), connections={"A_I0": ["W1END0"]}
    )
    two_lut_tiles.tileDic[io.name] = io
    mocker.patch(
        f"{CHARACTERIZE}.characterize_pips",
        side_effect=lambda _timing, *, pips, **_: dict.fromkeys(pips, ns(1.0)),
    )
    mocker.patch(f"{CHARACTERIZE}.characterize_bel", return_value=BelArcs())

    if characterised:
        characterize(two_lut_tiles, mocker.Mock())
    else:
        set_placeholder_timing(two_lut_tiles)

    assert io.bels[0].arcs is not None
    assert io.switch_matrix.pip_delays is not None
    assert list(io.switch_matrix.pip_delays) == [SwitchPip(src="W1END0", dst="A_I0")]


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

    characterize(fabric, mocker.Mock())

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
    switch_matrix = fabric.superTileDic["ST"].switch_matrix
    assert switch_matrix is not None
    assert switch_matrix.pip_delays == {SwitchPip(src="BOT_SJ0", dst="ST_I0"): ns(1.5)}
    assert [
        (call.args[0], call.kwargs["instance"]) for call in bel_timing.call_args_list
    ] == [("ST", ("Inst_ST_ST_LUT4c_frame_config_dffesr",))]
    assert st_bel.arcs == BelArcs()
