"""Build pairing graphs and emit packed mapping results for LUT cells.

This module contains the performance-focused mapper that applies the configured
architecture feasibility checks, runs graph matching, and produces packed/passthrough
collections plus run statistics.
"""

import networkx as nx
from loguru import logger

from fabulous.fabric_cad.fabxplore.lut_combinator.core.architecture import (
    FracLutArchitecture,
    PairBinding,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.models import (
    LogicalLutCell,
    MappingResult,
    MappingStats,
    MatchingMode,
)


class PairMappingProgressTracker:
    """Report batched mapping progress while keeping algorithm code clean.

    This helper centralizes user-facing progress output for the pair mapper.
    It stores internal counters for each mapping phase and prints updates at
    adaptive batch intervals so long runs still look active and responsive.

    Parameters
    ----------
    enabled : bool
        If ``True``, emit progress lines to standard output.
    mode : MatchingMode
        Matching strategy selected for pair mapping.
    passthrough : bool
        Whether LUT(K+1) passthrough mapping is enabled.
    """

    def __init__(self, enabled: bool, mode: MatchingMode, passthrough: bool) -> None:
        self.enabled = enabled
        self.mode = mode
        self.passthrough = passthrough

        self._kp1_total = 0
        self._kp1_done = 0
        self._kp1_mapped = 0
        self._kp1_rejected = 0
        self._kp1_batch = 1

        self._pair_total = 0
        self._pair_done = 0
        self._pair_feasible = 0
        self._pair_batch = 1

    def on_start(self, total_cells: int, top_name: str) -> None:
        """Print a mapping start banner with core run settings.

        Parameters
        ----------
        total_cells : int
            Number of LUT cells considered for mapping in the top module.
        top_name : str
            Name of the current top module.
        """
        self._print(
            f"Start map_luts: total_cells={total_cells}, top={top_name}, "
            f"mode={self.mode.value}, passthrough={self.passthrough}"
        )

    def on_partitioned(
        self,
        pair_candidates: int,
        kp1_candidates: int,
        blocked: int,
    ) -> None:
        """Print LUT partition counts after width-based classification.

        Parameters
        ----------
        pair_candidates : int
            Number of LUTs eligible for pair matching (width ``<= K``).
        kp1_candidates : int
            Number of LUTs with width ``K+1``.
        blocked : int
            Number of LUTs too wide for this architecture.
        """
        self._print(
            "Partitioned LUTs: "
            f"pair_candidates={pair_candidates}, "
            f"kp1_candidates={kp1_candidates}, "
            f"blocked={blocked}"
        )

    def begin_kp1_packing(self, total: int) -> None:
        """Reset counters for the LUT(K+1) passthrough packing phase.

        Parameters
        ----------
        total : int
            Total number of LUT(K+1) candidates to process.
        """
        self._kp1_total = total
        self._kp1_done = 0
        self._kp1_mapped = 0
        self._kp1_rejected = 0
        self._kp1_batch = self._batch_size_for_total(total)

    def on_kp1_result(self, mapped: bool) -> None:
        """Record one LUT(K+1) outcome and emit batched progress if needed.

        Parameters
        ----------
        mapped : bool
            ``True`` when the current LUT(K+1) was mapped; otherwise rejected.
        """
        self._kp1_done += 1
        if mapped:
            self._kp1_mapped += 1
        else:
            self._kp1_rejected += 1

        if not self._should_emit(self._kp1_done, self._kp1_total, self._kp1_batch):
            return
        self._print_progress(
            "LUT(K+1) passthrough packing",
            self._kp1_done,
            self._kp1_total,
            f"mapped={self._kp1_mapped}, rejected={self._kp1_rejected}",
        )

    def on_kp1_passthrough_disabled(self, count: int) -> None:
        """Print a notice when LUT(K+1) mapping is disabled by configuration.

        Parameters
        ----------
        count : int
            Number of LUT(K+1) cells moved directly to passthrough.
        """
        if count <= 0:
            return
        self._print(
            f"Passthrough disabled: moved {count} LUT(K+1) cells to passthrough."
        )

    def begin_pair_scan(self, node_count: int) -> None:
        """Reset counters and announce the pair-feasibility scan.

        Parameters
        ----------
        node_count : int
            Number of graph nodes (pair candidate LUTs) in the scan.
        """
        self._pair_total = (node_count * (node_count - 1)) // 2
        self._pair_done = 0
        self._pair_feasible = 0
        self._pair_batch = self._batch_size_for_total(self._pair_total)
        self._print(
            f"Building candidate graph: nodes={node_count}, "
            f"possible_pairs={self._pair_total}"
        )

    def on_pair_checked(self, feasible: bool) -> None:
        """Record one candidate-pair check and print batched scan progress.

        Parameters
        ----------
        feasible : bool
            ``True`` if the tested pair can be packed by the architecture.
        """
        self._pair_done += 1
        if feasible:
            self._pair_feasible += 1

        if not self._should_emit(self._pair_done, self._pair_total, self._pair_batch):
            return
        self._print_progress(
            "Pair feasibility scan",
            self._pair_done,
            self._pair_total,
            f"feasible_edges={self._pair_feasible}",
        )

    def on_graph_ready(self, graph: nx.Graph) -> None:
        """Print graph summary after pair-candidate graph construction.

        Parameters
        ----------
        graph : nx.Graph
            Fully built feasibility graph used by the matching stage.
        """
        self._print(
            f"Candidate graph ready: nodes={graph.number_of_nodes()}, "
            f"edges={graph.number_of_edges()}"
        )

    def on_matching_start(self) -> None:
        """Print a message when matching computation begins."""
        self._print(f"Running matching: mode={self.mode.value}")

    def on_matching_done(self, selected_pairs: int) -> None:
        """Print matching completion and selected pair count.

        Parameters
        ----------
        selected_pairs : int
            Number of matched LUT pairs selected by the solver.
        """
        self._print(f"Matching complete: selected_pairs={selected_pairs}")

    def on_unmatched_to_passthrough(self, count: int) -> None:
        """Print count of unmatched candidates moved to passthrough.

        Parameters
        ----------
        count : int
            Number of unmatched pair-candidate LUTs.
        """
        self._print(f"Unmatched pair candidates moved to passthrough: {count}")

    def on_summary(self, stats: MappingStats) -> None:
        """Print final high-level mapping statistics for the run.

        Parameters
        ----------
        stats : MappingStats
            Aggregated counters produced by the mapping process.
        """
        self._print(
            "Mapping summary: "
            f"mapped_groups={stats.mapped_groups}, "
            f"mapped_luts={stats.mapped_luts}, "
            f"passthrough_luts={stats.passthrough_luts}, "
            f"total_after={stats.total_cells_after}"
        )

    def _print(self, message: str) -> None:
        """Emit one prefixed progress line when progress output is enabled.

        Parameters
        ----------
        message : str
            Message text to print after the standard mapper prefix.
        """
        if self.enabled:
            logger.info(f"[PairLutMapper] {message}")

    def _print_progress(
        self, label: str, done: int, total: int, extra: str = ""
    ) -> None:
        """Print a formatted progress line with percentage completion.

        Parameters
        ----------
        label : str
            Phase label displayed at the beginning of the progress line.
        done : int
            Number of completed items in the current phase.
        total : int
            Total number of items for the current phase.
        extra : str
            Optional suffix with phase-specific counters.
        """
        if total <= 0:
            self._print(f"{label}: 0/0")
            return
        pct: float = (100.0 * done) / float(total)
        suffix = f" ({extra})" if extra else ""
        self._print(f"{label}: {done}/{total} ({pct:.1f}%){suffix}")

    def _should_emit(self, done: int, total: int, batch: int) -> bool:
        """Decide whether a batched progress update should be emitted now.

        Parameters
        ----------
        done : int
            Number of completed items.
        total : int
            Total number of items to process.
        batch : int
            Batch stride used for periodic updates.

        Returns
        -------
        bool
            ``True`` when a progress line should be printed.
        """
        if total <= 0:
            return True
        return done % batch == 0 or done == total

    def _batch_size_for_total(self, total: int) -> int:
        """Choose an adaptive progress batch size from phase workload.

        Parameters
        ----------
        total : int
            Total number of items in the current phase.

        Returns
        -------
        int
            Batch size used to throttle progress output frequency.
        """
        if total <= 0:
            return 1
        if total <= 2_000:
            return max(1, total // 10)
        if total <= 50_000:
            return 2_500
        if total <= 500_000:
            return 20_000
        return 100_000


class PairLutMapper:
    """Map logical LUTs into fractional packed cells using graph matching.

    The mapper supports optional LUT(K+1) passthrough decomposition and
    two pair-selection strategies provided by NetworkX.

    Parameters
    ----------
    architecture : FracLutArchitecture
        Target architecture used for pair/full-LUT feasibility checks.
    passthrough : bool
        If ``True``, attempt to map LUT(K+1) cells using architecture
        full-LUT decomposition before pair matching.
    mode : MatchingMode
        Matching strategy used on the candidate pairing graph.
    progress : bool
        If ``True``, print progress updates during mapping.
    """

    def __init__(
        self,
        architecture: FracLutArchitecture,
        passthrough: bool = False,
        mode: MatchingMode = MatchingMode.MAX_WEIGHT,
        progress: bool = True,
    ) -> None:
        self.arch = architecture
        self.passthrough = passthrough
        self.mode = mode
        self.progress = progress

    def map_luts(self, cells: list[LogicalLutCell], top_name: str) -> MappingResult:
        """Run LUT mapping and return packed result with statistics.

        The flow partitions LUTs by width, optionally handles LUT(K+1),
        builds a candidate graph for pair-feasible LUTs, chooses matching,
        and composes the final packed/passthrough result bundle.

        Parameters
        ----------
        cells : list[LogicalLutCell]
            Logical LUT cells extracted from the source top module.
        top_name : str
            Name of the top module associated with these cells.

        Returns
        -------
        MappingResult
            Mapping output including packed cells, passthrough LUTs,
            aggregate counters, and execution metadata.
        """
        progress = PairMappingProgressTracker(
            enabled=self.progress,
            mode=self.mode,
            passthrough=self.passthrough,
        )
        progress.on_start(total_cells=len(cells), top_name=top_name)

        pair_candidates: list[LogicalLutCell] = [
            c for c in cells if c.width <= self.arch.frac_lut_size
        ]
        single_kp1: list[LogicalLutCell] = [
            c for c in cells if c.width == self.arch.frac_lut_size + 1
        ]
        blocked: list[LogicalLutCell] = [
            c for c in cells if c.width > self.arch.frac_lut_size + 1
        ]

        progress.on_partitioned(
            pair_candidates=len(pair_candidates),
            kp1_candidates=len(single_kp1),
            blocked=len(blocked),
        )

        mapped: list = []
        passthrough: list[LogicalLutCell] = list(blocked)

        # Handle LUT(K+1) cells with architecture full-LUT decomposition if enabled.
        if self.passthrough:
            progress.begin_kp1_packing(total=len(single_kp1))
            for lut in single_kp1:
                # Old behavior:

                # New behavior: unify single-cell mapping via bind_single_lut.
                mapped_cell = self.arch.bind_single_lut(lut)
                if mapped_cell is None:
                    passthrough.append(lut)
                    progress.on_kp1_result(mapped=False)
                    continue
                mapped.append(mapped_cell)
                progress.on_kp1_result(mapped=True)
        else:
            passthrough.extend(single_kp1)
            progress.on_kp1_passthrough_disabled(count=len(single_kp1))

        graph: nx.Graph = nx.Graph()
        graph.add_nodes_from(range(len(pair_candidates)))

        bindings: dict[tuple[int, int], PairBinding] = {}
        input_sets: list[set[str]] = [set(c.input_nets) for c in pair_candidates]

        progress.begin_pair_scan(node_count=len(pair_candidates))

        # Build a weighted graph where edges represent feasible pairings and weights
        # correspond to the number of shared inputs (for max-weight matching).
        for i in range(len(pair_candidates)):
            for j in range(i + 1, len(pair_candidates)):
                binding: PairBinding | None = self.arch.try_bind_pair(
                    pair_candidates[i], pair_candidates[j]
                )

                progress.on_pair_checked(feasible=binding is not None)

                if binding is None:
                    continue

                shared: int = len(input_sets[i] & input_sets[j])
                graph.add_edge(i, j, weight=shared)
                bindings[(i, j)] = binding

        progress.on_graph_ready(graph)
        progress.on_matching_start()

        # Select pairs using the configured matching strategy.
        # Maximal matching is faster but may yield fewer pairs, while max-weight
        # matching aims for the best overall input sharing at the cost of runtime.
        if self.mode == MatchingMode.MAXIMAL:
            raw_matching = nx.maximal_matching(graph)
        else:
            raw_matching = nx.max_weight_matching(graph, maxcardinality=True)

        progress.on_matching_done(selected_pairs=len(raw_matching))

        used: set[int] = set()

        # Sort pairs for deterministic output and build mapped cells from bindings.
        for a, b in sorted(
            (tuple(sorted((u, v))) for u, v in raw_matching), key=lambda p: (p[0], p[1])
        ):
            binding = bindings.get((a, b))
            if binding is None:
                continue
            mapped.append(
                self.arch.build_mapped_cell(
                    f"{self.arch.name}_{pair_candidates[a].cell_id}"
                    f"_{pair_candidates[b].cell_id}",
                    binding,
                )
            )
            used.add(a)
            used.add(b)

        # Add any pair candidates that were not used in the matching to passthrough.
        unmatched: list[LogicalLutCell] = [
            cell for idx, cell in enumerate(pair_candidates) if idx not in used
        ]

        unmatched_passthrough_count: int = 0
        if self.passthrough:
            # Old behavior:

            # New behavior: map unmatched single LUTs into FRAC cells where possible.
            for lut in unmatched:
                mapped_cell = self.arch.bind_single_lut(lut)
                if mapped_cell is None:
                    passthrough.append(lut)
                    unmatched_passthrough_count += 1
                    continue
                mapped.append(mapped_cell)
        else:
            passthrough.extend(unmatched)
            unmatched_passthrough_count = len(unmatched)

        progress.on_unmatched_to_passthrough(count=unmatched_passthrough_count)

        # Compile type counts for statistics.
        type_count: dict[str, int] = {}
        for c in cells:
            type_count[c.cell_type] = type_count.get(c.cell_type, 0) + 1

        stats: MappingStats = MappingStats(
            total_luts_before=len(cells),
            total_cells_after=len(mapped) + len(passthrough),
            mapped_groups=len(mapped),
            mapped_luts=sum(len(x.placements) for x in mapped),
            passthrough_luts=len(passthrough),
            source_type_count=type_count,
        )

        progress.on_summary(stats)

        return MappingResult(
            architecture_name=self.arch.name,
            top_name=top_name,
            mapped_cells=mapped,
            passthrough_luts=passthrough,
            stats=stats,
            metadata={
                "frac_lut_size": self.arch.frac_lut_size,
                "num_shared_inputs": self.arch.num_shared_inputs,
                "passthrough": self.passthrough,
                "mode": self.mode.value,
            },
        )
