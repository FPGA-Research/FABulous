"""Tests for the `export_sdc` CLI command."""

from pathlib import Path

from pytest_mock import MockerFixture

from fabulous.fabric_cad.gen_sdc import FVS_BATCH_FRACTION, FVS_SINGLE_MAX
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from tests.conftest import run_cmd


def test_export_sdc_tile_writes_default_path(cli: FABulousREPL) -> None:
    """Running export_sdc with a tile writes the SDC to the default tile path."""
    tile_name = next(iter(cli.fabulousAPI.fabric.tileDic))
    run_cmd(cli, f"export_sdc {tile_name}")
    out = Path(cli.projectDir) / "Tile" / tile_name / f"{tile_name}_loop_break.sdc"
    assert out.exists()
    assert "FABulous SDC loop-break export" in out.read_text()


def test_export_sdc_output_override(cli: FABulousREPL, tmp_path: Path) -> None:
    """The -o flag overrides the default output path."""
    tile_name = next(iter(cli.fabulousAPI.fabric.tileDic))
    target = tmp_path / "custom.sdc"
    run_cmd(cli, f"export_sdc {tile_name} -o {target}")
    assert target.exists()


def test_export_sdc_requires_tile(cli: FABulousREPL) -> None:
    """export_sdc with no tile is rejected by argparse; no file is written."""
    run_cmd(cli, "export_sdc")
    assert list((Path(cli.projectDir) / "Tile").glob("**/*_loop_break.sdc")) == []


def test_export_sdc_unknown_tile_is_rejected(cli: FABulousREPL) -> None:
    """An unknown tile name raises a clean CommandError; no file is written."""
    run_cmd(cli, "export_sdc NotARealTile")
    assert not (
        Path(cli.projectDir) / "Tile" / "NotARealTile" / "NotARealTile_loop_break.sdc"
    ).exists()


def test_export_sdc_supertile_writes_per_subtile(cli: FABulousREPL) -> None:
    """A super tile name exports one SDC per constituent sub-tile."""
    super_name, super_tile = next(iter(cli.fabulousAPI.fabric.superTileDic.items()))
    run_cmd(cli, f"export_sdc {super_name}")
    tile_root = Path(cli.projectDir) / "Tile"
    for sub in super_tile.tiles:
        matches = list(tile_root.glob(f"**/{sub.name}_loop_break.sdc"))
        assert matches, f"no loop-break SDC written for sub-tile {sub.name}"


def test_export_sdc_supertile_output_dir(cli: FABulousREPL, tmp_path: Path) -> None:
    """For a super tile, -o is treated as a directory holding one SDC per sub-tile."""
    super_name, super_tile = next(iter(cli.fabulousAPI.fabric.superTileDic.items()))
    run_cmd(cli, f"export_sdc {super_name} -o {tmp_path}")
    for sub in super_tile.tiles:
        assert (tmp_path / f"{sub.name}_loop_break.sdc").exists()


def test_export_sdc_fvs_knobs_default(cli: FABulousREPL, mocker: MockerFixture) -> None:
    """Without flags, the FVS tuning knobs default to the module constants."""
    spy = mocker.patch("fabulous.fabulous_repl.cmd_macro.export_tile_sdc")
    tile_name = next(iter(cli.fabulousAPI.fabric.tileDic))
    run_cmd(cli, f"export_sdc {tile_name}")
    _, kwargs = spy.call_args
    assert kwargs["single_max"] == FVS_SINGLE_MAX
    assert kwargs["batch_fraction"] == FVS_BATCH_FRACTION


def test_export_sdc_fvs_knobs_override(
    cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """The --fvs-single-max/--fvs-batch-fraction flags reach export_tile_sdc."""
    spy = mocker.patch("fabulous.fabulous_repl.cmd_macro.export_tile_sdc")
    tile_name = next(iter(cli.fabulousAPI.fabric.tileDic))
    run_cmd(cli, f"export_sdc {tile_name} --fvs-single-max 50 --fvs-batch-fraction 0.1")
    _, kwargs = spy.call_args
    assert kwargs["single_max"] == 50
    assert kwargs["batch_fraction"] == 0.1
