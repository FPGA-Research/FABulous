"""Tests for locating a tile's macro and running its tools."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.timing_model.config import (
    MacroSources,
    PhysicalSources,
    StructuralSources,
    TimingModelConfig,
)
from fabulous.fabric_cad.timing_model.macro import (
    PhysicalMacro,
    StructuralMacro,
    TileMacro,
    run_macro_tools,
    tile_macro,
)
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from tests.conftest import make_empty_tile, make_fabric_from_grid

MACRO = "fabulous.fabric_cad.timing_model.macro"


@pytest.fixture
def tiles() -> dict[str, Tile]:
    """Return tile types `A`, `B` and `C`."""
    return {name: make_empty_tile(name, pinOrderConfig={}) for name in "ABC"}


@pytest.mark.parametrize(
    ("name", "top", "scope"),
    [
        pytest.param("A", "A", (), id="own-macro"),
        pytest.param("B", "SUPER", ("Tile_X0Y1_B",), id="supertile-member"),
    ],
)
def test_tile_macro(
    tiles: dict[str, Tile], name: str, top: str, scope: tuple[str, ...]
) -> None:
    """A tile inside a supertile is timed at its instance in the supertile."""
    fabric = make_fabric_from_grid([[tiles["A"], tiles["C"]], [tiles["B"], None]])
    fabric.superTileDic = {
        "SUPER": SuperTile(
            name="SUPER",
            tileDir=Path(),
            tiles=[tiles["C"], tiles["B"]],
            tileMap=[[tiles["C"]], [tiles["B"]]],
        )
    }

    assert tile_macro(fabric, name) == TileMacro(tile=tiles[name], top=top, scope=scope)


def test_tile_placed_twice_in_a_supertile_raises(tiles: dict[str, Tile]) -> None:
    """A tile with two instances in its supertile has no single instance to time."""
    fabric = make_fabric_from_grid([[tiles["B"], tiles["B"]]])
    fabric.superTileDic = {
        "SUPER": SuperTile(
            name="SUPER",
            tileDir=Path(),
            tiles=[tiles["B"]],
            tileMap=[[tiles["B"], tiles["B"]]],
        )
    }

    with pytest.raises(ValueError, match="places tile 'B' 2 times"):
        tile_macro(fabric, "B")


@pytest.mark.parametrize(
    "sources",
    [
        pytest.param(StructuralSources(rtl_files=(Path("t.v"),)), id="structural"),
        pytest.param(
            PhysicalSources(
                rtl_files=(Path("t.v"),),
                netlist_file=Path("t.nl.v"),
                spef_files=(Path("t.spef"),),
            ),
            id="physical",
        ),
    ],
)
def test_run_macro_tools(
    tmp_path: Path, mocker: MockerFixture, sources: MacroSources
) -> None:
    """Synthesis is always timed; a physical macro also times its layout."""
    synthesize = mocker.patch(f"{MACRO}.YosysTool.synthesize_gate_level")
    write_sdf = mocker.patch(f"{MACRO}.OpenStaTool.write_sdf")
    mocker.patch(f"{MACRO}.NetlistIndex.read")
    graph = mocker.patch(f"{MACRO}.SdfTimingGraph")
    config = TimingModelConfig(
        project_dir=tmp_path,
        liberty_files=Path("cells.lib"),
        min_buf_cell_and_ports="BUF A Y",
    )

    timing = run_macro_tools(config, top="T", sources=sources, work_dir=tmp_path)

    synthesize.assert_called_once_with(
        verilog_files=[Path("t.v")],
        liberty_files=[Path("cells.lib")],
        top_name="T",
        netlist_file=tmp_path / "synth.v",
        techmap_files=[],
        tiehi_cell_and_port=None,
        tielo_cell_and_port=None,
        min_buf_cell_and_ports="BUF A Y",
    )
    sdf_calls = [
        (
            call.kwargs["netlist_file"],
            call.kwargs["spef_files"],
            call.kwargs["sdf_file"],
        )
        for call in write_sdf.call_args_list
    ]
    graph_files = [call.args[0] for call in graph.call_args_list]
    match sources:
        case StructuralSources():
            assert isinstance(timing, StructuralMacro)
            assert sdf_calls == [(tmp_path / "synth.v", [], tmp_path / "synth.sdf")]
            assert graph_files == [tmp_path / "synth.sdf"]
        case PhysicalSources():
            assert isinstance(timing, PhysicalMacro)
            assert sdf_calls == [
                (tmp_path / "synth.v", [], tmp_path / "synth.sdf"),
                (Path("t.nl.v"), [Path("t.spef")], tmp_path / "physical.sdf"),
            ]
            assert graph_files == [tmp_path / "synth.sdf", tmp_path / "physical.sdf"]
