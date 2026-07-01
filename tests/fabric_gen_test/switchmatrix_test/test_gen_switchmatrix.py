"""Tests for genTileSwitchMatrix.

Tests the feature that allows users to redirect CSV output to a custom directory when
converting .list files to .csv for switch matrix generation, as well as the
disableConfigBitsN feature for switch matrix generation.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import (
    _unconnected_port_diagnostic,
    gen_super_tile_switch_matrix,
    genTileSwitchMatrix,
)
from fabulous.fabric_generator.parser.parse_csv import parsePortLine
from tests.conftest import make_empty_tile, make_muladd_bel, sjump_port
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
            genTileSwitchMatrix(None, default_tile, False)

        expected_csv = tmp_path / "test_matrix.csv"
        assert expected_csv.exists()
        assert default_tile.matrixDir == expected_csv

    def test_creates_nested_output_directory(
        self,
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


class TestSuperTileSwitchMatrixConstants:
    """The supertile switch matrix exposes GND/VCC/VDD constants like normal tiles.

    `gen_super_tile_switch_matrix` reuses the shared matrix-body generator, so a
    `supertile_matrix.list` may drive a BEL input from a constant (tie-off) or
    offer one as a mux option. This guards that behaviour against a refactor.
    """

    def _gen(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[[str, str], CodeGenerator],
        connections: list[tuple[str, str]],
    ) -> str:
        mat = tmp_path / "supertile_matrix.list"
        create_switchmatrix_list(mat, connections)
        bot = make_empty_tile(
            "DSP_bot",
            [sjump_port("x", IO.OUTPUT, wireCount=1)],
            tileDir=tmp_path,
            matrixDir=tmp_path / "DSP_bot_switch_matrix.list",
            pinOrderConfig={},
        )
        bel = make_muladd_bel([("SUPER_A0", IO.INPUT), ("SUPER_B0", IO.INPUT)])
        supertile = SuperTile(
            name="DSP",
            tileDir=tmp_path,
            tiles=[bot],
            tileMap=[[bot]],
            bels=[bel],
            supertile_matrix_dir=mat,
            supertile_matrix_config_bits=1,
        )
        writer = code_generator_factory(".v", "DSP_switch_matrix")
        gen_super_tile_switch_matrix(writer, supertile)
        return writer.outFileName.read_text()

    def test_constants_declared(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> None:
        rtl = self._gen(
            tmp_path, code_generator_factory, [("SUPER_A0", "[DSP_bot_A0]")]
        )
        assert "parameter GND0 = 1'b0;" in rtl
        assert "parameter VCC0 = 1'b1;" in rtl
        assert "parameter VDD0 = 1'b1;" in rtl

    def test_constant_tie_off(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> None:
        rtl = self._gen(tmp_path, code_generator_factory, [("SUPER_A0", "[GND0]")])
        assert "assign SUPER_A0 = GND0;" in rtl

    def test_constant_as_mux_input(
        self,
        tmp_path: Path,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> None:
        rtl = self._gen(
            tmp_path, code_generator_factory, [("SUPER_B0{2}", "[VCC0|DSP_bot_x0]")]
        )
        assert "SUPER_B0_input = {DSP_bot_x0,VCC0}" in rtl
        assert "cus_mux21 inst_cus_mux21_SUPER_B0" in rtl


class TestUnconnectedPortDiagnostic:
    """The 'not connected to anything' error should explain NULL-wire expansion.

    A NULL-terminated spanning wire expands to ``wires x distance`` nested wires.
    When a switch matrix leaves some of those nested wires unconnected, the
    diagnostic should point back to the originating wire spec instead of just
    naming the bare expanded wire.
    """

    def test_null_terminated_spanning_wire_explains_expansion(self) -> None:
        ports, _ = parsePortLine("SOUTH,X1_Y1_2_X1_Y4_port,0,3,NULL,16")

        hint = _unconnected_port_diagnostic(ports, "X1_Y1_2_X1_Y4_port16")

        assert "X1_Y1_2_X1_Y4_port" in hint
        assert "48" in hint  # wires (16) x distance (3)
        assert "16" in hint  # original wire count
        assert "3" in hint  # distance
        assert "both ends" in hint

    def test_both_ends_named_wire_gives_no_hint(self) -> None:
        ports, _ = parsePortLine("NORTH,N4BEG,0,-4,N4END,4")

        assert _unconnected_port_diagnostic(ports, "N4BEG0") == ""

    def test_null_terminated_single_distance_gives_no_hint(self) -> None:
        ports, _ = parsePortLine("NORTH,NULL,0,-1,N1END,4")

        assert _unconnected_port_diagnostic(ports, "N1END0") == ""

    def test_unknown_port_name_gives_no_hint(self) -> None:
        ports, _ = parsePortLine("SOUTH,X1_Y1_2_X1_Y4_port,0,3,NULL,16")

        assert _unconnected_port_diagnostic(ports, "not_a_real_wire0") == ""


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
        genTileSwitchMatrix(
            writer,
            switchmatrix_tile,
            False,
            disable_config_bits_n=switchmatrix_fabric.disableConfigBitsN,
        )
        rtl = writer.outFileName.read_text()

        if expect_present:
            assert "ConfigBits_N" in rtl
            assert "S0N" in rtl
        else:
            assert "ConfigBits_N" not in rtl
            assert "S0N" not in rtl
            assert "S1N" not in rtl
