"""PnR pass wrapper for FABulous nextpnr fabric routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.fabric_router import (
    NextpnrRouter,
    NextpnrRouterOptions,
    NextpnrRouterResult,
)
from fabulous.fabric_cad.fabxplore.pnr.pnr_pass import PnRPass

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
    from fabulous.fabulous_api import FABulous_API


@dataclass
class FabricRouterPass(PnRPass):
    """Route the active design through FABulous nextpnr.

    Attributes
    ----------
    top_name : str | None
        Optional top module name. ``None`` uses ``PyosysBridge.top_name()``.
    out_dir : Path | None
        Optional output directory. ``None`` selects
        ``<project>/user_design/fabxplore``.
    nextpnr_exec : Path | str | None
        Optional nextpnr executable. ``None`` uses FABulous settings.
    json_path : Path | None
        Optional Yosys JSON netlist path.
    pcf_path : Path | None
        Optional concrete PCF path. ``None`` auto-generates one.
    fasm_path : Path | None
        Optional FASM output path.
    report_path : Path | None
        Optional nextpnr JSON report path.
    project_dir : Path | None
        Optional FABulous project root. ``None`` uses FABulous settings.
    extra_args : tuple[str, ...]
        Extra nextpnr arguments.
    write_json : bool
        Whether to write the pyosys design JSON before routing.
    check : bool
        Whether a non-zero nextpnr return code should raise an exception.
    live_output : bool
        Whether to stream nextpnr stdout/stderr live while capturing it.
    report_output : bool
        Whether to append captured nextpnr stdout/stderr to the report summary.
    report_output_max_lines : int | None
        Maximum trailing stdout/stderr lines to include in the report. ``None``
        includes the full captured output.
    """

    top_name: str | None = None
    out_dir: Path | None = None
    nextpnr_exec: Path | str | None = None
    json_path: Path | None = None
    pcf_path: Path | None = None
    fasm_path: Path | None = None
    report_path: Path | None = None
    project_dir: Path | None = None
    extra_args: tuple[str, ...] = ()
    write_json: bool = True
    check: bool = True
    live_output: bool = False
    report_output: bool = True
    report_output_max_lines: int | None = 200

    _result: NextpnrRouterResult | None = None

    def run_on(self, design: PyosysBridge, fab: FABulous_API) -> None:
        """Run FABulous nextpnr routing.

        Parameters
        ----------
        design : PyosysBridge
            Packed design associated with the architecture flow.
        fab : FABulous_API
            Loaded FABulous API instance.
        """
        options = NextpnrRouterOptions(
            top_name=self.top_name,
            out_dir=self.out_dir,
            nextpnr_exec=self.nextpnr_exec,
            json_path=self.json_path,
            pcf_path=self.pcf_path,
            fasm_path=self.fasm_path,
            report_path=self.report_path,
            project_dir=self.project_dir,
            extra_args=self.extra_args,
            write_json=self.write_json,
            check=self.check,
            live_output=self.live_output,
            report_output=self.report_output,
            report_output_max_lines=self.report_output_max_lines,
        )
        self._result = NextpnrRouter(options).route(design, fab)

    @property
    def report_summary(self) -> str:
        """Return the latest report summary.

        Returns
        -------
        str
            Report text, or a placeholder if the pass has not run.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> NextpnrRouterResult | None:
        """Return the latest structured result.

        Returns
        -------
        NextpnrRouterResult | None
            Latest result if available.
        """
        return self._result
