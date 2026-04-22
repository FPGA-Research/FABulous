"""Core analysis engine for design characterization.

This module runs read-only structural analysis on a ``PyosysBridge`` design by first
mapping Yosys JSON to internal models and then computing metrics on those models.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

import networkx as nx
from loguru import logger

from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.models import (
    ChainMetric,
    DesignAnalysisResult,
    DesignAnalysisStats,
    DesignAnalyzerConfig,
    DesignCharacterization,
    LogicalCell,
    TopModuleNetlist,
)
from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.netlist import (
    coarse_fine_custom_breakdown,
    count_unique_signal_bits,
    parse_top_module_json,
)
from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.report import (
    render_design_analysis_report,
)
from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.taxonomy import (
    DEFAULT_TAXONOMY,
    AnalyzerTaxonomy,
    CellFamily,
    ControlSignal,
    DesignTag,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class DesignAnalyzerProgressReporter:
    """Emit concise progress updates for design analysis runs.

    This class keeps logging behavior out of analysis logic so algorithms remain
    focused on computations while still providing useful terminal feedback.

    Parameters
    ----------
    enabled : bool
        If ``True``, progress messages are emitted through the logger.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def on_start(self, top_hint: str | None) -> None:
        """Log analysis start information.

        Parameters
        ----------
        top_hint : str | None
            Requested top module name, if explicitly provided.
        """
        if not self.enabled:
            return
        logger.info(
            "[DesignAnalyzer] Starting analysis"
            + (f" (requested top='{top_hint}')." if top_hint else ".")
        )

    def on_netlist_mapped(
        self,
        top_name: str,
        total_cells: int,
        total_ports: int,
    ) -> None:
        """Log netlist mapping summary.

        Parameters
        ----------
        top_name : str
            Selected top module.
        total_cells : int
            Number of cells in selected top module.
        total_ports : int
            Number of ports in selected top module.
        """
        if not self.enabled:
            return
        logger.info(
            f"[DesignAnalyzer] Parsed top='{top_name}' with "
            f"cells={total_cells}, ports={total_ports}."
        )

    def on_graph_built(self, nodes: int, edges: int) -> None:
        """Log dependency graph size.

        Parameters
        ----------
        nodes : int
            Number of cell nodes in graph.
        edges : int
            Number of directed edges in graph.
        """
        if not self.enabled:
            return
        logger.info(
            f"[DesignAnalyzer] Built dependency graph nodes={nodes}, edges={edges}."
        )

    def on_finish(self, tags: tuple[DesignTag, ...]) -> None:
        """Log completion summary.

        Parameters
        ----------
        tags : tuple[DesignTag, ...]
            Characterization tags assigned to the design.
        """
        if not self.enabled:
            return
        if tags:
            logger.info(
                "[DesignAnalyzer] Finished. Tags: "
                f"{', '.join(tag.value for tag in tags)}"
            )
        else:
            logger.info("[DesignAnalyzer] Finished.")


class CellFamilyClassifier:
    """Classify cell types into analysis families.

    This classifier supports mixed netlists that can contain both coarse Yosys
    primitives (``$...``) and fine gate-level primitives (``$_..._``).
    """

    def __init__(self, taxonomy: AnalyzerTaxonomy) -> None:
        self._taxonomy = taxonomy

    def families_for(self, cell_type: str) -> set[CellFamily]:
        """Return all matching family labels for a cell type.

        Parameters
        ----------
        cell_type : str
            Cell type string.

        Returns
        -------
        set[CellFamily]
            Matching family labels.
        """
        matched: set[CellFamily] = set()
        for family, patterns in self._taxonomy.family_patterns.items():
            if any(pattern.search(cell_type) for pattern in patterns):
                matched.add(family)
        return matched

    def is_sequential(self, cell_type: str) -> bool:
        """Return whether a cell type belongs to sequential logic.

        Parameters
        ----------
        cell_type : str
            Cell type string.

        Returns
        -------
        bool
            ``True`` for sequential cells.
        """
        return any(
            pattern.search(cell_type) for pattern in self._taxonomy.sequential_patterns
        )


@dataclass
class _ConnectivityGraph:
    """Internal connectivity graph representation.

    Attributes
    ----------
    succ : dict[str, set[str]]
        Successor adjacency map from producer cell id to consumer cell ids.
    pred : dict[str, set[str]]
        Predecessor adjacency map from consumer cell id to producer cell ids.
    """

    succ: dict[str, set[str]]
    pred: dict[str, set[str]]


class DesignAnalyzer:
    """Run comprehensive read-only design analysis on a pyosys design.

    Parameters
    ----------
    config : DesignAnalyzerConfig | None
        Analyzer configuration. If ``None``, defaults are used.
    """

    def __init__(self, config: DesignAnalyzerConfig | None = None) -> None:
        self.config: DesignAnalyzerConfig = config or DesignAnalyzerConfig()
        self._taxonomy: AnalyzerTaxonomy = DEFAULT_TAXONOMY
        self._classifier = CellFamilyClassifier(self._taxonomy)
        self._progress = DesignAnalyzerProgressReporter(enabled=self.config.progress)
        self._result: DesignAnalysisResult | None = None

    def analyze(self, design: PyosysBridge) -> DesignAnalysisResult:
        """Analyze a design without modifying it.

        Parameters
        ----------
        design : PyosysBridge
            Source design wrapper to analyze.

        Returns
        -------
        DesignAnalysisResult
            Full analysis result including rendered report text.

        Raises
        ------
        RuntimeError
            If netlist extraction or analysis fails.
        """
        self._progress.on_start(self.config.top_name)

        try:
            netlist_json: dict = design.to_netlist_dict()
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("Failed to export design as JSON through PyosysBridge.")
            raise RuntimeError("Could not export design into Yosys JSON.") from exc

        try:
            netlist: TopModuleNetlist = parse_top_module_json(
                netlist_json,
                top_name=self.config.top_name,
            )
        except Exception as exc:
            logger.exception("Failed to parse Yosys JSON into internal netlist model.")
            raise RuntimeError(
                "Could not parse Yosys JSON netlist for analysis."
            ) from exc

        self._progress.on_netlist_mapped(
            top_name=netlist.top_name,
            total_cells=len(netlist.cells),
            total_ports=len(netlist.ports),
        )

        stats: DesignAnalysisStats = self._analyze_netlist(netlist)
        characterization: DesignCharacterization = self._characterize(stats)

        result = DesignAnalysisResult(
            top_name=netlist.top_name,
            stats=stats,
            characterization=characterization,
            metadata={
                "creator": netlist.creator,
                "selected_top": netlist.top_name,
                "chain_metrics_enabled": str(self.config.include_chain_metrics),
            },
        )
        result.report_summary = render_design_analysis_report(
            result=result,
            max_type_rows=self.config.max_type_rows,
            taxonomy=self._taxonomy,
        )

        self._result = result
        self._progress.on_finish(result.characterization.tags)
        return result

    @property
    def result_data(self) -> DesignAnalysisResult | None:
        """Return the latest result produced by this analyzer instance.

        Returns
        -------
        DesignAnalysisResult | None
            The most recent analysis result, if available.
        """
        return self._result

    def _analyze_netlist(self, netlist: TopModuleNetlist) -> DesignAnalysisStats:
        """Compute raw metrics from a parsed top-module netlist.

        Parameters
        ----------
        netlist : TopModuleNetlist
            Parsed top-module netlist.

        Returns
        -------
        DesignAnalysisStats
            Aggregated analysis metrics.
        """
        stats = DesignAnalysisStats()
        cells: tuple[LogicalCell, ...] = netlist.cells

        stats.total_cells = len(cells)
        stats.total_ports = len(netlist.ports)
        stats.total_nets = count_unique_signal_bits(netlist)

        coarse_fine = coarse_fine_custom_breakdown(cells)
        stats.coarse_internal_cells = coarse_fine.get("coarse", 0)
        stats.fine_gate_cells = coarse_fine.get("fine", 0)
        stats.custom_cells = coarse_fine.get("custom", 0)

        type_counter: Counter[str] = Counter(cell.cell_type for cell in cells)
        stats.cell_type_counts = dict(type_counter)

        family_counter: Counter[CellFamily] = Counter()

        for cell in cells:
            ctype = cell.cell_type
            families = self._classifier.families_for(ctype)
            is_sequential = self._classifier.is_sequential(ctype)

            for fam in families:
                family_counter[fam] += 1

            if CellFamily.MEMORY in families:
                stats.memory_cells += 1
            elif is_sequential:
                stats.sequential_cells += 1
            elif ctype.startswith(("$", "$_")) or families:
                stats.combinational_cells += 1
            else:
                stats.unknown_cells += 1

            if is_sequential:
                self._accumulate_control_port_refs(stats, cell)

        stats.family_counts = dict(family_counter)

        graph = self._build_dependency_graph(cells)
        edge_count: int = sum(len(v) for v in graph.succ.values())
        self._progress.on_graph_built(nodes=len(cells), edges=edge_count)

        fanin_values: list[int] = [len(graph.pred[cell.cell_id]) for cell in cells]
        fanout_values: list[int] = [len(graph.succ[cell.cell_id]) for cell in cells]

        stats.max_fanin = max(fanin_values, default=0)
        stats.avg_fanin = sum(fanin_values) / len(fanin_values) if fanin_values else 0.0
        stats.max_fanout = max(fanout_values, default=0)
        stats.avg_fanout = (
            sum(fanout_values) / len(fanout_values) if fanout_values else 0.0
        )

        if self.config.include_chain_metrics:
            for fam in self._taxonomy.chain_families:
                node_ids: set[str] = {
                    cell.cell_id
                    for cell in cells
                    if fam in self._classifier.families_for(cell.cell_type)
                }
                stats.chain_metrics[fam] = self._compute_chain_metric(
                    family=fam,
                    node_ids=node_ids,
                    full_graph=graph,
                )

        return stats

    def _build_dependency_graph(
        self,
        cells: tuple[LogicalCell, ...],
    ) -> _ConnectivityGraph:
        """Create producer/consumer connectivity graph between cells.

        Parameters
        ----------
        cells : tuple[LogicalCell, ...]
            Cells from the top-module model.

        Returns
        -------
        _ConnectivityGraph
            Directed connectivity graph between cell instances.
        """
        producers: dict[str, set[str]] = defaultdict(set)
        consumers: dict[str, set[str]] = defaultdict(set)

        for cell in cells:
            cid = cell.cell_id

            for bit in cell.output_bits + cell.inout_bits:
                if _is_signal_bit(bit):
                    producers[bit].add(cid)

            for bit in cell.input_bits + cell.inout_bits:
                if _is_signal_bit(bit):
                    consumers[bit].add(cid)

        succ: dict[str, set[str]] = {cell.cell_id: set() for cell in cells}
        pred: dict[str, set[str]] = {cell.cell_id: set() for cell in cells}

        for bit, dst_cells in consumers.items():
            src_cells = producers.get(bit, set())
            if not src_cells:
                continue

            for src in src_cells:
                for dst in dst_cells:
                    if src == dst:
                        continue
                    succ[src].add(dst)
                    pred[dst].add(src)

        return _ConnectivityGraph(succ=succ, pred=pred)

    def _compute_chain_metric(
        self,
        family: CellFamily,
        node_ids: set[str],
        full_graph: _ConnectivityGraph,
    ) -> ChainMetric:
        """Compute connectivity metrics for one selected logic family.

        Parameters
        ----------
        family : CellFamily
            Family name for this metric.
        node_ids : set[str]
            Cell ids that belong to this family.
        full_graph : _ConnectivityGraph
            Full design dependency graph.

        Returns
        -------
        ChainMetric
            Connectivity metrics for this family.
        """
        if not node_ids:
            return ChainMetric(
                family=family,
                candidate_cells=0,
                largest_component=0,
                longest_path=0,
            )

        subgraph = nx.DiGraph()
        subgraph.add_nodes_from(node_ids)

        for src in node_ids:
            for dst in full_graph.succ.get(src, set()):
                if dst in node_ids:
                    subgraph.add_edge(src, dst)

        undirected = subgraph.to_undirected()
        largest_component: int = 0
        if undirected.number_of_nodes() > 0:
            largest_component = max(
                (len(c) for c in nx.connected_components(undirected)),
                default=0,
            )

        if subgraph.number_of_nodes() == 0:
            longest_path: int = 0
        else:
            condensed = nx.condensation(subgraph)
            longest_path = _longest_condensed_path(condensed)

        return ChainMetric(
            family=family,
            candidate_cells=len(node_ids),
            largest_component=largest_component,
            longest_path=longest_path,
        )

    def _accumulate_control_port_refs(
        self,
        stats: DesignAnalysisStats,
        cell: LogicalCell,
    ) -> None:
        """Count control-like port references on a sequential cell.

        Parameters
        ----------
        stats : DesignAnalysisStats
            Mutable aggregate stats.
        cell : LogicalCell
            Sequential cell to inspect.
        """
        for port_name in cell.connections:
            control_signal = self._classify_control_port(port_name)
            if control_signal is ControlSignal.CLOCK:
                stats.clock_port_refs += 1
            elif control_signal is ControlSignal.RESET:
                stats.reset_port_refs += 1
            elif control_signal is ControlSignal.SET:
                stats.set_port_refs += 1
            elif control_signal is ControlSignal.ENABLE:
                stats.enable_port_refs += 1

    def _classify_control_port(self, port_name: str) -> ControlSignal | None:
        """Classify one port name into a control-signal category.

        Parameters
        ----------
        port_name : str
            Raw port name.

        Returns
        -------
        ControlSignal | None
            Matching control category, if any.
        """
        name_upper = port_name.upper()
        for signal, prefixes in self._taxonomy.control_port_prefixes.items():
            if name_upper.startswith(prefixes):
                return signal
        return None

    def _characterize(self, stats: DesignAnalysisStats) -> DesignCharacterization:
        """Derive user-friendly tags, observations, and recommendations.

        Parameters
        ----------
        stats : DesignAnalysisStats
            Raw analysis metrics.

        Returns
        -------
        DesignCharacterization
            Human-centered interpretation of metrics.
        """
        total: int = max(stats.total_cells, 1)

        seq_ratio: float = stats.sequential_cells / total
        comb_ratio: float = stats.combinational_cells / total
        mem_ratio: float = stats.memory_cells / total
        mux_ratio: float = stats.family_counts.get(CellFamily.MUX, 0) / total
        arithmetic_ratio: float = (
            stats.family_counts.get(CellFamily.ARITHMETIC, 0) / total
        )
        carry_ratio: float = stats.family_counts.get(CellFamily.CARRY, 0) / total
        unknown_ratio: float = stats.unknown_cells / total
        thresholds = self._taxonomy.thresholds

        tags: list[DesignTag] = []
        observations: list[str] = []
        warnings: list[str] = []
        recommendations: list[str] = []

        if seq_ratio >= thresholds.sequential_heavy:
            tags.append(DesignTag.SEQUENTIAL_HEAVY)
            observations.append(
                "The design is strongly sequential and likely sensitive to FF/latch "
                "packing and clocking strategies."
            )
        elif comb_ratio >= thresholds.combinational_heavy:
            tags.append(DesignTag.COMBINATIONAL_HEAVY)
            observations.append(
                "The design is predominantly combinational and likely stresses "
                "logic mapping and local routing quality."
            )

        if arithmetic_ratio >= thresholds.arithmetic_heavy:
            tags.append(DesignTag.ARITHMETIC_HEAVY)
            observations.append(
                "Arithmetic primitives are frequent, so dedicated arithmetic/carry "
                "support should significantly impact QoR."
            )

        if carry_ratio >= thresholds.carry_active:
            tags.append(DesignTag.CARRY_ACTIVE)
            observations.append(
                "Carry-related structures are present in meaningful quantity."
            )

        if mux_ratio >= thresholds.mux_heavy:
            tags.append(DesignTag.MUX_HEAVY)
            observations.append(
                "Mux density is high, which can increase control-path routing pressure."
            )

        if mem_ratio >= thresholds.memory_active:
            tags.append(DesignTag.MEMORY_ACTIVE)
            observations.append(
                "Memory-style cells are visible; memory mapping and placement policy "
                "will affect this workload."
            )

        and_depth = stats.chain_metrics.get(
            CellFamily.AND_LIKE,
            ChainMetric(CellFamily.AND_LIKE, 0, 0, 0),
        ).longest_path
        or_depth = stats.chain_metrics.get(
            CellFamily.OR_LIKE,
            ChainMetric(CellFamily.OR_LIKE, 0, 0, 0),
        ).longest_path
        mux_depth = stats.chain_metrics.get(
            CellFamily.MUX,
            ChainMetric(CellFamily.MUX, 0, 0, 0),
        ).longest_path

        if max(and_depth, or_depth) >= thresholds.deep_boolean_chain:
            tags.append(DesignTag.DEEP_BOOLEAN_CHAINS)
            observations.append(
                "Deep AND/OR connectivity is present, which may create "
                "long critical paths."
            )

        if mux_depth >= thresholds.deep_mux_chain:
            observations.append(
                "Mux dependency depth is high, suggesting potential control-path "
                "timing risk."
            )

        if not tags:
            tags.append(DesignTag.MIXED_STRUCTURE)
            observations.append(
                "The design has a balanced mixed structure without one "
                "dominant primitive class."
            )

        if unknown_ratio >= thresholds.unknown_warning:
            warnings.append(
                "A large fraction of cells could not be clearly classified. "
                "Interpret family-level conclusions with caution."
            )

        if stats.custom_cells >= max(1, int(thresholds.custom_warning_ratio * total)):
            warnings.append(
                "Custom/non-Yosys cell types are common; technology-specific behavior "
                "may dominate implementation results."
            )

        if DesignTag.ARITHMETIC_HEAVY in tags or DesignTag.CARRY_ACTIVE in tags:
            recommendations.append(
                "Prioritize architecture variants with strong carry-chain and "
                "arithmetic support."
            )

        if DesignTag.MUX_HEAVY in tags:
            recommendations.append(
                "Prioritize routing-flexible switch matrices and evaluate "
                "mux-aware packing."
            )

        if DesignTag.DEEP_BOOLEAN_CHAINS in tags:
            recommendations.append(
                "Track critical-path timing closely; consider architecture "
                "options that reduce "
                "logic depth or improve local interconnect."
            )

        if seq_ratio >= thresholds.sequential_heavy:
            recommendations.append(
                "Include register-rich benchmark variants and evaluate "
                "sequential packing quality."
            )

        return DesignCharacterization(
            tags=tuple(tags),
            observations=tuple(observations),
            warnings=tuple(warnings),
            recommendations=tuple(recommendations),
        )


def _is_signal_bit(bit: str) -> bool:
    """Return whether a normalized bit token is a non-constant signal.

    Parameters
    ----------
    bit : str
        Normalized bit token.

    Returns
    -------
    bool
        ``True`` when token denotes a non-constant signal.
    """
    return bit.lower() not in {"0", "1", "x", "z"}


def _longest_condensed_path(condensed_graph: nx.DiGraph) -> int:
    """Compute longest weighted path length on a condensation DAG.

    Each condensation node represents one SCC in the original graph and carries
    a ``members`` field. This function counts path length in terms of member-cell
    counts, which gives a robust chain-depth estimate even when cycles exist.

    Parameters
    ----------
    condensed_graph : nx.DiGraph
        Condensation DAG from ``nx.condensation``.

    Returns
    -------
    int
        Longest weighted path length.
    """
    if condensed_graph.number_of_nodes() == 0:
        return 0

    dist: dict[int, int] = {}
    topo_nodes = list(nx.topological_sort(condensed_graph))

    for node in topo_nodes:
        members = condensed_graph.nodes[node].get("members", set())
        node_weight: int = len(members) if isinstance(members, set) else 1

        best_pred: int = 0
        for pred in condensed_graph.predecessors(node):
            best_pred = max(best_pred, dist.get(pred, 0))

        dist[node] = best_pred + max(node_weight, 1)

    return max(dist.values(), default=0)
