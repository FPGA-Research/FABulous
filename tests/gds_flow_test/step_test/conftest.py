"""Fixtures for gds_generator_test tests."""

import pytest


@pytest.fixture
def mock_config(mocker) -> dict:  # type: ignore[name-defined]
    """Create a mock Config object for testing."""
    config = mocker.MagicMock()
    # Add common config values that steps might use
    config["DESIGN_NAME"] = "test_design"
    config["RSZ_CORNERS"] = None
    config["STA_CORNERS"] = ["typical"]
    config["PDN_VERTICAL_LAYER"] = "met2"
    config["IO_PIN_V_LENGTH"] = None
    config["IO_PIN_H_LENGTH"] = None
    config["AUTO_ECO_DIODE_INSERT_MODE"] = "none"
    config["FABULOUS_RUN_TILE_OPTIMISATION"] = False
    config["FABULOUS_IGNORE_ERROR"] = False
    config["FABULOUS_IGNORE_ERRORS"] = False
    return config


@pytest.fixture
def mock_state(mocker) -> dict:  # type: ignore[name-defined]
    """Create a mock State object for testing."""
    state = mocker.MagicMock()
    state.metrics = {
        "klayout__drc_error__count": 0,
        "antenna__violating__nets": 0,
        "antenna__violating__pins": 0,
    }
    return state


@pytest.fixture
def mock_antenna_report() -> str:
    """Create a mock antenna report for testing."""
    return """╔═══════════════════════════════════════════════════╗
║           Antenna Violation Report               ║
╠═══════════════════════════════════════════════════╣
║ Net: net1                                         ║
║   Pins: 2                                         ║
║   Partial: 50.0 um²   Required: 40.0 um²         ║
║   Status: VIOLATING                               ║
║                                                    ║
║ Net: net2                                         ║
║   Pins: 1                                         ║
║   Partial: 45.0 um²   Required: 30.0 um²         ║
║   Status: VIOLATING                               ║
║                                                    ║
║ Net: net3                                         ║
║   Pins: 1                                         ║
║   Partial: 20.0 um²   Required: 30.0 um²         ║
║   Status: OK                                      ║
╚═══════════════════════════════════════════════════╝
Summary: 2 violations found
"""
