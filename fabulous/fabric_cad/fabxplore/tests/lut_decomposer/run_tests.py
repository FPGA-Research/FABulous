"""Ad-hoc tests for LUT decomposition."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_decomposer_pass import (
    LutDecomposerPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabulous_cli.helper import setup_logger

setup_logger(verbosity=0, debug=False)


def test_lut3_decomposes_to_two_lut2_and_equiv() -> None:
    """Test LUT3 decomposition into two LUT2 cofactors."""
    with TemporaryDirectory(prefix="lut_decomposer_lut3_") as td:
        tmp_dir = Path(td)
        base = _write_lut3_base(tmp_dir)
        mux = _write_mux4_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        result = LutDecomposerPass(
            source_lut_widths=[3],
            leaf_lut_width=2,
            mux_verilog_path=mux,
            mux_top_name="mux4_tile",
            mux_data_inputs=["A", "B", "C", "D"],
            mux_select_inputs=["S"],
            mux_outputs=["Y2", "Y4"],
            mux_configs=["cfg"],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.decomposed_luts == 1
        assert result.result_data.stats.generated_leaf_luts == 2

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, mux, "base")


def test_lut4_decomposes_to_four_lut2_and_equiv() -> None:
    """Test LUT4 decomposition into four LUT2 cofactors."""
    with TemporaryDirectory(prefix="lut_decomposer_lut4_") as td:
        tmp_dir = Path(td)
        base = _write_lut4_base(tmp_dir)
        mux = _write_mux4_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        result = LutDecomposerPass(
            source_lut_widths=[4],
            leaf_lut_width=2,
            mux_verilog_path=mux,
            mux_top_name="mux4_tile",
            mux_data_inputs=["A", "B", "C", "D"],
            mux_select_inputs=["S"],
            mux_outputs=["Y2", "Y4"],
            mux_configs=["cfg"],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.decomposed_luts == 1
        assert result.result_data.stats.generated_leaf_luts == 4

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, mux, "base")


def test_mux_shape_cache_is_used() -> None:
    """Test multiple same-width LUTs reuse one mux SAT solve."""
    with TemporaryDirectory(prefix="lut_decomposer_cache_") as td:
        tmp_dir = Path(td)
        base = _write_two_lut3_base(tmp_dir)
        mux = _write_mux4_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        result = LutDecomposerPass(
            source_lut_widths=[3],
            leaf_lut_width=2,
            mux_verilog_path=mux,
            mux_top_name="mux4_tile",
            mux_data_inputs=["A", "B", "C", "D"],
            mux_select_inputs=["S"],
            mux_outputs=["Y2", "Y4"],
            mux_configs=["cfg"],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.decomposed_luts == 2
        assert result.result_data.stats.mux_solves == 1
        assert result.result_data.stats.mux_cache_hits == 1


def test_many_luts_decompose_with_indexed_apply_and_equiv() -> None:
    """Test bulk decomposition uses stable cell names and preserves behavior."""
    with TemporaryDirectory(prefix="lut_decomposer_many_") as td:
        tmp_dir = Path(td)
        base = _write_many_lut3_base(tmp_dir, count=12)
        mux = _write_mux4_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        result = LutDecomposerPass(
            source_lut_widths=[3],
            leaf_lut_width=2,
            mux_verilog_path=mux,
            mux_top_name="mux4_tile",
            mux_data_inputs=["A", "B", "C", "D"],
            mux_select_inputs=["S"],
            mux_outputs=["Y2", "Y4"],
            mux_configs=["cfg"],
            top_name="base",
            track_progress=True,
            progress_chunk_size=5,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.decomposed_luts == 12
        assert result.result_data.stats.generated_leaf_luts == 24
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        for index in range(12):
            assert f"lut{index}" not in cells

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, mux, "base")


def test_unsupported_width_is_skipped() -> None:
    """Test unselected LUT widths remain untouched."""
    with TemporaryDirectory(prefix="lut_decomposer_skip_") as td:
        tmp_dir = Path(td)
        base = _write_lut3_base(tmp_dir)
        mux = _write_mux4_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        result = LutDecomposerPass(
            source_lut_widths=[4],
            leaf_lut_width=2,
            mux_verilog_path=mux,
            mux_top_name="mux4_tile",
            mux_data_inputs=["A", "B", "C", "D"],
            mux_select_inputs=["S"],
            mux_outputs=["Y2", "Y4"],
            mux_configs=["cfg"],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.candidate_luts == 0
        assert result.result_data.stats.decomposed_luts == 0
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "u_lut" in cells


def test_oversized_mux_shape_is_rejected_without_sat() -> None:
    """Test impossible cofactor counts do not enter SAT solving."""
    with TemporaryDirectory(prefix="lut_decomposer_oversized_") as td:
        tmp_dir = Path(td)
        base = _write_lut5_base(tmp_dir)
        mux = _write_mux4_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        result = LutDecomposerPass(
            source_lut_widths=[5],
            leaf_lut_width=2,
            mux_verilog_path=mux,
            mux_top_name="mux4_tile",
            mux_data_inputs=["A", "B", "C", "D"],
            mux_select_inputs=["S"],
            mux_outputs=["Y2", "Y4"],
            mux_configs=["cfg"],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.candidate_luts == 1
        assert result.result_data.stats.decomposed_luts == 0
        assert result.result_data.stats.failed_luts == 1
        assert result.result_data.stats.mux_solves == 0
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "u_lut" in cells


def test_decomposed_design_passes_hierarchy_check() -> None:
    """Test generated internal cell types are valid in the live design."""
    with TemporaryDirectory(prefix="lut_decomposer_hierarchy_") as td:
        tmp_dir = Path(td)
        base = _write_lut3_base(tmp_dir)
        mux = _write_mux4_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        result = LutDecomposerPass(
            source_lut_widths=[3],
            leaf_lut_width=2,
            mux_verilog_path=mux,
            mux_top_name="mux4_tile",
            mux_data_inputs=["A", "B", "C", "D"],
            mux_select_inputs=["S"],
            mux_outputs=["Y2", "Y4"],
            mux_configs=["cfg"],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        bridge.run_pass("hierarchy -top base -check")


def _write_mux4_tile(tmp_dir: Path) -> Path:
    """Write a small configurable mux tile.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Verilog file path.
    """
    path = tmp_dir / "mux4_tile.v"
    path.write_text(
        """
module mux4_tile(
  input A,
  input B,
  input C,
  input D,
  input [1:0] S,
  input cfg,
  output Y2,
  output Y4
);
  assign Y2 = S[0] ? B : A;
  assign Y4 = cfg ? (S[1] ? (S[0] ? D : C) : (S[0] ? B : A)) : Y2;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_lut3_base(tmp_dir: Path) -> Path:
    """Write a base design with one LUT3.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Verilog file path.
    """
    path = tmp_dir / "base_lut3.v"
    path.write_text(
        """
module base(input a, input b, input c, output y);
  wire [2:0] in = {c, b, a};
  $lut #(.LUT(8'h96), .WIDTH(32'd3)) u_lut (.A(in), .Y(y));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_lut4_base(tmp_dir: Path) -> Path:
    """Write a base design with one LUT4.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Verilog file path.
    """
    path = tmp_dir / "base_lut4.v"
    path.write_text(
        """
module base(input a, input b, input c, input d, output y);
  wire [3:0] in = {d, c, b, a};
  $lut #(.LUT(16'h6996), .WIDTH(32'd4)) u_lut (.A(in), .Y(y));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_lut5_base(tmp_dir: Path) -> Path:
    """Write a base design with one LUT5.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Verilog file path.
    """
    path = tmp_dir / "base_lut5.v"
    path.write_text(
        """
module base(input [4:0] a, output y);
  $lut #(.LUT(32'h69969669), .WIDTH(32'd5)) u_lut (.A(a), .Y(y));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_two_lut3_base(tmp_dir: Path) -> Path:
    """Write a base design with two LUT3 cells.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Verilog file path.
    """
    path = tmp_dir / "base_two_lut3.v"
    path.write_text(
        """
module base(input a, input b, input c, input d, input e, input f, output y0, output y1);
  wire [2:0] in0 = {c, b, a};
  wire [2:0] in1 = {f, e, d};
  $lut #(.LUT(8'h96), .WIDTH(32'd3)) lut0 (.A(in0), .Y(y0));
  $lut #(.LUT(8'he8), .WIDTH(32'd3)) lut1 (.A(in1), .Y(y1));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_many_lut3_base(tmp_dir: Path, count: int) -> Path:
    """Write a base design with many independent LUT3 cells.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    count : int
        Number of LUT3 cells to emit.

    Returns
    -------
    Path
        Verilog file path.
    """
    path = tmp_dir / "base_many_lut3.v"
    body = "\n".join(
        f"  $lut #(.LUT(8'h{(0x96 ^ index) & 0xFF:02x}), .WIDTH(32'd3)) "
        f"lut{index} (.A(a[{3 * index + 2}:{3 * index}]), .Y(y[{index}]));"
        for index in range(count)
    )
    path.write_text(
        f"""
module base(input [{3 * count - 1}:0] a, output [{count - 1}:0] y);
{body}
endmodule
""",
        encoding="utf-8",
    )
    return path


def _assert_equiv(gold: Path, gate: Path, mux: Path, top_name: str) -> None:
    """Run a Yosys equivalence check.

    Parameters
    ----------
    gold : Path
        Golden Verilog path.
    gate : Path
        Mapped Verilog path.
    mux : Path
        Mux primitive Verilog path.
    top_name : str
        Top module name.
    """
    design = ys.Design()

    def run(command: str) -> None:
        """Run one quiet Yosys command.

        Parameters
        ----------
        command : str
            Yosys command.
        """
        ys.run_pass(f"tee -q {command}", design)

    run(f"read_verilog {gold}")
    run(f"rename {top_name} {top_name}_gold")
    run(f"read_verilog {mux}")
    run(f"read_verilog -overwrite {gate}")
    run(f"rename {top_name} {top_name}_gate")
    run(f"equiv_make {top_name}_gold {top_name}_gate equiv")
    run("hierarchy -top equiv")
    run("flatten")
    run("opt_clean")
    run("equiv_simple -undef")
    run("equiv_status -assert")


def main() -> None:
    """Run all LUT decomposer tests."""
    test_lut3_decomposes_to_two_lut2_and_equiv()
    test_lut4_decomposes_to_four_lut2_and_equiv()
    test_mux_shape_cache_is_used()
    test_many_luts_decompose_with_indexed_apply_and_equiv()
    test_unsupported_width_is_skipped()
    test_oversized_mux_shape_is_rejected_without_sat()
    test_decomposed_design_passes_hierarchy_check()


if __name__ == "__main__":
    main()
