"""Tests for FABulous nextpnr router helpers.

These tests avoid invoking a real nextpnr binary. Instead, they exercise PCF generation,
command construction, metadata validation, and router orchestration with a small fake
executable that writes the expected FASM and JSON report artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest  # deptry: ignore[DEP004]

from fabulous.fabric_cad.fabxplore.modules.fabric_router.nextpnr import (
    NextpnrCommand,
    NextpnrRouter,
    NextpnrRouterOptions,
)
from fabulous.fabric_cad.fabxplore.modules.fabric_router.nextpnr.pcf import (
    auto_assign_pcf,
    extract_template_io_sites,
    filter_io_sites_by_bel_v2,
    normalize_template_pin,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge

if TYPE_CHECKING:
    from pathlib import Path


def test_normalize_template_pin_accepts_fabulous_forms() -> None:
    """Normalize template PCF pins to nextpnr BEL names."""
    assert normalize_template_pin("Tile_X0Y1.A") == "X0Y1/A"
    assert normalize_template_pin("Tile_X2Y3/B") == "X2Y3/B"
    assert normalize_template_pin("X4Y5.C") == "X4Y5/C"
    assert normalize_template_pin("X6Y7/D") == "X6Y7/D"


def test_auto_assign_pcf_flattens_ports_and_uses_template_order() -> None:
    """Auto-assign vector and scalar top ports to legal IO sites."""
    bridge = _bridge_from_verilog(
        """
module top(input [2:0] a, output y);
  assign y = |a;
endmodule
"""
    )

    pcf = auto_assign_pcf(
        design=bridge,
        top_name="top",
        template_pcf=_template_pcf(site_count=4),
    )

    assert pcf.splitlines() == [
        "set_io a[0] X0Y1/A",
        "set_io a[1] X0Y1/B",
        "set_io a[2] X0Y2/A",
        "set_io y X0Y2/B",
    ]


def test_auto_assign_pcf_filters_pass_through_template_sites() -> None:
    """Ignore non-IO pass-through BELs included in FABulous template PCFs."""
    bridge = _bridge_from_verilog(
        """
module top(input [2:0] a, output y);
  assign y = |a;
endmodule
"""
    )

    pcf = auto_assign_pcf(
        design=bridge,
        top_name="top",
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
    bridge = _bridge_from_verilog(
        """
module top(input [2:0] a, output y);
  assign y = |a;
endmodule
"""
    )

    with pytest.raises(ValueError, match="top-level port"):
        auto_assign_pcf(
            design=bridge,
            top_name="top",
            template_pcf=_template_pcf(site_count=3),
        )


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
    assert result.nextpnr_report["utilization"]["FAKE"]["used"] == 1
    assert "PASS" in result.report_summary
    assert "## Utilization" in result.report_summary
    assert "## Timing" in result.report_summary
    assert "## nextpnr Output" in result.report_summary
    assert "ARGS=--uarch fabulous" in result.report_summary
    assert "FAB_ROOT=" not in result.report_summary
    assert "ERR=diagnostic" in result.report_summary


class _FakeFab:
    """Small fake FABulous API exposing only ``genRoutingModel``."""

    def __init__(
        self,
        template_pcf: str,
        bel_v2: str | None = None,
    ) -> None:
        self.template_pcf = template_pcf
        self.bel_v2 = bel_v2 or _bel_v2_with_mixed_io_sites()

    def genRoutingModel(self) -> tuple[str, str, str, str]:  # noqa: N802
        """Return fake routing-model strings.

        Returns
        -------
        tuple[str, str, str, str]
            PIPs, legacy BELs, BEL v2, and template PCF text.
        """
        return "", "", self.bel_v2, self.template_pcf


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


def _write_project_metadata(project_dir: Path) -> None:
    """Write minimal project metadata files required by the router.

    Parameters
    ----------
    project_dir : Path
        Fake FABulous project root.
    """
    metadata_dir = project_dir / ".FABulous"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "bel.v2.txt").write_text("# bels\n", encoding="utf-8")
    (metadata_dir / "pips.txt").write_text("# pips\n", encoding="utf-8")
