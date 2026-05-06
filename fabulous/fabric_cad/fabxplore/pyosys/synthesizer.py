"""Defines the base class for architecture synthesizers.

This module defines the `ArchitectureSynthesizer` abstract base class, which
serves as a blueprint for synthesizers that generate FPGA architectures.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.models import (
    AluInitMode,
    ChainOp,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    MappingResult,
    MatchingMode,
)
from fabulous.fabric_cad.fabxplore.modules.lut_mapper.core.models import (
    LutMapperBackend,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.chain_mapper_pass import (
    ChainMapperPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.design_analyzer_pass import (
    DesignAnalyzerPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_combinator_pass import (
    LutCombinatorPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_layering_pass import (
    LutLayeringPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_mapper_pass import (
    LutMapperPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import (
    PyosysBridge,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.architecture import (
        FracLutArchitecture,
    )


class ArchitectureSynthesizer(ABC):
    """Interface for architecture-specific synthesis pipelines.

    Parameters
    ----------
    debug : bool
        Enable debug mode for verbose logging and intermediate design dumps.
    """

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self.design: PyosysBridge = PyosysBridge(debug=self.debug)
        self.primitives: set[str] = set()

        self._latest_lut_mapping_result: MappingResult | None = None
        self._latest_frac_lut_architecture: FracLutArchitecture | None = None

    def add_primitive(self, primitive: str | Path) -> None:
        """Add a primitive to the set of primitives.

        Parameters
        ----------
        primitive : str | Path
            The Verilog source code or file path of the primitive to add.
            Internally verilog files are stored as verilog code strings.
        """
        self.design.run_pass("read_verilog -lib -overwrite +/fabulous/prims.v")

        if isinstance(primitive, Path):
            primitive = primitive.read_text()
        self.primitives.add(primitive)

        for prim in self.primitives:
            self.design.read_verilog_string(prim, blackbox=True)

    def log_info(self, message: str) -> None:
        """Log an informational message.

        Parameters
        ----------
        message : str
            The message to log.
        """
        logger.info(message)

    def design_analyzer_pass(
        self,
        log_report: bool = True,
        top_name: str | None = None,
        include_chain_metrics: bool = True,
        max_type_rows: int = 24,
        progress: bool = True,
    ) -> DesignAnalyzerPass:
        """Run the DesignAnalyzerPass on the current design.

        Parameters
        ----------
        log_report : bool
            If ``True``, log a summary report of the design analysis results.
        top_name : str | None
            The name of the top module in the design to be processed.
            If None, use the top module of the current design.
        include_chain_metrics : bool
            Whether to include chain metrics in the analysis.
        max_type_rows : int
            The maximum number of type rows to consider in the analysis.
        progress : bool
            Whether to display progress during the analysis.

        Returns
        -------
        DesignAnalyzerPass
            The instance of the DesignAnalyzerPass after execution,
            containing the results.
        """
        result = DesignAnalyzerPass(
            top_name=top_name or self.design.top_name(),
            include_chain_metrics=include_chain_metrics,
            max_type_rows=max_type_rows,
            progress=progress,
        )

        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        return result

    def design_lut_combinator_pass(
        self,
        log_report: bool = True,
        frac_lut_size: int = 4,
        num_shared_inputs: int = 3,
        lut_name: str = "__frac_lut",
        top_name: str | None = None,
        passthrough: bool = False,
        mode: MatchingMode = MatchingMode.MAXIMAL,
        use_select_as_data_in_pair_mode: bool = False,
        allow_duplicate_private_nets: bool = True,
        reorder_leftover_luts: bool = False,
        reorder_opt_luts: bool = False,
    ) -> LutCombinatorPass:
        """Run the LutCombinatorPass on the current design.

        Parameters
        ----------
        log_report : bool
            If ``True``, log a summary report of the LUT combinator results.
        frac_lut_size : int
            The size of the fractional LUTs to be used in the architecture.
        num_shared_inputs : int
            The number of shared inputs allowed in the LUT architecture.
        lut_name : str
            The name to be used for the generated LUT cells.
        top_name : str | None
            The name of the top module in the design to be processed.
            If None, use the top module of the current design.
        passthrough : bool
            Whether to allow passthrough of non-mapped full LUTs.
        mode : MatchingMode
            The matching mode to be used for combining LUTs.
        use_select_as_data_in_pair_mode : bool
            Whether to enable the select-as-data dual-LUT pairing mode for more
            flexible mappings.
        allow_duplicate_private_nets : bool
            Whether pair mapping may assign the same net to private pins on both
            LUT sides.
        reorder_leftover_luts : bool
            Whether to run post-pack leftover reordering before the mapped FRAC
            cells are applied to the design.
        reorder_opt_luts : bool
            Whether to spend existing leftover LUT capacity to remove pair
            cells before the mapped FRAC cells are applied to the design.

        Returns
        -------
        LutCombinatorPass
            The instance of the LutCombinatorPass after execution,
            containing the results.
        """
        result = LutCombinatorPass(
            frac_lut_size=frac_lut_size,
            num_shared_inputs=num_shared_inputs,
            lut_name=lut_name,
            top_name=top_name or self.design.top_name(),
            passthrough=passthrough,
            mode=mode,
            use_select_as_data_in_pair_mode=use_select_as_data_in_pair_mode,
            allow_duplicate_private_nets=allow_duplicate_private_nets,
            reorder_leftover_luts=reorder_leftover_luts,
            reorder_opt_luts=reorder_opt_luts,
        )

        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        self._latest_lut_mapping_result = result.result_data
        self._latest_frac_lut_architecture = result.architecture
        self.add_primitive(result.verilog_model)

        return result

    def design_lut_layering_pass(
        self,
        overlay_verilog_paths: list[Path],
        overlay_top_name: str,
        log_report: bool = True,
        top_name: str | None = None,
        overlay_prefix: str = "design1_",
        base_prefix: str | None = "design0_",
        overlay_lut_size: int | None = None,
        overlay_mapper_max_tries: int = 4,
        overlay_mapper_cost_scale: int = 100,
        overlay_mapper_size_penalty: float = 1.4,
        overlay_mapper_retry_penalty: float = 1.8,
        overlay_mapper_fallback_lut_size: int = 2,
    ) -> LutLayeringPass:
        """Run LUT layering on the current packed design.

        Parameters
        ----------
        overlay_verilog_paths : list[Path]
            Verilog source files for the overlay design.
        overlay_top_name : str
            Top module name of the overlay design.
        log_report : bool
            If ``True``, log the LUT layering report after execution.
        top_name : str | None
            Base design top module. If ``None``, use the current design top.
        overlay_prefix : str
            Prefix applied to overlay ports, netnames, and cells.
        base_prefix : str | None
            Optional prefix applied to base ports and netnames. ``None`` keeps
            base names unchanged.
        overlay_lut_size : int | None
            Manual maximum LUT width used for overlay mapping. If set, skip the
            inventory-aware retry loop.
        overlay_mapper_max_tries : int
            Number of inventory-aware ABC9 cost-vector attempts before fallback.
        overlay_mapper_cost_scale : int
            Integer baseline for generated ABC9 LUT costs.
        overlay_mapper_size_penalty : float
            Compactness preference strength for larger LUTs in early attempts.
        overlay_mapper_retry_penalty : float
            Larger-LUT penalty multiplier used to push later attempts toward LUT2.
        overlay_mapper_fallback_lut_size : int
            Final forced maximum LUT size if inventory-aware attempts fail.

        Returns
        -------
        LutLayeringPass
            Pass instance containing layering result and report data.

        Raises
        ------
        RuntimeError
            If the LUT combinator pass has not been run in this synthesizer.
        """
        if (
            self._latest_lut_mapping_result is None
            or self._latest_frac_lut_architecture is None
        ):
            raise RuntimeError(
                "LUT layering requires running design_lut_combinator_pass first."
            )

        result = LutLayeringPass(
            overlay_verilog_paths=overlay_verilog_paths,
            overlay_top_name=overlay_top_name,
            base_mapping=self._latest_lut_mapping_result,
            architecture=self._latest_frac_lut_architecture,
            top_name=top_name or self.design.top_name(),
            overlay_prefix=overlay_prefix,
            base_prefix=base_prefix,
            overlay_lut_size=overlay_lut_size,
            overlay_mapper_max_tries=overlay_mapper_max_tries,
            overlay_mapper_cost_scale=overlay_mapper_cost_scale,
            overlay_mapper_size_penalty=overlay_mapper_size_penalty,
            overlay_mapper_retry_penalty=overlay_mapper_retry_penalty,
            overlay_mapper_fallback_lut_size=overlay_mapper_fallback_lut_size,
            debug=self.debug,
        )

        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        if result.result_data is not None:
            self._latest_lut_mapping_result = result.result_data.mapping

        self.add_primitive(result.verilog_model)

        return result

    def design_chain_mapper_pass(
        self,
        log_report: bool = True,
        chain_name: str = "__chain",
        ops: tuple[ChainOp, ...] = (
            ChainOp.ALU,
            ChainOp.REDUCE_AND,
            ChainOp.REDUCE_OR,
            ChainOp.REDUCE_XOR,
            ChainOp.REDUCE_BOOL,
        ),
        chunk_size: int = 4,
        min_chain_prims: int = 2,
        max_chain_prims: int | None = None,
        and_to_or: bool = False,
        or_to_and: bool = False,
        leave_short: bool = True,
        normalize_extract_reduce: bool = True,
        normalize_alumacc: bool = True,
        alu_init_mode: AluInitMode = AluInitMode.XOR,
        read_chain_blackbox: bool = True,
        run_clean: bool = True,
        debug_keep_techmap: bool = False,
        top_name: str | None = None,
    ) -> ChainMapperPass:
        """Run generated techmap chain mapping on the current design.

        Parameters
        ----------
        log_report : bool
            If ``True``, log the chain mapper report after execution.
        chain_name : str
            Target-independent primitive emitted by the generated techmap.
        ops : tuple[ChainOp, ...]
            Operation families to map.
        chunk_size : int
            Number of reduction input bits absorbed by one chain primitive.
        min_chain_prims : int
            Minimum number of emitted chain primitives before mapping.
        max_chain_prims : int | None
            Optional maximum number of primitives allowed for one mapped cell.
        and_to_or : bool
            Map AND reductions through OR chains using inversion.
        or_to_and : bool
            Map OR/BOOL reductions through AND chains using inversion.
        leave_short : bool
            Leave candidates shorter than ``min_chain_prims`` untouched.
        normalize_extract_reduce : bool
            Run ``extract_reduce`` before generated techmap.
        normalize_alumacc : bool
            Run ``alumacc`` before generated techmap.
        alu_init_mode : AluInitMode
            INIT encoding mode for ``$alu`` chain primitive instances.
        read_chain_blackbox : bool
            Read a blackbox declaration for ``chain_name`` before techmap.
        run_clean : bool
            Run ``clean`` after generated techmap.
        debug_keep_techmap : bool
            Keep the generated temporary techmap file for inspection.
        top_name : str | None
            Optional top module name. If ``None``, use current design top.

        Returns
        -------
        ChainMapperPass
            Pass instance containing the latest result and report.
        """
        result = ChainMapperPass(
            top_name=top_name or self.design.top_name(),
            chain_name=chain_name,
            ops=ops,
            chunk_size=chunk_size,
            min_chain_prims=min_chain_prims,
            max_chain_prims=max_chain_prims,
            and_to_or=and_to_or,
            or_to_and=or_to_and,
            leave_short=leave_short,
            normalize_extract_reduce=normalize_extract_reduce,
            normalize_alumacc=normalize_alumacc,
            alu_init_mode=alu_init_mode,
            read_chain_blackbox=read_chain_blackbox,
            run_clean=run_clean,
            debug_keep_techmap=debug_keep_techmap,
        )

        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        self.add_primitive(result.verilog_model)

        return result

    def design_lut_mapper_pass(
        self,
        log_report: bool = True,
        base_lut_size: int = 4,
        num_shared_inputs: int = 3,
        use_select_as_data_in_pair_mode: bool = False,
        max_lut_size: int = 8,
        backend: LutMapperBackend | str = LutMapperBackend.ABC9,
        sharing_penalty_factor: float = 1.0,
        size_penalty_factor: float = 1.0,
        pair_discount_strength: float = 0.5,
        larger_lut_base_multiplier: float = 2.0,
        larger_lut_discount_factor: float = 0.9,
        cost_scale: int = 100,
        min_cost: int = 1,
        max_cost: int | None = None,
        raw_cost_vector: tuple[int | float, ...] | None = None,
        run_opt_lut: bool = True,
        run_clean: bool = True,
        top_name: str | None = None,
    ) -> LutMapperPass:
        """Run architecture-aware ABC LUT mapping on the current design.

        Parameters
        ----------
        log_report : bool
            If ``True``, log the LUT mapper report after execution.
        base_lut_size : int
            Size ``K`` of the internal LUT fragments in the target fractional
            LUT architecture.
        num_shared_inputs : int
            Nominal number of shared inputs between the two internal LUT
            fragments.
        use_select_as_data_in_pair_mode : bool
            Whether pairability estimation should account for select-as-data
            mode as one additional effective private input.
        max_lut_size : int
            Largest LUT width ABC may generate.
        backend : LutMapperBackend | str
            Yosys backend used for LUT mapping. Supported values are ``"abc"``
            and ``"abc9"``.
        sharing_penalty_factor : float
            Multiplier for the required-shared-input pair table.
        size_penalty_factor : float
            Multiplier for the unused-capacity pair table.
        pair_discount_strength : float
            Maximum analytical cost discount for widths that pair well.
        larger_lut_base_multiplier : float
            Multiplicative growth factor for composed LUTs wider than
            ``base_lut_size``.
        larger_lut_discount_factor : float
            Per-extra-input discount for wider composed LUTs.
        cost_scale : int
            Base integer cost scale for analytical ABC costs.
        min_cost : int
            Minimum emitted ABC cost.
        max_cost : int | None
            Optional maximum emitted ABC cost.
        raw_cost_vector : tuple[int | float, ...] | None
            Optional direct ABC cost vector. If provided, analytical costs are
            ignored. A one-entry vector is broadcast to ``max_lut_size``.
        run_opt_lut : bool
            Whether to run ``opt_lut`` after the selected backend.
        run_clean : bool
            Whether to run ``clean`` after the selected backend.
        top_name : str | None
            Optional top module name for reporting. If ``None``, use the
            current design top.

        Returns
        -------
        LutMapperPass
            The pass instance after execution, containing the cost-vector
            result and rendered report.
        """
        result = LutMapperPass(
            base_lut_size=base_lut_size,
            num_shared_inputs=num_shared_inputs,
            use_select_as_data_in_pair_mode=use_select_as_data_in_pair_mode,
            max_lut_size=max_lut_size,
            backend=backend,
            sharing_penalty_factor=sharing_penalty_factor,
            size_penalty_factor=size_penalty_factor,
            pair_discount_strength=pair_discount_strength,
            larger_lut_base_multiplier=larger_lut_base_multiplier,
            larger_lut_discount_factor=larger_lut_discount_factor,
            cost_scale=cost_scale,
            min_cost=min_cost,
            max_cost=max_cost,
            raw_cost_vector=raw_cost_vector,
            run_opt_lut=run_opt_lut,
            run_clean=run_clean,
            top_name=top_name or self.design.top_name(),
            debug=self.debug,
        )

        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        return result

    @abstractmethod
    def synthesize(self) -> None:
        """Run the full synthesis pipeline for a user design."""

    @abstractmethod
    def generate_primitives(self) -> None:
        """Generate primitive definitions required by this architecture."""

    @abstractmethod
    def generate_switch_matrix(self) -> None:
        """Generate switch-matrix resources for routing integration."""
