"""Data models for nextpnr-backed fabric routing.

The nextpnr router writes a Yosys JSON netlist, a concrete PCF, a FASM file, and the
nextpnr JSON report into one output directory. These models keep user options, resolved
file paths, subprocess results, and parsed nextpnr metrics structured for the router,
PnR pass wrapper, and architecture synthesizer helper.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NextpnrRouterOptions(BaseModel):
    """Options for FABulous nextpnr routing.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    top_name : str | None
        Optional top module name. Required when ``json_path`` is provided.
        Otherwise ``None`` uses ``PyosysBridge.top_name()``.
    out_dir : Path | None
        Optional output directory. ``None`` selects
        ``<project>/user_design/fabxplore``.
    nextpnr_exec : Path | str | None
        Optional nextpnr executable. ``None`` uses FABulous settings.
    json_path : Path | None
        Optional input JSON netlist path. When provided, this JSON is the route
        design source of truth and has priority over the pyosys bridge design.
    json_output_path : Path | None
        Optional path for a persisted route JSON copy. When ``json_path`` is
        provided and ``write_json`` is enabled, the input JSON is copied here.
        When ``json_path`` is omitted and ``write_json`` is enabled, the pyosys
        bridge design is written here. ``None`` selects ``<out_dir>/<top>.json``.
    pcf_path : Path | None
        Optional concrete PCF path. ``None`` auto-generates one from the FABulous
        routing model.
    pcf_assignment_seed : int
        Deterministic seed for auto-generated PCF port-to-IO-site assignment.
        Seed ``1`` preserves template order.
    fasm_path : Path | None
        Optional FASM output path.
    report_path : Path | None
        Optional nextpnr JSON report path.
    project_dir : Path | None
        Optional FABulous project root. ``None`` uses FABulous settings.
    extra_args : tuple[str, ...]
        Extra nextpnr command-line arguments appended after standard arguments.
    write_json : bool
        Whether to persist the selected route JSON under the output artifacts.
        If disabled with a pyosys-bridge design source, the bridge JSON is
        written to a temporary file for nextpnr and removed after routing.
    check : bool
        Whether a non-zero nextpnr return code should raise an exception.
    live_output : bool
        Whether to stream nextpnr output live while still capturing it.
    report_output : bool
        Whether to append captured nextpnr output to the rendered report.
    report_output_max_lines : int | None
        Maximum trailing stdout/stderr lines appended to the report. ``None``
        includes full output.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    top_name: str | None = None
    out_dir: Path | None = None
    nextpnr_exec: Path | str | None = None
    json_path: Path | None = None
    json_output_path: Path | None = None
    pcf_path: Path | None = None
    pcf_assignment_seed: int = 1
    fasm_path: Path | None = None
    report_path: Path | None = None
    project_dir: Path | None = None
    extra_args: tuple[str, ...] = ()
    write_json: bool = True
    check: bool = True
    live_output: bool = False
    report_output: bool = True
    report_output_max_lines: int | None = 200

    @field_validator("top_name")
    @classmethod
    def _validate_optional_text(cls, value: str | None) -> str | None:
        """Validate optional text fields.

        Parameters
        ----------
        value : str | None
            Optional text value.

        Returns
        -------
        str | None
            Validated optional text.

        Raises
        ------
        ValueError
            If the provided string is empty.
        """
        if value == "":
            raise ValueError("top_name must not be empty")
        return value

    @field_validator("report_output_max_lines")
    @classmethod
    def _validate_optional_non_negative_int(cls, value: int | None) -> int | None:
        """Validate optional line-count limits.

        Parameters
        ----------
        value : int | None
            Optional maximum line count.

        Returns
        -------
        int | None
            Validated line count.

        Raises
        ------
        ValueError
            If the value is negative.
        """
        if value is not None and value < 0:
            raise ValueError("report_output_max_lines must be non-negative")
        return value

    @field_validator("pcf_assignment_seed")
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        """Validate positive integer options.

        Parameters
        ----------
        value : int
            Integer option value.

        Returns
        -------
        int
            Validated value.

        Raises
        ------
        ValueError
            If the value is not positive.
        """
        if value <= 0:
            raise ValueError("pcf_assignment_seed must be greater than 0")
        return value


class NextpnrRouterPaths(BaseModel):
    """Resolved file-system paths for one nextpnr run.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    project_dir : Path
        FABulous project directory used as ``FAB_ROOT``.
    metadata_dir : Path
        Project ``.FABulous`` metadata directory read by nextpnr.
    out_dir : Path
        Directory containing generated route artifacts.
    json_path : Path
        Yosys JSON netlist path.
    pcf_path : Path
        Concrete PCF path.
    fasm_path : Path
        FASM output path.
    report_path : Path
        nextpnr JSON report path.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    project_dir: Path
    metadata_dir: Path
    out_dir: Path
    json_path: Path
    pcf_path: Path
    fasm_path: Path
    report_path: Path


class NextpnrCommandResult(BaseModel):
    """Captured result from one nextpnr subprocess invocation.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    command : tuple[str, ...]
        Full command passed to ``subprocess.run``.
    returncode : int
        Process return code.
    stdout : str
        Captured standard output.
    stderr : str
        Captured standard error.
    """

    model_config = ConfigDict(frozen=True)

    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


class NextpnrRouterResult(BaseModel):
    """Structured result from one FABulous nextpnr routing run.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    options : NextpnrRouterOptions
        User-facing options used for the run.
    top_name : str
        Routed top module name.
    nextpnr_exec : Path | str
        nextpnr executable used for the subprocess.
    paths : NextpnrRouterPaths
        Resolved input and output paths.
    command_result : NextpnrCommandResult
        Captured subprocess result.
    nextpnr_report : dict[str, Any]
        Parsed nextpnr JSON report, or an empty dictionary if no report was
        produced.
    fasm_text : str | None
        Captured FASM output text, or ``None`` if nextpnr did not produce a FASM
        file.
    report_summary : str
        Human-readable route summary.
    warnings : tuple[str, ...]
        Non-fatal diagnostics collected during routing.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    options: NextpnrRouterOptions
    top_name: str
    nextpnr_exec: Path | str
    paths: NextpnrRouterPaths
    command_result: NextpnrCommandResult
    nextpnr_report: dict[str, Any] = Field(default_factory=dict)
    fasm_text: str | None = None
    report_summary: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """Return whether nextpnr finished successfully.

        Returns
        -------
        bool
            ``True`` when the subprocess return code is zero.
        """
        return self.command_result.returncode == 0
