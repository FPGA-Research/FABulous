"""Tests for the ProposeTileInterfaceOrder step."""

import json
from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.state.state import State

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import Side
from fabulous.fabric_generator.gds_generator.formats import (
    PLACEMENT_FORMAT,
    TILE_INTERFACE_ORDER_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    read_interface_order,
    write_interface_order,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    TILE_INTERFACE_FIXED_ORDER_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
    TILE_INTERFACE_VARIABLE,
)
from fabulous.fabric_generator.gds_generator.steps.propose_tile_interface_order import (
    ProposeTileInterfaceOrder,
)

# Two vertical pairs on a 100-wide die: N1 bit 0 feeds a mux at x = 80, bit 1
# a mux at x = 20, so the placer-driven order swaps them.
PLACEMENT = {
    "die": [0, 0, 100, 100],
    "instances": {
        "mux_a": {"master": "mux", "x": 80, "y": 50},
        "mux_b": {"master": "mux", "x": 20, "y": 50},
    },
    "pins": {
        "N1BEG[0]": {"io": "OUTPUT", "x": 30, "y": 100},
        "N1END[0]": {"io": "INPUT", "x": 30, "y": 0},
        "N1BEG[1]": {"io": "OUTPUT", "x": 70, "y": 100},
        "N1END[1]": {"io": "INPUT", "x": 70, "y": 0},
        "ext": {"io": "INPUT", "x": 50, "y": 0},
    },
    "nets": {
        "N1END[0]": {"bterms": ["N1END[0]"], "iterms": [["mux_a", "I", "INPUT"]]},
        "N1BEG[0]": {"bterms": ["N1BEG[0]"], "iterms": [["mux_a", "X", "OUTPUT"]]},
        "N1END[1]": {"bterms": ["N1END[1]"], "iterms": [["mux_b", "I", "INPUT"]]},
        "N1BEG[1]": {"bterms": ["N1BEG[1]"], "iterms": [["mux_b", "X", "OUTPUT"]]},
        "ext": {"bterms": ["ext"], "iterms": []},
        # A select net gives each mux three pins, so neither reads as a buffer.
        "sel": {
            "bterms": [],
            "iterms": [["mux_a", "S", "INPUT"], ["mux_b", "S", "INPUT"]],
        },
    },
}

PAIRS_YAML = (
    "- {axis: vertical, first: N1BEG, second: N1END, kind: routing, scalar: false}\n"
)


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, Path]:
    placement = tmp_path / "test_design.placement.json"
    placement.write_text(json.dumps(PLACEMENT))
    pairs = tmp_path / "test_design_pin_pairs.yaml"
    pairs.write_text(PAIRS_YAML)
    step_dir = tmp_path / "step"
    step_dir.mkdir()
    return {"placement": placement, "pairs": pairs, "step_dir": step_dir}


def test_skips_when_the_switch_is_off(mock_config: Config, mock_state: State) -> None:
    step = ProposeTileInterfaceOrder(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            TILE_INTERFACE_VARIABLE.name: False,
            TILE_INTERFACE_PAIRS_VARIABLE.name: "x.yaml",
        }
    )

    assert step.run(mock_state) == ({}, {})


def test_raises_without_pairs(mock_config: Config, mock_state: State) -> None:
    step = ProposeTileInterfaceOrder(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            TILE_INTERFACE_VARIABLE.name: True,
            TILE_INTERFACE_PAIRS_VARIABLE.name: None,
        }
    )

    with pytest.raises(GDSFlowError, match=TILE_INTERFACE_PAIRS_VARIABLE.name):
        step.run(mock_state)


def test_writes_the_order_as_a_view_with_offset_metrics(
    mock_config: Config, mock_state: State, inputs: dict[str, Path]
) -> None:
    step = ProposeTileInterfaceOrder(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            TILE_INTERFACE_VARIABLE.name: True,
            TILE_INTERFACE_PAIRS_VARIABLE.name: str(inputs["pairs"]),
            TILE_INTERFACE_FIXED_ORDER_VARIABLE.name: None,
        }
    )
    step.step_dir = str(inputs["step_dir"])

    views, metrics = step.run({PLACEMENT_FORMAT: str(inputs["placement"])})

    proposal = inputs["step_dir"] / "test_design.interface_order.yaml"
    assert str(views[TILE_INTERFACE_ORDER_FORMAT]) == str(proposal)
    assert read_interface_order(proposal) == {
        Side.NORTH: ["N1BEG[1]", "N1BEG[0]"],
        Side.SOUTH: ["N1END[1]", "N1END[0]"],
    }
    # Targets 80 and 20 against pins at 30 and 70, then against ranks 25 and 75.
    assert metrics == {
        "fabulous__tile_interface__offset_before": 100,
        "fabulous__tile_interface__offset_after": 10,
        "fabulous__tile_interface__pairs": 2,
    }


def test_a_fixed_order_keeps_the_ranks_of_its_pairs(
    mock_config: Config, mock_state: State, inputs: dict[str, Path], tmp_path: Path
) -> None:
    fixed = tmp_path / "project.interface_order.yaml"
    write_interface_order({Side.NORTH: ["N1BEG[0]"], Side.SOUTH: ["N1END[0]"]}, fixed)

    step = ProposeTileInterfaceOrder(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            TILE_INTERFACE_VARIABLE.name: True,
            TILE_INTERFACE_PAIRS_VARIABLE.name: str(inputs["pairs"]),
            TILE_INTERFACE_FIXED_ORDER_VARIABLE.name: str(fixed),
        }
    )
    step.step_dir = str(inputs["step_dir"])

    views, _ = step.run({PLACEMENT_FORMAT: str(inputs["placement"])})

    # Bit 0 targets x = 80 but the fixed order holds it at rank 0.
    assert read_interface_order(Path(views[TILE_INTERFACE_ORDER_FORMAT])) == {
        Side.NORTH: ["N1BEG[0]", "N1BEG[1]"],
        Side.SOUTH: ["N1END[0]", "N1END[1]"],
    }
