"""Tests for the FABulousTilePDN step."""

from decimal import Decimal
from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from librelane.steps.step import StepException
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.tile_pdn import FABulousTilePDN


@pytest.fixture
def tile_pdn_config(mock_config: Config) -> Config:
    """Config of a regular tile with IHP TopMetal1 stripes."""
    return mock_config.copy(
        FABULOUS_TILE_LOGICAL_WIDTH=1,
        PDN_VOFFSET=Decimal("13.6"),
        PDN_VPITCH=Decimal("75.6"),
        PDN_VWIDTH=Decimal("2.2"),
        PDN_VSPACING=Decimal(4),
    )


@pytest.fixture
def tile_pdn_state(mock_state: State) -> State:
    """Floorplan state of a regular IHP LUT4AB tile with 2.88 um core margins."""
    mock_state.metrics["design__die__bbox"] = "0.0 0.0 246.24 245.28"
    mock_state.metrics["design__core__bbox"] = "2.88 3.78 243.36 238.14"
    return mock_state


@pytest.mark.parametrize(
    ("tile_count", "die_bbox", "core_bbox", "expected"),
    [
        pytest.param(
            1,
            "0.0 0.0 246.24 245.28",
            "2.88 3.78 243.36 238.14",
            "VDD 13.60 4\nVSS 19.80 3\n",
            id="regular_tile_ends_on_partial_set",
        ),
        pytest.param(
            2,
            "0.0 0.0 492.48 245.28",
            "2.88 3.78 489.6 238.14",
            "VDD 13.60 4\nVSS 19.80 3\nVDD 259.84 4\nVSS 266.04 3\n",
            id="supertile_repeats_regular_tile_per_column",
        ),
    ],
)
def test_run_passes_planned_stripes(
    tile_pdn_config: Config,
    tile_pdn_state: State,
    mocker: MockerFixture,
    tmp_path: Path,
    tile_count: int,
    die_bbox: str,
    core_bbox: str,
    expected: str,
) -> None:
    """Test that every logical tile gets the stripes of a regular tile."""
    generate_pdn_run = mocker.patch(
        "librelane.steps.openroad.GeneratePDN.run", return_value=({}, {})
    )
    config = tile_pdn_config.copy(FABULOUS_TILE_LOGICAL_WIDTH=tile_count)
    tile_pdn_state.metrics["design__die__bbox"] = die_bbox
    tile_pdn_state.metrics["design__core__bbox"] = core_bbox
    step = FABulousTilePDN(config, tile_pdn_state)
    step.config = config
    step.step_dir = str(tmp_path)

    step.run(tile_pdn_state)

    generate_pdn_run.assert_called_once()
    assert (tmp_path / "pdn_stripes.txt").read_text() == expected


def test_run_rejects_offset_outside_logical_tile_core(
    tile_pdn_config: Config, tile_pdn_state: State, mocker: MockerFixture
) -> None:
    """Test that an offset past the core of a logical tile is rejected."""
    generate_pdn_run = mocker.patch("librelane.steps.openroad.GeneratePDN.run")
    config = tile_pdn_config.copy(PDN_VOFFSET=Decimal(250))
    step = FABulousTilePDN(config, tile_pdn_state)
    step.config = config

    with pytest.raises(StepException, match="PDN_VOFFSET"):
        step.run(tile_pdn_state)
    generate_pdn_run.assert_not_called()
