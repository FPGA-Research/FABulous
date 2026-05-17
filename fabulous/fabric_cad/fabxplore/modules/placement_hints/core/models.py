"""Data models for placement hint generation.

The placement-hints pass is intentionally independent from mapping passes. It looks at
the current netlist, detects structural patterns such as linear chains, and writes
uniform cell attributes that a downstream placer can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class PlacementRuleKind(StrEnum):
    """Supported placement hint rule kinds.

    Attributes
    ----------
    LINEAR_CHAIN
        Detect linear cell chains connected from one source port to one sink
        port.
    """

    LINEAR_CHAIN = "linear_chain"


class PlacementAttributeNames(BaseModel):
    """Attribute names emitted by the placement-hints pass.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    kind : str
        Attribute storing the structural hint kind.
    name : str
        Attribute storing the user-facing rule name.
    cluster_id : str
        Attribute storing the unique cluster identifier.
    role : str
        Attribute storing the cell role inside the cluster.
    index : str
        Attribute storing the zero-based cell index inside the cluster.
    size : str
        Attribute storing the number of cells in the cluster.
    """

    model_config = ConfigDict(frozen=True)

    kind: str
    name: str
    cluster_id: str
    role: str
    index: str
    size: str

    @classmethod
    def from_prefix(cls, prefix: str) -> PlacementAttributeNames:
        """Build the standard attribute names from a common prefix.

        Parameters
        ----------
        prefix : str
            Common attribute prefix.

        Returns
        -------
        PlacementAttributeNames
            Attribute-name bundle.
        """
        return cls(
            kind=f"{prefix}_KIND",
            name=f"{prefix}_NAME",
            cluster_id=f"{prefix}_ID",
            role=f"{prefix}_ROLE",
            index=f"{prefix}_INDEX",
            size=f"{prefix}_SIZE",
        )


class LinearChainRule(BaseModel):
    """Describe a linear placement chain.

    A chain edge is detected when one matched cell's ``source_port`` net feeds
    another matched cell's ``sink_port`` net.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    kind : Literal["linear_chain"]
        Rule discriminator.
    name : str
        Human-readable chain name used in emitted attributes.
    cell_types : tuple[str, ...]
        Cell types that may participate in this chain.
    source_port : str
        Output-like port used to drive the next chain stage.
    sink_port : str
        Input-like port used to receive the previous chain stage.
    min_length : int
        Minimum number of stages required before emitting a cluster.
    allow_branching : bool
        If ``False``, branching chain nets raise an error. If ``True``,
        ambiguous chain nets are skipped.
    allow_single_stage : bool
        Whether isolated cells may be emitted as single-stage clusters.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["linear_chain"] = "linear_chain"
    name: str
    cell_types: tuple[str, ...]
    source_port: str
    sink_port: str
    min_length: int = 2
    allow_branching: bool = False
    allow_single_stage: bool = False

    @field_validator("name", "source_port", "sink_port")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        """Validate that a string field is not empty.

        Parameters
        ----------
        value : str
            User-provided field value.

        Returns
        -------
        str
            Validated string.

        Raises
        ------
        ValueError
            If the value is empty.
        """
        if not value:
            raise ValueError("field must not be empty")
        return value

    @field_validator("cell_types")
    @classmethod
    def _validate_cell_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate that at least one cell type is provided.

        Parameters
        ----------
        value : tuple[str, ...]
            User-provided cell type tuple.

        Returns
        -------
        tuple[str, ...]
            Validated cell types.

        Raises
        ------
        ValueError
            If no cell types are provided.
        """
        if not value:
            raise ValueError("cell_types must not be empty")
        if any(not cell_type for cell_type in value):
            raise ValueError("cell_types must not contain empty values")
        return value

    @field_validator("min_length")
    @classmethod
    def _validate_min_length(cls, value: int) -> int:
        """Validate the minimum chain length.

        Parameters
        ----------
        value : int
            User-provided minimum chain length.

        Returns
        -------
        int
            Validated minimum chain length.

        Raises
        ------
        ValueError
            If the minimum length is less than one.
        """
        if value < 1:
            raise ValueError("min_length must be at least 1")
        return value


type PlacementRule = LinearChainRule
type PlacementRuleInput = LinearChainRule | dict[str, object]
type AttributeValue = str | int | bool


class PlacementHintsOptions(BaseModel):
    """Options for one placement-hints pass run.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    rules : tuple[PlacementRule, ...]
        Structural hint rules to apply.
    attribute_prefix : str
        Prefix used for emitted placement-hint attributes.
    overwrite_existing : bool
        Whether existing placement attributes may be replaced.
    fail_on_conflict : bool
        Whether conflicting generated or existing attributes should raise.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of processed rule matches between progress updates.
    top_name : str | None
        Top module to process.
    """

    model_config = ConfigDict(frozen=True)

    rules: tuple[PlacementRule, ...]
    attribute_prefix: str = "FAB_CLUSTER"
    overwrite_existing: bool = False
    fail_on_conflict: bool = True
    track_progress: bool = True
    progress_chunk_size: int = 100
    top_name: str | None = None

    @field_validator("rules", mode="before")
    @classmethod
    def _coerce_rules(cls, value: object) -> tuple[PlacementRule, ...]:
        """Coerce user rule dictionaries into typed rule models.

        Parameters
        ----------
        value : object
            User-provided rules.

        Returns
        -------
        tuple[PlacementRule, ...]
            Typed placement rules.

        Raises
        ------
        ValueError
            If an unknown rule kind is provided.
        TypeError
            If a rule is not a dictionary or a valid model instance.
        """
        if value is None:
            return ()
        raw_rules = value if isinstance(value, list | tuple) else (value,)
        rules: list[PlacementRule] = []
        for raw_rule in raw_rules:
            if isinstance(raw_rule, LinearChainRule):
                rules.append(raw_rule)
                continue
            if not isinstance(raw_rule, dict):
                raise TypeError("placement hint rules must be dictionaries")
            kind = raw_rule.get("kind", PlacementRuleKind.LINEAR_CHAIN.value)
            if kind == PlacementRuleKind.LINEAR_CHAIN.value:
                rules.append(LinearChainRule.model_validate(raw_rule))
                continue
            raise ValueError(f"unsupported placement hint rule kind: {kind}")
        return tuple(rules)

    @field_validator("rules")
    @classmethod
    def _validate_rules(
        cls,
        value: tuple[PlacementRule, ...],
    ) -> tuple[PlacementRule, ...]:
        """Validate that at least one rule is present.

        Parameters
        ----------
        value : tuple[PlacementRule, ...]
            Typed rules.

        Returns
        -------
        tuple[PlacementRule, ...]
            Validated rules.

        Raises
        ------
        ValueError
            If no rules are provided.
        """
        if not value:
            raise ValueError("rules must not be empty")
        return value

    @field_validator("attribute_prefix")
    @classmethod
    def _validate_attribute_prefix(cls, value: str) -> str:
        """Validate the emitted attribute prefix.

        Parameters
        ----------
        value : str
            User-provided prefix.

        Returns
        -------
        str
            Validated prefix.

        Raises
        ------
        ValueError
            If the prefix is empty.
        """
        if not value:
            raise ValueError("attribute_prefix must not be empty")
        return value

    @field_validator("progress_chunk_size")
    @classmethod
    def _validate_progress_chunk_size(cls, value: int) -> int:
        """Validate progress chunk size.

        Parameters
        ----------
        value : int
            User-provided chunk size.

        Returns
        -------
        int
            Validated chunk size.

        Raises
        ------
        ValueError
            If the chunk size is less than one.
        """
        if value < 1:
            raise ValueError("progress_chunk_size must be at least 1")
        return value

    @property
    def attribute_names(self) -> PlacementAttributeNames:
        """Return emitted attribute names.

        Returns
        -------
        PlacementAttributeNames
            Attribute-name bundle.
        """
        return PlacementAttributeNames.from_prefix(self.attribute_prefix)


@dataclass(frozen=True)
class PlacementHintCell:
    """Represent one cell in the selected module.

    Attributes
    ----------
    cell_id : str
        Cell instance name.
    cell_type : str
        Cell type name.
    attributes : dict[str, str]
        Existing cell attributes.
    connections : dict[str, tuple[str, ...]]
        Port-to-net connections.
    """

    cell_id: str
    cell_type: str
    attributes: dict[str, str]
    connections: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class PlacementHintDesign:
    """Represent the top module inspected by the placement-hints pass.

    Attributes
    ----------
    top_name : str
        Top module name.
    cells : tuple[PlacementHintCell, ...]
        Cells in reader order.
    """

    top_name: str
    cells: tuple[PlacementHintCell, ...]


@dataclass(frozen=True)
class PlacementCluster:
    """Represent one detected placement cluster.

    Attributes
    ----------
    rule_name : str
        Rule name that produced the cluster.
    cluster_id : str
        Unique cluster identifier.
    cells : tuple[str, ...]
        Cell IDs in cluster order.
    """

    rule_name: str
    cluster_id: str
    cells: tuple[str, ...]


@dataclass(frozen=True)
class PlacementHintAssignment:
    """Represent attributes to write to one cell.

    Attributes
    ----------
    cell_id : str
        Target cell instance name.
    attributes : dict[str, AttributeValue]
        Attributes to write.
    """

    cell_id: str
    attributes: dict[str, AttributeValue]


@dataclass
class PlacementHintsStats:
    """Counters collected by the placement-hints pass.

    Attributes
    ----------
    total_cells : int
        Number of cells inspected.
    rules : int
        Number of rules applied.
    candidate_cells : int
        Number of rule-matching cell visits.
    clusters : int
        Number of emitted clusters.
    assigned_cells : int
        Number of cells receiving placement attributes.
    skipped_chains : int
        Number of detected or possible chains skipped by rule filters.
    conflicts : int
        Number of generated or existing attribute conflicts.
    """

    total_cells: int = 0
    rules: int = 0
    candidate_cells: int = 0
    clusters: int = 0
    assigned_cells: int = 0
    skipped_chains: int = 0
    conflicts: int = 0


@dataclass(frozen=True)
class PlacementHintsResult:
    """Result bundle for one placement-hints pass run.

    Attributes
    ----------
    top_name : str
        Processed top module.
    options : PlacementHintsOptions
        Options used for the run.
    stats : PlacementHintsStats
        Summary counters.
    clusters : tuple[PlacementCluster, ...]
        Detected clusters.
    assignments : tuple[PlacementHintAssignment, ...]
        Attribute assignments written to cells.
    report_summary : str
        Human-readable report.
    """

    top_name: str
    options: PlacementHintsOptions
    stats: PlacementHintsStats
    clusters: tuple[PlacementCluster, ...] = ()
    assignments: tuple[PlacementHintAssignment, ...] = ()
    report_summary: str = ""
