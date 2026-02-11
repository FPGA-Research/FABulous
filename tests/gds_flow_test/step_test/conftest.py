"""Fixtures fceor gds_generator_test tests."""

from decimal import Decimal

import pytest
from librelane.config.config import Config
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


@pytest.fixture(autouse=True)
def mock_out_step_init(mocker: MockerFixture) -> None:
    mocker.patch("librelane.steps.Step.__init__", return_value=None)


@pytest.fixture
def mock_config() -> Config:  # type: ignore[name-defined]
    """Create a mock Config object for testing."""
    # Add common config values that steps might use

    return Config(
        {
            "DESIGN_NAME": "test_design",
            "RSZ_CORNERS": None,
            "STA_CORNERS": ["typical"],
            "PDN_VERTICAL_LAYER": "met2",
            "IO_PIN_V_LENGTH": None,
            "IO_PIN_H_LENGTH": None,
            "AUTO_ECO_DIODE_INSERT_MODE": "none",
            "FABULOUS_RUN_TILE_OPTIMISATION": False,
            "FABULOUS_IGNORE_ERROR": False,
            "FABULOUS_IGNORE_ERRORS": False,
            "IGNORE_ANTENNA_VIOLATIONS": False,
            "IGNORE_DEFAULT_DIE_AREA": False,
            "FABULOUS_OPTIMISATION_WIDTH_STEP_COUNT": 5,
            "FABULOUS_OPTIMISATION_HEIGHT_STEP_COUNT": 5,
            "FABULOUS_IO_MIN_WIDTH": 1,
            "FABULOUS_IO_MIN_HEIGHT": 1,
            "FABULOUS_OPT_MODE": OptMode.FIND_MIN_WIDTH,
        }
    )


@pytest.fixture
def mock_state(mocker: MockerFixture) -> dict:  # type: ignore[name-defined]
    """Create a mock State object for testing."""

    state = mocker.MagicMock()
    state.metrics = {
        "klayout__drc_error__count": 0,
        "route__drc_errors": 0,
        "antenna__violating__nets": 0,
        "antenna__violating__pins": 0,
        "pdk__site_width": Decimal("0.46"),
        "pdk__site_height": Decimal("2.72"),
        "design__instance__area__stdcell": 5000,
    }
    return state


@pytest.fixture
def mock_antenna_report() -> str:
    """Create a mock antenna report for testing."""
    return """
┏━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ P / R ┃ Partial ┃ Required ┃ Net             ┃ Pin       ┃ Layer     ┃
┡━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ 10.08 │ 2016.10 │ 200.00   │ SS4END[10]      │ _3249_/A  │ TopMetal1 │
│ 8.82  │ 1764.52 │ 200.00   │ NN4END[7]       │ _3194_/A  │ TopMetal1 │
│ 1.71  │ 341.17  │ 200.00   │ S2MID[4]        │ _1193_/A  │ TopMetal1 │
│ 1.71  │ 341.17  │ 200.00   │ S2MID[4]        │ _1525_/A2 │ TopMetal1 │
│ 1.71  │ 341.17  │ 200.00   │ S2MID[4]        │ _1896_/A1 │ TopMetal1 │
│ 1.71  │ 341.17  │ 200.00   │ S2MID[4]        │ _3223_/A  │ TopMetal1 │
│ 1.34  │ 267.01  │ 200.00   │ SS4END[7]       │ _3246_/A  │ Metal4    │
│ 1.33  │ 265.29  │ 200.00   │ SS4END[9]       │ _3248_/A  │ Metal4    │
│ 1.31  │ 262.04  │ 200.00   │ SS4END[15]      │ _3254_/A  │ Metal4    │
│ 1.30  │ 259.57  │ 200.00   │ N2MID[4]        │ _1180_/A  │ TopMetal1 │
│ 1.30  │ 259.57  │ 200.00   │ N2MID[4]        │ _1322_/A0 │ TopMetal1 │
│ 1.30  │ 259.57  │ 200.00   │ N2MID[4]        │ _1525_/A0 │ TopMetal1 │
│ 1.30  │ 259.57  │ 200.00   │ N2MID[4]        │ _3171_/A  │ TopMetal1 │
│ 1.30  │ 259.57  │ 200.00   │ S4END[15]       │ _3238_/A  │ Metal4    │
│ 1.29  │ 257.45  │ 200.00   │ NN4END[14]      │ _3201_/A  │ Metal4    │
│ 1.26  │ 252.45  │ 200.00   │ NN4END[4]       │ _3191_/A  │ Metal4    │
│ 1.22  │ 243.44  │ 200.00   │ SS4END[13]      │ _3252_/A  │ Metal4    │
│ 1.21  │ 242.51  │ 200.00   │ SS4END[12]      │ _3251_/A  │ Metal4    │
│ 1.15  │ 230.03  │ 200.00   │ SS4END[8]       │ _3247_/A  │ Metal4    │
│ 1.12  │ 223.93  │ 200.00   │ SS4END[6]       │ _3245_/A  │ Metal4    │
│ 0.87  │ 174.03  │ 200.00   │ N2END[2]        │ _1216_/A1 │ TopMetal1 │
│ 0.87  │ 174.03  │ 200.00   │ N2END[2]        │ _1271_/A0 │ TopMetal1 │
│ 0.87  │ 174.03  │ 200.00   │ N2END[2]        │ _1333_/A2 │ TopMetal1 │
│ 0.87  │ 174.03  │ 200.00   │ N2END[2]        │ _1455_/A0 │ TopMetal1 │
│ 0.84  │ 168.47  │ 200.00   │ FrameStrobe[19] │ _3154_/A  │ Metal4    │
│ 0.03  │ 6.95    │ 200.00   │ FrameStrobe[19] │ _3154_/A  │ Metal5    │
│ 0.03  │ 6.70    │ 200.00   │ SS4END[6]       │ _3245_/A  │ Metal5    │
└───────┴─────────┴──────────┴─────────────────┴───────────┴───────────┘
    """
