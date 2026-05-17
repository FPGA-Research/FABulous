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
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.ff_materializer_pass import (
    FfMaterializerPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_combinator_pass import (
    LutCombinatorPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_decomposer_pass import (
    LutDecomposerPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_layering_pass import (
    LutLayeringPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_mapper_pass import (
    LutMapperPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.morph_tile_pass import (
    MorphTilePass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.placement_hints_pass import (
    PlacementHintsPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.reg_absorber_pass import (
    RegAbsorberPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import (
    PyosysBridge,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.models import (
        FfPortsInputAlias,
        LaneInput,
    )
    from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.architecture import (
        FracLutArchitecture,
    )
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
        MorphCircuitKind,
    )
    from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.models import (
        PlacementRuleInput,
    )
    from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
        ConfigValue,
        FfPortsInput,
        RuleInput,
    )
    from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass
    from fabulous.fabulous_api import FABulous_API


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

        self._pass_history: list[SynthPass] = []

        self._latest_lut_mapping_result: MappingResult | None = None
        self._latest_frac_lut_architecture: FracLutArchitecture | None = None
        self._lut_layering_count: int = 0

        self._fabulous_api: FABulous_API | None = None

    def attach_fabulous_api(self, api: FABulous_API) -> None:
        """Attach the loaded FABulous project API to this architecture flow.

        Parameters
        ----------
        api : FABulous_API
            FABulous API instance with project context and fabric data.
        """
        self._fabulous_api = api

    @property
    def fab(self) -> FABulous_API:
        """Return the attached FABulous API instance.

        Raises
        ------
        RuntimeError
            If no FABulous API instance has been attached.
        """
        if self._fabulous_api is None:
            raise RuntimeError("FABulous API not attached to architecture flow.")
        return self._fabulous_api

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

    def design_report_summary_pass(
        self,
        log_report: bool = True,
        path: Path | None = None,
    ) -> str:
        """Summary report of the current design.

        Parameters
        ----------
        log_report : bool
            If ``True``, log the report summary.
        path : Path | None
            Optional file path to write the report summary to.
            If ``None``, do not write to a file.

        Returns
        -------
        str
            The generated report summary string.
        """
        r_sep: str = """
            ===================================================================
        """.strip()

        report: str = f"\n{r_sep}\n\n".join(
            r.report_summary for r in self._pass_history
        )

        if log_report:
            self.log_info(report)
        if path is not None:
            path.write_text(report)

        return report

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

        self._pass_history.append(result)

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
        self._lut_layering_count = 0
        self.add_primitive(result.verilog_model)

        self._pass_history.append(result)

        return result

    def design_lut_layering_pass(
        self,
        overlay_verilog_paths: list[Path],
        overlay_top_name: str,
        log_report: bool = True,
        top_name: str | None = None,
        overlay_prefix: str | None = None,
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
        overlay_prefix : str | None
            Prefix applied to overlay ports, netnames, and cells. If ``None``,
            use ``design1_`` for the first layer, ``design2_`` for the second
            layer, and so on.
        base_prefix : str | None
            Optional prefix applied to base ports and netnames. The default
            ``design0_`` is applied only to the first layer; later layers keep
            the already-prefixed base unchanged to avoid names such as
            ``design0_design0_*``. ``None`` always keeps base names unchanged.
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

        effective_overlay_prefix = (
            overlay_prefix
            if overlay_prefix is not None
            else f"design{self._lut_layering_count + 1}_"
        )
        effective_base_prefix = base_prefix
        if self._lut_layering_count > 0 and base_prefix == "design0_":
            effective_base_prefix = None

        result = LutLayeringPass(
            overlay_verilog_paths=overlay_verilog_paths,
            overlay_top_name=overlay_top_name,
            base_mapping=self._latest_lut_mapping_result,
            architecture=self._latest_frac_lut_architecture,
            top_name=top_name or self.design.top_name(),
            overlay_prefix=effective_overlay_prefix,
            base_prefix=effective_base_prefix,
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
            self._lut_layering_count += 1

        self.add_primitive(result.verilog_model)

        self._pass_history.append(result)

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

        self._pass_history.append(result)

        return result

    def design_morph_tile_pass(
        self,
        tile_verilog_path: Path,
        tile_top_name: str,
        tile_inputs: list[str],
        tile_outputs: list[str],
        log_report: bool = True,
        enabled_circuits: list[str | MorphCircuitKind] | None = None,
        circuit_options: dict[str, object] | None = None,
        tile_configs: list[str] | None = None,
        tile_config_prefixes: list[str] | None = None,
        tile_fixed_configs: dict[str, int | bool] | None = None,
        include_unused_inputs: bool = False,
        max_replacements: int | None = None,
        map_luts_first: bool = False,
        lut_map_size: int | None = None,
        allow_input_reuse: bool = True,
        allow_input_constants: bool = False,
        allow_output_reuse: bool = False,
        track_progress: bool = True,
        progress_chunk_size: int = 50,
        top_name: str | None = None,
    ) -> MorphTilePass:
        """Run morph-tile replacement on the current design.

        Parameters
        ----------
        tile_verilog_path : Path
            Verilog source file containing the morph-tile module.
        tile_top_name : str
            Module name to instantiate for replacements.
        tile_inputs : list[str]
            Candidate tile data input ports.
        tile_outputs : list[str]
            Candidate tile output ports.
        log_report : bool
            If ``True``, log the morph-tile report after execution.
        enabled_circuits : list[str | MorphCircuitKind] | None
            Circuit adapters to enable. ``None`` enables only normal ``$lut``.
        circuit_options : dict[str, object] | None
            Generic adapter option payload for future circuit kinds.
        tile_configs : list[str] | None
            Explicit tile configuration input ports.
        tile_config_prefixes : list[str] | None
            Prefixes used to classify BLIF inputs as configuration bits.
        tile_fixed_configs : dict[str, int | bool] | None
            Configuration bits fixed before candidate BLIF generation and
            emitted on replacement tile instances.
        include_unused_inputs : bool
            Whether tile inputs unused by a solved mapping are tied to zero.
        max_replacements : int | None
            Optional cap on successful replacements.
        map_luts_first : bool
            Whether to run a simple LUT mapping flow before replacement.
        lut_map_size : int | None
            Maximum LUT size for optional pre-mapping.
        allow_input_reuse : bool
            Whether SAT may map several tile inputs to the same LUT input.
        allow_input_constants : bool
            Whether SAT may tie tile inputs to constants.
        allow_output_reuse : bool
            Whether SAT may reuse tile outputs.
        track_progress : bool
            Whether to log morph-tile mapping progress.
        progress_chunk_size : int
            Number of processed candidate LUTs between progress updates.
        top_name : str | None
            Top module to process. If ``None``, use the current design top.

        Returns
        -------
        MorphTilePass
            Pass instance containing result and report data.
        """
        result = MorphTilePass(
            tile_verilog_path=tile_verilog_path,
            tile_top_name=tile_top_name,
            tile_inputs=tile_inputs,
            tile_outputs=tile_outputs,
            enabled_circuits=enabled_circuits,
            circuit_options=circuit_options,
            tile_configs=tile_configs,
            tile_config_prefixes=tile_config_prefixes,
            tile_fixed_configs=tile_fixed_configs,
            include_unused_inputs=include_unused_inputs,
            max_replacements=max_replacements,
            map_luts_first=map_luts_first,
            lut_map_size=lut_map_size,
            allow_input_reuse=allow_input_reuse,
            allow_input_constants=allow_input_constants,
            allow_output_reuse=allow_output_reuse,
            track_progress=track_progress,
            progress_chunk_size=progress_chunk_size,
            top_name=top_name or self.design.top_name(),
            debug=self.debug,
        )
        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        self.add_primitive(result.verilog_model)

        self._pass_history.append(result)

        return result

    def design_decompose_lut_pass(
        self,
        source_lut_widths: list[int],
        leaf_lut_width: int,
        mux_verilog_path: Path,
        mux_top_name: str,
        mux_data_inputs: list[str],
        mux_select_inputs: list[str],
        mux_outputs: list[str],
        log_report: bool = True,
        mux_configs: list[str] | None = None,
        mux_config_prefixes: list[str] | None = None,
        mux_dependency_paths: list[Path] | None = None,
        include_unused_mux_inputs: bool = False,
        max_decompositions: int | None = None,
        track_progress: bool = True,
        progress_chunk_size: int = 100,
        top_name: str | None = None,
    ) -> LutDecomposerPass:
        """Run high-LUT decomposition on the current design.

        Parameters
        ----------
        source_lut_widths : list[int]
            Source ``$lut`` widths to decompose.
        leaf_lut_width : int
            Width of generated cofactor ``$lut`` cells.
        mux_verilog_path : Path
            Verilog source containing the mux primitive.
        mux_top_name : str
            Mux primitive module name.
        mux_data_inputs : list[str]
            Candidate mux data input ports.
        mux_select_inputs : list[str]
            Candidate mux select input ports.
        mux_outputs : list[str]
            Candidate mux output ports.
        log_report : bool
            If ``True``, log the decomposition report after execution.
        mux_configs : list[str] | None
            Explicit mux configuration input ports.
        mux_config_prefixes : list[str] | None
            Prefixes used to classify mux configuration inputs.
        mux_dependency_paths : list[Path] | None
            Additional Verilog dependencies needed by the mux primitive.
        include_unused_mux_inputs : bool
            Whether unused mux inputs are tied to zero.
        max_decompositions : int | None
            Optional cap on successful decompositions.
        track_progress : bool
            Whether to log progress.
        progress_chunk_size : int
            Number of processed candidates between progress messages.
        top_name : str | None
            Top module to process. If ``None``, use the current design top.

        Returns
        -------
        LutDecomposerPass
            Pass instance containing result and report data.
        """
        result = LutDecomposerPass(
            source_lut_widths=source_lut_widths,
            leaf_lut_width=leaf_lut_width,
            mux_verilog_path=mux_verilog_path,
            mux_top_name=mux_top_name,
            mux_data_inputs=mux_data_inputs,
            mux_select_inputs=mux_select_inputs,
            mux_outputs=mux_outputs,
            mux_configs=mux_configs,
            mux_config_prefixes=mux_config_prefixes,
            mux_dependency_paths=mux_dependency_paths,
            include_unused_mux_inputs=include_unused_mux_inputs,
            max_decompositions=max_decompositions,
            track_progress=track_progress,
            progress_chunk_size=progress_chunk_size,
            top_name=top_name or self.design.top_name(),
            debug=self.debug,
        )
        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        self.add_primitive(result.verilog_model)

        self._pass_history.append(result)

        return result

    def design_absorb_registers_pass(
        self,
        cell_types: list[str],
        rules: list[RuleInput],
        log_report: bool = True,
        ff_ports: FfPortsInput | None = None,
        allow_extra_fanout: bool = False,
        strict: bool = False,
        track_progress: bool = True,
        progress_chunk_size: int = 100,
        top_name: str | None = None,
    ) -> RegAbsorberPass:
        """Absorb adjacent FFs into primitive sequential ports.

        Parameters
        ----------
        cell_types : list[str]
            Primitive cell types that may absorb FFs.
        rules : list[RuleInput]
            Absorption rules. Dicts are validated as pydantic models
            internally.
        log_report : bool
            If ``True``, log the register absorption report.
        ff_ports : FfPortsInput | None
            Supported FF cell port mapping. ``None`` selects defaults.
        allow_extra_fanout : bool
            Whether non-clean fanout patterns may be absorbed.
        strict : bool
            Whether invalid matches raise instead of being skipped.
        track_progress : bool
            Whether to log progress.
        progress_chunk_size : int
            Number of processed checks between progress updates.
        top_name : str | None
            Top module to process. If ``None``, use the current design top.

        Returns
        -------
        RegAbsorberPass
            Pass instance containing result and report data.
        """
        result = RegAbsorberPass(
            cell_types=cell_types,
            rules=rules,
            ff_ports=ff_ports,
            allow_extra_fanout=allow_extra_fanout,
            strict=strict,
            track_progress=track_progress,
            progress_chunk_size=progress_chunk_size,
            top_name=top_name or self.design.top_name(),
        )
        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        self._pass_history.append(result)

        return result

    def design_materialize_registers_pass(
        self,
        tile_verilog_path: Path,
        tile_top_name: str,
        tile_inputs: list[str],
        tile_outputs: list[str],
        lanes: list[LaneInput],
        log_report: bool = True,
        tile_configs: list[str] | None = None,
        tile_config_prefixes: list[str] | None = None,
        ff_ports: FfPortsInputAlias | None = None,
        pack_multiple_ffs_per_tile: bool = True,
        auto_config: bool = False,
        auto_config_overwrites: dict[str, ConfigValue] | None = None,
        max_replacements: int | None = None,
        fail_on_invalid_lane: bool = True,
        fail_on_auto_config_unsat: bool = False,
        fail_on_pack_conflict: bool = False,
        fail_on_unmaterialized_ff: bool = False,
        track_progress: bool = True,
        progress_chunk_size: int = 100,
        top_name: str | None = None,
    ) -> FfMaterializerPass:
        """Replace standalone FFs with configured tile register lanes.

        Parameters
        ----------
        tile_verilog_path : Path
            Verilog source file containing the replacement tile module.
        tile_top_name : str
            Module name to instantiate for replacements.
        tile_inputs : list[str]
            Scalar tile input ports exposed to the pass.
        tile_outputs : list[str]
            Scalar tile output ports exposed to the pass.
        lanes : list[LaneInput]
            Register lane definitions. Dicts are validated as pydantic models.
        log_report : bool
            If ``True``, log the FF materializer report.
        tile_configs : list[str] | None
            Explicit scalar tile configuration bits.
        tile_config_prefixes : list[str] | None
            Prefixes used to discover config bits from emitted BLIF.
        ff_ports : FfPortsInputAlias | None
            Supported FF cell mapping. ``None`` selects defaults.
        pack_multiple_ffs_per_tile : bool
            Whether multiple lanes may be filled in one replacement tile
            instance.
        auto_config : bool
            If ``True``, solve one shared identity-path config for each packed
            lane set. Lane-local ``config`` entries are invalid in this mode.
        auto_config_overwrites : dict[str, ConfigValue] | None
            Fixed config constraints used by ``auto_config`` and copied into
            emitted replacements. Ignored when ``auto_config`` is ``False``.
        max_replacements : int | None
            Optional cap on replaced FFs.
        fail_on_invalid_lane : bool
            Whether invalid lane definitions should raise instead of being
            ignored.
        fail_on_auto_config_unsat : bool
            Whether unsatisfiable auto-config attempts should raise.
        fail_on_pack_conflict : bool
            Whether config, parameter, or shared-port packing conflicts should
            raise.
        fail_on_unmaterialized_ff : bool
            Whether any supported FF left unreplaced should raise.
        track_progress : bool
            Whether progress should be logged.
        progress_chunk_size : int
            Number of processed FFs between progress updates.
        top_name : str | None
            Top module to process. If ``None``, use the current design top.

        Returns
        -------
        FfMaterializerPass
            Pass instance containing result and report data.
        """
        result = FfMaterializerPass(
            tile_verilog_path=tile_verilog_path,
            tile_top_name=tile_top_name,
            tile_inputs=tile_inputs,
            tile_outputs=tile_outputs,
            lanes=lanes,
            tile_configs=tile_configs,
            tile_config_prefixes=tile_config_prefixes,
            ff_ports=ff_ports,
            pack_multiple_ffs_per_tile=pack_multiple_ffs_per_tile,
            auto_config=auto_config,
            auto_config_overwrites=auto_config_overwrites,
            max_replacements=max_replacements,
            fail_on_invalid_lane=fail_on_invalid_lane,
            fail_on_auto_config_unsat=fail_on_auto_config_unsat,
            fail_on_pack_conflict=fail_on_pack_conflict,
            fail_on_unmaterialized_ff=fail_on_unmaterialized_ff,
            track_progress=track_progress,
            progress_chunk_size=progress_chunk_size,
            top_name=top_name or self.design.top_name(),
        )
        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        self.add_primitive(result.verilog_model)

        self._pass_history.append(result)

        return result

    def design_placement_hints_pass(
        self,
        rules: list[PlacementRuleInput],
        log_report: bool = True,
        attribute_prefix: str = "FAB_CLUSTER",
        overwrite_existing: bool = False,
        fail_on_conflict: bool = True,
        track_progress: bool = True,
        progress_chunk_size: int = 100,
        top_name: str | None = None,
    ) -> PlacementHintsPass:
        """Add structural placement hint attributes to existing cells.

        Parameters
        ----------
        rules : list[PlacementRuleInput]
            Structural hint rules. Each rule is a typed model or dictionary with
            a ``kind`` field.
        log_report : bool
            If ``True``, log the placement-hints report.
        attribute_prefix : str
            Prefix used for emitted placement-hint attributes.
        overwrite_existing : bool
            Whether existing placement-hint attributes may be replaced.
        fail_on_conflict : bool
            Whether generated or existing attribute conflicts should raise.
        track_progress : bool
            Whether progress should be logged.
        progress_chunk_size : int
            Number of processed candidate cells between progress updates.
        top_name : str | None
            Top module to process. If ``None``, use the current design top.

        Returns
        -------
        PlacementHintsPass
            Pass instance containing result and report data.
        """
        result = PlacementHintsPass(
            rules=rules,
            attribute_prefix=attribute_prefix,
            overwrite_existing=overwrite_existing,
            fail_on_conflict=fail_on_conflict,
            track_progress=track_progress,
            progress_chunk_size=progress_chunk_size,
            top_name=top_name or self.design.top_name(),
        )
        result.run_on(self.design)

        if log_report:
            self.log_info(result.report_summary)

        self._pass_history.append(result)

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

        self._pass_history.append(result)

        return result

    @abstractmethod
    def run_flow(self) -> None:
        """Run the full synthesis pipeline for a user design."""
