"""Tests for switch matrix construction and generation."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.custom_exception import (
    InvalidSwitchMatrixDefinition,
    InvalidTileDefinition,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, MultiplexerStyle
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import (
    _unconnected_port_diagnostic,
    gen_super_tile_switch_matrix,
    genTileSwitchMatrix,
)
from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV, parsePortLine
from fabulous.fabric_generator.parser.parse_switchmatrix import parseMatrix
from fabulous.fabulous_settings import init_context
from tests.conftest import make_empty_tile, make_muladd_bel, sjump_port
from tests.fabric_gen_test.conftest import (
    create_switchmatrix_list,
    find_switch_matrix_tile,
)


class TestCanonicalListOrder:
    """A `.list` matrix is read once into canonical port/BEL signal order.

    The mux-output keys follow the canonical source order and each mux's inputs
    follow the canonical dest-column order (BEL output order here), independent
    of the order lines appear in the `.list`. `PreserveListOrder` instead keeps
    the `.list` order, reversed (MSB-first).
    """

    def _bel_and_list(self, tmp_path: Path) -> tuple[Bel, Path]:
        # BEL input `A` is the mux output; BEL outputs X, Y, Z are the mux
        # inputs, giving a canonical dest order of [X, Y, Z].
        bel = make_muladd_bel(
            [
                ("A", IO.INPUT),
                ("X", IO.OUTPUT),
                ("Y", IO.OUTPUT),
                ("Z", IO.OUTPUT),
            ]
        )
        list_file = tmp_path / "m.list"
        # Deliberately out of canonical order: Z, X, Y.
        list_file.write_text("A,Z\nA,X\nA,Y\n")
        return bel, list_file

    def test_default_uses_canonical_dest_order(self, tmp_path: Path) -> None:
        bel, list_file = self._bel_and_list(tmp_path)
        sm = SwitchMatrix.from_file(list_file, "T", ports=[], bels=[bel])
        assert list(sm.connections.keys()) == ["A"]
        assert sm.connections["A"] == ["X", "Y", "Z"]

    def test_preserve_list_order_keeps_reversed_list_order(
        self, tmp_path: Path
    ) -> None:
        bel, list_file = self._bel_and_list(tmp_path)
        sm = SwitchMatrix.from_file(
            list_file, "T", ports=[], bels=[bel], preserve_list_order=True
        )
        # .list order is Z, X, Y; MSB-first keeps its reverse.
        assert sm.connections["A"] == ["Y", "X", "Z"]


class TestListExport:
    """to_list_file writes one compact `{N}output,[inputs]` line per mux."""

    def test_compact_per_mux_format_round_trips(self, tmp_path: Path) -> None:
        sm = SwitchMatrix(
            matrix_file=Path("x.csv"),
            connections={"A_I": ["X", "Y"], "B_I": ["Z"], "C_I": []},
        )
        out = tmp_path / "m.list"
        sm.to_list_file(out)
        # One line per connected mux; inputs always written reversed (MSB-first);
        # the empty C_I is omitted.
        assert out.read_text() == "{2}A_I,[Y|X]\n{1}B_I,[Z]\n"
        # A preserve read recovers the exact input order.
        assert SwitchMatrix.from_file(
            out, "T", preserve_list_order=True
        ).connections == {
            "A_I": ["X", "Y"],
            "B_I": ["Z"],
        }

    def test_preserve_list_order_round_trips(self, tmp_path: Path) -> None:
        bel = make_muladd_bel(
            [("A", IO.INPUT), ("X", IO.OUTPUT), ("Y", IO.OUTPUT), ("Z", IO.OUTPUT)]
        )
        sm = SwitchMatrix(
            matrix_file=Path("x.csv"),
            connections={"A": ["Z", "Y", "X"]},
            preserve_list_order=True,
        )
        out = tmp_path / "m.list"
        sm.to_list_file(out)
        # Inputs are written reversed so a preserve-order (MSB-first) read
        # recovers the stored order.
        assert out.read_text() == "{3}A,[X|Y|Z]\n"
        back = SwitchMatrix.from_file(
            out, "T", ports=[], bels=[bel], preserve_list_order=True
        ).connections
        assert back["A"] == ["Z", "Y", "X"]


class TestCsvExportReaderDecides:
    """to_csv_file always encodes per-mux position; the reader applies the flag.

    Column headers are global (first-seen across rows), so an all-`1` CSV loses
    a mux whose input order differs from that column order. The CSV always
    encodes each input's 1-based descending position, and a preserve read
    recovers the exact order while a legacy read falls back to column order.
    """

    def test_preserve_read_recovers_order_legacy_read_uses_columns(
        self, tmp_path: Path
    ) -> None:
        # B's order [X, Y] differs from the global column order [Y, Z, X].
        conns = {"A": ["Y", "Z"], "B": ["X", "Y"]}
        sm = SwitchMatrix(matrix_file=Path("x.csv"), connections=conns)
        out = tmp_path / "m.csv"
        sm.to_csv_file(out, "T")
        # preserve read honours the encoded position -> exact per-mux order
        assert parseMatrix(out, preserve_list_order=True) == conns
        # legacy read treats every entry as 1 -> column order (B reordered)
        assert parseMatrix(out, preserve_list_order=False) == {
            "A": ["Y", "Z"],
            "B": ["Y", "X"],
        }


class TestSwitchMatrixValidation:
    """from_file validates connections against tile signals when ports are given."""

    def _bel(self) -> Bel:
        # BEL input A is a valid mux output; BEL output X a valid mux input.
        return make_muladd_bel([("A", IO.INPUT), ("X", IO.OUTPUT)])

    def test_csv_rejects_unknown_output(self, tmp_path: Path) -> None:
        csv = tmp_path / "m.csv"
        csv.write_text("T,X\nBOGUS,1\n")
        with pytest.raises(InvalidSwitchMatrixDefinition):
            SwitchMatrix.from_file(csv, "T", ports=[], bels=[self._bel()])

    def test_list_rejects_unknown_input(self, tmp_path: Path) -> None:
        lst = tmp_path / "m.list"
        lst.write_text("A,NOT_A_SIGNAL\n")
        with pytest.raises(InvalidSwitchMatrixDefinition):
            SwitchMatrix.from_file(lst, "T", ports=[], bels=[self._bel()])

    def test_without_ports_skips_validation(self, tmp_path: Path) -> None:
        # No tile context (e.g. the list_to_csv/csv_to_list CLI) -> no validation.
        csv = tmp_path / "m.csv"
        csv.write_text("T,X\nBOGUS,1\n")
        assert SwitchMatrix.from_file(csv, "T").connections == {"BOGUS": ["X"]}


class TestHdlSwitchMatrix:
    """Hand-written HDL matrices: only config bits are read, generation skipped."""

    def test_from_file_extracts_config_bits_only(self, tmp_path: Path) -> None:
        v = tmp_path / "T_switch_matrix.v"
        v.write_text("// NumberOfConfigBits: 7\nmodule T(); endmodule\n")
        sm = SwitchMatrix.from_file(v, "T")
        assert sm.connections == {}
        assert sm.no_config_bits == 7

    def test_missing_config_bits_defaults_to_zero(self, tmp_path: Path) -> None:
        v = tmp_path / "T_switch_matrix.vhdl"
        v.write_text("entity T is end T;\n")
        assert SwitchMatrix.from_file(v, "T").no_config_bits == 0

    def test_generation_skips_hdl_matrix(self, tmp_path: Path) -> None:
        v = tmp_path / "T_switch_matrix.v"
        v.write_text("// NumberOfConfigBits: 0\nmodule T(); endmodule\n")
        tile = make_empty_tile("T", tileDir=tmp_path, matrixDir=v, pinOrderConfig={})
        # No writer is needed: an HDL matrix returns before any RTL is emitted.
        # (A non-HDL matrix would dereference the None writer and raise.)
        genTileSwitchMatrix(None, tile, False)


class TestPreserveListOrderEndToEnd:
    """`PreserveListOrder` in the fabric CSV threads through to tile matrices."""

    def test_flag_reorders_but_preserves_connectivity(self, project: Path) -> None:
        init_context(project)
        default = parseFabricCSV(str(project / "fabric.csv"))

        fabric_csv = project / "fabric.csv"
        fabric_csv.write_text(
            fabric_csv.read_text().replace(
                "ParametersEnd", "PreserveListOrder,TRUE\nParametersEnd"
            )
        )
        preserved = parseFabricCSV(str(project / "fabric.csv"))

        default_conns = {
            t.name: t.switch_matrix.connections for t in default.tileDic.values()
        }
        preserved_conns = {
            t.name: t.switch_matrix.connections for t in preserved.tileDic.values()
        }

        # Same tiles, same mux outputs, same mux inputs - only input order may
        # change, proving PreserveListOrder is honoured without dropping links.
        assert default_conns.keys() == preserved_conns.keys()
        for name, d in default_conns.items():
            p = preserved_conns[name]
            assert list(d.keys()) == list(p.keys())
            for mux_out, inputs in d.items():
                assert set(inputs) == set(p[mux_out])

        # The flag must actually reorder at least one real (multi-input) mux.
        assert any(
            default_conns[name] != preserved_conns[name] for name in default_conns
        ), "PreserveListOrder=TRUE did not reorder any switch matrix"


class TestMissingMatrix:
    """A tile CSV with no MATRIX line is rejected at parse time."""

    def test_tile_without_matrix_raises(self, project: Path) -> None:
        init_context(project)
        # Pick a tile definition CSV that declares a switch matrix and drop it.
        tile_csv = next(
            p
            for p in (project / "Tile").rglob("*.csv")
            if any(line.startswith("MATRIX") for line in p.read_text().splitlines())
        )
        tile_csv.write_text(
            "\n".join(
                line
                for line in tile_csv.read_text().splitlines()
                if not line.startswith("MATRIX")
            )
        )
        with pytest.raises(InvalidTileDefinition):
            parseFabricCSV(str(project / "fabric.csv"))


_INPUT_ASSIGN = re.compile(r"assign\s+(\w+)_input\s*=\s*\{([^}]*)\};")


class TestPreserveListOrderGeneration:
    """PreserveListOrder must flip the generated mux-input vector order.

    Generation drives each `{port}_input` vector from the reversed connection
    list, so the flag's MSB-first reordering surfaces directly in the emitted
    `assign {port}_input = {...}` statements - the ordering a bitstream depends
    on. Parse/export coverage alone would not catch a generation regression.
    """

    def _generated_input_vectors(
        self,
        fabric_csv: Path,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> tuple[Tile, dict[str, list[str]]]:
        """Generate a tile's switch matrix and return its `{port}_input` RHS lists."""
        init_context(fabric_csv.parent)
        tile = find_switch_matrix_tile(parseFabricCSV(str(fabric_csv)))
        writer = code_generator_factory(".v", f"{tile.name}_switch_matrix")
        genTileSwitchMatrix(
            writer, tile, False, multiplexer_style=MultiplexerStyle.CUSTOM
        )
        rtl = writer.outFileName.read_text()
        return tile, {
            m.group(1): m.group(2).split(",") for m in _INPUT_ASSIGN.finditer(rtl)
        }

    def test_flag_flips_generated_input_vector_order(
        self,
        project: Path,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> None:
        fabric_csv = project / "fabric.csv"
        default_tile, default_inputs = self._generated_input_vectors(
            fabric_csv, code_generator_factory
        )

        fabric_csv.write_text(
            fabric_csv.read_text().replace(
                "ParametersEnd", "PreserveListOrder,TRUE\nParametersEnd"
            )
        )
        preserved_tile, preserved_inputs = self._generated_input_vectors(
            fabric_csv, code_generator_factory
        )

        # The emitted vector is the reversed connection list: generation must
        # faithfully mirror the (flag-ordered) connections, both ways.
        for tile, inputs in (
            (default_tile, default_inputs),
            (preserved_tile, preserved_inputs),
        ):
            for port, rhs in inputs.items():
                assert rhs == tile.switch_matrix.connections[port][::-1]

        # Same muxes generated, and the flag must actually flip at least one.
        assert default_inputs.keys() == preserved_inputs.keys()
        flipped = [
            p for p in default_inputs if default_inputs[p] != preserved_inputs[p]
        ]
        assert flipped, "PreserveListOrder=TRUE changed no generated mux-input vector"

        # Where a vector flips, the source set is identical - only order differs.
        for port in flipped:
            assert set(default_inputs[port]) == set(preserved_inputs[port])


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
            switch_matrix=SwitchMatrix.from_file(mat, "DSP"),
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
