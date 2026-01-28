"""Tests for csv_output_dir parameter in genTileSwitchMatrix.

Tests the feature that allows users to redirect CSV output to a custom
directory when converting .list files to .csv for switch matrix generation.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
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
        connections_factory: Callable[..., dict[str, list[str]]],
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
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix",
            side_effect=lambda tile, path: create_switchmatrix_csv(path, tile.name),
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV",
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value=connections_factory(),
        )

        with pytest.raises(AttributeError):
            genTileSwitchMatrix(
                None, default_fabric, default_tile, False,
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
        connections_factory: Callable[..., dict[str, list[str]]],
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test backward compatibility: default writes CSV next to .list file."""
        list_file = tmp_path / "test_matrix.list"
        create_switchmatrix_list(list_file)
        default_tile.matrixDir = list_file

        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix",
            side_effect=lambda tile, path: create_switchmatrix_csv(path, tile.name),
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV",
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value=connections_factory(),
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
        connections_factory: Callable[..., dict[str, list[str]]],
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
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix",
            side_effect=lambda tile, path: create_switchmatrix_csv(path, tile.name),
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV",
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value=connections_factory(),
        )

        with pytest.raises(AttributeError):
            genTileSwitchMatrix(
                None, default_fabric, default_tile, False,
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
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value={},
        )

        with pytest.raises(AttributeError):
            genTileSwitchMatrix(
                None, mocker.MagicMock(), default_tile, False,
                csv_output_dir=custom_output_dir,
            )

        # Verify parseMatrix called with original .csv path
        mock_parse.assert_called_once()
        assert mock_parse.call_args[0][0] == csv_file

        # Verify tile.matrixDir unchanged and no new CSV created
        assert default_tile.matrixDir == csv_file
        assert not (custom_output_dir / "test_matrix.csv").exists()
