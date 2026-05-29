"""Tests for the switch-block factorizer module."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer import (
    MuxReductionRule,
    SwitchBlockFactorizer,
    SwitchBlockFactorizerOptions,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes import (
    SwitchBlockFactorizerPass,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList

if TYPE_CHECKING:
    from collections.abc import Iterator


class _FakeTile:
    """Minimal FABulous tile test double."""

    def __init__(
        self,
        name: str,
        matrix_dir: Path,
        bel_config_bits: int = 0,
    ) -> None:
        self.name = name
        self.matrixDir = matrix_dir
        self.tileDir = matrix_dir.parent / f"{name}.csv"
        self.matrixConfigBits = 0
        self.bel_config_bits = bel_config_bits

    @property
    def globalConfigBits(self) -> int:
        """Return total fake config bits.

        Returns
        -------
        int
            Matrix plus BEL config bits.
        """
        return self.matrixConfigBits + self.bel_config_bits


class _FakeFabric:
    """Minimal FABulous fabric test double."""

    def __init__(self, tile: _FakeTile) -> None:
        self.tile = tile
        self.frameBitsPerRow = 8
        self.maxFramesPerCol = 8

    def getTileByName(self, tile_name: str) -> _FakeTile | None:
        """Return the fake tile by name.

        Parameters
        ----------
        tile_name : str
            Requested tile name.

        Returns
        -------
        _FakeTile | None
            Fake tile or ``None``.
        """
        return self.tile if tile_name == self.tile.name else None


class _FakeFab:
    """Minimal FABulous API test double."""

    def __init__(self, tile_csv: Path, tile: _FakeTile) -> None:
        self.tile_csv = tile_csv
        self.fabric = _FakeFabric(tile)
        self.fileExtension = ".v"
        self.output_file: Path | None = None
        self.load_count = 0

    def setWriterOutputFile(self, output_file: Path) -> None:
        """Record the active writer output file.

        Parameters
        ----------
        output_file : Path
            Output path.
        """
        self.output_file = output_file

    def loadFabric(self, fabric_csv: Path) -> None:
        """Refresh tile matrix metadata from the tile CSV.

        Parameters
        ----------
        fabric_csv : Path
            Fabric CSV path, unused by the fake API.
        """
        _ = fabric_csv
        self.load_count += 1
        matrix_path = _matrix_path_from_tile_csv(self.tile_csv)
        self.fabric.tile.matrixDir = matrix_path
        self.fabric.tile.matrixConfigBits = _estimate_list_config_bits(matrix_path)

    def genSwitchMatrix(self, tile_name: str) -> None:
        """Write fake switch-matrix RTL and CSV.

        Parameters
        ----------
        tile_name : str
            Tile name.
        """
        assert self.output_file is not None
        self.output_file.write_text(f"module {tile_name}_switch_matrix; endmodule\n")
        self.output_file.with_suffix(".csv").write_text(
            f"{tile_name},generated\n",
            encoding="utf-8",
        )

    def genConfigMem(self, tile_name: str, config_mem: Path) -> None:
        """Write fake config-memory artifacts.

        Parameters
        ----------
        tile_name : str
            Tile name.
        config_mem : Path
            Config-memory CSV path.
        """
        assert self.output_file is not None
        config_mem.write_text("Frame,ConfigBits_ranges\n", encoding="utf-8")
        self.output_file.write_text(f"module {tile_name}_ConfigMem; endmodule\n")

    def genTile(self, tile_name: str) -> None:
        """Write fake tile RTL.

        Parameters
        ----------
        tile_name : str
            Tile name.
        """
        assert self.output_file is not None
        self.output_file.write_text(f"module {tile_name}; endmodule\n")


def _fake_fpga_model(fab: _FakeFab) -> SimpleNamespace:
    """Return the bridge-shaped object expected by PnR modules."""
    return SimpleNamespace(user_design=object(), fab=fab)


def test_factorizer_rewrites_list_in_place_and_regenerates_csv() -> None:
    """Test list factorization, tile CSV update, and generated CSV replacement."""
    with _project("fac_tile") as project:
        tile_dir = project / "Tile" / "fac_tile"
        matrix_list = tile_dir / "fac_tile_switch_matrix.list"
        matrix_list.write_text(
            "{8}LA_I0,[N0|N1|E0|E1|S0|S1|W0|W1]\nKEEP,X0\n",
            encoding="utf-8",
        )
        stale_csv = tile_dir / "fac_tile_switch_matrix.csv"
        stale_csv.write_text("stale csv\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "fac_tile", matrix_list.name)
        tile = _FakeTile("fac_tile", matrix_list)
        fab = _FakeFab(tile_csv, tile)

        result = SwitchBlockFactorizer(
            SwitchBlockFactorizerOptions(
                tile_name="fac_tile",
                tile_dir=tile_dir,
                tile_csv=tile_csv,
                switch_matrix=matrix_list,
                global_reduction=1,
                track_progress=False,
            )
        ).run(_fake_fpga_model(fab))

        list_text = matrix_list.read_text(encoding="utf-8")
        tile_csv_text = tile_csv.read_text(encoding="utf-8")
        assert "{4}J_FAC_G0_0_BEG0,[N0|N1|E0|E1]" in list_text
        assert "{4}J_FAC_G0_1_BEG0,[S0|S1|W0|W1]" in list_text
        assert "{2}LA_I0,[J_FAC_G0_0_END0|J_FAC_G0_1_END0]" in list_text
        assert "JUMP,J_FAC_G0_0_BEG,0,0,J_FAC_G0_0_END,1," in tile_csv_text
        assert "MATRIX,./fac_tile_switch_matrix.list" in tile_csv_text
        assert stale_csv.read_text(encoding="utf-8") == "fac_tile,generated\n"
        assert result.stats.added_jump_wires == 2
        assert result.stats.max_fanin_before == 8
        assert result.stats.max_fanin_after == 4
        assert result.stats.reachability_preserved
        assert fab.load_count == 1


def test_factorizer_accepts_csv_and_normalizes_to_list() -> None:
    """Test CSV input parsing and normalized list output."""
    with _project("csv_tile") as project:
        tile_dir = project / "Tile" / "csv_tile"
        matrix_csv = tile_dir / "csv_tile_switch_matrix.csv"
        matrix_csv.write_text(
            "csv_tile,N0,N1,E0,E1\nLA_I0,1,1,1,1,#,4\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "csv_tile", matrix_csv.name)
        tile = _FakeTile("csv_tile", matrix_csv)
        fab = _FakeFab(tile_csv, tile)

        result = SwitchBlockFactorizer(
            SwitchBlockFactorizerOptions(
                tile_name="csv_tile",
                tile_dir=tile_dir,
                tile_csv=tile_csv,
                switch_matrix=matrix_csv,
                global_reduction=1,
                track_progress=False,
            )
        ).run(_fake_fpga_model(fab))

        normalized_list = tile_dir / "csv_tile_switch_matrix.list"
        assert normalized_list.is_file()
        assert result.source_matrix == matrix_csv
        assert result.switch_matrix_list == normalized_list
        assert "MATRIX,./csv_tile_switch_matrix.list" in tile_csv.read_text(
            encoding="utf-8"
        )
        assert "{2}J_FAC_G0_0_BEG0,[N0|N1]" in normalized_list.read_text(
            encoding="utf-8"
        )
        assert matrix_csv.read_text(encoding="utf-8") == "csv_tile,generated\n"


def test_factorizer_applies_global_before_explicit_rules() -> None:
    """Test explicit rules operate after global factorization."""
    with _project("rule_tile") as project:
        tile_dir = project / "Tile" / "rule_tile"
        matrix_list = tile_dir / "rule_tile_switch_matrix.list"
        sources = "|".join(f"S{i}" for i in range(16))
        matrix_list.write_text(f"{{16}}OUT,[{sources}]\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "rule_tile", matrix_list.name)
        tile = _FakeTile("rule_tile", matrix_list)
        fab = _FakeFab(tile_csv, tile)

        result = SwitchBlockFactorizer(
            SwitchBlockFactorizerOptions(
                tile_name="rule_tile",
                tile_dir=tile_dir,
                tile_csv=tile_csv,
                switch_matrix=matrix_list,
                global_reduction=1,
                reduction_rules=[MuxReductionRule(from_fanin=8, to_fanin=4)],
                track_progress=False,
            )
        ).run(_fake_fpga_model(fab))

        assert result.stats.added_jump_wires == 6
        assert result.stats.max_fanin_after == 4
        text = matrix_list.read_text(encoding="utf-8")
        assert "{2}OUT,[J_FAC_G0_0_END0|J_FAC_G0_1_END0]" in text
        assert "{2}J_FAC_G0_0_BEG0,[J_FAC_R0_2_END0|J_FAC_R0_3_END0]" in text
        assert "{4}J_FAC_R0_2_BEG0,[S0|S1|S2|S3]" in text


def test_factorizer_rejects_too_many_jump_wires_before_rewrite() -> None:
    """Test max_added_jump_wires prevents in-place mutation."""
    with _project("limit_tile") as project:
        tile_dir = project / "Tile" / "limit_tile"
        matrix_list = tile_dir / "limit_tile_switch_matrix.list"
        original = "{8}LA_I0,[N0|N1|E0|E1|S0|S1|W0|W1]\n"
        matrix_list.write_text(original, encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "limit_tile", matrix_list.name)
        tile = _FakeTile("limit_tile", matrix_list)
        fab = _FakeFab(tile_csv, tile)

        message = ""
        try:
            SwitchBlockFactorizer(
                SwitchBlockFactorizerOptions(
                    tile_name="limit_tile",
                    tile_dir=tile_dir,
                    tile_csv=tile_csv,
                    switch_matrix=matrix_list,
                    global_reduction=1,
                    max_added_jump_wires=1,
                    track_progress=False,
                )
            ).run(_fake_fpga_model(fab))
        except RuntimeError as exc:
            message = str(exc)

        assert "max_added_jump_wires" in message
        assert matrix_list.read_text(encoding="utf-8") == original


def test_factorizer_uses_config_bit_capacity_override() -> None:
    """Test the capacity override replaces the loaded fabric capacity."""
    with _project("capacity_tile") as project:
        tile_dir = project / "Tile" / "capacity_tile"
        matrix_list = tile_dir / "capacity_tile_switch_matrix.list"
        matrix_list.write_text("OUT,A\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "capacity_tile", matrix_list.name)
        tile = _FakeTile("capacity_tile", matrix_list, bel_config_bits=70)
        fab = _FakeFab(tile_csv, tile)

        result = SwitchBlockFactorizer(
            SwitchBlockFactorizerOptions(
                tile_name="capacity_tile",
                tile_dir=tile_dir,
                tile_csv=tile_csv,
                switch_matrix=matrix_list,
                global_reduction=0,
                config_bit_capacity_override=80,
                track_progress=False,
            )
        ).run(_fake_fpga_model(fab))

        assert result.stats.total_config_bits_after == 70


def test_factorizer_pass_exposes_result_data() -> None:
    """Test PnR pass wrapper stores structured result data."""
    with _project("pass_tile") as project:
        tile_dir = project / "Tile" / "pass_tile"
        matrix_list = tile_dir / "pass_tile_switch_matrix.list"
        matrix_list.write_text("{4}OUT,[A|B|C|D]\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "pass_tile", matrix_list.name)
        tile = _FakeTile("pass_tile", matrix_list)
        fab = _FakeFab(tile_csv, tile)
        switch_pass = SwitchBlockFactorizerPass(
            tile_name="pass_tile",
            tile_dir=tile_dir,
            tile_csv=tile_csv,
            switch_matrix=matrix_list,
            global_reduction=1,
            track_progress=False,
        )

        switch_pass.run_on(_fake_fpga_model(fab))

        assert switch_pass.result_data is not None
        assert switch_pass.result_data.stats.added_jump_wires == 2
        assert "Switch Block Factorizer Report" in switch_pass.report_summary


@contextmanager
def _project(tile_name: str) -> Iterator[Path]:
    """Create a temporary FABulous-like project.

    Parameters
    ----------
    tile_name : str
        Tile directory name.

    Yields
    ------
    Path
        Project directory.
    """
    with TemporaryDirectory(prefix="switch_block_factorizer_") as td:
        project = Path(td)
        (project / "Tile" / tile_name).mkdir(parents=True)
        (project / "fabric.csv").write_text(
            f"FabricBegin\nTile,./Tile/{tile_name}/{tile_name}.csv\nFabricEnd\n",
            encoding="utf-8",
        )
        yield project


def _write_tile_csv(tile_dir: Path, tile_name: str, matrix_name: str) -> Path:
    """Write a small tile CSV.

    Parameters
    ----------
    tile_dir : Path
        Tile directory.
    tile_name : str
        Tile name.
    matrix_name : str
        Matrix filename relative to the tile directory.

    Returns
    -------
    Path
        Tile CSV path.
    """
    tile_csv = tile_dir / f"{tile_name}.csv"
    tile_csv.write_text(
        "\n".join(
            [
                f"TILE,{tile_name}",
                "NORTH,N0,0,-1,S0,1",
                f"MATRIX,./{matrix_name}",
                "EndTILE",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return tile_csv


def _matrix_path_from_tile_csv(tile_csv: Path) -> Path:
    """Return the matrix path from a tile CSV.

    Parameters
    ----------
    tile_csv : Path
        Tile CSV path.

    Returns
    -------
    Path
        Matrix path.

    Raises
    ------
    ValueError
        If the tile CSV has no MATRIX row.
    """
    for line in tile_csv.read_text(encoding="utf-8").splitlines():
        fields = [field.strip() for field in line.split(",")]
        if fields and fields[0] == "MATRIX":
            return (tile_csv.parent / fields[1]).resolve()
    raise ValueError("tile CSV has no MATRIX row")


def _estimate_list_config_bits(matrix_list: Path) -> int:
    """Estimate config bits from a FABulous list file.

    Parameters
    ----------
    matrix_list : Path
        Switch-matrix list file.

    Returns
    -------
    int
        Estimated switch-matrix config bits.
    """
    connections = parseList(matrix_list, collect="source")
    return sum(
        (len(sources) - 1).bit_length()
        for sources in connections.values()
        if len(sources) >= 2
    )


if __name__ == "__main__":
    test_factorizer_rewrites_list_in_place_and_regenerates_csv()
    test_factorizer_accepts_csv_and_normalizes_to_list()
    test_factorizer_applies_global_before_explicit_rules()
    test_factorizer_rejects_too_many_jump_wires_before_rewrite()
    test_factorizer_uses_config_bit_capacity_override()
    test_factorizer_pass_exposes_result_data()
