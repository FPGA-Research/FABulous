"""Data models for switch-block factorization."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MuxReductionRule(BaseModel):
    """Describe one exact mux-fanin factorization rule."""

    model_config = ConfigDict(frozen=True)

    from_fanin: int
    to_fanin: int

    @model_validator(mode="after")
    def _validate_rule(self) -> MuxReductionRule:
        """Validate fanin values.

        Returns
        -------
        MuxReductionRule
            Validated rule.

        Raises
        ------
        ValueError
            If fanin values are invalid.
        """
        if self.from_fanin < 2:
            raise ValueError("from_fanin must be at least 2")
        if self.to_fanin < 2:
            raise ValueError("to_fanin must be at least 2")
        if self.to_fanin >= self.from_fanin:
            raise ValueError("to_fanin must be smaller than from_fanin")
        return self


class SwitchBlockFactorizerOptions(BaseModel):
    """Options for graph-local switch-block factorization."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    tile_name: str
    global_reduction: int | None = 1
    reduction_rules: list[MuxReductionRule] = Field(default_factory=list)
    min_mux_fanin_to_factorize: int = 3
    jump_prefix: str = "J_FAC"
    max_added_jump_wires: int | None = None
    config_bit_margin: int | None = None
    config_bit_limit: int | None = None
    track_progress: bool = True

    @field_validator("tile_name", "jump_prefix")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        """Validate non-empty text options.

        Parameters
        ----------
        value : str
            Text option value.

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

    @field_validator("global_reduction")
    @classmethod
    def _validate_global_reduction(cls, value: int | None) -> int | None:
        """Validate global factorization depth.

        Parameters
        ----------
        value : int | None
            Global factorization level count.

        Returns
        -------
        int | None
            Validated value.

        Raises
        ------
        ValueError
            If the value is negative.
        """
        if value is not None and value < 0:
            raise ValueError("global_reduction must be non-negative or None")
        return value

    @field_validator(
        "min_mux_fanin_to_factorize",
    )
    @classmethod
    def _validate_non_negative_int(cls, value: int) -> int:
        """Validate non-negative integer options.

        Parameters
        ----------
        value : int
            Integer option value.

        Returns
        -------
        int
            Validated integer.

        Raises
        ------
        ValueError
            If the value is negative.
        """
        if value < 0:
            raise ValueError("value must be non-negative")
        return value

    @field_validator("max_added_jump_wires", "config_bit_limit")
    @classmethod
    def _validate_optional_positive_int(cls, value: int | None) -> int | None:
        """Validate optional positive integer limits.

        Parameters
        ----------
        value : int | None
            Optional integer limit.

        Returns
        -------
        int | None
            Validated limit.

        Raises
        ------
        ValueError
            If the value is not positive.
        """
        if value is not None and value <= 0:
            raise ValueError("limit must be positive when set")
        return value


class SwitchBlockFactorizerArtifact(BaseModel):
    """Generated or updated switch-block factorizer artifact."""

    model_config = ConfigDict(frozen=True)

    kind: str
    path: Path


class SwitchBlockFactorizerStats(BaseModel):
    """Summary statistics for one switch-block factorization run."""

    model_config = ConfigDict(frozen=True)

    mux_rows_before: int = 0
    mux_rows_after: int = 0
    pips_before: int = 0
    pips_after: int = 0
    max_fanin_before: int = 0
    max_fanin_after: int = 0
    matrix_config_bits_before: int = 0
    matrix_config_bits_after: int = 0
    fixed_config_bits: int = 0
    total_config_bits_before: int = 0
    total_config_bits_after: int = 0
    effective_config_bit_limit: int | None = None
    blocked_reductions: int = 0
    added_jump_wires: int = 0
    factorized_rows: int = 0
    generated_hierarchy_pips: int = 0
    fanin_histogram_before: dict[int, int] = Field(default_factory=dict)
    fanin_histogram_after: dict[int, int] = Field(default_factory=dict)
    reachability_preserved: bool = True


class SwitchBlockFactorizerResult(BaseModel):
    """Result bundle produced by switch-block factorization."""

    model_config = ConfigDict(frozen=True)

    options: SwitchBlockFactorizerOptions
    tile_name: str
    artifacts: tuple[SwitchBlockFactorizerArtifact, ...] = ()
    stats: SwitchBlockFactorizerStats = Field(
        default_factory=SwitchBlockFactorizerStats
    )
    warnings: tuple[str, ...] = ()
    report_summary: str = ""
