"""Tests for grouping a fabric into macros and running their tools."""

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
    MemberTile,
    PhysicalMacro,
    StructuralMacro,
    SuperTileMacro,
    TileMacro,
    fabric_macros,
    run_macro_tools,
)
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from tests.conftest import make_empty_tile, make_fabric_from_grid

MACRO = "fabulous.fabric_cad.timing_model.macro"


@pytest.fixture
def tiles() -> dict[str, Tile]:
    """Return tile types `A`, `B` and `C`."""
    return {name: make_empty_tile(name, pinOrderConfig={}) for name in "ABC"}


def _super_tile(name: str, tile_map: list[list[Tile | None]]) -> SuperTile:
    """Build a supertile of the tiles in `tile_map`."""
    tiles = list({t.name: t for row in tile_map for t in row if t is not None}.values())
    return SuperTile(name=name, tileDir=Path(), tiles=tiles, tileMap=tile_map)


def test_fabric_macros_synthesise_each_supertile_once(
    tiles: dict[str, Tile],
) -> None:
    """A supertile holds its members at their instances; other tiles stand alone."""
    fabric = make_fabric_from_grid([[tiles["A"], tiles["C"]], [tiles["B"], None]])
    super_tile = _super_tile("SUPER", [[tiles["C"]], [tiles["B"]]])
    fabric.superTileDic = {"SUPER": super_tile}

    macros = fabric_macros(fabric)

    assert macros == [
        SuperTileMacro(
            super_tile=super_tile,
            members=(
                MemberTile(tile=tiles["C"], instance="Tile_X0Y0_C"),
                MemberTile(tile=tiles["B"], instance="Tile_X0Y1_B"),
            ),
        ),
        TileMacro(tile=tiles["A"]),
    ]
    assert [macro.top for macro in macros] == ["SUPER", "A"]


@pytest.mark.parametrize(
    ("tile_maps", "message"),
    [
        pytest.param(
            {"SUPER": [["B", "B"]]},
            "Supertile 'SUPER' places tile 'B' more than once",
            id="twice-in-one-supertile",
        ),
        pytest.param(
            {"S1": [["B"]], "S2": [["B", "C"]]},
            "Tile 'B' is in supertile 'S1' and in supertile 'S2'",
            id="in-two-supertiles",
        ),
    ],
)
def test_tile_with_two_supertile_instances_raises(
    tiles: dict[str, Tile], tile_maps: dict[str, list[list[str]]], message: str
) -> None:
    """A tile type with two instances has no single instance to characterise."""
    fabric = make_fabric_from_grid([[tiles["B"], tiles["C"]]])
    fabric.superTileDic = {
        name: _super_tile(name, [[tiles[t] for t in row] for row in tile_map])
        for name, tile_map in tile_maps.items()
    }

    with pytest.raises(ValueError, match=message):
        fabric_macros(fabric)


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
