"""Tests for assembling a project from a registered fabric and tile library."""

from pathlib import Path

import pytest
from fabulous_fabrics import FabricSource
from fabulous_tiles import TileLibrary, load_primitives, load_tile_library

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_repl.project_assets import copy_fabric, copy_tile_library


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, newline="")


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    """An asset tree shaped like the fabulous_tiles and fabulous_fabrics packages."""
    root = tmp_path / "assets"
    _write(root / "tiles/demo/demo.csv", "TileLibraryBegin\nTileLibraryEnd\n")
    _write(root / "tiles/demo/include/Base.csv", "NORTH,N1BEG,0,-1,N1END,4\n")
    _write(
        root / "tiles/demo/LUT/LUT.csv",
        "TILE,LUT,DEPRECATED\n"
        "BEL,../../../primitives/LUT4/fabulous/LUT4.{HDL_SUFFIX},LA_,,\n"
        "BEL,../../../primitives/LUT4/fabulous/LUT4.{HDL_SUFFIX},LB_,,\n"
        "EndTILE\n",
    )
    _write(
        root / "tiles/demo/DSP/DSP_bot/DSP_bot.csv",
        "TILE,DSP_bot\n"
        "BEL,../../../../primitives/MULADD/fabulous/MULADD.{HDL_SUFFIX}\n"
        "EndTILE\n",
    )
    for name in ("LUT4", "MULADD"):
        _write(
            root / f"primitives/{name}/fabulous/{name}.v", f"module {name}; endmodule\n"
        )
        _write(
            root / f"primitives/{name}/fabulous/{name}.vhdl", f"entity {name} is end;\n"
        )
    _write(
        root / "fabrics/demo/fabric.yaml", "description: Demo.\ntile_library: demo\n"
    )
    _write(root / "fabrics/demo/common/fabric.csv", "FabricBegin\nFabricEnd\n")
    _write(root / "fabrics/demo/verilog/Fabric/models_pack.v", "// verilog\n")
    _write(root / "fabrics/demo/vhdl/Fabric/models_pack.vhdl", "-- vhdl\n")
    return root


def _library(assets: Path) -> TileLibrary:
    return load_tile_library(
        assets / "tiles/demo",
        load_primitives(assets / "primitives"),
        assets / "primitives",
    )


@pytest.mark.parametrize(
    ("lang", "models_pack"),
    [
        (HDLType.VERILOG, "Fabric/models_pack.v"),
        (HDLType.VHDL, "Fabric/models_pack.vhdl"),
    ],
)
def test_copy_fabric_copies_common_then_language(
    assets: Path, tmp_path: Path, lang: HDLType, models_pack: str
) -> None:
    project = tmp_path / "proj"
    fabric = FabricSource.from_dir(assets / "fabrics/demo", {"demo": _library(assets)})
    copy_fabric(project, fabric, lang)
    assert (project / "fabric.csv").read_text() == "FabricBegin\nFabricEnd\n"
    assert (project / models_pack).is_file()
    assert not (project / "fabric.yaml").exists()


@pytest.mark.parametrize(
    ("lang", "suffix"), [(HDLType.VERILOG, "v"), (HDLType.VHDL, "vhdl")]
)
def test_copy_tile_library_localises_bel_rows(
    assets: Path, tmp_path: Path, lang: HDLType, suffix: str
) -> None:
    project = tmp_path / "proj"
    copy_tile_library(project, _library(assets), lang)
    tile = project / "Tile"
    assert (tile / "LUT/LUT.csv").read_text() == (
        "TILE,LUT,DEPRECATED\n"
        "BEL,./LUT4.{HDL_SUFFIX},LA_,,\n"
        "BEL,./LUT4.{HDL_SUFFIX},LB_,,\n"
        "EndTILE\n"
    )
    assert (tile / f"LUT/LUT4.{suffix}").is_file()
    assert (tile / "DSP/DSP_bot/DSP_bot.csv").read_text() == (
        "TILE,DSP_bot\nBEL,./MULADD.{HDL_SUFFIX}\nEndTILE\n"
    )
    assert (tile / f"DSP/DSP_bot/MULADD.{suffix}").is_file()
    assert (tile / "include/Base.csv").is_file()
    assert not (tile / "demo.csv").exists()


def test_copy_tile_library_keeps_crlf(assets: Path, tmp_path: Path) -> None:
    csv = assets / "tiles/demo/LUT/LUT.csv"
    csv.write_bytes(csv.read_bytes().replace(b"\n", b"\r\n"))
    project = tmp_path / "proj"
    copy_tile_library(project, _library(assets), HDLType.VERILOG)
    assert (
        b"BEL,./LUT4.{HDL_SUFFIX},LA_,,\r\n"
        in (project / "Tile/LUT/LUT.csv").read_bytes()
    )


def test_copied_files_are_writable_from_read_only_package(
    assets: Path, tmp_path: Path
) -> None:
    library = _library(assets)
    for path in assets.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    project = tmp_path / "proj"
    try:
        copy_tile_library(project, library, HDLType.VERILOG)
    finally:
        for path in assets.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
    for path in (project / "Tile").rglob("*"):
        assert path.stat().st_mode & 0o200, path


@pytest.mark.parametrize("lang", [HDLType.SYSTEM_VERILOG])
def test_copy_rejects_unsupported_language(
    assets: Path, tmp_path: Path, lang: HDLType
) -> None:
    library = _library(assets)
    fabric = FabricSource.from_dir(assets / "fabrics/demo", {"demo": library})
    with pytest.raises(ValueError, match=str(lang)):
        copy_tile_library(tmp_path / "proj", library, lang)
    with pytest.raises(ValueError, match=str(lang)):
        copy_fabric(tmp_path / "proj", fabric, lang)


def test_bel_name_clash_raises(assets: Path, tmp_path: Path) -> None:
    _write(assets / "primitives/other/fabulous/other.v", "module other; endmodule\n")
    _write(
        assets / "primitives/other/fabulous/LUT4.v", "module LUT4_other; endmodule\n"
    )
    _write(
        assets / "tiles/demo/LUT/LUT.csv",
        "TILE,LUT\n"
        "BEL,../../../primitives/LUT4/fabulous/LUT4.v\n"
        "BEL,../../../primitives/other/fabulous/LUT4.v\n"
        "EndTILE\n",
    )
    with pytest.raises(FileExistsError, match="LUT4.v"):
        copy_tile_library(tmp_path / "proj", _library(assets), HDLType.VERILOG)


# `A.v` sorts before `LUT.csv` and `LUT4.v` after it, so both copy orders are covered.
@pytest.mark.parametrize("primitive", ["A", "LUT4"])
def test_tile_file_clashing_with_bel_raises(
    assets: Path, tmp_path: Path, primitive: str
) -> None:
    _write(
        assets / f"primitives/{primitive}/fabulous/{primitive}.v",
        f"module {primitive}; endmodule\n",
    )
    _write(assets / f"tiles/demo/LUT/{primitive}.v", "module tile_local; endmodule\n")
    _write(
        assets / "tiles/demo/LUT/LUT.csv",
        f"TILE,LUT\nBEL,../../../primitives/{primitive}/fabulous/{primitive}"
        ".{HDL_SUFFIX}\nEndTILE\n",
    )
    with pytest.raises(FileExistsError, match=f"{primitive}.v"):
        copy_tile_library(tmp_path / "proj", _library(assets), HDLType.VERILOG)
