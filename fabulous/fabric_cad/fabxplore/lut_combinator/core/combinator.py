"""Coordinate parsing, mapping, and export for LUT combinator workflows.

This module defines the high-level orchestration class used by tests and scripts to run
the full mapping flow from multiple input representations. It keeps the mapper core
focused on feasibility and pairing, while this layer manages JSON loading, pyosys
conversion, and report generation.
"""

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.lut_combinator.core.architecture import (
    FracLutArchitecture,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.json_transform import (
    apply_mapping_to_json,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.models import (
    LutSpec,
    MappingResult,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.netlist import (
    parse_model_json,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.packer import (
    MatchingMode,
    PairLutMapper,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.report import render_report
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


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
    lut_spec : LutSpec
        LUT specification defining naming patterns and parameters for LUT cells.
    passthrough : bool
        If ``True``, map LUT(K+1) cells through architecture full-LUT mode.
    mode : MatchingMode
        Pair selection strategy used by the mapper.
    debug : bool
        If ``True``, enable debug logging in pyosys bridge for design conversions.
    """

    architecture: FracLutArchitecture
    top_name: str
    lut_spec: LutSpec
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
        self.print_name = "[LutCombinator]"

        self._mapped_netlist_dict: dict | None = None
        self._mapped_result: MappingResult | None = None

    def map_from_design(
        self, design: PyosysBridge, inplace: bool = False
    ) -> MappingResult:
        """Run mapping from an existing pyosys design object.

        Parameters
        ----------
        design : PyosysBridge
            pyosys design wrapper containing the source netlist.
        inplace : bool
            If True, modify the input design in place with mapped cells.
            If False, do not modify the input design and only return mapping
            results.

        Returns
        -------
        MappingResult
            Mapping result for the configured architecture and top module.
        """
        bridge: PyosysBridge = design
        bridge.load_design(design.design)
        netl: dict = bridge.to_netlist_dict()

        arch = self.config.architecture
        logger.info(
            f"{self.print_name} "
            f"Starting mapping. "
            f"(top={self.config.top_name}, arch={arch.name}, "
            f"mode={self.config.mode.value}, passthrough={self.config.passthrough})"
        )
        logger.info(
            f"{self.print_name} "
            f"Architecture config: frac_lut_size={arch.frac_lut_size}, "
            f"num_shared_inputs={arch.num_shared_inputs}, "
            f"private_inputs_per_lut={arch.private_inputs_per_lut}"
        )

        result = self._run_mapping(netl)

        if inplace:
            bridge.load_netlist_dict(self._mapped_netlist_dict)

        return result

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

    def write_report(self, path: Path) -> None:
        """Write a mapping report to a text file.

        Parameters
        ----------
        path : Path
            Output file path for the report.
        """
        report_text = self.build_report()
        path.write_text(report_text, encoding="utf-8")

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
        model = parse_model_json(
            model_json=src_json,
            top_name=self.config.top_name,
            lut_spec=self.config.lut_spec,
        )

        mapper: PairLutMapper = PairLutMapper(
            architecture=self.config.architecture,
            passthrough=self.config.passthrough,
            mode=self.config.mode,
        )
        result: MappingResult = mapper.map_luts(
            list(model.lut_cells), top_name=model.top_name
        )

        mapped_netlist_dict: dict = apply_mapping_to_json(
            model_json=src_json, mapping=result
        )

        result.report_summary = render_report(result)

        self._mapped_result = result
        self._mapped_netlist_dict = mapped_netlist_dict

        logger.info(
            f"{self.print_name} "
            f"Done. "
            f"before={result.stats.total_luts_before}, "
            f"mapped_groups={result.stats.mapped_groups}, "
            f"mapped_luts={result.stats.mapped_luts}, "
            f"passthrough_luts={result.stats.passthrough_luts}, "
            f"after={result.stats.total_cells_after}"
        )

        return result
