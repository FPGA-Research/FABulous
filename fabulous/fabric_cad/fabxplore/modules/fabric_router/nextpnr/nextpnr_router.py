"""Main nextpnr router orchestration for FABulous designs.

``NextpnrRouter`` connects the active pyosys design to FABulous' nextpnr generic
micro-architecture. It resolves default paths, writes the design JSON, generates a
PCF from the in-memory FABulous routing model, validates that project
``.FABulous`` metadata exists, invokes nextpnr, and parses the JSON report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fabulous.fabric_cad.fabxplore.modules.fabric_router.nextpnr import (
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
            Loaded FABulous API instance. The router uses it to obtain the
            in-memory template PCF from ``genRoutingModel``.

        Returns
        -------
        NextpnrRouterResult
            Structured route result and parsed nextpnr report.

        Raises
        ------
        RuntimeError
            If nextpnr returns a non-zero exit code while ``check`` is enabled.
        """
        context = get_context()
        top_name = self.options.top_name or design.top_name()
        project_dir = Path(self.options.project_dir or context.proj_dir)
        paths = _resolve_paths(self.options, project_dir, top_name)
        nextpnr_exec = self.options.nextpnr_exec or context.nextpnr_path

        paths.out_dir.mkdir(parents=True, exist_ok=True)
        _validate_metadata(paths.metadata_dir)

        if self.options.write_json:
            design.write_json_path(paths.json_path)

        if self.options.pcf_path is None:
            _, _, bel_v2, template_pcf = fab.genRoutingModel()
            pcf_text = pcf.auto_assign_pcf(
                design=design,
                top_name=top_name,
                template_pcf=template_pcf,
                bel_v2=bel_v2,
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

        result = NextpnrRouterResult(
            options=self.options,
            top_name=top_name,
            nextpnr_exec=nextpnr_exec,
            paths=paths,
            command_result=command_result,
            nextpnr_report=nextpnr_report,
        )
        result = result.model_copy(
            update={"report_summary": report.render_nextpnr_router_report(result)}
        )
        if self.options.check and not result.passed:
            raise RuntimeError(_render_failure(result))
        return result


def _resolve_paths(
    options: NextpnrRouterOptions,
    project_dir: Path,
    top_name: str,
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

    Returns
    -------
    NextpnrRouterPaths
        Resolved paths for one route run.
    """
    out_dir = options.out_dir or project_dir / "user_design" / "fabxplore"
    out_dir = Path(out_dir)
    return NextpnrRouterPaths(
        project_dir=project_dir,
        metadata_dir=project_dir / ".FABulous",
        out_dir=out_dir,
        json_path=Path(options.json_path or out_dir / f"{top_name}.json"),
        pcf_path=Path(options.pcf_path or out_dir / f"{top_name}.pcf"),
        fasm_path=Path(options.fasm_path or out_dir / f"{top_name}.fasm"),
        report_path=Path(
            options.report_path or out_dir / f"{top_name}_nextpnr_report.json"
        ),
    )


def _validate_metadata(metadata_dir: Path) -> None:
    """Validate required FABulous routing metadata files.

    Parameters
    ----------
    metadata_dir : Path
        Project ``.FABulous`` metadata directory.

    Raises
    ------
    FileNotFoundError
        If required routing metadata files are missing.
    """
    required = [metadata_dir / "bel.v2.txt", metadata_dir / "pips.txt"]
    missing = [path for path in required if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(
            "FABulous routing metadata is missing. "
            "Run write_routingmodel_bitreamspec() or the FABulous generation flow "
            f"first: {missing_text}"
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
