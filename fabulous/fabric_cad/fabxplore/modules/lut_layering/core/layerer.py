"""Implement LUT layering on top of packed fractional LUT mappings.

The layerer is the orchestration point for multi-layer synthesis. It maps an
overlay design to Yosys ``$lut`` cells in a fresh pyosys bridge, prefixes and
bit-remaps that overlay netlist, places every overlay LUT into reusable leftover
space from a previous LUT-combinator result, and reloads the merged JSON into the
base design.
"""

from dataclasses import replace

from loguru import logger

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    LogicalLutCell,
    MappingResult,
    PackedCell,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.netlist import (
    parse_model_json,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.inventory import (
    collect_leftover_slots,
    effective_leftover_width,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.json_merge import (
    max_integer_bit,
    merge_overlay_module,
    prefix_base_top_names,
    prepare_overlay_json,
    replace_packed_cells,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.models import (
    LayeredLutPlacement,
    LeftoverSlot,
    LutLayeringConfig,
    LutLayeringResult,
    LutLayeringStats,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.report import (
    render_layering_report,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class LutLayerer:
    """Inject a second LUT-mapped design into existing FRAC LUT leftovers.

    The class is deliberately strict: all overlay LUTs must fit in the current
    leftover inventory. If any overlay LUT cannot be placed, the input design is
    left unchanged and a ``RuntimeError`` is raised.

    Parameters
    ----------
    config : LutLayeringConfig
        Layering configuration, base mapping, and architecture context.
    """

    def __init__(self, config: LutLayeringConfig) -> None:
        self.config = config
        self.print_name = "[LutLayerer]"

    def map_from_design(
        self, design: PyosysBridge, inplace: bool = True
    ) -> LutLayeringResult:
        """Run layering against an already packed base design.

        Parameters
        ----------
        design : PyosysBridge
            Base pyosys design containing already emitted FRAC LUT cells.
        inplace : bool
            If ``True``, reload ``design`` with the merged layered JSON.

        Returns
        -------
        LutLayeringResult
            Updated mapping, report stats, placements, and overlay LUT data.
        """
        base_json = design.to_netlist_dict()
        result, layered_json = self._run_layering(base_json)
        if inplace:
            design.load_netlist_dict(layered_json)
        return result

    def _run_layering(self, base_json: dict) -> tuple[LutLayeringResult, dict]:
        """Execute layering from a parsed base JSON dictionary.

        Parameters
        ----------
        base_json : dict
            Current base design JSON dictionary.

        Returns
        -------
        tuple[LutLayeringResult, dict]
            Structured result and merged JSON dictionary.
        """
        slots = collect_leftover_slots(
            self.config.base_mapping, self.config.architecture
        )
        overlay_lut_size = self._select_overlay_lut_size(slots)

        logger.info(
            f"{self.print_name} Starting layering. "
            f"(base_top={self.config.top_name}, "
            f"overlay_top={self.config.overlay_top_name}, "
            f"overlay_lut_size={overlay_lut_size})"
        )

        overlay_json = self._synthesize_overlay_to_luts(overlay_lut_size)
        prepared_overlay = prepare_overlay_json(
            overlay_json=overlay_json,
            overlay_top_name=self.config.overlay_top_name,
            prefix=self.config.overlay_prefix,
            fresh_bit_start=max_integer_bit(base_json) + 1,
        )
        overlay_model = parse_model_json(
            model_json=prepared_overlay.netlist_json,
            top_name=prepared_overlay.top_name,
            lut_spec=self.config.lut_spec,
        )
        overlay_luts = tuple(
            sorted(overlay_model.lut_cells, key=lambda lut: (-lut.width, lut.cell_id))
        )

        placements, updated_mapping = self._place_overlay_luts(
            overlay_luts=overlay_luts,
            slots=slots,
        )

        slot_packed_ids = {
            self.config.base_mapping.mapped_cells[slot.cell_index].packed_id
            for slot in slots
        }
        replaced_cells = {
            cell.packed_id: cell
            for cell in updated_mapping.mapped_cells
            if cell.packed_id in slot_packed_ids
        }
        consumed_overlay_luts = {placement.overlay_cell_id for placement in placements}

        layered_json = prefix_base_top_names(
            base_json=base_json,
            top_name=self.config.top_name,
            prefix=self.config.base_prefix,
        )
        layered_json = replace_packed_cells(
            model_json=layered_json,
            top_name=self.config.top_name,
            replacements=replaced_cells,
        )
        layered_json = merge_overlay_module(
            base_json=layered_json,
            top_name=self.config.top_name,
            overlay=prepared_overlay,
            removed_overlay_lut_ids=consumed_overlay_luts,
        )

        stats = self._build_stats(
            slots=slots,
            placements=placements,
            overlay_luts=overlay_luts,
            mapped_cells=updated_mapping.mapped_cells,
        )
        report_summary = render_layering_report(
            config=self.config,
            stats=stats,
            slots=slots,
            placements=placements,
            overlay_lut_size=overlay_lut_size,
        )

        metadata = dict(updated_mapping.metadata)
        metadata.update(
            {
                "lut_layering_enabled": True,
                "lut_layering_overlay_top": self.config.overlay_top_name,
                "lut_layering_overlay_luts": len(overlay_luts),
                "lut_layering_injected_luts": len(placements),
                "_lut_layering_report": report_summary,
            }
        )
        final_mapping = replace(
            updated_mapping,
            metadata=metadata,
            report_summary=updated_mapping.report_summary,
        )

        logger.info(
            f"{self.print_name} Done. "
            f"overlay_luts={len(overlay_luts)}, injected={len(placements)}, "
            f"leftover_after={stats.reusable_leftover_after}"
        )

        return (
            LutLayeringResult(
                mapping=final_mapping,
                stats=stats,
                placements=placements,
                report_summary=report_summary,
                overlay_luts=overlay_luts,
            ),
            layered_json,
        )

    def _synthesize_overlay_to_luts(self, overlay_lut_size: int) -> dict:
        """Return overlay design JSON after mapping to Yosys ``$lut`` cells.

        Parameters
        ----------
        overlay_lut_size : int
            Maximum LUT width passed to ABC.

        Returns
        -------
        dict
            LUT-mapped overlay JSON.
        """
        bridge = PyosysBridge(debug=self.config.debug)
        bridge.read_verilog_paths(
            self.config.overlay_verilog_paths,
            replace_design=True,
        )
        bridge.run_pass(f"hierarchy -check -top {self.config.overlay_top_name}")
        bridge.run_pass("proc")
        bridge.run_pass("opt")
        bridge.run_pass("flatten")
        bridge.run_pass("techmap")
        bridge.run_pass("opt")
        bridge.run_pass(f"abc9 -lut {overlay_lut_size}")
        bridge.run_pass("opt_lut")
        bridge.run_pass("clean")
        return bridge.to_netlist_dict()

    def _select_overlay_lut_size(self, slots: tuple[LeftoverSlot, ...]) -> int:
        """Return the LUT size to use for overlay mapping.

        Parameters
        ----------
        slots : tuple[LeftoverSlot, ...]
            Current reusable leftover inventory.

        Returns
        -------
        int
            Explicit or derived overlay LUT size.

        Raises
        ------
        RuntimeError
            If no slots exist or the requested LUT size cannot fit.
        """
        if not slots:
            raise RuntimeError(
                "LUT layering requires at least one reusable leftover slot"
            )

        max_slot = max(slot.effective_leftover_width for slot in slots)
        if self.config.overlay_lut_size is None:
            return max_slot

        if self.config.overlay_lut_size < 1:
            raise RuntimeError("overlay_lut_size must be >= 1")
        if self.config.overlay_lut_size > max_slot:
            raise RuntimeError(
                f"overlay_lut_size={self.config.overlay_lut_size} exceeds "
                f"available maximum leftover width {max_slot}"
            )
        return self.config.overlay_lut_size

    def _place_overlay_luts(
        self,
        overlay_luts: tuple[LogicalLutCell, ...],
        slots: tuple[LeftoverSlot, ...],
    ) -> tuple[tuple[LayeredLutPlacement, ...], MappingResult]:
        """Place all overlay LUTs into leftover slots and return updated mapping.

        Parameters
        ----------
        overlay_luts : tuple[LogicalLutCell, ...]
            Prefixed overlay LUTs to inject.
        slots : tuple[LeftoverSlot, ...]
            Candidate slots from the current base mapping.

        Returns
        -------
        tuple[tuple[LayeredLutPlacement, ...], MappingResult]
            Applied placements and updated mapping.

        Raises
        ------
        RuntimeError
            If any overlay LUT cannot be placed legally.
        """
        mapped_cells = list(self.config.base_mapping.mapped_cells)
        available_slots = list(slots)
        placements: list[LayeredLutPlacement] = []

        for overlay_lut in overlay_luts:
            placed = self._try_place_one_lut(
                overlay_lut=overlay_lut,
                mapped_cells=mapped_cells,
                available_slots=available_slots,
            )
            if placed is None:
                raise RuntimeError(
                    f"Overlay LUT '{overlay_lut.cell_id}' (LUT{overlay_lut.width}) "
                    "does not fit in remaining leftover inventory"
                )

            placement, consumed_slot_index = placed
            placements.append(placement)
            available_slots.pop(consumed_slot_index)

        stats = self.config.base_mapping.stats
        updated_stats = replace(
            stats,
            total_luts_before=stats.total_luts_before + len(overlay_luts),
            mapped_luts=stats.mapped_luts + len(overlay_luts),
            source_type_count=_add_type_counts(
                stats.source_type_count,
                _width_count(overlay_luts),
            ),
        )

        updated_mapping = MappingResult(
            architecture_name=self.config.base_mapping.architecture_name,
            top_name=self.config.base_mapping.top_name,
            mapped_cells=mapped_cells,
            passthrough_luts=list(self.config.base_mapping.passthrough_luts),
            stats=updated_stats,
            metadata=dict(self.config.base_mapping.metadata),
            report_summary=self.config.base_mapping.report_summary,
        )

        return tuple(placements), updated_mapping

    def _try_place_one_lut(
        self,
        overlay_lut: LogicalLutCell,
        mapped_cells: list[PackedCell],
        available_slots: list[LeftoverSlot],
    ) -> tuple[LayeredLutPlacement, int] | None:
        """Try to place one overlay LUT into the best remaining slot.

        Parameters
        ----------
        overlay_lut : LogicalLutCell
            Overlay LUT to place.
        mapped_cells : list[PackedCell]
            Mutable mapped-cell list being updated.
        available_slots : list[LeftoverSlot]
            Remaining candidate slots.

        Returns
        -------
        tuple[LayeredLutPlacement, int] | None
            Placement plus consumed slot-list index, or ``None`` if no legal
            slot exists.
        """
        ordered_slots = sorted(
            enumerate(available_slots),
            key=lambda item: (
                item[1].effective_leftover_width - overlay_lut.width,
                item[1].effective_leftover_width,
                item[1].packed_id,
            ),
        )

        for slot_list_index, slot in ordered_slots:
            if slot.effective_leftover_width < overlay_lut.width:
                continue

            host_cell = mapped_cells[slot.cell_index]
            host_lut = host_cell.placements[0].cell
            binding = self.config.architecture.try_bind_pair(host_lut, overlay_lut)
            if binding is None:
                continue

            rebuilt = self.config.architecture.build_mapped_cell(
                host_cell.packed_id,
                binding,
            )
            mapped_cells[slot.cell_index] = rebuilt

            leftover_after = effective_leftover_width(
                rebuilt,
                self.config.architecture,
            )
            placement = LayeredLutPlacement(
                overlay_cell_id=overlay_lut.cell_id,
                overlay_width=overlay_lut.width,
                host_packed_id=host_cell.packed_id,
                host_cell_id=host_lut.cell_id,
                consumed_width=overlay_lut.width,
                leftover_width_after=leftover_after,
            )
            return placement, slot_list_index

        return None

    def _build_stats(
        self,
        slots: tuple[LeftoverSlot, ...],
        placements: tuple[LayeredLutPlacement, ...],
        overlay_luts: tuple[LogicalLutCell, ...],
        mapped_cells: list[PackedCell],
    ) -> LutLayeringStats:
        """Build aggregate report stats for a completed run.

        Parameters
        ----------
        slots : tuple[LeftoverSlot, ...]
            Candidate slots before layering.
        placements : tuple[LayeredLutPlacement, ...]
            Applied placements.
        overlay_luts : tuple[LogicalLutCell, ...]
            Overlay LUTs considered by the layerer.
        mapped_cells : list[PackedCell]
            Final mapped-cell list.

        Returns
        -------
        LutLayeringStats
            Aggregate counters.
        """
        remaining_slots = collect_leftover_slots(
            replace(self.config.base_mapping, mapped_cells=mapped_cells),
            self.config.architecture,
        )
        return LutLayeringStats(
            slots_before=len(slots),
            reusable_leftover_before=sum(
                slot.effective_leftover_width for slot in slots
            ),
            overlay_luts=len(overlay_luts),
            overlay_lut_inputs=sum(lut.width for lut in overlay_luts),
            injected_luts=len(placements),
            reusable_leftover_after=sum(
                slot.effective_leftover_width for slot in remaining_slots
            ),
            overlay_width_count=_width_count(overlay_luts),
            remaining_width_count={
                f"LUT{slot.effective_leftover_width}": sum(
                    1
                    for other in remaining_slots
                    if other.effective_leftover_width == slot.effective_leftover_width
                )
                for slot in remaining_slots
            },
        )


def _width_count(luts: tuple[LogicalLutCell, ...]) -> dict[str, int]:
    """Return LUT width histogram for logical LUTs."""
    counts: dict[str, int] = {}
    for lut in luts:
        label = f"LUT{lut.width}"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _add_type_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    """Return merged type counts."""
    out = dict(left)
    for label, count in right.items():
        out[label] = out.get(label, 0) + count
    return out
