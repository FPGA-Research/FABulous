"""Ad-hoc tests for FF materialization."""

from pathlib import Path
from tempfile import TemporaryDirectory

from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.ff_materializer_pass import (
    FfMaterializerPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabulous_cli.helper import setup_logger

setup_logger(verbosity=0, debug=False)


def test_single_dff_materialization() -> None:
    """Test one scalar FF is replaced by one tile instance."""
    with TemporaryDirectory(prefix="ff_mat_single_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        assert result.result_data.stats.inserted_tiles == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        tile_cells = _cells_by_type(cells, "reg_tile")
        assert len(tile_cells) == 1
        assert {"I0", "Q0", "CLK", "ConfigBits"} <= set(tile_cells[0]["connections"])
        assert tile_cells[0]["connections"]["ConfigBits"][2] == "1"
        bridge.run_pass("hierarchy -top base -check")


def test_two_ffs_pack_into_one_tile() -> None:
    """Test two independent FFs can fill two lanes in one tile."""
    with TemporaryDirectory(prefix="ff_mat_pack_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert len(_cells_by_type(cells, "reg_tile")) == 1
        assert not _has_cell_type(cells, "$dff")


def test_pack_disabled_creates_one_tile_per_ff() -> None:
    """Test disabling packing creates one replacement tile for each FF."""
    with TemporaryDirectory(prefix="ff_mat_no_pack_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=False)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 2
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert len(_cells_by_type(cells, "reg_tile")) == 2


def test_ff_chain_is_preserved_when_packed() -> None:
    """Test a two-FF pipeline keeps the intermediate net between lanes."""
    with TemporaryDirectory(prefix="ff_mat_chain_") as td:
        tmp_dir = Path(td)
        base = _write_chain_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        _run_materializer(bridge, tile, pack=True)

        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "reg_tile")[0]
        output_nets = {
            tuple(tile_cell["connections"]["Q0"]),
            tuple(tile_cell["connections"]["Q1"]),
        }
        input_nets = {
            tuple(tile_cell["connections"]["I0"]),
            tuple(tile_cell["connections"]["I1"]),
        }
        assert output_nets & input_nets
        assert not _has_cell_type(cells, "$dff")


def test_dffe_with_variable_enable_is_skipped_by_default() -> None:
    """Test variable enable FFs are skipped unless a lane opts in."""
    with TemporaryDirectory(prefix="ff_mat_dffe_skip_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, include_enable=False)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 0
        assert result.result_data.stats.skipped_control_mismatch == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert _has_cell_type(cells, "$dffe")


def test_dffe_enable_can_be_wired_to_tile() -> None:
    """Test enabled FFs can wire their enable signal to a tile port."""
    with TemporaryDirectory(prefix="ff_mat_dffe_wire_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, include_enable=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "reg_tile")[0]
        assert "EN" in tile_cell["connections"]
        assert not _has_cell_type(cells, "$dffe")


def test_sdff_reset_can_be_wired_to_tile() -> None:
    """Test reset FFs can wire their reset signal to a tile port."""
    with TemporaryDirectory(prefix="ff_mat_sdff_wire_") as td:
        tmp_dir = Path(td)
        base = _write_sdff_base(tmp_dir, reset_value=0)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, include_reset=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "reg_tile")[0]
        assert "SR" in tile_cell["connections"]
        assert not _has_cell_type(cells, "$sdff")


def test_reset_value_mismatch_is_skipped() -> None:
    """Test reset value mismatch prevents materialization."""
    with TemporaryDirectory(prefix="ff_mat_reset_mismatch_") as td:
        tmp_dir = Path(td)
        base = _write_sdff_base(tmp_dir, reset_value=1)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, include_reset=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 0
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert _has_cell_type(cells, "$sdff")


def test_config_conflict_prevents_packing_second_ff() -> None:
    """Test conflicting config bits start a second replacement tile."""
    with TemporaryDirectory(prefix="ff_mat_config_conflict_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(
            bridge,
            tile,
            pack=True,
            second_lane_config={"ConfigBits[2]": 0},
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 2


def test_max_replacements_limits_materialization() -> None:
    """Test max_replacements caps replaced FFs."""
    with TemporaryDirectory(prefix="ff_mat_limit_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, max_replacements=1)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        assert result.result_data.stats.skipped_limit == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert _has_cell_type(cells, "$dff")


def test_escaped_ff_name_materialization() -> None:
    """Test generated escaped FF names round-trip through the writer."""
    with TemporaryDirectory(prefix="ff_mat_escaped_") as td:
        tmp_dir = Path(td)
        base = _write_escaped_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")


def _run_materializer(
    bridge: PyosysBridge,
    tile: Path,
    pack: bool,
    include_enable: bool = True,
    include_reset: bool = False,
    max_replacements: int | None = None,
    second_lane_config: dict[str, int | bool] | None = None,
) -> FfMaterializerPass:
    """Run the materializer pass with a common two-lane tile.

    Parameters
    ----------
    bridge : PyosysBridge
        Design bridge to mutate.
    tile : Path
        Tile Verilog path.
    pack : bool
        Whether packing is enabled.
    include_enable : bool
        Whether lanes accept enabled FFs.
    include_reset : bool
        Whether lanes accept reset FFs.
    max_replacements : int | None
        Optional replacement cap.
    second_lane_config : dict[str, int | bool] | None
        Optional second-lane config override.

    Returns
    -------
    FfMaterializerPass
        Executed pass.
    """
    result = FfMaterializerPass(
        tile_verilog_path=tile,
        tile_top_name="reg_tile",
        tile_inputs=["I0", "I1", "CLK", "EN", "SR"],
        tile_outputs=["Q0", "Q1"],
        tile_config_prefixes=["ConfigBits"],
        lanes=[
            {
                "data_port": "I0",
                "output_port": "Q0",
                "clock_port": "CLK",
                "include_enable_ff": include_enable,
                "enable_tile_port": "EN",
                "enable_neutral": 1,
                "include_reset_ff": include_reset,
                "reset_tile_port": "SR",
                "reset_neutral": 0,
                "reset_kind": "sync",
                "reset_value": 0,
                "config": {"ConfigBits[2]": 1},
                "params": {"MODE": "ff_only"},
            },
            {
                "data_port": "I1",
                "output_port": "Q1",
                "clock_port": "CLK",
                "include_enable_ff": include_enable,
                "enable_tile_port": "EN",
                "enable_neutral": 1,
                "include_reset_ff": include_reset,
                "reset_tile_port": "SR",
                "reset_neutral": 0,
                "reset_kind": "sync",
                "reset_value": 0,
                "config": second_lane_config or {"ConfigBits[3]": 1},
                "params": {"MODE": "ff_only"},
            },
        ],
        pack_multiple_ffs_per_tile=pack,
        max_replacements=max_replacements,
        top_name="base",
        track_progress=False,
    )
    result.run_on(bridge)
    return result


def _load_base(base: Path) -> PyosysBridge:
    """Load and process a base design.

    Parameters
    ----------
    base : Path
        Base Verilog path.

    Returns
    -------
    PyosysBridge
        Processed design bridge.
    """
    bridge = PyosysBridge(debug=False)
    bridge.read_verilog_paths([base])
    bridge.run_pass("proc")
    return bridge


def _write_tile(tmp_dir: Path) -> Path:
    """Write a two-lane configurable tile model.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "reg_tile.v"
    path.write_text(
        """
module reg_tile #(
  parameter MODE = "comb"
) (
  input I0,
  input I1,
  input CLK,
  input EN,
  input SR,
  input [7:0] ConfigBits,
  output Q0,
  output Q1
);
  assign Q0 = I0 ^ ConfigBits[0];
  assign Q1 = I1 ^ ConfigBits[1];
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_single_dff_base(tmp_dir: Path) -> Path:
    """Write a design with one inferred DFF.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_single.v"
    path.write_text(
        """
module base(input clk, input d, output reg q);
  always @(posedge clk) q <= d;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_two_dff_base(tmp_dir: Path) -> Path:
    """Write a design with two independent inferred DFFs."""
    path = tmp_dir / "base_two.v"
    path.write_text(
        """
module base(input clk, input d0, input d1, output reg q0, output reg q1);
  always @(posedge clk) begin
    q0 <= d0;
    q1 <= d1;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_chain_base(tmp_dir: Path) -> Path:
    """Write a design with a two-FF pipeline."""
    path = tmp_dir / "base_chain.v"
    path.write_text(
        """
module base(input clk, input d, output q0, output q1);
  reg r0;
  reg r1;
  assign q0 = r0;
  assign q1 = r1;
  always @(posedge clk) begin
    r0 <= d;
    r1 <= r0;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_dffe_base(tmp_dir: Path) -> Path:
    """Write a design with an explicit Yosys ``$dffe`` cell."""
    path = tmp_dir / "base_dffe.v"
    path.write_text(
        """
module base(input clk, input en, input d, output q);
  \\$dffe #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1),
    .EN_POLARITY(1'b1)
  ) u_ff (
    .CLK(clk),
    .EN(en),
    .D(d),
    .Q(q)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_sdff_base(tmp_dir: Path, reset_value: int) -> Path:
    """Write a design with an explicit Yosys ``$sdff`` cell."""
    path = tmp_dir / "base_sdff.v"
    path.write_text(
        f"""
module base(input clk, input rst, input d, output q);
  \\$sdff #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1),
    .SRST_POLARITY(1'b1),
    .SRST_VALUE(1'b{reset_value})
  ) u_ff (
    .CLK(clk),
    .SRST(rst),
    .D(d),
    .Q(q)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_escaped_base(tmp_dir: Path) -> Path:
    """Write a design with an escaped generated-style FF name."""
    path = tmp_dir / "base_escaped.v"
    path.write_text(
        """
module base(input clk, input d, output q);
  \\$dff #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1)
  ) \\$auto$ff.materializer$1.slice[0]  (
    .CLK(clk),
    .D(d),
    .Q(q)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _cells_by_type(
    cells: dict[str, dict[str, object]],
    cell_type: str,
) -> list[dict[str, object]]:
    """Return cells with a selected type."""
    return [
        cell
        for cell in cells.values()
        if str(cell.get("type")).removeprefix("\\") == cell_type
    ]


def _has_cell_type(cells: dict[str, dict[str, object]], cell_type: str) -> bool:
    """Return whether a netlist dictionary contains a cell type."""
    return any(
        str(cell.get("type")).removeprefix("\\") == cell_type for cell in cells.values()
    )


def main() -> None:
    """Run all FF materializer tests."""
    test_single_dff_materialization()
    test_two_ffs_pack_into_one_tile()
    test_pack_disabled_creates_one_tile_per_ff()
    test_ff_chain_is_preserved_when_packed()
    test_dffe_with_variable_enable_is_skipped_by_default()
    test_dffe_enable_can_be_wired_to_tile()
    test_sdff_reset_can_be_wired_to_tile()
    test_reset_value_mismatch_is_skipped()
    test_config_conflict_prevents_packing_second_ff()
    test_max_replacements_limits_materialization()
    test_escaped_ff_name_materialization()


if __name__ == "__main__":
    main()
