"""Architecture-aware ABC LUT cost mapper.

This module contains the main ``LutMapper`` facade. It computes an ABC
``-luts`` cost vector from fractional-LUT pairability assumptions and can apply
the resulting ABC command directly to a ``PyosysBridge`` design.
"""

from dataclasses import replace

from fabulous.fabric_cad.fabxplore.modules.lut_mapper.core.models import (
    LutCostVector,
    LutMapperConfig,
    LutMapperResult,
    normalize_raw_cost_vector,
)
from fabulous.fabric_cad.fabxplore.modules.lut_mapper.core.report import (
    render_lut_mapper_report,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class LutMapper:
    """Compute and run architecture-aware ABC LUT mapping.

    The mapper estimates which LUT widths are attractive for a downstream
    fractional-LUT packer. It first builds a pair feasibility table from the
    architecture:

    ``required_shared = max(0, w0 + w1 - (K + P_eff))``

    and combines it with a size table:

    ``unused_capacity = 2*K - (w0 + w1)``

    The two tables are multiplied by user-controlled factors and converted to
    per-width pairability scores. Those scores discount the ABC costs for
    widths that should pack well. LUTs wider than ``K`` are then costed relative
    to the emitted ``LUTK`` cost, because the selected backend only sees the
    final cost vector and therefore compares all widths by those emitted numbers. If
    ``raw_cost_vector`` is set in the config, the analytical cost calculation is
    bypassed and the provided vector is used directly.

    Parameters
    ----------
    config : LutMapperConfig
        Cost-model and ABC command configuration.
    """

    def __init__(self, config: LutMapperConfig) -> None:
        self.config = config
        self._last_result: LutMapperResult | None = None

    def map_from_design(
        self,
        design: PyosysBridge,
        inplace: bool = False,
        top_name: str | None = None,
    ) -> LutMapperResult:
        """Run ABC LUT mapping on a pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Design wrapper that should be mapped.
        inplace : bool
            If ``True``, modify ``design`` directly. If ``False``, run mapping
            on a cloned temporary design and return only the report/result data.
        top_name : str | None
            Optional top module name for reporting. If ``None``, the mapper
            queries the design's current top module.

        Returns
        -------
        LutMapperResult
            Result object with analytical tables, emitted command, and report.
        """
        bridge = design if inplace else PyosysBridge(debug=self.config.debug)
        if not inplace:
            bridge.load_netlist_dict(design.to_netlist_dict())

        result = self.build_result(top_name=top_name or bridge.top_name())

        bridge.run_pass(result.abc_command)
        for command in result.followup_commands:
            bridge.run_pass(command)

        self._last_result = result
        return result

    def build_result(self, top_name: str = "top") -> LutMapperResult:
        """Build cost tables and commands without running pyosys.

        Parameters
        ----------
        top_name : str
            Top module name to embed in the report.

        Returns
        -------
        LutMapperResult
            Complete cost-model result.
        """
        widths = tuple(range(1, self.config.base_lut_size + 1))
        effective_shared = self._effective_shared_inputs()
        effective_private = self.config.base_lut_size - effective_shared
        pair_capacity = self.config.base_lut_size + effective_private

        sharing_table = self._build_required_sharing_table(widths, pair_capacity)
        size_table = self._build_size_penalty_table(widths)
        combined_table = self._build_combined_penalty_table(sharing_table, size_table)
        pairability = self._compute_pairability_by_width(combined_table)
        cost_vector = self._compute_cost_vector(pairability)
        abc_command = self._abc_command(cost_vector)
        followup_commands = self._followup_commands()

        result = LutMapperResult(
            top_name=top_name,
            config=self.config,
            effective_shared_inputs=effective_shared,
            effective_private_inputs=effective_private,
            pair_capacity=pair_capacity,
            widths=widths,
            sharing_required_table=sharing_table,
            size_penalty_table=size_table,
            combined_penalty_table=combined_table,
            pairability_by_width=pairability,
            cost_vector=cost_vector,
            abc_command=abc_command,
            followup_commands=followup_commands,
        )
        return replace(result, report_summary=render_lut_mapper_report(result))

    @property
    def report_summary(self) -> str:
        """Return the latest rendered report.

        Returns
        -------
        str
            Report text for the latest run, or a placeholder if no run exists.
        """
        return (
            self._last_result.report_summary
            if self._last_result
            else "No result available."
        )

    @property
    def result_data(self) -> LutMapperResult | None:
        """Return the latest result object.

        Returns
        -------
        LutMapperResult | None
            Latest result if mapping has been run, otherwise ``None``.
        """
        return self._last_result

    def _effective_shared_inputs(self) -> int:
        """Return the effective shared-input count used by the pair model.

        Returns
        -------
        int
            Shared-input count after applying the select-as-data private-input
            bonus and clamping to the valid ``[0, base_lut_size]`` range.
        """
        select_bonus = 1 if self.config.use_select_as_data_in_pair_mode else 0
        return max(
            0,
            min(
                self.config.base_lut_size,
                self.config.num_shared_inputs - select_bonus,
            ),
        )

    def _build_required_sharing_table(
        self,
        widths: tuple[int, ...],
        pair_capacity: int,
    ) -> tuple[tuple[int, ...], ...]:
        """Build the pair feasibility table.

        Parameters
        ----------
        widths : tuple[int, ...]
            LUT widths included in the table.
        pair_capacity : int
            Maximum number of unique inputs available to a two-LUT pair.

        Returns
        -------
        tuple[tuple[int, ...], ...]
            Matrix where entry ``[i][j]`` is the number of shared inputs
            required to pack ``widths[i]`` with ``widths[j]``.
        """
        return tuple(
            tuple(max(0, left + right - pair_capacity) for right in widths)
            for left in widths
        )

    def _build_size_penalty_table(
        self,
        widths: tuple[int, ...],
    ) -> tuple[tuple[float, ...], ...]:
        """Build the unused-capacity size penalty table.

        Parameters
        ----------
        widths : tuple[int, ...]
            LUT widths included in the table.

        Returns
        -------
        tuple[tuple[float, ...], ...]
            Matrix where entry ``[i][j]`` is the unused two-fragment input
            capacity after pairing ``widths[i]`` with ``widths[j]``.
        """
        total_capacity = 2 * self.config.base_lut_size
        return tuple(
            tuple(float(max(0, total_capacity - (left + right))) for right in widths)
            for left in widths
        )

    def _build_combined_penalty_table(
        self,
        sharing_table: tuple[tuple[int, ...], ...],
        size_table: tuple[tuple[float, ...], ...],
    ) -> tuple[tuple[float, ...], ...]:
        """Combine sharing and size tables using configured penalty factors.

        Parameters
        ----------
        sharing_table : tuple[tuple[int, ...], ...]
            Required-shared-input table.
        size_table : tuple[tuple[float, ...], ...]
            Unused-capacity table.

        Returns
        -------
        tuple[tuple[float, ...], ...]
            Combined penalty table. Lower values represent more desirable pair
            sizes for the downstream fractional LUT packer.
        """
        return tuple(
            tuple(
                self.config.sharing_penalty_factor * float(sharing_value)
                + self.config.size_penalty_factor * size_value
                for sharing_value, size_value in zip(
                    sharing_row,
                    size_row,
                    strict=True,
                )
            )
            for sharing_row, size_row in zip(sharing_table, size_table, strict=True)
        )

    def _compute_pairability_by_width(
        self,
        combined_table: tuple[tuple[float, ...], ...],
    ) -> tuple[float, ...]:
        """Convert the combined pair table into per-width pairability scores.

        Parameters
        ----------
        combined_table : tuple[tuple[float, ...], ...]
            Combined penalty matrix for pair sizes.

        Returns
        -------
        tuple[float, ...]
            Average normalized desirability for each source width. Values are
            in ``[0.0, 1.0]`` where larger means easier or more attractive to
            pair.
        """
        flat = [value for row in combined_table for value in row]
        min_value = min(flat)
        max_value = max(flat)
        if max_value == min_value:
            return tuple(1.0 for _ in combined_table)

        pairability: list[float] = []
        for row in combined_table:
            scores = [
                1.0 - ((value - min_value) / (max_value - min_value)) for value in row
            ]
            pairability.append(sum(scores) / len(scores))
        return tuple(pairability)

    def _compute_cost_vector(
        self,
        pairability_by_width: tuple[float, ...],
    ) -> LutCostVector:
        """Compute the final ABC LUT cost vector.

        Parameters
        ----------
        pairability_by_width : tuple[float, ...]
            Pairability score for widths ``1`` through ``base_lut_size``.

        Returns
        -------
        LutCostVector
            Cost vector emitted to the selected backend. If a raw override is
            configured, the override is normalized and returned directly.
        """
        if self.config.raw_cost_vector is not None:
            return LutCostVector(
                costs=normalize_raw_cost_vector(
                    self.config.raw_cost_vector,
                    self.config.max_lut_size,
                ),
                raw_override_used=True,
            )

        costs: list[int] = []
        for width in range(
            1,
            min(self.config.base_lut_size, self.config.max_lut_size) + 1,
        ):
            pairability = pairability_by_width[width - 1]
            raw_cost = self.config.cost_scale * (
                1.0 - self.config.pair_discount_strength * pairability
            )
            costs.append(self._clamp_cost(raw_cost))

        base_cost = costs[-1]
        for width in range(self.config.base_lut_size + 1, self.config.max_lut_size + 1):
            extra_inputs = width - self.config.base_lut_size
            raw_cost = (
                base_cost
                * (self.config.larger_lut_base_multiplier**extra_inputs)
                * (self.config.larger_lut_discount_factor**extra_inputs)
            )
            costs.append(self._clamp_cost(raw_cost))

        return LutCostVector(costs=tuple(costs), raw_override_used=False)

    def _clamp_cost(self, value: float) -> int:
        """Round and clamp one analytical cost value.

        Parameters
        ----------
        value : float
            Raw analytical cost before integer conversion.

        Returns
        -------
        int
            Integer cost bounded by ``min_cost`` and optional ``max_cost``.
        """
        cost = max(self.config.min_cost, int(round(value)))
        if self.config.max_cost is not None:
            cost = min(cost, self.config.max_cost)
        return cost

    def _abc_command(self, cost_vector: LutCostVector) -> str:
        """Build the backend command that consumes the cost vector.

        Parameters
        ----------
        cost_vector : LutCostVector
            Final LUT cost vector.

        Returns
        -------
        str
            Yosys command for either ``abc`` or ``abc9`` with ``-luts``.
        """
        return f"{self.config.backend.value} -luts {cost_vector.to_yosys_luts_arg()}"

    def _followup_commands(self) -> tuple[str, ...]:
        """Return post-mapping cleanup and LUT optimization commands.

        Returns
        -------
        tuple[str, ...]
            Additional pyosys commands executed after the backend command.
        """
        commands: list[str] = []
        if self.config.run_opt_lut:
            commands.append("opt_lut")
            commands.append("opt_lut_ins")
        if self.config.run_clean:
            commands.append("clean")
        return tuple(commands)
