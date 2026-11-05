"""Tests for the configuration memory model and its CSV form."""

from dataclasses import replace
from pathlib import Path

import pytest

from fabulous.fabric_definition.configmem import (
    ConfigMem,
    ConfigMemFrame,
    Crosspoint,
    empty_config_mem,
)
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile

# A 3-frame, 8-line grid: frame 0 holds a descending run, frame 2 one bit.
FRAMES = (
    ConfigMemFrame("frame0", 0, 8, {7: 3, 6: 2, 5: 1}),
    ConfigMemFrame("frame1", 1, 8, {}),
    ConfigMemFrame("frame2", 2, 8, {4: 0}),
)
SOURCE = Path("T_ConfigMem.csv")
MEMORY = ConfigMem(FRAMES, 8, 3, source=SOURCE)


def test_bit_at_reads_the_mask_from_the_highest_data_line() -> None:
    assert MEMORY.bit_at == {
        Crosspoint(0, 7): 3,
        Crosspoint(0, 6): 2,
        Crosspoint(0, 5): 1,
        Crosspoint(2, 4): 0,
    }
    assert MEMORY.crosspoint_of[0] == Crosspoint(2, 4)
    assert MEMORY.free_crosspoints[:3] == [
        Crosspoint(0, 4),
        Crosspoint(0, 3),
        Crosspoint(0, 2),
    ]
    assert len(MEMORY.free_crosspoints) == 24 - 4


@pytest.mark.parametrize(
    ("ranges", "bits"),
    [
        pytest.param("6:4", [6, 5, 4], id="descending_run"),
        pytest.param("4:6", [4, 5, 6], id="ascending_run"),
        pytest.param("6;4;5", [6, 4, 5], id="list"),
        pytest.param(" 6 : 4 ", [6, 5, 4], id="whitespace"),
    ],
)
def test_from_csv_reads_every_range_form(
    tmp_path: Path, ranges: str, bits: list[int]
) -> None:
    path = tmp_path / "T_ConfigMem.csv"
    path.write_text(
        "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges\n"
        f"frame0,0,3,1110_0000,{ranges}\n"
        "frame1,1,0,0000_0000,# NULL\n"
    )
    memory = ConfigMem.from_csv(path, frame_bits_per_row=8, max_frames_per_col=2)
    assert memory.frame_bits_per_row == 8
    assert memory.source == path
    assert memory.frames[0].config_bit_ranges == bits
    assert memory.frames[1] == ConfigMemFrame("frame1", 1, 8, {})


def test_to_csv_round_trips_and_writes_runs_compactly(tmp_path: Path) -> None:
    path = tmp_path / "T_ConfigMem.csv"
    replace(MEMORY, source=path).to_csv()
    assert path.read_text() == (
        "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges\n"
        "frame0,0,3,1110_0000,3:1\n"
        "frame1,1,0,0000_0000,# NULL\n"
        "frame2,2,1,0001_0000,0\n"
    )
    assert (
        ConfigMem.from_csv(path, frame_bits_per_row=8, max_frames_per_col=3) == MEMORY
    )


def test_row_order_in_the_file_carries_no_meaning(tmp_path: Path) -> None:
    """Rows are ordered by `frame_index`, not by file position."""
    path = tmp_path / "T_ConfigMem.csv"
    replace(MEMORY, source=path).to_csv()
    header, *rows = path.read_text().splitlines(keepends=True)
    path.write_text(header + "".join(reversed(rows)))

    assert (
        ConfigMem.from_csv(path, frame_bits_per_row=8, max_frames_per_col=3) == MEMORY
    )


@pytest.mark.parametrize(
    ("frames", "message"),
    [
        pytest.param((FRAMES[0], FRAMES[2]), "indexed 0 .. n-1", id="frame_gap"),
        pytest.param(
            (ConfigMemFrame("frame0", 0, 4, {3: 0}),),
            "over 4 data lines",
            id="mask_width",
        ),
        pytest.param(
            (
                ConfigMemFrame("frame0", 0, 8, {7: 0}),
                ConfigMemFrame("frame1", 1, 8, {7: 0}),
            ),
            r"\[0\] allocated more than once",
            id="duplicate_bit",
        ),
    ],
)
def test_rejects_inconsistent_frames(
    frames: tuple[ConfigMemFrame, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ConfigMem(frames, 8, len(frames), source=SOURCE)


def test_from_csv_rejects_a_mask_its_ranges_do_not_fill(tmp_path: Path) -> None:
    path = tmp_path / "T_ConfigMem.csv"
    path.write_text(
        "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges\n"
        "frame0,0,3,1110_0000,1:0\n"
    )
    with pytest.raises(ValueError, match="marks 3 data lines used but lists 2"):
        ConfigMem.from_csv(path, frame_bits_per_row=8, max_frames_per_col=1)


def test_a_memory_cannot_be_built_against_the_wrong_grid(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MaxFramesPerCol is 4"):
        ConfigMem(FRAMES, 8, 4, source=SOURCE)
    path = tmp_path / "T_ConfigMem.csv"
    replace(MEMORY, source=path).to_csv()
    with pytest.raises(ValueError, match="MaxFramesPerCol is 4"):
        ConfigMem.from_csv(path, frame_bits_per_row=8, max_frames_per_col=4)


def test_default_packs_from_the_highest_bit_down() -> None:
    memory = ConfigMem.default(
        10, frame_bits_per_row=4, max_frames_per_col=4, source=SOURCE
    )
    assert [frame.used_bits_mask.to01() for frame in memory.frames] == [
        "1111",
        "1111",
        "1100",
        "0000",
    ]
    assert [frame.config_bit_ranges for frame in memory.frames] == [
        [9, 8, 7, 6],
        [5, 4, 3, 2],
        [1, 0],
        [],
    ]
    with pytest.raises(ValueError, match="exceed fabric capacity"):
        ConfigMem.default(17, frame_bits_per_row=4, max_frames_per_col=4, source=SOURCE)


def test_rebuilt_with_inverts_bit_at() -> None:
    assert MEMORY.rebuilt_with(MEMORY.bit_at) == MEMORY
    with pytest.raises(ValueError, match="contiguous range from 0"):
        MEMORY.rebuilt_with({Crosspoint(0, 0): 1})
    with pytest.raises(ValueError, match="outside the 3 x 8 frame grid"):
        MEMORY.rebuilt_with({Crosspoint(3, 0): 0})


def _tile(tmp_path: Path, config_mem: ConfigMem) -> Tile:
    """Build a bare tile in `tmp_path`, carrying `config_mem`."""
    return Tile(
        name="T",
        ports=[],
        bels=[],
        tileDir=tmp_path / "T.csv",
        switch_matrix=SwitchMatrix(matrix_file=Path(), connections={}),
        config_mem=config_mem,
        gen_ios=[],
        userCLK=False,
    )


def test_a_tile_carries_the_memory_it_was_built_with(tmp_path: Path) -> None:
    """A tile requires a memory and keeps the one it was given."""
    empty = empty_config_mem(tmp_path / "T_ConfigMem.csv")

    assert _tile(tmp_path, empty).config_mem is empty
    assert _tile(tmp_path, MEMORY).config_mem is MEMORY


def test_an_empty_memory_still_names_its_file(tmp_path: Path) -> None:
    """The file is decided when the tile is parsed, before anything is written."""
    empty = empty_config_mem(tmp_path / "T_ConfigMem.csv")

    assert empty.source == tmp_path / "T_ConfigMem.csv"
    assert empty.config_bits == 0


def test_a_memory_read_back_carries_the_file_it_came_from(tmp_path: Path) -> None:
    """`from_csv` names its source, and a mapping survives the round trip."""
    path = tmp_path / "T_ConfigMem.csv"
    replace(MEMORY, source=path).to_csv()

    read_back = ConfigMem.from_csv(path, frame_bits_per_row=8, max_frames_per_col=3)

    assert read_back.source == path
    assert read_back.bit_at == MEMORY.bit_at


def test_to_csv_writes_where_the_source_says(tmp_path: Path) -> None:
    """The only writer takes its destination from the memory, directory and all."""
    path = tmp_path / "Tile" / "T" / "T_ConfigMem.csv"
    replace(MEMORY, source=path).to_csv()

    assert (
        ConfigMem.from_csv(path, frame_bits_per_row=8, max_frames_per_col=3) == MEMORY
    )
