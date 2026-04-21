"""Pyosys custom pass wrapper for the DesignAnalyzer.

This pass runs read-only design analysis on a ``PyosysBridge`` object and stores
structured result data plus a rendered report summary.
"""

from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.analyzer import (
    DesignAnalyzer,
)
from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.models import (
    DesignAnalysisResult,
    DesignAnalyzerConfig,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class DesignAnalyzerPass(SynthPass):
    """Read-only pyosys pass for comprehensive design characterization.

    Attributes
    ----------
    top_name : str | None
        Optional explicit top module name for analysis.
    include_chain_metrics : bool
        If ``True``, compute connectivity chain metrics.
    max_type_rows : int
        Maximum number of rows in the report's cell-type table.
    progress : bool
        If ``True``, emit progress logs during analysis.
    """

    top_name: str | None = None
    include_chain_metrics: bool = True
    max_type_rows: int = 24
    progress: bool = True

    _result: DesignAnalysisResult | None = None

    def run_on(self, design: PyosysBridge) -> None:
        """Run design analysis without modifying the source design.

        Parameters
        ----------
        design : PyosysBridge
            Design wrapper to analyze.
        """
        cfg = DesignAnalyzerConfig(
            top_name=self.top_name,
            include_chain_metrics=self.include_chain_metrics,
            max_type_rows=self.max_type_rows,
            progress=self.progress,
        )
        analyzer = DesignAnalyzer(config=cfg)
        self._result = analyzer.analyze(design)

    @property
    def report_summary(self) -> str:
        """Return report summary string from the latest run.

        Returns
        -------
        str
            Rendered report summary.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> DesignAnalysisResult | None:
        """Return structured result data from the latest run.

        Returns
        -------
        DesignAnalysisResult | None
            Latest result object if available.
        """
        return self._result
