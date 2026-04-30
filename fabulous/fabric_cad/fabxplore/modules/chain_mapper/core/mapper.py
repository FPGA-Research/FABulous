"""Coordinate techmap-based lowering into generic chain primitives.

This module owns the execution flow around the chain mapper. It optionally runs
Yosys normalization passes, asks the selected per-cell renderers to generate
techmap Verilog, reads the generic chain blackbox, applies all generated map
files to a ``PyosysBridge`` design, and collects report data.

Cell-specific behavior deliberately lives outside this module in
``cell_mappers.py``. Keeping those renderers separate lets this class stay
focused on orchestration: command ordering, temporary-file lifetime, pyosys
interaction, and before/after cell histograms.
"""

import shlex
import tempfile
from dataclasses import replace
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.cell_mappers import (
    AluTechmap,
    ChainCellTechmap,
    ReduceAndTechmap,
    ReduceBoolTechmap,
    ReduceOrTechmap,
    ReduceXorTechmap,
)
from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.models import (
    ChainMapperConfig,
    ChainMapperResult,
    ChainMapperStats,
    ChainOp,
)
from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.report import (
    render_chain_mapper_report,
)
from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.templates import (
    CHAIN_BLACKBOX_TEMPLATE,
    TEMPLATE_ENV,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class ChainMapper:
    """Run normalization and generated techmap for generic chain mapping.

    Parameters
    ----------
    config : ChainMapperConfig
        Chain mapper configuration controlling selected operations, chunking,
        normalization passes, and emitted primitive name.
    """

    def __init__(self, config: ChainMapperConfig) -> None:
        self.config = config
        self.cell_mappers = self._build_cell_mappers()
        self._last_result: ChainMapperResult | None = None

    def map_from_design(self, design: PyosysBridge) -> ChainMapperResult:
        """Run chain mapping on a pyosys design in place.

        Parameters
        ----------
        design : PyosysBridge
            Active pyosys design to normalize and techmap.

        Returns
        -------
        ChainMapperResult
            Result bundle containing generated techmap text, command log, cell
            histograms, and report text.
        """
        commands: list[str] = []

        if self.config.normalize_extract_reduce:
            self._run(design, "extract_reduce", commands)
        if self.config.normalize_alumacc:
            self._run(design, "alumacc", commands)
            self._run(design, "opt_clean", commands)

        before_counts = self._count_top_cells(design)

        techmap_files = self.render_techmap_files()
        techmap_verilog = self.render_techmap_verilog()
        if self.config.read_chain_blackbox:
            design.read_verilog_string(self.render_chain_blackbox(), blackbox=True)

        techmap_paths = self._write_techmap_files(techmap_files)
        try:
            if techmap_paths:
                map_args = " ".join(
                    f"-map {shlex.quote(str(path))}" for path in techmap_paths
                )
                self._run(design, f"techmap -autoproc {map_args}", commands)
            if self.config.run_clean:
                self._run(design, "clean", commands)

            after_counts = self._count_top_cells(design)
            result = ChainMapperResult(
                top_name=self.config.top_name,
                chain_name=self.config.chain_name,
                config=self.config,
                stats=ChainMapperStats(
                    before_counts=before_counts,
                    after_counts=after_counts,
                    commands=tuple(commands),
                    generated_modules=self._generated_modules(),
                ),
                techmap_verilog=techmap_verilog,
                techmap_path=str(techmap_paths[0])
                if self.config.debug_keep_techmap and len(techmap_paths) == 1
                else None,
                techmap_paths=tuple(str(path) for path in techmap_paths)
                if self.config.debug_keep_techmap
                else (),
            )
            result = replace(result, report_summary=render_chain_mapper_report(result))
            self._last_result = result
            return result
        finally:
            if not self.config.debug_keep_techmap:
                for techmap_path in techmap_paths:
                    techmap_path.unlink(missing_ok=True)

    def render_techmap_verilog(self) -> str:
        """Render all selected chain techmap modules as one inspection string.

        Returns
        -------
        str
            Concatenated Verilog map file text for inspection and reports.
        """
        sections = []
        for name, verilog in self.render_techmap_files():
            sections.append(f"// --- {name} ---\n{verilog}")
        return "\n".join(sections)

    def render_techmap_files(self) -> tuple[tuple[str, str], ...]:
        """Render one techmap Verilog file per selected source cell.

        Returns
        -------
        tuple[tuple[str, str], ...]
            ``(name, verilog)`` pairs where each Verilog string is suitable for
            one ``techmap -map`` input.
        """
        return tuple(cell_mapper.render() for cell_mapper in self.cell_mappers)

    def render_chain_blackbox(self) -> str:
        """Render the blackbox declaration for the emitted chain primitive.

        Returns
        -------
        str
            Verilog blackbox module text.
        """
        return TEMPLATE_ENV.from_string(CHAIN_BLACKBOX_TEMPLATE).render(
            chain_name=self.config.chain_name,
            alu_init_mode=self.config.alu_init_mode.value,
        )

    @property
    def report_summary(self) -> str:
        """Return the latest rendered report.

        Returns
        -------
        str
            Latest report, or a placeholder if no mapping run is available.
        """
        return (
            self._last_result.report_summary
            if self._last_result
            else "No result available."
        )

    @property
    def result_data(self) -> ChainMapperResult | None:
        """Return the latest structured mapping result.

        Returns
        -------
        ChainMapperResult | None
            Latest result object if available.
        """
        return self._last_result

    def _build_cell_mappers(self) -> tuple[ChainCellTechmap, ...]:
        """Build the selected per-cell techmap renderer instances.

        Returns
        -------
        tuple[ChainCellTechmap, ...]
            Cell-specific techmap renderers in deterministic map order.
        """
        cell_mappers: list[ChainCellTechmap] = []
        if ChainOp.REDUCE_OR in self.config.ops:
            cell_mappers.append(ReduceOrTechmap(self.config))
        if ChainOp.REDUCE_AND in self.config.ops:
            cell_mappers.append(ReduceAndTechmap(self.config))
        if ChainOp.REDUCE_XOR in self.config.ops:
            cell_mappers.append(ReduceXorTechmap(self.config))
        if ChainOp.REDUCE_BOOL in self.config.ops:
            cell_mappers.append(ReduceBoolTechmap(self.config))
        if ChainOp.ALU in self.config.ops:
            cell_mappers.append(AluTechmap(self.config))
        return tuple(cell_mappers)

    def _generated_modules(self) -> tuple[str, ...]:
        """Return generated techmap module names for reporting.

        Returns
        -------
        tuple[str, ...]
            Names of modules generated by the techmap, for report summaries.
        """
        return tuple(cell_mapper.module_name for cell_mapper in self.cell_mappers)

    def _run(
        self,
        design: PyosysBridge,
        command: str,
        commands: list[str],
    ) -> None:
        """Run a pyosys command and record it.

        Parameters
        ----------
        design : PyosysBridge
            Design wrapper to mutate.
        command : str
            Yosys command to execute.
        commands : list[str]
            Mutable command log to append to.
        """
        design.run_pass(command)
        commands.append(command)

    def _count_top_cells(self, design: PyosysBridge) -> dict[str, int]:
        """Count cells by type in the configured top module.

        Parameters
        ----------
        design : PyosysBridge
            Design wrapper to inspect.

        Returns
        -------
        dict[str, int]
            Cell-type histogram for ``config.top_name``.
        """
        netlist = design.to_netlist_dict()
        module = netlist.get("modules", {}).get(self.config.top_name, {})
        counts: dict[str, int] = {}
        for cell in module.get("cells", {}).values():
            cell_type = str(cell.get("type", ""))
            counts[cell_type] = counts.get(cell_type, 0) + 1
        return counts

    def _write_techmap_files(
        self,
        techmap_files: tuple[tuple[str, str], ...],
    ) -> tuple[Path, ...]:
        """Write generated techmap Verilog snippets to temporary files.

        Parameters
        ----------
        techmap_files : tuple[tuple[str, str], ...]
            Rendered ``(name, verilog)`` techmap file contents.

        Returns
        -------
        tuple[Path, ...]
            Temporary file paths containing the map files.
        """
        paths: list[Path] = []
        for name, verilog in techmap_files:
            with tempfile.NamedTemporaryFile(
                mode="w",
                prefix=f"{name}_",
                suffix=".v",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(verilog)
                paths.append(Path(tmp.name))
        return tuple(paths)
