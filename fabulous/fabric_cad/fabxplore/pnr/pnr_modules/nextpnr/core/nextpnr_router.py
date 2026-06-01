"""Main nextpnr router orchestration for FABulous designs.

``NextpnrRouter`` connects a Yosys JSON design to FABulous' nextpnr generic
micro-architecture. The JSON can come from an explicit input file or from the
active pyosys bridge design. It resolves default paths, stages the selected JSON,
generates a PCF from the selected design ports and the project routing metadata,
validates that project ``.FABulous`` metadata exists, invokes nextpnr,
and parses the JSON report.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

from fabulous.fabric_cad.fabxplore.pnr.pnr_modules.nextpnr.core import (
    models,
    nextpnr_command,
    pcf,
    report,
)
from fabulous.fabulous_settings import get_context

NextpnrRouterOptions = models.NextpnrRouterOptions
NextpnrRouterPaths = models.NextpnrRouterPaths
NextpnrRouterResult = models.NextpnrRouterResult

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
    from fabulous.fabulous_api import FABulous_API


class NextpnrRouter:
    """Route a packed pyosys design with FABulous nextpnr.

    Parameters
    ----------
    options : NextpnrRouterOptions
        Normalized router options.
    """

    def __init__(self, options: NextpnrRouterOptions) -> None:
        self.options = options

    def route(
        self,
        design: PyosysBridge,
        fab: FABulous_API,
    ) -> NextpnrRouterResult:
        """Run nextpnr for the active FABulous project.

        Parameters
        ----------
        design : PyosysBridge
            Packed pyosys design to export and route.
        fab : FABulous_API
            Loaded FABulous API instance. Kept in the route signature for API
            compatibility; routing metadata is read from ``.FABulous``.

        Returns
        -------
        NextpnrRouterResult
            Structured route result and parsed nextpnr report.

        Raises
        ------
        ValueError
            If ``json_path`` is provided without ``top_name``, if the selected
            top is missing from the selected design source, or if there are not
            enough legal IO sites for auto-PCF generation.
        RuntimeError
            If nextpnr returns a non-zero exit code while ``check`` is enabled.
        """
        _ = fab
        context = get_context()
        project_dir = Path(self.options.project_dir or context.proj_dir)
        input_json_path = (
            Path(self.options.json_path) if self.options.json_path is not None else None
        )
        if input_json_path is not None and self.options.top_name is None:
            raise ValueError("top_name is required when json_path is provided")
        top_name = self.options.top_name or design.top_name()
        out_dir = Path(
            self.options.out_dir or project_dir / "user_design" / "fabxplore"
        )
        temp_dir = None
        if input_json_path is None and not self.options.write_json:
            temp_dir = TemporaryDirectory()
            route_json_path = Path(temp_dir.name) / f"{top_name}.json"
        elif input_json_path is not None and not self.options.write_json:
            route_json_path = input_json_path
        else:
            route_json_path = Path(
                self.options.json_output_path or out_dir / f"{top_name}.json"
            )

        paths = _resolve_paths(
            self.options,
            project_dir,
            top_name,
            out_dir=out_dir,
            json_path=route_json_path,
        )
        nextpnr_exec = self.options.nextpnr_exec or context.nextpnr_path

        try:
            paths.out_dir.mkdir(parents=True, exist_ok=True)
            _validate_metadata(
                paths.metadata_dir,
                require_template_pcf=self.options.pcf_path is None,
            )

            if input_json_path is not None:
                if self.options.write_json:
                    paths.json_path.parent.mkdir(parents=True, exist_ok=True)
                    if input_json_path.resolve() != paths.json_path.resolve():
                        shutil.copy2(input_json_path, paths.json_path)
            else:
                paths.json_path.parent.mkdir(parents=True, exist_ok=True)
                design.write_json_path(paths.json_path)

            if self.options.pcf_path is None:
                bel_v2, template_pcf = _read_auto_pcf_metadata(paths.metadata_dir)
                pcf_text = pcf.auto_assign_pcf_for_ports(
                    ports=pcf.extract_json_ports(paths.json_path, top_name),
                    template_pcf=template_pcf,
                    bel_v2=bel_v2,
                    pcf_assignment_seed=self.options.pcf_assignment_seed,
                )
                paths.pcf_path.write_text(pcf_text, encoding="utf-8")

            command = nextpnr_command.NextpnrCommand(
                executable=nextpnr_exec,
                fab_root=project_dir,
            )
            command_result = command.run(
                json_path=paths.json_path,
                pcf_path=paths.pcf_path,
                fasm_path=paths.fasm_path,
                report_path=paths.report_path,
                extra_args=self.options.extra_args,
                live_output=self.options.live_output,
            )
            nextpnr_report = _read_report(paths.report_path)
            fasm_text = _read_fasm(paths.fasm_path)

            result = NextpnrRouterResult(
                options=self.options,
                top_name=top_name,
                nextpnr_exec=nextpnr_exec,
                paths=paths,
                command_result=command_result,
                nextpnr_report=nextpnr_report,
                fasm_text=fasm_text,
            )
            result = result.model_copy(
                update={"report_summary": report.render_nextpnr_router_report(result)}
            )
            if self.options.check and not result.passed:
                raise RuntimeError(_render_failure(result))
            return result
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()


def _resolve_paths(
    options: NextpnrRouterOptions,
    project_dir: Path,
    top_name: str,
    *,
    out_dir: Path,
    json_path: Path,
) -> NextpnrRouterPaths:
    """Resolve project, output, and nextpnr artifact paths.

    Parameters
    ----------
    options : NextpnrRouterOptions
        Router options.
    project_dir : Path
        FABulous project root.
    top_name : str
        Top module name used for default file names.
    out_dir : Path
        Output directory for route artifacts.
    json_path : Path
        JSON netlist path consumed by nextpnr.

    Returns
    -------
    NextpnrRouterPaths
        Resolved paths for one route run.
    """
    return NextpnrRouterPaths(
        project_dir=project_dir,
        metadata_dir=project_dir / ".FABulous",
        out_dir=out_dir,
        json_path=json_path,
        pcf_path=Path(options.pcf_path or out_dir / f"{top_name}.pcf"),
        fasm_path=Path(options.fasm_path or out_dir / f"{top_name}.fasm"),
        report_path=Path(
            options.report_path or out_dir / f"{top_name}_nextpnr_report.json"
        ),
    )


def _validate_metadata(
    metadata_dir: Path,
    *,
    require_template_pcf: bool = False,
) -> None:
    """Validate required FABulous routing metadata files.

    Parameters
    ----------
    metadata_dir : Path
        Project ``.FABulous`` metadata directory.
    require_template_pcf : bool
        Whether ``template.pcf`` is required for auto-PCF generation.

    Raises
    ------
    FileNotFoundError
        If required routing metadata files are missing.
    """
    required = [metadata_dir / "bel.v2.txt", metadata_dir / "pips.txt"]
    if require_template_pcf:
        required.append(metadata_dir / "template.pcf")
    missing = [path for path in required if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(
            "FABulous routing metadata is missing. "
            "Run write_routingmodel_bitreamspec() or the FABulous generation flow "
            f"first: {missing_text}"
        )


def _read_auto_pcf_metadata(metadata_dir: Path) -> tuple[str, str]:
    """Read metadata files needed for automatic PCF assignment.

    Parameters
    ----------
    metadata_dir : Path
        Project ``.FABulous`` metadata directory.

    Returns
    -------
    tuple[str, str]
        ``bel.v2.txt`` text and ``template.pcf`` text.
    """
    return (
        (metadata_dir / "bel.v2.txt").read_text(encoding="utf-8"),
        (metadata_dir / "template.pcf").read_text(encoding="utf-8"),
    )


def _read_report(report_path: Path) -> dict[str, Any]:
    """Read a nextpnr JSON report if it exists.

    Parameters
    ----------
    report_path : Path
        nextpnr report path.

    Returns
    -------
    dict[str, Any]
        Parsed report dictionary, or an empty dictionary if the report is missing
        or empty.
    """
    if not report_path.exists() or report_path.stat().st_size == 0:
        return {}
    return json.loads(report_path.read_text(encoding="utf-8"))


def _read_fasm(fasm_path: Path) -> str | None:
    """Read a nextpnr FASM file if it exists.

    Parameters
    ----------
    fasm_path : Path
        FASM output path.

    Returns
    -------
    str | None
        FASM text, or ``None`` if nextpnr did not produce the file.
    """
    if not fasm_path.exists():
        return None
    return fasm_path.read_text(encoding="utf-8")


def _render_failure(result: NextpnrRouterResult) -> str:
    """Render a failure message with useful command output.

    Parameters
    ----------
    result : NextpnrRouterResult
        Failed route result.

    Returns
    -------
    str
        Failure message for an exception.
    """
    stdout_tail = _tail(result.command_result.stdout)
    stderr_tail = _tail(result.command_result.stderr)
    command = " ".join(result.command_result.command)
    return (
        "nextpnr failed with return code "
        f"{result.command_result.returncode}.\n"
        f"Command: {command}\n"
        f"stdout tail:\n{stdout_tail}\n"
        f"stderr tail:\n{stderr_tail}"
    )


def _tail(text: str, lines: int = 20) -> str:
    """Return the last lines from a text blob.

    Parameters
    ----------
    text : str
        Text to trim.
    lines : int
        Maximum number of trailing lines.

    Returns
    -------
    str
        Last ``lines`` lines, or an empty string when ``text`` is empty.
    """
    if not text:
        return ""
    return "\n".join(text.splitlines()[-lines:])
