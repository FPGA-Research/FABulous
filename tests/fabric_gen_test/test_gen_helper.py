"""
Tests for helper functions in the fabric generation module.

This module tests helper functions like file conversion and bootstrapping utilities
that support the main fabric generation functionality.
"""

import pytest

from FABulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix


class TestGenHelper:
    """Test class for fabric generation helper functions."""

    @pytest.mark.parametrize(
        ("list_content", "expected_connections", "test_name"),
        [
            # Basic list file conversion
            (
                ["E1END[0|1],[N1BEG0|N1BEG1]\n", "LUT_A,N1BEG0\n"],
                {
                    "E1END0": ["N1BEG0"],
                    "E1END1": ["N1BEG1"],
                    "LUT_A": ["N1BEG0"],
                },
                "basic_conversion",
            ),
            # Complex multi-output conversion
            (
                [
                    "E1END[0|1],[N1BEG0|N1BEG1]\n",
                    "E2END[0|2|4],[S1BEG0|S1BEG1|S1BEG2]\n",
                    "LUT_A,N1BEG0\n",
                    "LUT_B,S1BEG1\n",
                ],
                {
                    "E1END0": ["N1BEG0", "N1BEG1"],
                    "E1END1": ["N1BEG0", "N1BEG1"],
                    "E2END0": ["S1BEG0", "S1BEG1", "S1BEG2"],
                    "E2END2": ["S1BEG0", "S1BEG1", "S1BEG2"],
                    "E2END4": ["S1BEG0", "S1BEG1", "S1BEG2"],
                    "LUT_A": ["N1BEG0"],
                    "LUT_B": ["S1BEG1"],
                },
                "complex_multi_output",
            ),
            # Single direct connection
            (
                ["LUT_OUT,FF_IN\n", "FF_OUT,TILE_OUT\n"],
                {
                    "LUT_OUT": ["FF_IN"],
                    "FF_OUT": ["TILE_OUT"],
                },
                "direct_connections",
            ),
            # Wide range connections
            (
                ["WIDE[0:7],[INPUT0|INPUT1|INPUT2|INPUT3]\n"],
                {
                    "WIDE0": ["INPUT0", "INPUT1", "INPUT2", "INPUT3"],
                    "WIDE1": ["INPUT0", "INPUT1", "INPUT2", "INPUT3"],
                    "WIDE2": ["INPUT0", "INPUT1", "INPUT2", "INPUT3"],
                    "WIDE3": ["INPUT0", "INPUT1", "INPUT2", "INPUT3"],
                    "WIDE4": ["INPUT0", "INPUT1", "INPUT2", "INPUT3"],
                    "WIDE5": ["INPUT0", "INPUT1", "INPUT2", "INPUT3"],
                    "WIDE6": ["INPUT0", "INPUT1", "INPUT2", "INPUT3"],
                    "WIDE7": ["INPUT0", "INPUT1", "INPUT2", "INPUT3"],
                },
                "wide_range_connections",
            ),
            # Mixed range and single connections
            (
                [
                    "N[1:3]BEG,[E1END0|E1END1]\n",
                    "S1BEG0,W1END0\n",
                    "CLK_IN,[LUT_CLK|FF_CLK]\n",
                ],
                {
                    "N1BEG": ["E1END0", "E1END1"],
                    "N2BEG": ["E1END0", "E1END1"],
                    "N3BEG": ["E1END0", "E1END1"],
                    "S1BEG0": ["W1END0"],
                    "CLK_IN": ["LUT_CLK", "FF_CLK"],
                },
                "mixed_range_single",
            ),
        ],
        ids=lambda x: x[2] if isinstance(x, tuple) and len(x) > 2 else str(x),
    )
    def test_list_file_conversion(
        self,
        default_fabric,
        default_tile,
        code_generator_factory,
        tmp_path,
        mocker,
        list_content,
        expected_connections,
        test_name,
    ):
        """Test conversion of .list files to CSV before processing with various scenarios."""
        # Setup list file
        list_file = tmp_path / f"test_matrix_{test_name}.list"
        default_tile.matrixDir = list_file
        csv_file = tmp_path / f"test_matrix_{test_name}.csv"

        # Create list file with test content
        with open(list_file, "w") as f:
            f.writelines(list_content)

        writer = code_generator_factory(".v")

        # Setup mocks using pytest-mock
        mock_bootstrap = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix"
        )
        mock_list2csv = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV"
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value=expected_connections,
        )

        # Execute the function
        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        # Verify conversion methods were called
        mock_bootstrap.assert_called_once_with(default_tile, csv_file)
        mock_list2csv.assert_called_once_with(list_file, csv_file)

        # Verify tile.matrixDir was updated
        assert default_tile.matrixDir == csv_file

    def test_bootstrap_switch_matrix(
        self, default_fabric, default_tile, code_generator_factory, tmp_path, mocker
    ):
        """Test the bootstrap switch matrix functionality for list files."""
        # Setup list file that will trigger bootstrap
        list_file = tmp_path / "test_matrix.list"
        default_tile.matrixDir = list_file

        # Create a list file
        with open(list_file, "w") as f:
            f.write("E1END[0|1],[N1BEG0|N1BEG1]\n")

        writer = code_generator_factory(".v")

        # Setup mocks to test bootstrap behavior
        mock_bootstrap = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix"
        )
        mock_list2csv = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV"
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value={
                "E1END0": ["N1BEG0"],
            },
        )

        # Execute the function
        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        # Verify bootstrap was called (should be called for list files after conversion)
        expected_csv_file = tmp_path / "test_matrix.csv"
        mock_bootstrap.assert_called_once_with(default_tile, expected_csv_file)
        mock_list2csv.assert_called_once_with(list_file, expected_csv_file)

    def test_file_format_detection(
        self, default_fabric, default_tile, code_generator_factory, tmp_path, mocker
    ):
        """Test that the system correctly detects different file formats."""
        writer = code_generator_factory(".v")

        # Test .list file format detection
        list_file = tmp_path / "test_matrix.list"
        default_tile.matrixDir = list_file
        list_file.write_text("E1END[0|1],[N1BEG0|N1BEG1]\n")

        mock_list2csv = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV"
        )
        mock_bootstrap = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix"
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value={"E1END0": ["N1BEG0"]},
        )

        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        # Verify list2CSV was called for .list files
        mock_list2csv.assert_called_once()
        mock_bootstrap.assert_called_once()

    def test_csv_file_processing(
        self, default_fabric, default_tile, code_generator_factory, tmp_path, mocker
    ):
        """Test that CSV files are processed directly without conversion."""
        # Setup CSV file
        csv_file = tmp_path / "test_matrix.csv"
        default_tile.matrixDir = csv_file

        with open(csv_file, "w") as f:
            f.write("DefaultTile,E1END0\n")
            f.write("N1BEG0,1\n")

        writer = code_generator_factory(".v")

        # Setup mocks
        mock_list2csv = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV"
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value={"E1END0": ["N1BEG0"]},
        )

        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        # Verify list2CSV was not called for CSV files
        mock_list2csv.assert_not_called()

        # Verify the tile matrixDir remains unchanged for CSV files
        assert default_tile.matrixDir == csv_file

    def test_matrix_dir_update_after_conversion(
        self, default_fabric, default_tile, code_generator_factory, tmp_path, mocker
    ):
        """Test that tile.matrixDir is correctly updated after file conversion."""
        # Setup list file
        list_file = tmp_path / "test_matrix.list"
        default_tile.matrixDir = list_file
        expected_csv_file = tmp_path / "test_matrix.csv"

        list_file.write_text("E1END[0|1],[N1BEG0|N1BEG1]\n")

        writer = code_generator_factory(".v")

        # Setup mocks
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix"
        )
        mocker.patch("FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV")
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value={"E1END0": ["N1BEG0"]},
        )

        # Store original path
        original_path = default_tile.matrixDir

        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        # Verify the matrixDir was updated from .list to .csv
        assert original_path == list_file
        assert default_tile.matrixDir == expected_csv_file
        assert default_tile.matrixDir.suffix == ".csv"

    def test_helper_function_integration(
        self, default_fabric, default_tile, code_generator_factory, tmp_path, mocker
    ):
        """Test integration of helper functions with list file processing."""
        # Setup file with list format
        list_file = tmp_path / "test_matrix.list"
        default_tile.matrixDir = list_file

        with open(list_file, "w") as f:
            f.write("E1END[0|1],[N1BEG0|N1BEG1]\n")
            f.write("LUT_A,N1BEG0\n")

        writer = code_generator_factory(".v")

        # Setup mocks - but don't mock the entire flow, just verify calls
        mock_bootstrap = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.bootstrapSwitchMatrix"
        )
        mock_list2csv = mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.list2CSV"
        )
        mocker.patch(
            "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
            return_value={"E1END0": ["N1BEG0"], "LUT_A": ["N1BEG0"]},
        )

        # Execute the function
        genTileSwitchMatrix(writer, default_fabric, default_tile, False)

        # Verify both helper functions were called
        expected_csv_file = tmp_path / "test_matrix.csv"
        mock_list2csv.assert_called_once_with(list_file, expected_csv_file)
        mock_bootstrap.assert_called_once_with(default_tile, expected_csv_file)
