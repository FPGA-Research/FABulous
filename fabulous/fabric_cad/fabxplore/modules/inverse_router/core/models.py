"""Data models for benchmark-driven inverse routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

BenchmarkSource = Path | dict[str, Any]


class InverseRouterOptions(BaseModel):
    """Options for inverse-routing resource scoring and pruning.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    tile_name : str
        Tile type to score and optionally modify.
    training_benchmarks : dict[str, BenchmarkSource]
        Benchmarks used to learn routing-resource scores.
    test_benchmarks : dict[str, BenchmarkSource]
        Benchmarks used only for post-pruning validation.
    io_seed_count : int
        Number of deterministic auto-PCF assignments per benchmark set.
    io_seed_start : int
        First auto-PCF assignment seed.
    optimize_switch_matrix : bool
        Whether switch-matrix pruning should be applied to the graph.
    switch_matrix_remove_unused_ratio : float
        Ratio of score-zero matrix PIPs to remove.
    switch_matrix_remove_used_ratio : float
        Ratio of score-positive matrix PIPs to remove after unused pruning.
    switch_matrix_active_pip_value : int | None
        Value assigned to kept matrix PIPs. If ``None``, original delays are
        kept where available.
    optimize_external_pips : bool
        Whether external logical-track pruning should be applied to the graph.
    external_remove_unused_ratio : float
        Ratio of score-zero external tracks to remove.
    external_remove_used_ratio : float
        Ratio of score-positive external tracks to remove after unused pruning.
    validate_training : bool
        Whether training benchmarks are rerun after graph updates.
    validate_test : bool
        Whether test benchmarks are run after graph updates.
    nextpnr_exec : Path | str | None
        Optional nextpnr executable.
    extra_args : tuple[str, ...]
        Extra nextpnr command-line arguments.
    live_output : bool
        Whether nextpnr output should be streamed live.
    track_progress : bool
        Whether progress messages should be logged.
    progress_chunk_size : int
        Number of route cases between progress messages.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    tile_name: str
    training_benchmarks: dict[str, BenchmarkSource] = Field(default_factory=dict)
    test_benchmarks: dict[str, BenchmarkSource] = Field(default_factory=dict)
    io_seed_count: int = 1
    io_seed_start: int = 1
    optimize_switch_matrix: bool = True
    switch_matrix_remove_unused_ratio: float = 1.0
    switch_matrix_remove_used_ratio: float = 0.0
    switch_matrix_active_pip_value: int | None = 1
    optimize_external_pips: bool = False
    external_remove_unused_ratio: float = 1.0
    external_remove_used_ratio: float = 0.0
    validate_training: bool = True
    validate_test: bool = True
    nextpnr_exec: Path | str | None = None
    extra_args: tuple[str, ...] = ()
    live_output: bool = False
    track_progress: bool = True
    progress_chunk_size: int = 1

    @field_validator("tile_name")
    @classmethod
    def _validate_non_empty_text(cls, value: str) -> str:
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
            raise ValueError("tile_name must not be empty")
        return value

    @field_validator("io_seed_count", "io_seed_start", "progress_chunk_size")
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

    @field_validator("switch_matrix_active_pip_value")
    @classmethod
    def _validate_optional_positive_int(cls, value: int | None) -> int | None:
        """Validate optional positive integer options.

        Parameters
        ----------
        value : int | None
            Optional integer value.

        Returns
        -------
        int | None
            Validated value.

        Raises
        ------
        ValueError
            If the value is not positive.
        """
        if value is not None and value <= 0:
            raise ValueError("switch_matrix_active_pip_value must be positive")
        return value

    @field_validator(
        "switch_matrix_remove_unused_ratio",
        "switch_matrix_remove_used_ratio",
        "external_remove_unused_ratio",
        "external_remove_used_ratio",
    )
    @classmethod
    def _validate_ratio(cls, value: float) -> float:
        """Validate ratio options.

        Parameters
        ----------
        value : float
            Ratio value.

        Returns
        -------
        float
            Validated ratio.

        Raises
        ------
        ValueError
            If the value is outside ``0..1``.
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError("ratio values must be between 0 and 1")
        return value


class InverseRouterRouteResult(BaseModel):
    """Summary for one route run.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    benchmark_name : str
        Benchmark top/case name.
    seed : int
        Auto-PCF assignment seed used for the route.
    phase : str
        ``training``, ``training_validation``, or ``test_validation``.
    passed : bool
        Whether nextpnr returned success.
    fasm_available : bool
        Whether the route produced FASM text.
    error : str | None
        Non-fatal error while routing or parsing.
    """

    model_config = ConfigDict(frozen=True)

    benchmark_name: str
    seed: int
    phase: str
    passed: bool
    fasm_available: bool = False
    error: str | None = None


class InverseRouterPruneStats(BaseModel):
    """Pruning counts for one resource class.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    candidates : int
        Number of score-tracked candidate PIPs.
    unused_candidates : int
        Number of candidates with score zero.
    used_candidates : int
        Number of candidates with positive score.
    removed_unused : int
        Number of score-zero candidates removed.
    removed_used : int
        Number of score-positive candidates removed.
    kept : int
        Number of candidates kept after pruning.
    """

    model_config = ConfigDict(frozen=True)

    candidates: int = 0
    unused_candidates: int = 0
    used_candidates: int = 0
    removed_unused: int = 0
    removed_used: int = 0
    kept: int = 0


class InverseRouterResult(BaseModel):
    """Structured inverse-router result.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    options : InverseRouterOptions
        Options used for this run.
    tile_name : str
        Scored tile type.
    training_routes : list[InverseRouterRouteResult]
        Training route collection results.
    training_validation_routes : list[InverseRouterRouteResult]
        Post-update training validation results.
    test_validation_routes : list[InverseRouterRouteResult]
        Post-update test validation results.
    switch_matrix_score : Any
        Matrix whose nonzero values are observed usage counts.
    final_switch_matrix : Any
        Final kept switch matrix produced by pruning.
    switch_matrix_stats : InverseRouterPruneStats
        Switch-matrix pruning statistics.
    external_scores : dict[Any, int]
        Tile-local external logical-track usage counts.
    final_external_pips : list[Any]
        External logical tracks kept after pruning.
    removed_external_pips : list[Any]
        External logical tracks selected for removal.
    external_stats : InverseRouterPruneStats
        External pruning statistics.
    report_summary : str
        Human-readable report.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    options: InverseRouterOptions
    tile_name: str
    training_routes: list[InverseRouterRouteResult] = Field(default_factory=list)
    training_validation_routes: list[InverseRouterRouteResult] = Field(
        default_factory=list
    )
    test_validation_routes: list[InverseRouterRouteResult] = Field(default_factory=list)
    switch_matrix_score: Any = None
    final_switch_matrix: Any = None
    switch_matrix_stats: InverseRouterPruneStats = Field(
        default_factory=InverseRouterPruneStats
    )
    external_scores: dict[Any, int] = Field(default_factory=dict)
    final_external_pips: list[Any] = Field(default_factory=list)
    removed_external_pips: list[Any] = Field(default_factory=list)
    external_stats: InverseRouterPruneStats = Field(
        default_factory=InverseRouterPruneStats
    )
    report_summary: str = ""
