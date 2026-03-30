"""Tests for genTileSwitchMatrix.

Tests the csv_output_dir feature and the disableConfigBitsN feature
for switch matrix generation.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
from tests.fabric_gen_test.conftest import (
    create_switchmatrix_csv,
    create_switchmatrix_list,
)


class TestListFileCsvOutputDirectory:
    """Test class for csv_output_dir parameter in genTileSwitchMatrix.

    Note: These tests focus only on the CSV output path logic. The function
    is allowed to fail after CSV path logic executes since we're not testing
    full RTL generation.
    """

    def test_csv_written_to_custom_directory(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test that CSV is written to specified csv_output_dir for .list input."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        list_file = source_dir / "test_matrix.list"
        create_switchmatrix_list(list_file)

        custom_output_dir = tmp_path / "custom_output"
        default_tile.matrixDir = list_file

        mocker.patch(
            "fabulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix",
            side_effect=lambda tile, path: create_switchmatrix_csv(path, tile.name),
        )
        mocker.patch(
            "fabulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV",
        )

        with pytest.raises(AttributeError):
            genTileSwitchMatrix(
                None,
                default_fabric,
                default_tile,
                False,
                csv_output_dir=custom_output_dir,
            )

        expected_csv = custom_output_dir / "test_matrix.csv"
        assert expected_csv.exists()
        assert not (source_dir / "test_matrix.csv").exists()
        assert default_tile.matrixDir == expected_csv

    def test_default_writes_to_same_directory(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test backward compatibility: default writes CSV next to .list file."""
        list_file = tmp_path / "test_matrix.list"
        create_switchmatrix_list(list_file)
        default_tile.matrixDir = list_file

        mocker.patch(
            "fabulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix",
            side_effect=lambda tile, path: create_switchmatrix_csv(path, tile.name),
        )
        mocker.patch(
            "fabulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV",
        )

        with pytest.raises(AttributeError):
            genTileSwitchMatrix(None, default_fabric, default_tile, False)

        expected_csv = tmp_path / "test_matrix.csv"
        assert expected_csv.exists()
        assert default_tile.matrixDir == expected_csv

    def test_creates_nested_output_directory(
        self,
        default_fabric: Fabric,
        default_tile: Tile,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test that nested csv_output_dir is auto-created."""
        list_file = tmp_path / "test_matrix.list"
        create_switchmatrix_list(list_file)
        default_tile.matrixDir = list_file

        custom_output_dir = tmp_path / "nested" / "deeply" / "output"
        assert not custom_output_dir.exists()

        mocker.patch(
            "fabulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix",
            side_effect=lambda tile, path: create_switchmatrix_csv(path, tile.name),
        )
        mocker.patch(
            "fabulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV",
        )

        with pytest.raises(AttributeError):
            genTileSwitchMatrix(
                None,
                default_fabric,
                default_tile,
                False,
                csv_output_dir=custom_output_dir,
            )

        assert custom_output_dir.exists()
        assert (custom_output_dir / "test_matrix.csv").exists()

    def test_csv_input_ignores_csv_output_dir(
        self,
        default_tile: Tile,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test that csv_output_dir is ignored when input is already .csv."""
        csv_file = tmp_path / "source" / "test_matrix.csv"
        csv_file.parent.mkdir()
        create_switchmatrix_csv(csv_file, default_tile.name)

        custom_output_dir = tmp_path / "custom_output"
        custom_output_dir.mkdir()

        default_tile.matrixDir = csv_file

        mock_parse = mocker.patch(
            "fabulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value={},
        )

        with pytest.raises(AttributeError):
            genTileSwitchMatrix(
                None,
                mocker.MagicMock(),
                default_tile,
                False,
                csv_output_dir=custom_output_dir,
            )

        # Verify parseMatrix called with original .csv path
        mock_parse.assert_called_once()
        assert mock_parse.call_args[0][0] == csv_file

        # Verify tile.matrixDir unchanged and no new CSV created
        assert default_tile.matrixDir == csv_file
        assert not (custom_output_dir / "test_matrix.csv").exists()


class TestDisableConfigBitsN:
    """Test ConfigBits_N and S*N port presence based on disableConfigBitsN."""

    @pytest.mark.parametrize(
        ("disable_n", "expect_present"),
        [(False, True), (True, False)],
        ids=["configbits_n_enabled", "configbits_n_disabled"],
    )
    def test_switchmatrix_configbits_n_presence(
        self,
        switchmatrix_fabric: Fabric,
        switchmatrix_tile: Tile,
        mux4_connections: dict[str, list[str]],
        code_generator_factory: Callable[..., CodeGenerator],
        tmp_path: Path,
        mocker: MockerFixture,
        disable_n: bool,
        expect_present: bool,
    ) -> None:
        """Test ConfigBits_N and S*N port presence in switch matrix RTL."""
        switchmatrix_fabric.disableConfigBitsN = disable_n

        csv_file = tmp_path / f"{switchmatrix_tile.name}_matrix.csv"
        create_switchmatrix_csv(
            csv_file,
            switchmatrix_tile.name,
            destinations=list(mux4_connections.keys()),
            sources=list({s for srcs in mux4_connections.values() for s in srcs}),
        )
        switchmatrix_tile.matrixDir = csv_file

        mocker.patch(
            "fabulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value=mux4_connections,
        )

        writer = code_generator_factory(".v", f"{switchmatrix_tile.name}_switch_matrix")
        genTileSwitchMatrix(writer, switchmatrix_fabric, switchmatrix_tile, False)
        rtl = writer.outFileName.read_text()

        if expect_present:
            assert "ConfigBits_N" in rtl
            assert "S0N" in rtl
        else:
            assert "ConfigBits_N" not in rtl
            assert "S0N" not in rtl
            assert "S1N" not in rtl
