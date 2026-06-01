"""Tests for FABulous nextpnr router helpers.

These tests avoid invoking a real nextpnr binary. Instead, they exercise PCF generation,
command construction, metadata validation, and router orchestration with a small fake
executable that writes the expected FASM and JSON report artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest  # deptry: ignore[DEP004]

from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge
from fabulous.fabric_cad.fabxplore.pnr.pnr_modules.nextpnr import (
    NextpnrCommand,
    NextpnrRouter,
    NextpnrRouterOptions,
)
from fabulous.fabric_cad.fabxplore.pnr.pnr_modules.nextpnr.core.pcf import (
    auto_assign_pcf_for_ports,
    extract_json_ports,
    extract_template_io_sites,
    filter_io_sites_by_bel_v2,
    normalize_template_pin,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.tests.fab_graph.test_fab_graph import (
    _write_and_load_api,
)


def test_normalize_template_pin_accepts_fabulous_forms() -> None:
    """Normalize template PCF pins to nextpnr BEL names."""
    assert normalize_template_pin("Tile_X0Y1.A") == "X0Y1/A"
    assert normalize_template_pin("Tile_X2Y3/B") == "X2Y3/B"
    assert normalize_template_pin("X4Y5.C") == "X4Y5/C"
    assert normalize_template_pin("X6Y7/D") == "X6Y7/D"


def test_auto_assign_pcf_for_ports_uses_template_order() -> None:
    """Auto-assign flattened top ports to legal IO sites."""
    pcf = auto_assign_pcf_for_ports(
        ports=["a[0]", "a[1]", "a[2]", "y"],
        template_pcf=_template_pcf(site_count=4),
    )

    assert pcf.splitlines() == [
        "set_io a[0] X0Y1/A",
        "set_io a[1] X0Y1/B",
        "set_io a[2] X0Y2/A",
        "set_io y X0Y2/B",
    ]


def test_auto_assign_pcf_for_ports_uses_seeded_site_permutation() -> None:
    """Permute legal IO sites with a deterministic non-default seed."""
    pcf = auto_assign_pcf_for_ports(
        ports=["a[0]", "a[1]", "a[2]", "y"],
        template_pcf=_template_pcf(site_count=4),
        pcf_assignment_seed=2,
    )

    assert pcf.splitlines() == [
        "set_io a[0] X0Y1/B",
        "set_io a[1] X0Y2/A",
        "set_io a[2] X0Y2/B",
        "set_io y X0Y1/A",
    ]


def test_auto_assign_pcf_for_ports_rejects_non_positive_seed() -> None:
    """Require positive auto-PCF assignment seeds."""
    with pytest.raises(ValueError, match="pcf_assignment_seed"):
        auto_assign_pcf_for_ports(
            ports=["a"],
            template_pcf=_template_pcf(site_count=1),
            pcf_assignment_seed=0,
        )


def test_auto_assign_pcf_filters_pass_through_template_sites() -> None:
    """Ignore non-IO pass-through BELs included in FABulous template PCFs."""
    pcf = auto_assign_pcf_for_ports(
        ports=["a[0]", "a[1]", "a[2]", "y"],
        template_pcf=(
            "set_io Tile_X0Y1_A Tile_X0Y1.A\n"
            "set_io Tile_X0Y1_B Tile_X0Y1.B\n"
            "set_io Tile_X9Y1_A Tile_X9Y1.A\n"
            "set_io Tile_X9Y1_B Tile_X9Y1.B\n"
            "set_io Tile_X0Y2_A Tile_X0Y2.A\n"
            "set_io Tile_X0Y2_B Tile_X0Y2.B\n"
        ),
        bel_v2=_bel_v2_with_mixed_io_sites(),
    )

    assert pcf.splitlines() == [
        "set_io a[0] X0Y1/A",
        "set_io a[1] X0Y1/B",
        "set_io a[2] X0Y2/A",
        "set_io y X0Y2/B",
    ]


def test_auto_assign_pcf_rejects_too_few_sites() -> None:
    """Reject auto PCF assignment when the fabric has too few IO sites."""
    with pytest.raises(ValueError, match="top-level port"):
        auto_assign_pcf_for_ports(
            ports=["a[0]", "a[1]", "a[2]", "y"],
            template_pcf=_template_pcf(site_count=3),
        )


def test_json_port_helpers_flatten_named_top(tmp_path: Path) -> None:
    """Extract flattened ports from an explicit Yosys JSON netlist."""
    json_path = _write_json_netlist(
        tmp_path / "input.json",
        top_name="json_top",
        ports={"j": [2, 3], "z": [4]},
    )

    assert extract_json_ports(json_path, "json_top") == ["j[0]", "j[1]", "z"]
    assert auto_assign_pcf_for_ports(
        ["j[0]", "j[1]", "z"],
        _template_pcf(site_count=3),
    ).splitlines() == [
        "set_io j[0] X0Y1/A",
        "set_io j[1] X0Y1/B",
        "set_io z X0Y2/A",
    ]


def test_extract_template_io_sites_rejects_empty_template() -> None:
    """Reject template PCF strings without legal IO entries."""
    with pytest.raises(ValueError, match="set_io"):
        extract_template_io_sites("# no io here\n")


def test_filter_io_sites_by_bel_v2_rejects_no_real_io_sites() -> None:
    """Reject a template when BEL v2 marks all candidate sites as non-IO BELs."""
    sites = extract_template_io_sites("set_io Tile_X9Y1_A Tile_X9Y1.A\n")

    with pytest.raises(ValueError, match="usable IO"):
        filter_io_sites_by_bel_v2(
            sites,
            "BelBegin,X9Y1,A,InPass4_frame_config_mux,RAM2FAB_D0_\n",
        )


def test_nextpnr_command_builds_and_runs_with_fab_root(tmp_path: Path) -> None:
    """Run a fake nextpnr executable and capture FAB_ROOT-dependent output."""
    executable = _fake_nextpnr(tmp_path)
    command = NextpnrCommand(executable=executable, fab_root=tmp_path)
    report_path = tmp_path / "route.json"
    fasm_path = tmp_path / "route.fasm"

    result = command.run(
        json_path=tmp_path / "design.json",
        pcf_path=tmp_path / "design.pcf",
        fasm_path=fasm_path,
        report_path=report_path,
        extra_args=("--seed", "1"),
    )

    assert result.returncode == 0
    assert f"FAB_ROOT={tmp_path}" in result.stdout
    assert "--seed 1" in result.stdout
    assert report_path.exists()
    assert fasm_path.exists()


def test_nextpnr_command_can_stream_live_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Mirror fake nextpnr output live while preserving captured streams."""
    executable = _fake_nextpnr(tmp_path)
    command = NextpnrCommand(executable=executable, fab_root=tmp_path)

    result = command.run(
        json_path=tmp_path / "design.json",
        pcf_path=tmp_path / "design.pcf",
        fasm_path=tmp_path / "route.fasm",
        report_path=tmp_path / "route.json",
        live_output=True,
    )

    captured = capsys.readouterr()
    assert result.returncode == 0
    assert "FAB_ROOT=" in result.stdout
    assert "ERR=diagnostic" in result.stderr
    assert "FAB_ROOT=" in captured.out
    assert "ERR=diagnostic" in captured.err


def test_router_rejects_missing_project_metadata(tmp_path: Path) -> None:
    """Require project .FABulous metadata before invoking nextpnr."""
    bridge = _bridge_from_verilog(
        "module top(input a, output y); assign y = a; endmodule"
    )
    router = NextpnrRouter(
        NextpnrRouterOptions(
            project_dir=tmp_path,
            nextpnr_exec=_fake_nextpnr(tmp_path),
            check=False,
        )
    )

    with pytest.raises(FileNotFoundError, match="bel.v2.txt"):
        router.route(bridge, _FakeFab(_template_pcf(site_count=2)))


def test_router_rejects_missing_template_pcf_for_auto_pcf(tmp_path: Path) -> None:
    """Require template PCF metadata when the router auto-generates PCF."""
    metadata_dir = tmp_path / ".FABulous"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "bel.v2.txt").write_text(
        _bel_v2_with_mixed_io_sites(),
        encoding="utf-8",
    )
    (metadata_dir / "pips.txt").write_text("# pips\n", encoding="utf-8")
    bridge = _bridge_from_verilog(
        "module top(input a, output y); assign y = a; endmodule"
    )
    router = NextpnrRouter(
        NextpnrRouterOptions(
            project_dir=tmp_path,
            nextpnr_exec=_fake_nextpnr(tmp_path),
            check=False,
        )
    )

    with pytest.raises(FileNotFoundError, match="template.pcf"):
        router.route(bridge, _FakeFab(_template_pcf(site_count=2)))


def test_router_writes_artifacts_and_parses_report(tmp_path: Path) -> None:
    """Route through a fake nextpnr command and parse the emitted report."""
    _write_project_metadata(tmp_path)
    bridge = _bridge_from_verilog(
        "module top(input a, output y); assign y = a; endmodule"
    )
    out_dir = tmp_path / "user_design" / "fabxplore"
    router = NextpnrRouter(
        NextpnrRouterOptions(
            project_dir=tmp_path,
            out_dir=out_dir,
            nextpnr_exec=_fake_nextpnr(tmp_path),
            report_output_max_lines=1,
        )
    )

    result = router.route(bridge, _FakeFab(_template_pcf(site_count=2)))

    assert result.passed
    assert result.paths.out_dir == out_dir
    assert result.paths.json_path.exists()
    assert result.paths.pcf_path.read_text(encoding="utf-8").splitlines() == [
        "set_io a X0Y1/A",
        "set_io y X0Y1/B",
    ]
    assert result.paths.fasm_path.read_text(encoding="utf-8") == "# fake fasm\n"
    assert result.fasm_text == "# fake fasm\n"
    assert result.nextpnr_report["utilization"]["FAKE"]["used"] == 1
    assert "PASS" in result.report_summary
    assert "## Utilization" in result.report_summary
    assert "## Timing" in result.report_summary
    assert "## nextpnr Output" in result.report_summary
    assert "ARGS=--uarch fabulous" in result.report_summary
    assert "FAB_ROOT=" not in result.report_summary
    assert "ERR=diagnostic" in result.report_summary


def test_router_routes_external_json_and_auto_pcf_from_json(tmp_path: Path) -> None:
    """Prefer explicit JSON design ports over the attached pyosys bridge."""
    _write_project_metadata(tmp_path)
    bridge = _bridge_from_verilog(
        "module bridge_top(input bridge_a, output bridge_y); "
        "assign bridge_y = bridge_a; endmodule"
    )
    json_path = _write_json_netlist(
        tmp_path / "custom.json",
        top_name="json_top",
        ports={"j": [2, 3], "z": [4]},
    )
    out_dir = tmp_path / "route_out"
    router = NextpnrRouter(
        NextpnrRouterOptions(
            project_dir=tmp_path,
            out_dir=out_dir,
            top_name="json_top",
            json_path=json_path,
            write_json=False,
            nextpnr_exec=_fake_nextpnr(tmp_path),
        )
    )

    result = router.route(bridge, _FakeFab(_template_pcf(site_count=3)))

    assert result.passed
    assert result.top_name == "json_top"
    assert result.paths.json_path == json_path
    assert not (out_dir / "json_top.json").exists()
    assert result.paths.pcf_path.read_text(encoding="utf-8").splitlines() == [
        "set_io j[0] X0Y1/A",
        "set_io j[1] X0Y1/B",
        "set_io z X0Y2/A",
    ]


def test_router_uses_auto_pcf_assignment_seed(tmp_path: Path) -> None:
    """Use router options to permute auto-generated PCF assignments."""
    _write_project_metadata(tmp_path)
    bridge = _bridge_from_verilog(
        "module top(input [2:0] a, output y); assign y = |a; endmodule"
    )
    router = NextpnrRouter(
        NextpnrRouterOptions(
            project_dir=tmp_path,
            nextpnr_exec=_fake_nextpnr(tmp_path),
            pcf_assignment_seed=2,
        )
    )

    result = router.route(bridge, _FakeFab(_template_pcf(site_count=4)))

    assert result.paths.pcf_path.read_text(encoding="utf-8").splitlines() == [
        "set_io a[0] X0Y1/B",
        "set_io a[1] X0Y2/A",
        "set_io a[2] X0Y2/B",
        "set_io y X0Y1/A",
    ]


def test_router_copies_external_json_when_write_json_is_enabled(
    tmp_path: Path,
) -> None:
    """Persist a routed copy of an explicit input JSON when requested."""
    _write_project_metadata(tmp_path)
    bridge = _bridge_from_verilog(
        "module bridge_top(input bridge_a, output bridge_y); "
        "assign bridge_y = bridge_a; endmodule"
    )
    json_path = _write_json_netlist(
        tmp_path / "input.json",
        top_name="json_top",
        ports={"j": [2, 3], "z": [4]},
    )
    json_output_path = tmp_path / "route_out" / "copied.json"
    router = NextpnrRouter(
        NextpnrRouterOptions(
            project_dir=tmp_path,
            top_name="json_top",
            json_path=json_path,
            json_output_path=json_output_path,
            write_json=True,
            nextpnr_exec=_fake_nextpnr(tmp_path),
        )
    )

    result = router.route(bridge, _FakeFab(_template_pcf(site_count=3)))

    assert result.passed
    assert result.paths.json_path == json_output_path
    assert json.loads(json_output_path.read_text(encoding="utf-8")) == json.loads(
        json_path.read_text(encoding="utf-8")
    )
    assert result.paths.pcf_path.read_text(encoding="utf-8").splitlines() == [
        "set_io j[0] X0Y1/A",
        "set_io j[1] X0Y1/B",
        "set_io z X0Y2/A",
    ]


def test_router_requires_top_name_for_external_json(tmp_path: Path) -> None:
    """Reject explicit JSON routing without an explicit top name."""
    _write_project_metadata(tmp_path)
    bridge = _bridge_from_verilog(
        "module bridge_top(input bridge_a, output bridge_y); "
        "assign bridge_y = bridge_a; endmodule"
    )
    json_path = _write_json_netlist(
        tmp_path / "input.json",
        top_name="json_top",
        ports={"j": [2, 3], "z": [4]},
    )
    router = NextpnrRouter(
        NextpnrRouterOptions(
            project_dir=tmp_path,
            json_path=json_path,
            write_json=False,
            nextpnr_exec=_fake_nextpnr(tmp_path),
        )
    )

    with pytest.raises(ValueError, match="top_name"):
        router.route(bridge, _FakeFab(_template_pcf(site_count=3)))


def test_router_uses_temporary_bridge_json_when_not_persisting(
    tmp_path: Path,
) -> None:
    """Route a pyosys bridge design without leaving a JSON artifact behind."""
    _write_project_metadata(tmp_path)
    bridge = _bridge_from_verilog(
        "module top(input a, output y); assign y = a; endmodule"
    )
    out_dir = tmp_path / "route_out"
    router = NextpnrRouter(
        NextpnrRouterOptions(
            project_dir=tmp_path,
            out_dir=out_dir,
            write_json=False,
            nextpnr_exec=_fake_nextpnr(tmp_path),
        )
    )

    result = router.route(bridge, _FakeFab(_template_pcf(site_count=2)))

    assert result.passed
    assert not (out_dir / "top.json").exists()
    assert not result.paths.json_path.exists()
    assert result.paths.pcf_path.read_text(encoding="utf-8").splitlines() == [
        "set_io a X0Y1/A",
        "set_io y X0Y1/B",
    ]


def test_pnr_bridge_routes_with_temporary_graph_routing_model(
    tmp_path: Path,
) -> None:
    """Route through PnRBridge while restoring original routing metadata."""
    _write_project_metadata(
        tmp_path,
        template_pcf="# original template is intentionally unusable\n",
    )
    original_metadata = _read_routing_model_metadata(tmp_path)

    design = _bridge_from_verilog(
        "module top(input a, output y); assign y = a; endmodule"
    )
    bridge = _FakePnRBridge(
        project_dir=tmp_path,
        fabulous_api=_FakeFab(_template_pcf(site_count=2)),
        pyosys_bridge=design,
    )

    bridge.write_routing_model = lambda path=None: _write_candidate_routing_model(
        path,
        site_count=2,
    )

    result = bridge.nextpnr_route(
        nextpnr_exec=_fake_nextpnr(tmp_path),
        check=True,
        log_report=False,
    )

    assert result.passed
    assert result.paths.json_path.exists()
    assert result.paths.pcf_path.read_text(encoding="utf-8").splitlines() == [
        "set_io a X0Y1/A",
        "set_io y X0Y1/B",
    ]
    assert _read_routing_model_metadata(tmp_path) == original_metadata


def test_pnr_bridge_prefers_input_json_over_bridge_design(tmp_path: Path) -> None:
    """Keep PnRBridge top and auto-PCF based on explicit input JSON."""
    _write_project_metadata(tmp_path)
    original_metadata = _read_routing_model_metadata(tmp_path)

    design = _bridge_from_verilog(
        "module bridge_top(input bridge_a, output bridge_y); "
        "assign bridge_y = bridge_a; endmodule"
    )
    bridge = _FakePnRBridge(
        project_dir=tmp_path,
        fabulous_api=_FakeFab(_template_pcf(site_count=3)),
        pyosys_bridge=design,
    )
    bridge.write_routing_model = lambda path=None: _write_candidate_routing_model(
        path,
        site_count=3,
    )
    json_path = _write_json_netlist(
        tmp_path / "custom.json",
        top_name="json_top",
        ports={"j": [2, 3], "z": [4]},
    )

    result = bridge.nextpnr_route(
        top_name="json_top",
        json_path=json_path,
        write_json=False,
        nextpnr_exec=_fake_nextpnr(tmp_path),
        check=True,
        log_report=False,
    )

    assert result.top_name == "json_top"
    assert result.paths.json_path == json_path
    assert result.paths.pcf_path.read_text(encoding="utf-8").splitlines() == [
        "set_io j[0] X0Y1/A",
        "set_io j[1] X0Y1/B",
        "set_io z X0Y2/A",
    ]
    assert _read_routing_model_metadata(tmp_path) == original_metadata


def test_pnr_bridge_batch_test_routes_path_and_memory_json(tmp_path: Path) -> None:
    """Route several explicit JSON benchmarks through temporary batch artifacts."""
    _write_project_metadata(tmp_path)
    original_metadata = _read_routing_model_metadata(tmp_path)

    design = _bridge_from_verilog(
        "module bridge_top(input bridge_a, output bridge_y); "
        "assign bridge_y = bridge_a; endmodule"
    )
    bridge = _FakePnRBridge(
        project_dir=tmp_path,
        fabulous_api=_FakeFab(_template_pcf(site_count=4)),
        pyosys_bridge=design,
    )
    bridge.write_routing_model = lambda path=None: _write_candidate_routing_model(
        path,
        site_count=4,
    )
    path_json = _write_json_netlist(
        tmp_path / "path_top.json",
        top_name="path_top",
        ports={"a": [2], "y": [3]},
    )
    memory_json = _json_netlist_dict(
        top_name="memory_top",
        ports={"d": [2, 3], "q": [4]},
    )

    results = bridge.nextpnr_batch_test(
        {
            "path_top": path_json,
            "memory_top": memory_json,
        },
        nextpnr_exec=_fake_nextpnr(tmp_path),
    )

    assert [result.top_name for result in results] == ["path_top", "memory_top"]
    assert all(result.passed for result in results)
    assert all(not result.paths.out_dir.exists() for result in results)
    assert _read_routing_model_metadata(tmp_path) == original_metadata


def test_pnr_bridge_update_from_project_rebuilds_graph(tmp_path: Path) -> None:
    """Reload disk edits into FABulous and rebuild the bridge graph snapshot."""
    fab = _write_and_load_api(tmp_path)
    design = _bridge_from_verilog(
        "module top(input a, output y); assign y = a; endmodule"
    )
    bridge = PnRBridge(tmp_path, fab, design)
    added_pair = ("LONG_END1", "LOCAL_BEG0")
    matrix_list = tmp_path / "Tile" / "Toy" / "Toy_switch_matrix.list"

    assert added_pair not in _matrix_pairs(bridge)
    matrix_list.write_text(
        matrix_list.read_text(encoding="utf-8") + "LONG_END1,LOCAL_BEG0\n",
        encoding="utf-8",
    )
    assert added_pair not in _matrix_pairs(bridge)

    bridge.update_from_project()

    assert added_pair in _matrix_pairs(bridge)
    assert design.top_name() == "top"


class _FakePnRBridge(PnRBridge):
    """Small bridge that avoids building a full routing graph for router tests."""

    def __init__(
        self,
        project_dir: Path,
        fabulous_api: _FakeFab,
        pyosys_bridge: PyosysBridge,
    ) -> None:
        self.project_dir = project_dir
        self.fab = fabulous_api
        self._pyosys_bridge = pyosys_bridge


class _FakeFab:
    """Small fake FABulous API object for router API compatibility."""

    def __init__(
        self,
        template_pcf: str,
        bel_v2: str | None = None,
    ) -> None:
        self.template_pcf = template_pcf
        self.bel_v2 = bel_v2 or _bel_v2_with_mixed_io_sites()

    def genRoutingModel(self) -> tuple[str, str, str, str]:  # noqa: N802
        """Fail if router code still regenerates routing metadata.

        Returns
        -------
        tuple[str, str, str, str]
            Unused routing-model tuple; this fake always raises instead.

        Raises
        ------
        AssertionError
            Always raised; tests expect routing metadata to be read from disk.
        """
        raise AssertionError("router must read routing metadata from .FABulous")


def _bridge_from_verilog(verilog_text: str) -> PyosysBridge:
    """Create a bridge from one Verilog source string.

    Parameters
    ----------
    verilog_text : str
        Verilog source text.

    Returns
    -------
    PyosysBridge
        Bridge containing the parsed design.
    """
    bridge = PyosysBridge()
    bridge.read_verilog_string(verilog_text, replace_design=True)
    return bridge


def _write_json_netlist(
    path: Path,
    *,
    top_name: str,
    ports: dict[str, list[int]],
) -> Path:
    """Write a minimal Yosys JSON netlist.

    Parameters
    ----------
    path : Path
        Destination JSON path.
    top_name : str
        Top module name.
    ports : dict[str, list[int]]
        Port names mapped to JSON bit lists.

    Returns
    -------
    Path
        Written JSON path.
    """
    path.write_text(
        json.dumps(_json_netlist_dict(top_name=top_name, ports=ports)),
        encoding="utf-8",
    )
    return path


def _json_netlist_dict(
    *,
    top_name: str,
    ports: dict[str, list[int]],
) -> dict[str, object]:
    """Return a minimal Yosys JSON netlist dictionary.

    Parameters
    ----------
    top_name : str
        Top module name.
    ports : dict[str, list[int]]
        Port names mapped to JSON bit lists.

    Returns
    -------
    dict[str, object]
        Minimal JSON netlist dictionary.
    """
    return {
        "modules": {
            top_name: {
                "attributes": {"top": "00000000000000000000000000000001"},
                "ports": {
                    name: {"direction": "input", "bits": bits}
                    for name, bits in ports.items()
                },
                "cells": {},
                "netnames": {},
            }
        }
    }


def _matrix_pairs(bridge: PnRBridge) -> set[tuple[str, str]]:
    """Return active Toy matrix pairs from a bridge graph.

    Parameters
    ----------
    bridge : PnRBridge
        Bridge to inspect.

    Returns
    -------
    set[tuple[str, str]]
        Active ``(source_name, destination_name)`` pairs.
    """
    return {
        (key.source_name, key.destination_name)
        for key in bridge.matrix_resources("Toy")
    }


def _template_pcf(site_count: int) -> str:
    """Return a FABulous-style template PCF with a requested number of sites.

    Parameters
    ----------
    site_count : int
        Number of generated IO sites.

    Returns
    -------
    str
        Template PCF text.
    """
    sites = [
        ("Tile_X0Y1_A", "Tile_X0Y1.A"),
        ("Tile_X0Y1_B", "Tile_X0Y1.B"),
        ("Tile_X0Y2_A", "Tile_X0Y2.A"),
        ("Tile_X0Y2_B", "Tile_X0Y2.B"),
    ]
    return "\n".join(f"set_io {cell} {pin}" for cell, pin in sites[:site_count]) + "\n"


def _bel_v2_with_mixed_io_sites() -> str:
    """Return BEL v2 text with real IO and pass-through candidates.

    Returns
    -------
    str
        BEL v2 metadata containing the template sites used by the tests.
    """
    return "\n".join(
        [
            "BelBegin,X0Y1,A,IO_1_bidirectional_frame_config_pass,A_",
            "BelBegin,X0Y1,B,IO_1_bidirectional_frame_config_pass,B_",
            "BelBegin,X9Y1,A,InPass4_frame_config_mux,RAM2FAB_D0_",
            "BelBegin,X9Y1,B,OutPass4_frame_config_mux,FAB2RAM_D0_",
            "BelBegin,X0Y2,A,IO_1_bidirectional_frame_config_pass,A_",
            "BelBegin,X0Y2,B,IO_1_bidirectional_frame_config_pass,B_",
        ]
    )


def _fake_nextpnr(tmp_path: Path) -> Path:
    """Create a fake nextpnr executable for subprocess tests.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory for the script.

    Returns
    -------
    Path
        Executable script path.
    """
    executable = tmp_path / "fake_nextpnr.py"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

args = sys.argv[1:]
report = pathlib.Path(args[args.index("--report") + 1])
fasm = None
for index, arg in enumerate(args):
    if arg == "-o" and args[index + 1].startswith("fasm="):
        fasm = pathlib.Path(args[index + 1].split("=", 1)[1])

if fasm is None:
    raise SystemExit("missing fasm option")

report.parent.mkdir(parents=True, exist_ok=True)
fasm.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({"utilization": {"FAKE": {"used": 1, "available": 2}}}))
fasm.write_text("# fake fasm\\n")
print("FAB_ROOT=" + os.environ.get("FAB_ROOT", ""))
print("ARGS=" + " ".join(args))
print("ERR=diagnostic", file=sys.stderr)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _write_project_metadata(
    project_dir: Path,
    *,
    bel_v2: str | None = None,
    template_pcf: str | None = None,
) -> None:
    """Write minimal project metadata files required by the router.

    Parameters
    ----------
    project_dir : Path
        Fake FABulous project root.
    bel_v2 : str | None
        Optional BEL v2 metadata. If ``None``, write mixed IO metadata.
    template_pcf : str | None
        Optional template PCF. If ``None``, write four legal IO sites.
    """
    metadata_dir = project_dir / ".FABulous"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "bel.v2.txt").write_text(
        bel_v2 or _bel_v2_with_mixed_io_sites(),
        encoding="utf-8",
    )
    (metadata_dir / "bel.txt").write_text("# bels\n", encoding="utf-8")
    (metadata_dir / "pips.txt").write_text("# pips\n", encoding="utf-8")
    (metadata_dir / "template.pcf").write_text(
        template_pcf or _template_pcf(site_count=4),
        encoding="utf-8",
    )


def _read_routing_model_metadata(project_dir: Path) -> dict[str, str]:
    """Read routing-model metadata files from a fake project.

    Parameters
    ----------
    project_dir : Path
        Fake FABulous project root.

    Returns
    -------
    dict[str, str]
        Routing-model file names mapped to file text.
    """
    metadata_dir = project_dir / ".FABulous"
    return {
        file_name: (metadata_dir / file_name).read_text(encoding="utf-8")
        for file_name in (
            "pips.txt",
            "bel.txt",
            "bel.v2.txt",
            "template.pcf",
        )
    }


def _write_candidate_routing_model(
    path: Path | str | None,
    *,
    site_count: int,
) -> None:
    """Write candidate graph routing metadata for bridge tests.

    Parameters
    ----------
    path : Path | str | None
        Metadata directory selected by ``PnRBridge``.
    site_count : int
        Number of template PCF sites to expose.

    Raises
    ------
    ValueError
        If no metadata path is provided.
    """
    if path is None:
        raise ValueError("candidate routing model tests require an explicit path")

    metadata_dir = Path(path)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "pips.txt").write_text(
        "# graph candidate pips\n",
        encoding="utf-8",
    )
    (metadata_dir / "bel.txt").write_text(
        "# graph candidate bels\n",
        encoding="utf-8",
    )
    (metadata_dir / "bel.v2.txt").write_text(
        _bel_v2_with_mixed_io_sites(),
        encoding="utf-8",
    )
    (metadata_dir / "template.pcf").write_text(
        _template_pcf(site_count=site_count),
        encoding="utf-8",
    )
