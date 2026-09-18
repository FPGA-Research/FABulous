"""Tests for the ProposeConfigMapping step."""

import json
from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.state.state import State

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    PLACEMENT_FORMAT,
    RECONNECT_FORMAT,
)
from fabulous.fabric_generator.gds_generator.steps.propose_config_mapping import (
    ProposeConfigMapping,
)
from fabulous.fabric_generator.gds_generator.variables import (
    CONFIG_MAPPING_TARGET_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
    CONFIG_MEM_CSV_VARIABLE,
)

# One data line at y = 50 and one strobe line at x = 50 with a single latch.
ONE_LATCH_PLACEMENT = {
    "die": [0, 0, 100, 100],
    "data_y": {"0": [50, 50]},
    "strobe_x": {"0": [50, 50]},
    "latches": [
        {
            "frame": 0,
            "data_bit": 0,
            "instance": "lat",
            "x": 20,
            "y": 80,
            "data_pin": "D",
            "strobe_pin": "GATE",
        }
    ],
}

CURRENT_CSV = (
    "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges\n"
    "Frame0,0,1,1,0\n"
)

# Two data lines at y = 30 and y = 70 with the only latch on FrameData[1], so a
# mapping that allocates FrameData[0] does not describe this netlist.
TWO_DATA_LINE_PLACEMENT = {
    "die": [0, 0, 100, 100],
    "data_y": {"0": [30, 30], "1": [70, 70]},
    "strobe_x": {"0": [50, 50]},
    "latches": [
        {
            "frame": 0,
            "data_bit": 1,
            "instance": "lat",
            "x": 20,
            "y": 70,
            "data_pin": "D",
            "strobe_pin": "GATE",
        }
    ],
}

STALE_CSV = (
    "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges\n"
    "Frame0,0,1,01,0\n"
)

TARGET_CSV = (
    "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges\n"
    "Frame0,0,1,10,0\n"
)


def test_skips_when_the_switch_is_off(mock_config: Config, mock_state: State) -> None:
    step = ProposeConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: False,
            CONFIG_MEM_CSV_VARIABLE.name: "x.csv",
        }
    )

    assert step.run(mock_state) == ({}, {})


def test_raises_without_a_csv(mock_config: Config, mock_state: State) -> None:
    step = ProposeConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{CONFIG_MAPPING_VARIABLE.name: True, CONFIG_MEM_CSV_VARIABLE.name: None}
    )

    with pytest.raises(GDSFlowError, match=CONFIG_MEM_CSV_VARIABLE.name):
        step.run(mock_state)


def test_writes_the_proposal_and_the_reconnections(
    mock_config: Config, mock_state: State, tmp_path: Path
) -> None:
    placement = tmp_path / "test_design.placement.json"
    placement.write_text(json.dumps(ONE_LATCH_PLACEMENT))
    current = tmp_path / "test_design_ConfigMem.csv"
    current.write_text(CURRENT_CSV)
    step_dir = tmp_path / "step"
    step_dir.mkdir()

    step = ProposeConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            CONFIG_MEM_CSV_VARIABLE.name: str(current),
            CONFIG_MAPPING_TARGET_VARIABLE.name: None,
        }
    )
    step.step_dir = str(step_dir)

    views, metrics = step.run({PLACEMENT_FORMAT: str(placement)})

    proposal = step_dir / "test_design.ConfigMem.csv"
    assert set(views) == {CONFIG_MEM_FORMAT, RECONNECT_FORMAT}
    assert str(views[CONFIG_MEM_FORMAT]) == str(proposal)
    assert proposal.read_text() == CURRENT_CSV
    assert json.loads(Path(views[RECONNECT_FORMAT]).read_text()) == {
        "lat": {"D": "FrameData[0]", "GATE": "FrameStrobe[0]"}
    }
    assert metrics == {
        "fabulous__config_mapping__stub_before": 60,
        "fabulous__config_mapping__stub_after": 60,
        "fabulous__config_mapping__unplaced_bits": 0,
        "fabulous__config_mapping__unchanged": 1,
    }
    assert current.read_text() == CURRENT_CSV


def test_reads_the_target_mapping_when_set(
    mock_config: Config, mock_state: State, tmp_path: Path
) -> None:
    placement = tmp_path / "test_design.placement.json"
    placement.write_text(json.dumps(TWO_DATA_LINE_PLACEMENT))
    stale = tmp_path / "test_design_ConfigMem.csv"
    stale.write_text(STALE_CSV)
    target = tmp_path / "iter_1.ConfigMem.csv"
    target.write_text(TARGET_CSV)
    step_dir = tmp_path / "step"
    step_dir.mkdir()

    step = ProposeConfigMapping(mock_config, mock_state)
    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            CONFIG_MEM_CSV_VARIABLE.name: str(stale),
            CONFIG_MAPPING_TARGET_VARIABLE.name: str(target),
        }
    )
    step.step_dir = str(step_dir)

    views, _ = step.run({PLACEMENT_FORMAT: str(placement)})

    assert Path(views[CONFIG_MEM_FORMAT]).read_text() == TARGET_CSV
    assert json.loads(Path(views[RECONNECT_FORMAT]).read_text()) == {
        "lat": {"D": "FrameData[1]", "GATE": "FrameStrobe[0]"}
    }

    step.config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            CONFIG_MEM_CSV_VARIABLE.name: str(stale),
            CONFIG_MAPPING_TARGET_VARIABLE.name: None,
        }
    )
    with pytest.raises(GDSFlowError, match="does not allocate"):
        step.run({PLACEMENT_FORMAT: str(placement)})
