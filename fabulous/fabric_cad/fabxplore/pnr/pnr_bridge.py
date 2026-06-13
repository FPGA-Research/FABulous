"""High-level bridge between graph edits, pyosys designs, and PnR tools.

``PnRBridge`` combines the editable `FabGraph` routing model with a packed
``PyosysBridge`` design.  This lets optimization code mutate the routing graph and
immediately evaluate the candidate architecture with nextpnr.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

from loguru import logger

from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.fab_graph import FabGraph
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.rgraph import (
    RoutingFabricGraph,
)
from fabulous.fabric_cad.fabxplore.pnr.pnr_modules.nextpnr.core.nextpnr_router import (
    NextpnrRouter,
    NextpnrRouterOptions,
    NextpnrRouterResult,
)
from fabulous.fabric_cad.fabxplore.utils.fabulous_fasm import (
    FabulousFasmDocument,
    parse_fabulous_fasm,
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

    @property
    def user_design(self) -> PyosysBridge:
        """The packed pyosys design attached to this PnR bridge.

        Returns
        -------
        PyosysBridge
            The packed pyosys design attached to this PnR bridge.
        """
        return self._pyosys_bridge

    def update_from_project(self) -> None:
        """Reload the current project from disk and rebuild the routing graph.

        Use this after editing project files directly under ``Tile/`` or
        ``fabric.csv``. The method reloads FABulous first, then replaces the
        internal graph snapshot with one built from the refreshed fabric object.
        The packed pyosys design attached to this bridge is left unchanged.
        """
        self._reload_project(self.project_dir)
        self._graph = RoutingFabricGraph.from_fabric(self.fab.fabric)

    def evaluate_fasm(self, fasm_text: str) -> FabulousFasmDocument:
        """Evaluate a FASM string against the current FABulous fabric state.

        This parses the FASM text into a document, resolves any FABulous-specific
        semantics, and returns the resulting document. This is useful for
        interpreting the PnR output FASM in terms of the current FabGraph state.

        Parameters
        ----------
        fasm_text : str
            The FASM text to evaluate.

        Returns
        -------
        FabulousFasmDocument
            The evaluated FASM document reflecting the current fabric state.
        """
        return parse_fabulous_fasm(fasm_text, self)

    def nextpnr_route(
        self,
        top_name: str | None = None,
        out_dir: Path | None = None,
        nextpnr_exec: Path | str | None = None,
        json_path: Path | None = None,
        json_output_path: Path | None = None,
        pcf_path: Path | None = None,
        pcf_assignment_seed: int = 1,
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
            Optional top module name. Required when ``json_path`` is provided.
            Otherwise ``None`` uses the active ``PyosysBridge`` design top.
        out_dir : Path | None
            Optional output directory. If ``None``, write generated artifacts to
            ``<project>/user_design/fabxplore``.
        nextpnr_exec : Path | str | None
            Optional nextpnr executable. If ``None``, use FABulous settings.
        json_path : Path | None
            Optional existing Yosys JSON netlist path. When provided, this JSON
            is the route design source of truth and has priority over the
            attached ``PyosysBridge`` design.
        json_output_path : Path | None
            Optional persisted JSON output path used when ``write_json`` is
            enabled. If ``json_path`` is provided, the input JSON is copied here.
            If ``json_path`` is omitted, the pyosys bridge design is written
            here. ``None`` selects ``<out_dir>/<top>.json``.
        pcf_path : Path | None
            Optional concrete PCF path. If ``None``, auto-generate a PCF from
            the in-memory FABulous routing model.
        pcf_assignment_seed : int
            Positive deterministic seed for auto-generated PCF assignment. Seed
            ``1`` preserves template order.
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
            Whether to persist the selected route JSON under the output artifacts.
            If disabled and ``json_path`` is omitted, the pyosys bridge design is
            written to a temporary JSON file for nextpnr and removed afterwards.
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
        metadata_dir = route_project_dir / ".FABulous"

        options = NextpnrRouterOptions(
            top_name=top_name,
            out_dir=out_dir,
            nextpnr_exec=nextpnr_exec,
            json_path=json_path,
            json_output_path=json_output_path,
            pcf_path=pcf_path,
            pcf_assignment_seed=pcf_assignment_seed,
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

        with self._temporary_routing_model_override(metadata_dir):
            result = NextpnrRouter(options).route(self._pyosys_bridge, self.fab)

            if log_report:
                logger.info(result.report_summary)

            summary_path = (
                Path(out_dir) / "summary.txt"
                if out_dir is not None
                else route_project_dir / "user_design" / "fabxplore" / "summary.txt"
            )
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(result.report_summary, encoding="utf-8")

            return result

    def nextpnr_batch_test(
        self,
        designs: dict[str, Path | dict[str, Any]],
        *,
        nextpnr_exec: Path | str | None = None,
        project_dir: Path | None = None,
        extra_args: list[str] | tuple[str, ...] | None = None,
        pcf_assignment_seed: int = 1,
        check: bool = False,
        live_output: bool = False,
    ) -> list[NextpnrRouterResult]:
        """Route several JSON netlists as temporary benchmark cases.

        Parameters
        ----------
        designs : dict[str, Path | dict[str, Any]]
            Mapping from top module name to either an existing Yosys JSON path or
            an in-memory Yosys JSON dictionary.
        nextpnr_exec : Path | str | None
            Optional nextpnr executable. If ``None``, use FABulous settings.
        project_dir : Path | None
            Optional FABulous project root. If ``None``, use this bridge's
            project root.
        extra_args : list[str] | tuple[str, ...] | None
            Extra nextpnr command-line arguments.
        pcf_assignment_seed : int
            Positive deterministic seed for auto-generated PCF assignment. Seed
            ``1`` preserves template order.
        check : bool
            Whether a non-zero nextpnr return code should raise an exception.
            Defaults to ``False`` so a batch can collect failed routes.
        live_output : bool
            Whether to stream nextpnr stdout/stderr live while capturing it.

        Returns
        -------
        list[NextpnrRouterResult]
            Route results in input order. Artifact paths inside each result point
            to temporary files that are deleted when this method returns.

        Raises
        ------
        TypeError
            If a design source is neither a ``Path`` nor a JSON dictionary.
        """
        route_project_dir = Path(project_dir or self.project_dir)
        metadata_dir = route_project_dir / ".FABulous"
        results: list[NextpnrRouterResult] = []

        with TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with self._temporary_routing_model_override(metadata_dir):
                for index, (top_name, source) in enumerate(designs.items()):
                    case_dir = tmp_root / f"case_{index}"
                    case_dir.mkdir(parents=True, exist_ok=True)

                    if isinstance(source, Path):
                        json_path = source
                    elif isinstance(source, dict):
                        json_path = case_dir / "input.json"
                        json_path.write_text(json.dumps(source), encoding="utf-8")
                    else:
                        raise TypeError(
                            "batch design sources must be Path or JSON dict, "
                            f"got {type(source).__name__}"
                        )

                    options = NextpnrRouterOptions(
                        top_name=top_name,
                        out_dir=case_dir,
                        nextpnr_exec=nextpnr_exec,
                        json_path=json_path,
                        project_dir=route_project_dir,
                        extra_args=tuple(extra_args or ()),
                        pcf_assignment_seed=pcf_assignment_seed,
                        write_json=False,
                        check=check,
                        live_output=live_output,
                    )
                    results.append(
                        NextpnrRouter(options).route(self._pyosys_bridge, self.fab)
                    )

        return results

    @contextmanager
    def _temporary_routing_model_override(self, metadata_dir: Path) -> Iterator[None]:
        """Temporarily replace routing metadata with the graph-rendered model.

        The current routing-model files are stored as bytes, the graph-rendered
        routing model is written to the real project metadata directory for
        nextpnr, and the previous file state is restored when the ``with`` block
        exits.

        Parameters
        ----------
        metadata_dir : Path
            Project ``.FABulous`` directory to replace for one route run.

        Yields
        ------
        None
            Control while the graph-rendered routing model is installed.
        """
        routing_model_files = (
            "pips.txt",
            "bel.txt",
            "bel.v2.txt",
            "template.pcf",
        )
        original_files = {
            file_name: (metadata_dir / file_name).read_bytes()
            if (metadata_dir / file_name).exists()
            else None
            for file_name in routing_model_files
        }

        try:
            self.write_routing_model(metadata_dir)
            yield
        finally:
            for file_name, original_content in original_files.items():
                path = metadata_dir / file_name
                if original_content is not None:
                    path.write_bytes(original_content)
                else:
                    path.unlink(missing_ok=True)
