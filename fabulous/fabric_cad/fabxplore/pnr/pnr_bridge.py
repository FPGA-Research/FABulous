"""High-level bridge between graph edits, pyosys designs, and PnR tools.

``PnRBridge`` combines the editable `FabGraph` routing model with a packed
``PyosysBridge`` design.  This lets optimization code mutate the routing graph and
immediately evaluate the candidate architecture with nextpnr.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.fab_graph import FabGraph
from fabulous.fabric_cad.fabxplore.pnr.pnr_modules.nextpnr.core.nextpnr_router import (
    NextpnrRouter,
    NextpnrRouterOptions,
    NextpnrRouterResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
    from fabulous.fabulous_api import FABulous_API


class PnRBridge(FabGraph):
    """Combine an editable FABulous routing graph with a packed pyosys design.

    Parameters
    ----------
    project_dir : Path
        FABulous project root used for graph write-back and routing metadata.
    fabulous_api : FABulous_API
        Loaded FABulous API instance.
    pyosys_bridge : PyosysBridge
        Packed design representation used by downstream routers.
    """

    def __init__(
        self,
        project_dir: Path,
        fabulous_api: FABulous_API,
        pyosys_bridge: PyosysBridge,
    ) -> None:
        super().__init__(fabulous_api, project_dir)
        self._pyosys_bridge = pyosys_bridge

    def nextpnr_route(
        self,
        top_name: str | None = None,
        out_dir: Path | None = None,
        nextpnr_exec: Path | str | None = None,
        json_path: Path | None = None,
        pcf_path: Path | None = None,
        fasm_path: Path | None = None,
        report_path: Path | None = None,
        project_dir: Path | None = None,
        extra_args: list[str] | tuple[str, ...] | None = None,
        write_json: bool = True,
        check: bool = True,
        live_output: bool = False,
        report_output: bool = True,
        report_output_max_lines: int | None = 200,
        log_report: bool = True,
    ) -> NextpnrRouterResult:
        """Route the active design with FABulous nextpnr.

        Parameters
        ----------
        top_name : str | None
            Optional top module name. If ``None``, infer it from the active
            ``PyosysBridge`` design.
        out_dir : Path | None
            Optional output directory. If ``None``, write generated artifacts to
            ``<project>/user_design/fabxplore``.
        nextpnr_exec : Path | str | None
            Optional nextpnr executable. If ``None``, use FABulous settings.
        json_path : Path | None
            Optional existing Yosys JSON netlist path.  When provided,
            ``write_json`` must be ``False`` so the file is not overwritten.
            If ``None``, use ``<out_dir>/<top>.json``.
        pcf_path : Path | None
            Optional concrete PCF path. If ``None``, auto-generate a PCF from
            the in-memory FABulous routing model.
        fasm_path : Path | None
            Optional FASM output path. If ``None``, use ``<out_dir>/<top>.fasm``.
        report_path : Path | None
            Optional nextpnr JSON report path. If ``None``, use
            ``<out_dir>/<top>_nextpnr_report.json``.
        project_dir : Path | None
            Optional FABulous project root. If ``None``, use this bridge's
            project root.
        extra_args : list[str] | tuple[str, ...] | None
            Extra nextpnr command-line arguments.
        write_json : bool
            Whether to write the active pyosys design JSON before running nextpnr.
        check : bool
            Whether a non-zero nextpnr return code should raise an exception.
        live_output : bool
            Whether to stream nextpnr stdout/stderr live while capturing it.
        report_output : bool
            Whether to append captured nextpnr stdout/stderr to the report summary.
        report_output_max_lines : int | None
            Maximum trailing stdout/stderr lines to include in the report.
            ``None`` includes the full captured output.
        log_report : bool
            If ``True``, log the nextpnr route report after execution.

        Returns
        -------
        NextpnrRouterResult
            The result of the nextpnr routing process, including paths to generated
            artifacts and a summary report.
        """
        route_project_dir = Path(project_dir or self.project_dir)
        pips_path = route_project_dir / ".FABulous" / "pips.txt"

        options = NextpnrRouterOptions(
            top_name=top_name or self._pyosys_bridge.top_name(),
            out_dir=out_dir,
            nextpnr_exec=nextpnr_exec,
            json_path=json_path,
            pcf_path=pcf_path,
            fasm_path=fasm_path,
            report_path=report_path,
            project_dir=route_project_dir,
            extra_args=tuple(extra_args or ()),
            write_json=write_json,
            check=check,
            live_output=live_output,
            report_output=report_output,
            report_output_max_lines=report_output_max_lines,
        )

        with self._temporary_pips_override(pips_path):
            result = NextpnrRouter(options).route(self._pyosys_bridge, self.fab)

            if log_report:
                logger.info(result.report_summary)

            s_dir: Path = (
                out_dir
                if out_dir is not None
                else (route_project_dir / "user_design" / "fabxplore" / "summary.txt")
            )
            s_dir.parent.mkdir(parents=True, exist_ok=True)
            s_dir.write_text(result.report_summary)

            return result

    @contextmanager
    def _temporary_pips_override(self, pips_path: Path) -> Iterator[None]:
        """Temporarily replace ``pips.txt`` with graph-rendered PIPs.

        The current file contents are stored as bytes, the graph-rendered PIPs
        are written to the real path for nextpnr, and the previous file state is
        restored when the ``with`` block exits.

        Parameters
        ----------
        pips_path : Path
            Project ``.FABulous/pips.txt`` file to replace for one route run.

        Yields
        ------
        None
            Control while the graph-rendered PIPs are installed.
        """
        original_pips = pips_path.read_bytes() if pips_path.exists() else None

        try:
            self.write_pips(pips_path)
            yield
        finally:
            if original_pips is not None:
                pips_path.write_bytes(original_pips)
            else:
                pips_path.unlink(missing_ok=True)
