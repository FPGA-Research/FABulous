"""Tests for ExtractPDKInfo step.

This step has custom run() logic that converts string metrics to Decimal.
"""

from decimal import Decimal

from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from FABulous.fabric_generator.gds_generator.steps.extract_pdk_info import (
    ExtractPDKInfo,
)


class TestExtractPDKInfo:
    """Test suite for ExtractPDKInfo step - focuses on Decimal conversion."""

    def test_run_converts_metrics_to_decimal(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ):
        """Test that run method converts site dimensions to Decimal."""
        step = ExtractPDKInfo(mock_config)

        mocker.patch(
            "FABulous.fabric_generator.gds_generator.steps.extract_pdk_info.Floorplan.run",
            return_value=(
                {},
                {"pdk__site_width": "0.46", "pdk__site_height": "2.72"},
            ),
        )

        views_update, metrics_update = step.run(mock_state)

        assert isinstance(metrics_update["pdk__site_width"], Decimal)
        assert isinstance(metrics_update["pdk__site_height"], Decimal)
        assert metrics_update["pdk__site_width"] == Decimal("0.46")
        assert metrics_update["pdk__site_height"] == Decimal("2.72")
