"""Coordinate parsing, mapping, and export for LUT combinator workflows.

This module defines the high-level orchestration class used by tests and scripts to run
the full mapping flow from multiple input representations. It keeps the mapper core
focused on feasibility and pairing, while this layer manages JSON loading, pyosys
conversion, and report generation.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.lut_combinator.core.architecture import (
    FracLutArchitecture,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.json_transform import (
    apply_mapping_to_json,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.models import MappingResult
from fabulous.fabric_cad.fabxplore.lut_combinator.core.netlist import (
    load_json_dict,
    parse_model_json,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.packer import (
    MatchingMode,
    PairLutMapper,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.lut_combinator.core.report import render_report


@dataclass(frozen=True)
class LutCombinatorConfig:
    """Store immutable options for one LUT combinator mapping run.

    The configuration bundles architecture selection, top module name,
    optional LUT(K+1) passthrough behavior, and matching strategy.

    Attributes
    ----------
    architecture : FracLutArchitecture
        Target fractional LUT architecture model.
    top_name : str
        Top-level module name to parse and map.
    passthrough : bool
        If ``True``, map LUT(K+1) cells through architecture full-LUT mode.
    mode : MatchingMode
        Pair selection strategy used by the mapper.
    debug : bool
        If ``True``, enable debug logging in pyosys bridge for design conversions.
    """

    architecture: FracLutArchitecture
    top_name: str
    passthrough: bool = False
    mode: MatchingMode = MatchingMode.MAX_WEIGHT
    debug: bool = False


class LutCombinator:
    """Run end-to-end LUT mapping for one configured architecture.

    This facade accepts JSON, Verilog, or pyosys design input and produces
    mapped artifacts in JSON/design/Verilog forms plus reporting metadata.
    It is intentionally stateful to expose lazy properties after each run.

    The object stores mapping configuration and lazily generates
    mapped design/verilog views only when requested by properties.

    Parameters
    ----------
    config : LutCombinatorConfig
        Mapping configuration for this instance.
    """

    def __init__(self, config: LutCombinatorConfig) -> None:
        self.config = config

        self._input_json: dict | None = None
        self._mapped_json: dict | None = None
        self._mapped_result: MappingResult | None = None

        self._mapped_design: object | None = None
        self._mapped_verilog: str | None = None

    def _print_info(self, message: str) -> None:
        """Print one user-facing progress line.

        Parameters
        ----------
        message : str
            Text to print with a standard ``LutCombinator`` prefix.
        """
        logger.info(f"[LutCombinator] {message}")

    def _print_start(self, source_kind: str, source: str) -> None:
        """Print standardized startup details for a mapping run.

        This includes source information, top name, matching mode, passthrough
        setting, and architecture dimensions so users can confirm configuration
        before long-running mapping steps begin.

        Parameters
        ----------
        source_kind : str
            Human-readable source type (for example ``"JSON"`` or
            ``"Verilog"``).
        source : str
            Source path or descriptive source label.
        """
        arch = self.config.architecture
        self._print_info(
            f"Starting mapping from {source_kind}: {source} "
            f"(top={self.config.top_name}, arch={arch.name}, "
            f"mode={self.config.mode.value}, passthrough={self.config.passthrough})"
        )
        self._print_info(
            f"Architecture config: frac_lut_size={arch.frac_lut_size}, "
            f"num_shared_inputs={arch.num_shared_inputs}, "
            f"private_inputs_per_lut={arch.private_inputs_per_lut}"
        )

    def _print_stage(self, stage: str) -> None:
        """Print a pipeline stage checkpoint message.

        Parameters
        ----------
        stage : str
            Short description of the current processing stage.
        """
        self._print_info(stage)

    def _print_result_summary(self, result: MappingResult) -> None:
        """Print final high-level statistics for a completed mapping run.

        Parameters
        ----------
        result : MappingResult
            Mapping result object containing aggregate counters to summarize.
        """
        self._print_info(
            "Done. "
            f"before={result.stats.total_luts_before}, "
            f"mapped_groups={result.stats.mapped_groups}, "
            f"mapped_luts={result.stats.mapped_luts}, "
            f"passthrough_luts={result.stats.passthrough_luts}, "
            f"after={result.stats.total_cells_after}"
        )

    @property
    def mapped_result(self) -> MappingResult | None:
        """Return the most recent mapping result object.

        This property is ``None`` until one of the ``map_from_*`` methods
        has run successfully.

        Returns
        -------
        MappingResult | None
            Last computed mapping result, or ``None`` if not available.
        """
        return self._mapped_result

    @property
    def mapped_json_dict(self) -> dict | None:
        """Return the mapped netlist JSON dictionary for the last run.

        Returns
        -------
        dict | None
            In-memory mapped JSON object, or ``None`` if mapping has not
            been executed yet.
        """
        return self._mapped_json

    @property
    def mapped_json_string(self) -> str | None:
        """Return pretty-printed mapped JSON text for the last run.

        Returns
        -------
        str | None
            Indented JSON string when mapped output exists, otherwise
            ``None``.
        """
        return (
            None
            if self._mapped_json is None
            else (json.dumps(self._mapped_json, indent=2))
        )

    @property
    def mapped_design(self) -> object | None:
        """Return a lazy pyosys design view of mapped JSON output.

        The design object is created on first access and cached.

        Returns
        -------
        object | None
            pyosys design object for the mapped netlist, or ``None`` when
            no mapped JSON exists.
        """
        if self._mapped_design is None and self._mapped_json is not None:
            bridge: PyosysBridge = PyosysBridge(debug=self.config.debug)
            bridge.load_netlist_dict(self._mapped_json)
            self._mapped_design = bridge.design
        return self._mapped_design

    @property
    def mapped_verilog_string(self) -> str | None:
        """Return lazy Verilog emission from mapped JSON output.

        Verilog text is emitted on first access and cached for reuse.

        Returns
        -------
        str | None
            Emitted Verilog netlist string, or ``None`` when no mapped
            JSON is available.
        """
        if self._mapped_verilog is None and self._mapped_json is not None:
            self._print_stage("Emitting mapped Verilog from mapped JSON.")
            bridge: PyosysBridge = PyosysBridge(debug=self.config.debug)
            bridge.load_netlist_dict(self._mapped_json)
            self._mapped_verilog = bridge.get_verilog_string
            self._print_stage("Mapped Verilog emission complete.")
        return self._mapped_verilog

    def map_from_json(self, json_input: str | Path | dict) -> MappingResult:
        """Run mapping from JSON input and store mapped artifacts.

        Parameters
        ----------
        json_input : str | Path | dict
            JSON source as file path, raw JSON string, or parsed dict.

        Returns
        -------
        MappingResult
            Mapping result for the configured architecture and top module.
        """
        self._print_start("JSON", str(json_input))
        self._print_stage("Loading JSON input.")
        src: dict = load_json_dict(json_input)
        self._print_stage("JSON input loaded.")
        self._input_json = src
        return self._run_mapping(src)

    def map_from_verilog(self, verilog_input: str | Path) -> MappingResult:
        """Run mapping from a Verilog file by converting through pyosys JSON.

        Parameters
        ----------
        verilog_input : str | Path
            Path to Verilog netlist source.

        Returns
        -------
        MappingResult
            Mapping result for the configured architecture and top module.
        """
        path: Path = Path(verilog_input)
        self._print_start("Verilog", str(path))
        self._print_stage("Reading Verilog into pyosys design.")
        bridge: PyosysBridge = PyosysBridge(debug=self.config.debug)
        bridge.read_verilog_path(path)
        self._print_stage("Converting source design to JSON dictionary.")
        self._input_json = bridge.get_netlist_dict
        self._print_stage("Source design conversion complete.")
        return self._run_mapping(self._input_json)

    def map_from_design(self, design: object) -> MappingResult:
        """Run mapping from an existing pyosys design object.

        Parameters
        ----------
        design : object
            pyosys design instance containing the source netlist.

        Returns
        -------
        MappingResult
            Mapping result for the configured architecture and top module.
        """
        self._print_start("pyosys design", "<in-memory>")
        self._print_stage("Converting input design to JSON dictionary.")
        bridge: PyosysBridge = PyosysBridge(debug=self.config.debug)
        bridge.load_design(design)
        self._input_json = bridge.get_netlist_dict
        self._print_stage("Input design conversion complete.")
        return self._run_mapping(self._input_json)

    def build_report(self) -> str:
        """Render a textual mapping report for the latest run.

        Returns
        -------
        str
            Report text produced from mapped result and template.

        Raises
        ------
        RuntimeError
            If no mapping run is available yet.
        """
        if self._mapped_result is None:
            raise RuntimeError("No mapping run available. Call map_* first.")
        return render_report(self._mapped_result)

    def _run_mapping(self, src_json: dict) -> MappingResult:
        """Execute the core mapping pipeline from parsed JSON input.

        This internal helper parses LUT cells, runs pair mapping, applies
        structural JSON replacement, and refreshes all cached views.

        Parameters
        ----------
        src_json : dict
            Parsed source netlist JSON dictionary.

        Returns
        -------
        MappingResult
            Mapping result object with updated metadata.
        """
        self._print_stage("Parsing LUT cells from source netlist.")
        model = parse_model_json(src_json, top_name=self.config.top_name)
        self._print_stage(f"Parsed {len(model.lut_cells)} LUT cells.")

        self._print_stage("Running LUT packing/matching.")
        mapper: PairLutMapper = PairLutMapper(
            architecture=self.config.architecture,
            passthrough=self.config.passthrough,
            mode=self.config.mode,
        )
        result: MappingResult = mapper.map_luts(
            list(model.lut_cells), top_name=model.top_name
        )
        self._print_stage("Applying mapped cells back to JSON netlist.")

        mapped_json: dict = apply_mapping_to_json(src_json, result)

        self._mapped_result = result
        self._mapped_json = mapped_json
        self._mapped_design = None
        self._mapped_verilog = None

        result.metadata["mapped_json_size"] = len(json.dumps(mapped_json))
        self._print_result_summary(result)
        return result
