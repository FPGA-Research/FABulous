"""Data models for graph-only switch-matrix pattern generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


class RoutingPipPattern(StrEnum):
    """Routing-resource pattern names supported by the graph pass."""

    NONE = "none"
    FULL = "full"
    SUBSET = "subset"
    WILTON = "wilton"
    UNIVERSAL = "universal"
    LUT_CARRY_RICH = "lut_carry_rich"


class SwitchMatrixPatternOptions(BaseModel):
    """Options for graph-only switch-matrix pattern application.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    tile_name : str
        FABulous tile type to modify in the graph.
    input_fanin : int
        Number of sources generated for each BEL input row.
    include_bel_output_sources : bool
        Whether BEL outputs are eligible as local source columns.
    include_constant_sources : bool
        Whether constant wires are eligible as source columns.
    output_fanin : int
        Number of sources generated for each uncovered routing output row.
    cover_unconnected_matrix_rows : bool
        Whether uncovered routing output rows should receive sources.
    routing_pip_pattern : RoutingPipPattern
        Routing-resource pattern name.
    routing_pip_fs : int
        Number of routing-resource sources per generated route-through row.
    generate_straight_routing_pips : bool
        Whether same-direction route-through pairs are generated.
    generate_turn_routing_pips : bool
        Whether turn route-through pairs are generated.
    hierarchy_enabled : bool
        Whether BEL input access should be built through generated JUMP levels.
    hierarchy_levels : list[int]
        Fanins for generated JUMP hierarchy levels.
    hierarchy_jump_prefix : str
        Prefix for generated hierarchy JUMP resources.
    hierarchy_replace_direct_input_pips : bool
        Whether hierarchy PIPs replace direct BEL-input PIPs.
    replace_existing_matrix : bool
        Whether generated pairs replace the tile matrix instead of adding to it.
    delay : float
        Delay assigned to generated active matrix resources.
    track_progress : bool
        Whether progress messages should be logged.
    progress_chunk_size : int
        Number of generated rows between progress messages.
    """

    model_config = ConfigDict(frozen=True)

    tile_name: str
    input_fanin: int = 6
    include_bel_output_sources: bool = True
    include_constant_sources: bool = True
    output_fanin: int = 3
    cover_unconnected_matrix_rows: bool = True
    routing_pip_pattern: RoutingPipPattern = RoutingPipPattern.WILTON
    routing_pip_fs: int = 4
    generate_straight_routing_pips: bool = True
    generate_turn_routing_pips: bool = True
    hierarchy_enabled: bool = False
    hierarchy_levels: list[int] = Field(default_factory=lambda: [2, 2])
    hierarchy_jump_prefix: str = "J_LOCAL"
    hierarchy_replace_direct_input_pips: bool = True
    replace_existing_matrix: bool = False
    delay: float = 8.0
    track_progress: bool = True
    progress_chunk_size: int = 100

    @field_validator("tile_name", "hierarchy_jump_prefix")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        """Validate non-empty text options.

        Parameters
        ----------
        value : str
            Text option.

        Returns
        -------
        str
            Validated text.

        Raises
        ------
        ValueError
            If the text is empty.
        """
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator(
        "input_fanin",
        "output_fanin",
        "routing_pip_fs",
        "progress_chunk_size",
    )
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        """Validate positive integer options.

        Parameters
        ----------
        value : int
            Integer option.

        Returns
        -------
        int
            Validated integer.

        Raises
        ------
        ValueError
            If the value is not positive.
        """
        if value <= 0:
            raise ValueError("value must be positive")
        return value

    @field_validator("delay")
    @classmethod
    def _validate_delay(cls, value: float) -> float:
        """Validate generated PIP delay.

        Parameters
        ----------
        value : float
            Delay value.

        Returns
        -------
        float
            Validated delay.

        Raises
        ------
        ValueError
            If the delay is not positive.
        """
        if value <= 0:
            raise ValueError("delay must be positive")
        return value

    @field_validator("hierarchy_levels")
    @classmethod
    def _validate_hierarchy_levels(cls, value: list[int]) -> list[int]:
        """Validate generated hierarchy fanins.

        Parameters
        ----------
        value : list[int]
            Hierarchy fanins.

        Returns
        -------
        list[int]
            Validated fanins.

        Raises
        ------
        ValueError
            If no levels are provided or a fanin is invalid.
        """
        if not value:
            raise ValueError("hierarchy_levels must not be empty")
        if any(level < 2 for level in value):
            raise ValueError("hierarchy_levels must contain fanins of at least 2")
        return value

    @model_validator(mode="after")
    def _validate_pattern_activity(self) -> SwitchMatrixPatternOptions:
        """Validate that at least one route-through direction is enabled.

        Returns
        -------
        SwitchMatrixPatternOptions
            Validated options.

        Raises
        ------
        ValueError
            If a routing pattern is requested with all directions disabled.
        """
        if (
            self.routing_pip_pattern
            not in (RoutingPipPattern.NONE, RoutingPipPattern.FULL)
            and not self.generate_straight_routing_pips
            and not self.generate_turn_routing_pips
        ):
            raise ValueError(
                "at least one route-through direction must be enabled when "
                "routing_pip_pattern is not 'none'"
            )
        return self


class SwitchMatrixPatternApplyResult(BaseModel):
    """Result returned by one concrete routing-pattern implementation.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    generated_bel_input_pips : int
        BEL-input PIPs requested by the implementation before deduplication.
    generated_output_coverage_pips : int
        Output-row coverage PIPs requested before deduplication.
    generated_routing_pips : int
        Routing-resource PIPs requested by the selected pattern.
    generated_hierarchy_pips : int
        PIPs requested for generated JUMP hierarchy stages.
    added_jump_wires : int
        Number of generated external JUMP resources.
    applied_pips : int
        Number of unique generated pairs applied to the FPGA model.
    compatible_routing_groups : int
        Number of routing-resource groups used by the selected pattern.
    warnings : tuple[str, ...]
        Non-fatal diagnostics.
    """

    model_config = ConfigDict(frozen=True)

    generated_bel_input_pips: int = 0
    generated_output_coverage_pips: int = 0
    generated_routing_pips: int = 0
    generated_hierarchy_pips: int = 0
    added_jump_wires: int = 0
    applied_pips: int = 0
    compatible_routing_groups: int = 0
    warnings: tuple[str, ...] = ()


class SwitchMatrixPatternImplementation(ABC):
    """Abstract base class for switch-matrix pattern implementations."""

    @abstractmethod
    def apply(
        self,
        fpga_model: PnRBridge,
        options: SwitchMatrixPatternOptions,
    ) -> SwitchMatrixPatternApplyResult:
        """Apply one pattern to the active FPGA model.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous API, and editable routing graph.
        options : SwitchMatrixPatternOptions
            Normalized pattern options.

        Returns
        -------
        SwitchMatrixPatternApplyResult
            Pattern-local counts and warnings.
        """


class SwitchMatrixPatternStats(BaseModel):
    """Summary statistics for one switch-matrix pattern application.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    rows_before : int
        Matrix row count before applying the pattern.
    rows_after : int
        Matrix row count after applying the pattern.
    columns_before : int
        Matrix column count before applying the pattern.
    columns_after : int
        Matrix column count after applying the pattern.
    active_pips_before : int
        Active matrix PIPs before applying the pattern.
    active_pips_after : int
        Active matrix PIPs after applying the pattern.
    generated_bel_input_pips : int
        BEL-input PIPs requested by the pass before deduplication.
    generated_output_coverage_pips : int
        Output-row coverage PIPs requested by the pass before deduplication.
    generated_routing_pips : int
        Routing-resource PIPs requested by the selected pattern.
    generated_hierarchy_pips : int
        PIPs requested for generated JUMP hierarchy stages.
    added_jump_wires : int
        Number of generated external JUMP resources.
    applied_pips : int
        Number of unique generated pairs applied to the graph.
    compatible_routing_groups : int
        Number of routing-resource groups used by the selected pattern.
    matrix_config_bits_before : int
        Matrix config bits before applying the pattern.
    matrix_config_bits_after : int
        Matrix config bits after applying the pattern.
    total_config_bits_after : int
        Total tile config bits after applying the pattern.
    """

    model_config = ConfigDict(frozen=True)

    rows_before: int = 0
    rows_after: int = 0
    columns_before: int = 0
    columns_after: int = 0
    active_pips_before: int = 0
    active_pips_after: int = 0
    generated_bel_input_pips: int = 0
    generated_output_coverage_pips: int = 0
    generated_routing_pips: int = 0
    generated_hierarchy_pips: int = 0
    added_jump_wires: int = 0
    applied_pips: int = 0
    compatible_routing_groups: int = 0
    matrix_config_bits_before: int = 0
    matrix_config_bits_after: int = 0
    total_config_bits_after: int = 0


class SwitchMatrixPatternResult(BaseModel):
    """Result bundle produced by switch-matrix pattern application.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    options : SwitchMatrixPatternOptions
        Normalized options.
    tile_name : str
        Tile type modified by the pass.
    stats : SwitchMatrixPatternStats
        Summary statistics.
    warnings : tuple[str, ...]
        Non-fatal diagnostics.
    report_summary : str
        Human-readable report text.
    """

    model_config = ConfigDict(frozen=True)

    options: SwitchMatrixPatternOptions
    tile_name: str
    stats: SwitchMatrixPatternStats = Field(default_factory=SwitchMatrixPatternStats)
    warnings: tuple[str, ...] = ()
    report_summary: str = ""
