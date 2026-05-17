"""Detect structural placement hints and produce attribute assignments."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.models import (
    AttributeValue,
    LinearChainRule,
    PlacementCluster,
    PlacementHintAssignment,
    PlacementHintCell,
    PlacementHintDesign,
    PlacementHintsOptions,
    PlacementHintsResult,
    PlacementHintsStats,
)
from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.process_tracker import (
    PlacementHintsProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.reader import (
    PlacementHintsReader,
)
from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.report import (
    render_placement_hints_report,
)
from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.writer import (
    PlacementHintsWriter,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class PlacementHinter:
    """Generate placement hint attributes from structural netlist rules.

    Parameters
    ----------
    options : PlacementHintsOptions
        Hint generation options.
    """

    def __init__(self, options: PlacementHintsOptions) -> None:
        self.options = options
        self.reader = PlacementHintsReader()
        self.writer = PlacementHintsWriter()
        self._last_result: PlacementHintsResult | None = None

    def map_from_design(
        self,
        design: PyosysBridge,
        top_name: str | None = None,
    ) -> PlacementHintsResult:
        """Generate and write placement hints on a pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Design to inspect and mutate.
        top_name : str | None
            Optional top module override.

        Returns
        -------
        PlacementHintsResult
            Result with detected clusters and assignments.
        """
        hint_design = self.reader.read_design(
            design,
            top_name=top_name or self.options.top_name,
        )
        result = self.plan(hint_design)
        self.writer.apply(design, result)
        result = replace(result, report_summary=render_placement_hints_report(result))
        self._last_result = result
        return result

    def plan(self, design: PlacementHintDesign) -> PlacementHintsResult:
        """Plan placement-hint assignments without mutating a design.

        Parameters
        ----------
        design : PlacementHintDesign
            Design model to inspect.

        Returns
        -------
        PlacementHintsResult
            Planned clusters and assignments.
        """
        stats = PlacementHintsStats(
            total_cells=len(design.cells),
            rules=len(self.options.rules),
        )
        tracker = PlacementHintsProcessTracker(
            enabled=self.options.track_progress,
            chunk_size=self.options.progress_chunk_size,
        )
        tracker.start(rules=len(self.options.rules), cells=len(design.cells))

        assignments: dict[str, dict[str, AttributeValue]] = {}
        clusters: list[PlacementCluster] = []
        for rule in self.options.rules:
            new_clusters = self._plan_linear_chain_rule(
                design=design,
                rule=rule,
                stats=stats,
                tracker=tracker,
            )
            for cluster in new_clusters:
                clusters.append(cluster)
                self._merge_cluster_assignments(
                    design=design,
                    cluster=cluster,
                    rule=rule,
                    assignments=assignments,
                    stats=stats,
                )

        planned = tuple(
            PlacementHintAssignment(cell_id=cell_id, attributes=attributes)
            for cell_id, attributes in assignments.items()
        )
        stats.clusters = len(clusters)
        stats.assigned_cells = len(planned)
        tracker.finish(clusters=stats.clusters, assigned_cells=stats.assigned_cells)
        return PlacementHintsResult(
            top_name=design.top_name,
            options=self.options,
            stats=stats,
            clusters=tuple(clusters),
            assignments=planned,
        )

    @property
    def report_summary(self) -> str:
        """Return the latest report summary.

        Returns
        -------
        str
            Latest report text, or a placeholder if no run is available.
        """
        return (
            self._last_result.report_summary
            if self._last_result
            else "No result available."
        )

    @property
    def result_data(self) -> PlacementHintsResult | None:
        """Return the latest result data.

        Returns
        -------
        PlacementHintsResult | None
            Latest result object if available.
        """
        return self._last_result

    def _plan_linear_chain_rule(
        self,
        design: PlacementHintDesign,
        rule: LinearChainRule,
        stats: PlacementHintsStats,
        tracker: PlacementHintsProcessTracker,
    ) -> tuple[PlacementCluster, ...]:
        """Detect clusters for one linear-chain rule.

        Parameters
        ----------
        design : PlacementHintDesign
            Design to inspect.
        rule : LinearChainRule
            Linear-chain rule.
        stats : PlacementHintsStats
            Mutable statistics.
        tracker : PlacementHintsProcessTracker
            Progress tracker.

        Returns
        -------
        tuple[PlacementCluster, ...]
            Detected clusters for this rule.

        Raises
        ------
        ValueError
            If the rule detects invalid structures and branching is not allowed.
        """
        cells = {
            cell.cell_id: cell
            for cell in design.cells
            if cell.cell_type in set(rule.cell_types)
        }
        stats.candidate_cells += len(cells)
        for _cell in cells.values():
            tracker.tick()

        next_by_cell, prev_by_cell = self._build_linear_edges(cells, rule, stats)
        roots = tuple(
            cell_id
            for cell_id in cells
            if cell_id in next_by_cell and cell_id not in prev_by_cell
        )
        clusters: list[PlacementCluster] = []
        visited: set[str] = set()
        for root in roots:
            chain = self._walk_chain(root, next_by_cell)
            visited.update(chain)
            if self._chain_is_emittable(chain, rule):
                clusters.append(
                    PlacementCluster(
                        rule_name=rule.name,
                        cluster_id=f"{rule.name}_{len(clusters)}",
                        cells=chain,
                    )
                )
            else:
                stats.skipped_chains += 1

        edge_cells = set(next_by_cell) | set(prev_by_cell)
        unvisited_edge_cells = edge_cells - visited
        if unvisited_edge_cells:
            raise ValueError(
                f"linear_chain rule '{rule.name}' found a cycle or disconnected "
                f"edge group involving {sorted(unvisited_edge_cells)}"
            )

        if rule.allow_single_stage and rule.min_length <= 1:
            for cell_id in cells:
                if cell_id in edge_cells:
                    continue
                clusters.append(
                    PlacementCluster(
                        rule_name=rule.name,
                        cluster_id=f"{rule.name}_{len(clusters)}",
                        cells=(cell_id,),
                    )
                )
        return tuple(clusters)

    def _build_linear_edges(
        self,
        cells: dict[str, PlacementHintCell],
        rule: LinearChainRule,
        stats: PlacementHintsStats,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Build one-to-one chain edges for a linear-chain rule.

        Parameters
        ----------
        cells : dict[str, PlacementHintCell]
            Rule-matching cells keyed by cell ID.
        rule : LinearChainRule
            Linear-chain rule.
        stats : PlacementHintsStats
            Mutable statistics.

        Returns
        -------
        tuple[dict[str, str], dict[str, str]]
            Forward and reverse edge maps.

        Raises
        ------
        ValueError
            If branching or multi-bit chain ports are encountered.
        """
        sources_by_net: dict[str, list[str]] = {}
        sinks_by_net: dict[str, list[str]] = {}
        for cell in cells.values():
            source_net = _single_net(cell, rule.source_port)
            sink_net = _single_net(cell, rule.sink_port)
            if source_net is not None:
                sources_by_net.setdefault(source_net, []).append(cell.cell_id)
            if sink_net is not None:
                sinks_by_net.setdefault(sink_net, []).append(cell.cell_id)

        next_by_cell: dict[str, str] = {}
        prev_by_cell: dict[str, str] = {}
        for net in sorted(set(sources_by_net) & set(sinks_by_net)):
            sources = sources_by_net[net]
            sinks = sinks_by_net[net]
            if len(sources) != 1 or len(sinks) != 1:
                if rule.allow_branching:
                    stats.skipped_chains += 1
                    continue
                stats.conflicts += 1
                raise ValueError(
                    f"linear_chain rule '{rule.name}' found branching on net "
                    f"'{net}': sources={sources}, sinks={sinks}"
                )
            source = sources[0]
            sink = sinks[0]
            if source == sink:
                if rule.allow_branching:
                    stats.skipped_chains += 1
                    continue
                stats.conflicts += 1
                raise ValueError(
                    f"linear_chain rule '{rule.name}' found self-loop on "
                    f"cell '{source}' net '{net}'"
                )
            next_by_cell[source] = sink
            prev_by_cell[sink] = source
        return next_by_cell, prev_by_cell

    def _walk_chain(self, root: str, next_by_cell: dict[str, str]) -> tuple[str, ...]:
        """Walk a linear chain from one root.

        Parameters
        ----------
        root : str
            Root cell ID.
        next_by_cell : dict[str, str]
            Forward edge map.

        Returns
        -------
        tuple[str, ...]
            Chain cells in order.

        Raises
        ------
        ValueError
            If the walk reaches a cycle.
        """
        chain = [root]
        seen = {root}
        cursor = root
        while cursor in next_by_cell:
            cursor = next_by_cell[cursor]
            if cursor in seen:
                raise ValueError(f"linear chain cycle involving cell '{cursor}'")
            seen.add(cursor)
            chain.append(cursor)
        return tuple(chain)

    def _chain_is_emittable(
        self,
        chain: tuple[str, ...],
        rule: LinearChainRule,
    ) -> bool:
        """Return whether a chain satisfies rule length filters.

        Parameters
        ----------
        chain : tuple[str, ...]
            Chain cells in order.
        rule : LinearChainRule
            Linear-chain rule.

        Returns
        -------
        bool
            ``True`` when placement hints should be emitted.
        """
        if len(chain) < rule.min_length:
            return False
        return len(chain) > 1 or rule.allow_single_stage

    def _merge_cluster_assignments(
        self,
        design: PlacementHintDesign,
        cluster: PlacementCluster,
        rule: LinearChainRule,
        assignments: dict[str, dict[str, AttributeValue]],
        stats: PlacementHintsStats,
    ) -> None:
        """Merge one cluster's attributes into assignment state.

        Parameters
        ----------
        design : PlacementHintDesign
            Design containing existing attributes.
        cluster : PlacementCluster
            Cluster to write.
        rule : LinearChainRule
            Rule that produced the cluster.
        assignments : dict[str, dict[str, AttributeValue]]
            Mutable assignment map.
        stats : PlacementHintsStats
            Mutable statistics.
        """
        cells = {cell.cell_id: cell for cell in design.cells}
        names = self.options.attribute_names
        for index, cell_id in enumerate(cluster.cells):
            attributes: dict[str, AttributeValue] = {
                names.kind: "linear_chain",
                names.name: rule.name,
                names.cluster_id: cluster.cluster_id,
                names.role: "stage",
                names.index: index,
                names.size: len(cluster.cells),
            }
            self._merge_cell_attributes(
                cell=cells[cell_id],
                attributes=attributes,
                assignments=assignments,
                stats=stats,
            )

    def _merge_cell_attributes(
        self,
        cell: PlacementHintCell,
        attributes: dict[str, AttributeValue],
        assignments: dict[str, dict[str, AttributeValue]],
        stats: PlacementHintsStats,
    ) -> None:
        """Merge attribute updates for one cell.

        Parameters
        ----------
        cell : PlacementHintCell
            Target cell.
        attributes : dict[str, AttributeValue]
            Proposed attribute updates.
        assignments : dict[str, dict[str, AttributeValue]]
            Mutable assignment map.
        stats : PlacementHintsStats
            Mutable statistics.

        Raises
        ------
        ValueError
            If an existing or generated attribute conflicts with the update.
        """
        target = assignments.setdefault(cell.cell_id, {})
        for name, value in attributes.items():
            existing = cell.attributes.get(name)
            if (
                existing is not None
                and not self.options.overwrite_existing
                and existing != _attribute_to_text(value)
            ):
                stats.conflicts += 1
                if self.options.fail_on_conflict:
                    raise ValueError(
                        f"Cell '{cell.cell_id}' already has attribute "
                        f"{name}={existing}, cannot write {value}"
                    )
                continue
            if name in target and target[name] != value:
                stats.conflicts += 1
                if self.options.fail_on_conflict:
                    raise ValueError(
                        f"Cell '{cell.cell_id}' has conflicting generated "
                        f"attribute {name}: {target[name]} vs {value}"
                    )
                continue
            target[name] = value


def _single_net(cell: PlacementHintCell, port: str) -> str | None:
    """Return a single connected net for a cell port.

    Parameters
    ----------
    cell : PlacementHintCell
        Cell to inspect.
    port : str
        Port name to read.

    Returns
    -------
    str | None
        Connected net token, or ``None`` when the port is absent or constant.

    Raises
    ------
    ValueError
        If the port is multi-bit.
    """
    bits = cell.connections.get(port)
    if not bits:
        return None
    if len(bits) != 1:
        raise ValueError(
            f"Cell '{cell.cell_id}' port '{port}' must be scalar for placement "
            f"chain detection"
        )
    bit = bits[0]
    return None if bit in {"0", "1", "x", "z"} else bit


def _attribute_to_text(value: AttributeValue) -> str:
    """Return a text form comparable with reader attributes.

    Parameters
    ----------
    value : AttributeValue
        Attribute value.

    Returns
    -------
    str
        Comparable text.
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)
