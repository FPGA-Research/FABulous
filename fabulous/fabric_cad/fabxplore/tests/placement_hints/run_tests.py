"""Ad-hoc tests for placement hint generation."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.placement_hints_pass import (
    PlacementHintsPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabulous_cli.helper import setup_logger

setup_logger(verbosity=0, debug=False)


class _PlacementHintsTestSynthesizer(ArchitectureSynthesizer):
    """Tiny concrete synthesizer for placement-hints pass tests."""

    def synthesize(self) -> None:
        """No-op synthesis entry point for tests."""

    def generate_primitives(self) -> None:
        """No-op primitive generation for tests."""

    def generate_switch_matrix(self) -> None:
        """No-op switch-matrix generation for tests."""


def test_linear_chain_assigns_indices() -> None:
    """Test one chain receives stable cluster indices and size."""
    with TemporaryDirectory(prefix="placement_hints_chain_") as td:
        tmp_dir = Path(td)
        base = _write_three_stage_chain(tmp_dir)
        bridge = _load_base(base)

        result = _run_chain_hints(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.clusters == 1
        assert result.result_data.stats.assigned_cells == 3
        cells = _top_cells(bridge)
        for index, cell_id in enumerate(("u0", "u1", "u2")):
            attributes = cells[cell_id]["attributes"]
            assert _attr_text(attributes["FAB_CLUSTER_KIND"]) == "linear_chain"
            assert _attr_text(attributes["FAB_CLUSTER_NAME"]) == "carry"
            assert _attr_text(attributes["FAB_CLUSTER_ID"]) == "carry_0"
            assert _attr_text(attributes["FAB_CLUSTER_ROLE"]) == "stage"
            assert _attr_text(attributes["FAB_CLUSTER_INDEX"]) == str(index)
            assert _attr_text(attributes["FAB_CLUSTER_SIZE"]) == "3"
        bridge.run_pass("hierarchy -top base -check")


def test_two_independent_chains_get_distinct_ids() -> None:
    """Test independent chains are assigned different cluster IDs."""
    with TemporaryDirectory(prefix="placement_hints_two_chains_") as td:
        tmp_dir = Path(td)
        base = _write_two_chains(tmp_dir)
        bridge = _load_base(base)

        result = _run_chain_hints(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.clusters == 2
        cells = _top_cells(bridge)
        assert _attr_text(cells["u0"]["attributes"]["FAB_CLUSTER_ID"]) == "carry_0"
        assert _attr_text(cells["u1"]["attributes"]["FAB_CLUSTER_ID"]) == "carry_0"
        assert _attr_text(cells["v0"]["attributes"]["FAB_CLUSTER_ID"]) == "carry_1"
        assert _attr_text(cells["v1"]["attributes"]["FAB_CLUSTER_ID"]) == "carry_1"


def test_single_stage_is_skipped_by_default() -> None:
    """Test isolated cells are not annotated by default."""
    with TemporaryDirectory(prefix="placement_hints_single_skip_") as td:
        tmp_dir = Path(td)
        base = _write_single_stage(tmp_dir)
        bridge = _load_base(base)

        result = _run_chain_hints(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.clusters == 0
        assert "FAB_CLUSTER_ID" not in _top_cells(bridge)["u0"]["attributes"]


def test_single_stage_can_be_enabled() -> None:
    """Test isolated cells can be annotated when requested."""
    with TemporaryDirectory(prefix="placement_hints_single_emit_") as td:
        tmp_dir = Path(td)
        base = _write_single_stage(tmp_dir)
        bridge = _load_base(base)

        result = _run_chain_hints(
            bridge,
            min_length=1,
            allow_single_stage=True,
        )

        assert result.result_data is not None
        assert result.result_data.stats.clusters == 1
        attributes = _top_cells(bridge)["u0"]["attributes"]
        assert _attr_text(attributes["FAB_CLUSTER_ID"]) == "carry_0"
        assert _attr_text(attributes["FAB_CLUSTER_SIZE"]) == "1"


def test_branching_chain_raises_by_default() -> None:
    """Test ambiguous chain fanout raises by default."""
    with TemporaryDirectory(prefix="placement_hints_branch_raise_") as td:
        tmp_dir = Path(td)
        base = _write_branching_chain(tmp_dir)
        bridge = _load_base(base)

        _assert_raises_contains(lambda: _run_chain_hints(bridge), "branching")


def test_branching_chain_can_be_skipped() -> None:
    """Test ambiguous chain fanout can be skipped."""
    with TemporaryDirectory(prefix="placement_hints_branch_skip_") as td:
        tmp_dir = Path(td)
        base = _write_branching_chain(tmp_dir)
        bridge = _load_base(base)

        result = _run_chain_hints(bridge, allow_branching=True)

        assert result.result_data is not None
        assert result.result_data.stats.clusters == 0
        assert result.result_data.stats.skipped_chains == 1


def test_existing_attribute_conflict_raises() -> None:
    """Test existing placement attributes are protected by default."""
    with TemporaryDirectory(prefix="placement_hints_conflict_") as td:
        tmp_dir = Path(td)
        base = _write_existing_attr_chain(tmp_dir)
        bridge = _load_base(base)

        _assert_raises_contains(
            lambda: _run_chain_hints(bridge),
            "already has attribute",
        )


def test_existing_attribute_can_be_overwritten() -> None:
    """Test existing placement attributes can be overwritten."""
    with TemporaryDirectory(prefix="placement_hints_overwrite_") as td:
        tmp_dir = Path(td)
        base = _write_existing_attr_chain(tmp_dir)
        bridge = _load_base(base)

        result = _run_chain_hints(bridge, overwrite_existing=True)

        assert result.result_data is not None
        attributes = _top_cells(bridge)["u0"]["attributes"]
        assert _attr_text(attributes["FAB_CLUSTER_KIND"]) == "linear_chain"


def test_synthesizer_wrapper_runs() -> None:
    """Test the ArchitectureSynthesizer convenience wrapper."""
    with TemporaryDirectory(prefix="placement_hints_synth_") as td:
        tmp_dir = Path(td)
        base = _write_three_stage_chain(tmp_dir)
        synth = _PlacementHintsTestSynthesizer(debug=False)
        synth.design.read_verilog_paths([base])

        result = synth.design_placement_hints_pass(
            rules=[_chain_rule()],
            top_name="base",
            track_progress=False,
            log_report=False,
        )

        assert result.result_data is not None
        assert result.result_data.stats.clusters == 1
        assert "Placement Hints Report" in result.report_summary


def test_attributes_can_be_emitted_to_verilog() -> None:
    """Test placement attributes are visible when Verilog keeps attributes."""
    with TemporaryDirectory(prefix="placement_hints_verilog_attrs_") as td:
        tmp_dir = Path(td)
        base = _write_three_stage_chain(tmp_dir)
        bridge = _load_base(base)

        _run_chain_hints(bridge)
        verilog_text = bridge.to_verilog_string(include_attributes=True)

        assert '(* FAB_CLUSTER_KIND = "linear_chain" *)' in verilog_text
        assert '(* FAB_CLUSTER_ID = "carry_0" *)' in verilog_text
        assert '(* FAB_CLUSTER_INDEX = "0" *)' in verilog_text
        assert '(* FAB_CLUSTER_SIZE = "3" *)' in verilog_text


def _run_chain_hints(
    bridge: PyosysBridge,
    min_length: int = 2,
    allow_branching: bool = False,
    allow_single_stage: bool = False,
    overwrite_existing: bool = False,
) -> PlacementHintsPass:
    """Run the placement-hints pass with one chain rule.

    Parameters
    ----------
    bridge : PyosysBridge
        Design to mutate.
    min_length : int
        Minimum emitted chain length.
    allow_branching : bool
        Whether ambiguous chain fanout should be skipped.
    allow_single_stage : bool
        Whether isolated stages should be annotated.
    overwrite_existing : bool
        Whether existing placement attributes may be overwritten.

    Returns
    -------
    PlacementHintsPass
        Executed pass object.
    """
    pass_ = PlacementHintsPass(
        rules=[
            _chain_rule(
                min_length=min_length,
                allow_branching=allow_branching,
                allow_single_stage=allow_single_stage,
            )
        ],
        overwrite_existing=overwrite_existing,
        top_name="base",
        track_progress=False,
    )
    pass_.run_on(bridge)
    return pass_


def _chain_rule(
    min_length: int = 2,
    allow_branching: bool = False,
    allow_single_stage: bool = False,
) -> dict[str, object]:
    """Return the standard test chain rule.

    Parameters
    ----------
    min_length : int
        Minimum emitted chain length.
    allow_branching : bool
        Whether branching should be skipped instead of raising.
    allow_single_stage : bool
        Whether isolated cells may form clusters.

    Returns
    -------
    dict[str, object]
        Placement hint rule dictionary.
    """
    return {
        "kind": "linear_chain",
        "name": "carry",
        "cell_types": ["chain_tile"],
        "source_port": "Co",
        "sink_port": "Ci",
        "min_length": min_length,
        "allow_branching": allow_branching,
        "allow_single_stage": allow_single_stage,
    }


def _load_base(base: Path) -> PyosysBridge:
    """Load a Verilog design for placement-hints tests.

    Parameters
    ----------
    base : Path
        Verilog path to read.

    Returns
    -------
    PyosysBridge
        Loaded design bridge.
    """
    bridge = PyosysBridge(debug=False)
    bridge.read_verilog_paths([base])
    return bridge


def _top_cells(bridge: PyosysBridge) -> dict[str, dict[str, object]]:
    """Return top-module cells from a bridge.

    Parameters
    ----------
    bridge : PyosysBridge
        Design bridge.

    Returns
    -------
    dict[str, dict[str, object]]
        Cell dictionary for module ``base``.
    """
    return bridge.to_netlist_dict()["modules"]["base"]["cells"]


def _attr_text(value: object) -> str:
    """Normalize a Yosys JSON attribute value for assertions.

    Parameters
    ----------
    value : object
        Raw attribute value.

    Returns
    -------
    str
        Comparable text.
    """
    text = str(value).strip().strip('"').strip()
    if text and set(text) <= {"0", "1"}:
        return str(int(text, 2))
    return text


def _assert_raises_contains(callback: Callable[[], object], text: str) -> None:
    """Assert that a callback raises ``ValueError`` containing text.

    Parameters
    ----------
    callback : Callable[[], object]
        Zero-argument callable to invoke.
    text : str
        Expected substring in the exception message.

    Raises
    ------
    AssertionError
        If the callback does not raise the expected error.
    """
    try:
        callback()
    except ValueError as exc:
        if text not in str(exc):
            raise AssertionError(f"expected '{text}' in '{exc}'") from exc
    else:
        raise AssertionError(f"expected ValueError containing '{text}'")


def _tile_definition() -> str:
    """Return a tiny tile module used by placement-hints tests.

    Returns
    -------
    str
        Verilog module text.
    """
    return """
module chain_tile (
  input Ci,
  output Co
);
  assign Co = Ci;
endmodule
"""


def _write_three_stage_chain(tmp_dir: Path) -> Path:
    """Write a design with one three-stage chain.

    Parameters
    ----------
    tmp_dir : Path
        Temporary directory.

    Returns
    -------
    Path
        Written Verilog path.
    """
    path = tmp_dir / "three_stage.v"
    path.write_text(
        f"""
{_tile_definition()}
module base(input a, output y);
  wire n0, n1;
  chain_tile u0(.Ci(a), .Co(n0));
  chain_tile u1(.Ci(n0), .Co(n1));
  chain_tile u2(.Ci(n1), .Co(y));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_two_chains(tmp_dir: Path) -> Path:
    """Write a design with two independent two-stage chains.

    Parameters
    ----------
    tmp_dir : Path
        Temporary directory.

    Returns
    -------
    Path
        Written Verilog path.
    """
    path = tmp_dir / "two_chains.v"
    path.write_text(
        f"""
{_tile_definition()}
module base(input a, input b, output y, output z);
  wire n0, n1;
  chain_tile u0(.Ci(a), .Co(n0));
  chain_tile u1(.Ci(n0), .Co(y));
  chain_tile v0(.Ci(b), .Co(n1));
  chain_tile v1(.Ci(n1), .Co(z));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_single_stage(tmp_dir: Path) -> Path:
    """Write a design with one isolated chain-capable cell.

    Parameters
    ----------
    tmp_dir : Path
        Temporary directory.

    Returns
    -------
    Path
        Written Verilog path.
    """
    path = tmp_dir / "single_stage.v"
    path.write_text(
        f"""
{_tile_definition()}
module base(input a, output y);
  chain_tile u0(.Ci(a), .Co(y));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_branching_chain(tmp_dir: Path) -> Path:
    """Write a design with branching chain fanout.

    Parameters
    ----------
    tmp_dir : Path
        Temporary directory.

    Returns
    -------
    Path
        Written Verilog path.
    """
    path = tmp_dir / "branching.v"
    path.write_text(
        f"""
{_tile_definition()}
module base(input a, output y, output z);
  wire n0;
  chain_tile u0(.Ci(a), .Co(n0));
  chain_tile u1(.Ci(n0), .Co(y));
  chain_tile u2(.Ci(n0), .Co(z));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_existing_attr_chain(tmp_dir: Path) -> Path:
    """Write a chain where one cell already has placement attributes.

    Parameters
    ----------
    tmp_dir : Path
        Temporary directory.

    Returns
    -------
    Path
        Written Verilog path.
    """
    path = tmp_dir / "existing_attr.v"
    path.write_text(
        f"""
{_tile_definition()}
module base(input a, output y);
  wire n0;
  (* FAB_CLUSTER_KIND = "old" *)
  chain_tile u0(.Ci(a), .Co(n0));
  chain_tile u1(.Ci(n0), .Co(y));
endmodule
""",
        encoding="utf-8",
    )
    return path


def main() -> None:
    """Run all placement-hints tests."""
    test_linear_chain_assigns_indices()
    test_two_independent_chains_get_distinct_ids()
    test_single_stage_is_skipped_by_default()
    test_single_stage_can_be_enabled()
    test_branching_chain_raises_by_default()
    test_branching_chain_can_be_skipped()
    test_existing_attribute_conflict_raises()
    test_existing_attribute_can_be_overwritten()
    test_synthesizer_wrapper_runs()
    test_attributes_can_be_emitted_to_verilog()


if __name__ == "__main__":
    main()
