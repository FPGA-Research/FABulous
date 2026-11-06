"""Tests for filling a `TimingDb` from the per-tile timing models."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture, MockType

from fabulous.fabric_cad.gen_npnr_model import placeholder_timing
from fabulous.fabric_cad.timing_db import (
    BelArcs,
    BelPin,
    DelayArc,
    SwitchPip,
    ns,
)
from fabulous.fabric_cad.timing_model.characterize import characterize
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from tests.conftest import make_empty_tile, make_fabric_from_grid


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
    """Place one LUT4AB tile type, holding two BELs, twice."""
    tile = make_empty_tile("LUT4AB", pinOrderConfig={})
    tile.bels = [_bel("LA_"), _bel("LONG_")]
    tile.switch_matrix = SwitchMatrix(
        matrix_file=Path(), connections={"LA_I0": ["J_BEG", "LONG_O"]}
    )
    return make_fabric_from_grid([[tile, tile]])


@pytest.fixture
def tile_model(mocker: MockerFixture) -> MockType:
    """Replace the tool-backed tile timing model with a fake."""
    model_class = mocker.patch(
        "fabulous.fabric_cad.timing_model.characterize.FABulousTileTimingModel"
    )
    model = model_class.return_value
    model.pip_delay.return_value = ns(6.0)
    model.tile_scope = ()
    model.bel_timing.side_effect = lambda bel, **_: BelArcs(
        delays=(DelayArc(BelPin("I0"), BelPin("O"), ns(len(bel.prefix))),)
    )
    return model


def test_characterize_times_each_pip_and_bel_of_a_tile_type_once(
    two_lut_tiles: Fabric, tile_model: MockType, mocker: MockerFixture
) -> None:
    """Repeated placements reuse the tile type's results; BEL prefixes stay apart."""
    timing = characterize(two_lut_tiles, mocker.Mock())

    assert tile_model.pip_delay.call_count == 2
    assert tile_model.bel_timing.call_count == 2
    pip = SwitchPip(src="LONG_O", dst="LA_I0")
    assert timing.pips.tile_delay("LUT4AB", pip) == ns(6.0)
    la, long = two_lut_tiles.tile[0][0].bels
    assert [
        call.kwargs["instance"] for call in tile_model.bel_timing.call_args_list
    ] == [
        (la.instance_name,),
        (long.instance_name,),
    ]
    assert timing.bels.tile_arcs("LUT4AB", la).delays[0].delay == ns(3)
    assert timing.bels.tile_arcs("LUT4AB", long).delays[0].delay == ns(5)


def test_bel_timing_rejects_unknown_tile(two_lut_tiles: Fabric) -> None:
    """BEL timing lookups name the tile type that has no timing."""
    timing = placeholder_timing(two_lut_tiles)

    with pytest.raises(ValueError, match="UNKNOWN"):
        timing.bels.tile_arcs("UNKNOWN", _bel("LA_"))


def test_characterize_gives_each_tile_type_its_own_temporary_work_dir(
    tile_model: MockType, mocker: MockerFixture
) -> None:
    """Tile types do not share tool outputs, and no files outlive the run."""
    work_dirs: list[Path] = []

    def fake_model(*, tile_name: str, work_dir: Path, **_: object) -> MockType:
        assert work_dir.name == tile_name
        assert work_dir.is_dir()
        assert not any(work_dir.iterdir())
        work_dirs.append(work_dir)
        return tile_model

    mocker.patch(
        "fabulous.fabric_cad.timing_model.characterize.FABulousTileTimingModel",
        side_effect=fake_model,
    )
    lut = make_empty_tile("LUT4AB", pinOrderConfig={})
    io = make_empty_tile("W_IO", pinOrderConfig={})

    characterize(make_fabric_from_grid([[io, lut]]), mocker.Mock())

    assert len(work_dirs) == 2
    assert work_dirs[0].parent == work_dirs[1].parent
    assert not work_dirs[0].parent.exists()
