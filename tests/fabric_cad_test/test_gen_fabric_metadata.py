"""Tests for fabric metadata export."""

from pathlib import Path

import pytest
import yaml

from fabulous.fabric_cad.gen_fabric_metadata import (
    SCHEMA_VERSION,
    MetadataFormat,
    _render_hdl_template,
    build_fabric_metadata,
    compute_bitstream_geometry,
    write_fabric_metadata,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, ConfigBitMode
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from tests.conftest import make_empty_tile


def _make_bel(module: str, config_bits: int = 4) -> Bel:
    return Bel(
        src=Path(f"{module}.v"),
        prefix="",
        module_name=module,
        internal=[("I", IO.INPUT), ("O", IO.OUTPUT)],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=config_bits,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )


def _make_logic_tile(
    name: str,
    *,
    bels: list[Bel] | None = None,
    tile_dir: Path | None = None,
    matrix_dir: Path | None = None,
) -> Tile:
    tile = make_empty_tile(
        name,
        pinOrderConfig={},
        tileDir=tile_dir if tile_dir is not None else Path(f"Tile/{name}"),
        matrixDir=(
            matrix_dir
            if matrix_dir is not None
            else Path(f"Tile/{name}/{name}_switch_matrix.list")
        ),
    )
    if bels is not None:
        tile.bels = bels
    tile.matrixConfigBits = 8
    return tile


def _make_fabric(**overrides: object) -> Fabric:
    """Build a Fabric that passes __post_init__ validation."""
    defaults: dict[str, object] = {
        "fabric_dir": Path("/proj/fabric.csv"),
        "frameBitsPerRow": 32,
        "maxFramesPerCol": 20,
        "frameSelectWidth": 5,
        "desync_flag": 20,
        "numberOfColumns": 3,
        "numberOfRows": 2,
        "rowSelectWidth": 5,
    }
    defaults.update(overrides)
    return Fabric(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def small_fabric() -> Fabric:
    """2x3 fabric: NULL corner, four LUT tiles, one IO tile."""
    lut = _make_logic_tile(
        "LUT4AB",
        bels=[
            Bel(
                src=Path("/proj/Tile/LUT4AB/LUT4c_frame_config.v"),
                prefix="",
                module_name="LUT4c_frame_config",
                internal=[("I", IO.INPUT), ("O", IO.OUTPUT)],
                external=[],
                configPort=[],
                sharedPort=[],
                configBit=19,
                belMap={},
                userCLK=False,
                ports_vectors={},
                carry={},
                localShared={},
            ),
            Bel(
                src=Path("/proj/Tile/LUT4AB/LUT4c_frame_config.v"),
                prefix="",
                module_name="LUT4c_frame_config",
                internal=[("I", IO.INPUT), ("O", IO.OUTPUT)],
                external=[],
                configPort=[],
                sharedPort=[],
                configBit=19,
                belMap={},
                userCLK=False,
                ports_vectors={},
                carry={},
                localShared={},
            ),
        ],
        tile_dir=Path("/proj/Tile/LUT4AB"),
        matrix_dir=Path("/proj/Tile/LUT4AB/LUT4AB_switch_matrix.list"),
    )
    io = _make_logic_tile(
        "W_IO",
        bels=[
            Bel(
                src=Path("/proj/Tile/W_IO/IOBUF.v"),
                prefix="",
                module_name="IOBUF",
                internal=[("I", IO.INPUT), ("O", IO.OUTPUT)],
                external=[],
                configPort=[],
                sharedPort=[],
                configBit=2,
                belMap={},
                userCLK=False,
                ports_vectors={},
                carry={},
                localShared={},
            )
        ],
        tile_dir=Path("/proj/Tile/W_IO"),
        matrix_dir=Path("/proj/Tile/W_IO/W_IO_switch_matrix.list"),
    )
    # grid (y major):
    # Y0: NULL, LUT4AB, LUT4AB
    # Y1: W_IO, LUT4AB, LUT4AB
    grid = [
        [None, lut, lut],
        [io, lut, lut],
    ]
    return _make_fabric(
        name="testFab",
        numberOfRows=2,
        numberOfColumns=3,
        tile=grid,
        tileDic={"LUT4AB": lut, "W_IO": io},
        configBitMode=ConfigBitMode.FRAME_BASED,
    )


class TestComputeBitstreamGeometry:
    """Bitstream size must match the bit_gen frame layout."""

    def test_demo_sized_fabric(self) -> None:
        # 10 cols x 16 rows matches the template demo layout.
        fabric = _make_fabric(numberOfRows=16, numberOfColumns=10)
        geo = compute_bitstream_geometry(fabric)
        # header 20 + desync 4 + 10*20*(4 + 14*4) = 24 + 200*60 = 12024
        assert geo["header_bytes"] == 20
        assert geo["desync_bytes"] == 4
        assert geo["data_rows"] == 14
        assert geo["bytes_per_frame"] == 60
        assert geo["length_bytes"] == 12024
        assert geo["length_words"] == 3006

    def test_minimal_rows(self) -> None:
        # With 2 rows, data_rows is 0: only frame-select words + header/desync.
        fabric = _make_fabric(numberOfRows=2, numberOfColumns=1)
        geo = compute_bitstream_geometry(fabric)
        assert geo["data_rows"] == 0
        assert geo["bytes_per_frame"] == 4
        # 20 + 1*20*4 + 4 = 104
        assert geo["length_bytes"] == 104
        assert geo["length_words"] == 26


class TestBuildFabricMetadata:
    """Structured inventory content."""

    def test_schema_and_geometry(self, small_fabric: Fabric) -> None:
        meta = build_fabric_metadata(small_fabric)
        assert meta["schema_version"] == SCHEMA_VERSION
        assert meta["name"] == "testFab"
        assert meta["fabric_csv"] == "fabric.csv"
        assert meta["geometry"] == {"columns": 3, "rows": 2}
        assert meta["configuration"]["mode"] == "FRAME_BASED"
        assert meta["configuration"]["frame_bits_per_row"] == 32
        assert meta["configuration"]["max_frames_per_col"] == 20
        assert meta["configuration"]["config_bits_capacity_per_column"] == 640
        assert "bitstream" in meta["configuration"]
        # 20 header + 3 cols * 20 frames * 4 bytes + 4 desync = 264
        assert meta["configuration"]["bitstream"]["length_bytes"] == 264

    def test_tile_and_primitive_counts(self, small_fabric: Fabric) -> None:
        meta = build_fabric_metadata(small_fabric)
        assert meta["tiles"]["counts"] == {
            "LUT4AB": 4,
            "NULL": 1,
            "W_IO": 1,
        }
        # 4 LUT tiles * 2 BELs + 1 IO tile * 1 BEL
        assert meta["primitives"]["counts"] == {
            "IOBUF": 1,
            "LUT4c_frame_config": 8,
        }
        assert meta["primitives"]["types"] == {
            "IOBUF": {"count": 1, "src": "Tile/W_IO/IOBUF.v"},
            "LUT4c_frame_config": {
                "count": 8,
                "src": "Tile/LUT4AB/LUT4c_frame_config.v",
            },
        }
        lut_type = meta["tiles"]["types"]["LUT4AB"]
        assert lut_type["count"] == 4
        assert lut_type["matrix_config_bits"] == 8
        # 8 matrix + 2*19 bel bits
        assert lut_type["config_bits"] == 8 + 38
        assert lut_type["tile_dir"] == "Tile/LUT4AB"
        assert lut_type["switch_matrix"] == "Tile/LUT4AB/LUT4AB_switch_matrix.list"
        assert lut_type["bels"] == [
            {
                "module": "LUT4c_frame_config",
                "count_per_tile": 2,
                "config_bits": 19,
                "src": "Tile/LUT4AB/LUT4c_frame_config.v",
            }
        ]

    def test_grid_is_row_major(self, small_fabric: Fabric) -> None:
        meta = build_fabric_metadata(small_fabric)
        assert meta["grid"] == [
            ["NULL", "LUT4AB", "LUT4AB"],
            ["W_IO", "LUT4AB", "LUT4AB"],
        ]


class TestWriteAndRender:
    """File writers and HDL renderers."""

    def test_write_all_formats(self, small_fabric: Fabric, tmp_path: Path) -> None:
        written = write_fabric_metadata(small_fabric, tmp_path)
        assert set(written) == set(MetadataFormat)
        assert written[MetadataFormat.YAML].name == "fabric_metadata.yaml"
        assert written[MetadataFormat.VERILOG].name == "testFab_defines.v"
        assert written[MetadataFormat.SYSTEMVERILOG].name == "testFab_pkg.sv"
        assert written[MetadataFormat.VHDL].name == "testFab_pkg.vhdl"
        for path in written.values():
            assert path.is_file()
            assert path.stat().st_size > 0

        yaml_path = written[MetadataFormat.YAML]
        loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert loaded["geometry"]["columns"] == 3
        assert loaded["primitives"]["counts"]["LUT4c_frame_config"] == 8

    def test_format_subset(self, small_fabric: Fabric, tmp_path: Path) -> None:
        written = write_fabric_metadata(
            small_fabric, tmp_path, formats=[MetadataFormat.YAML]
        )
        assert list(written) == [MetadataFormat.YAML]
        assert not (tmp_path / "testFab_defines.v").exists()
        assert not (tmp_path / "testFab_pkg.vhdl").exists()

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="is not a valid MetadataFormat"):
            MetadataFormat("json")

    def test_verilog_defines_content(self, small_fabric: Fabric) -> None:
        meta = build_fabric_metadata(small_fabric)
        text = _render_hdl_template("fabric_metadata_defines.v.j2", meta)
        assert "`define FABRIC_COLUMNS 3" in text
        assert "`define FABRIC_ROWS 2" in text
        assert "`define FABRIC_BITSTREAM_LENGTH_BYTES 264" in text
        assert "`define NUM_TILE_LUT4AB 4" in text
        assert "`define NUM_PRIM_LUT4c_frame_config 8" in text

    def test_systemverilog_package_content(self, small_fabric: Fabric) -> None:
        meta = build_fabric_metadata(small_fabric)
        text = _render_hdl_template("fabric_metadata_pkg.sv.j2", meta)
        assert "package testFab_pkg;" in text
        assert "parameter int FABRIC_COLUMNS = 3;" in text
        assert "parameter int NUM_TILE_W_IO = 1;" in text
        assert "parameter int NUM_PRIM_IOBUF = 1;" in text
        assert "endpackage : testFab_pkg" in text

    def test_vhdl_package_content(self, small_fabric: Fabric) -> None:
        meta = build_fabric_metadata(small_fabric)
        text = _render_hdl_template("fabric_metadata_pkg.vhdl.j2", meta)
        assert "package testFab_pkg is" in text
        assert "constant FABRIC_COLUMNS : integer := 3;" in text
        assert "constant NUM_TILE_W_IO : integer := 1;" in text
        assert "constant NUM_PRIM_IOBUF : integer := 1;" in text
        assert "constant FABRIC_BITSTREAM_LENGTH_BYTES : integer := 264;" in text
        assert "end package testFab_pkg;" in text

    def test_sanitize_identifier_in_counts(self) -> None:
        weird = _make_logic_tile(
            "tile-with-dash",
            bels=[_make_bel("1bad-name", 1)],
        )
        fabric = _make_fabric(
            name="fab",
            numberOfRows=2,
            numberOfColumns=1,
            tile=[[weird], [weird]],
            tileDic={"tile-with-dash": weird},
        )
        text = _render_hdl_template(
            "fabric_metadata_defines.v.j2", build_fabric_metadata(fabric)
        )
        assert "`define NUM_TILE_tile_with_dash 2" in text
        assert "`define NUM_PRIM_N_1bad_name 2" in text
