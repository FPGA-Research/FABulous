"""Data models for routing-demand evaluation."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DemandKind(StrEnum):
    """Demand strictness used by the evaluator."""

    HARD = "hard"
    SOFT = "soft"


class DemandCategory(StrEnum):
    """Report category used to explain demand intent."""

    ESSENTIAL = "essential"
    STRESS = "stress"
    SPECIAL = "special"
    RANDOM = "random"


class DemandProfileName(StrEnum):
    """Built-in demand profile names."""

    DEFAULT = "default"
    MINIMAL = "minimal"
    ROUTING_STRESS = "routing_stress"
    CONTROL_STRESS = "control_stress"
    FULL = "full"


class DemandClassName(StrEnum):
    """Internal demand class names used by profiles."""

    BEL_OUTPUT_ESCAPE = "bel_output_escape"
    BEL_INPUT_REACHABILITY = "bel_input_reachability"
    BEL_INPUT_SOURCE_COVERAGE = "bel_input_source_coverage"
    MATRIX_ROW_COVERAGE = "matrix_row_coverage"
    MATRIX_SOURCE_USEFULNESS = "matrix_source_usefulness"
    FANIN_DIVERSITY = "fanin_diversity"
    SOURCE_FANOUT_DIVERSITY = "source_fanout_diversity"
    SIDE_PAIR_BALANCE = "side_pair_balance"
    HIERARCHY_INTEGRITY = "hierarchy_integrity"
    LOCAL_FEEDBACK = "local_feedback"
    NEIGHBOR_FEEDBACK = "neighbor_feedback"
    STRAIGHT_ROUTING = "straight_routing"
    TURN_ROUTING = "turn_routing"
    SHORT_TO_LONG = "short_to_long"
    LONG_TO_SHORT = "long_to_short"
    MULTI_HOP = "multi_hop"
    ROUTING_REDUNDANCY = "routing_redundancy"
    BEL_INPUT_FANOUT = "bel_input_fanout"
    CONTROL_REACHABILITY = "control_reachability"
    CONTROL_NET = "control_net"
    CARRY_CHAIN = "carry_chain"
    DSP_RAM_ACCESS = "dsp_ram_access"
    IO_ACCESS = "io_access"
    RANDOM_LOCAL = "random_local"
    RANDOM_MEDIUM = "random_medium"
    RANDOM_LONG = "random_long"


class RandomDemandBucketStats(BaseModel):
    """Candidate statistics for one random demand bucket.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    demand_class : str
        Random demand class.
    candidate_pairs : int
        Distance-matching source/sink pairs.
    reachable_pairs : int
        Distance-matching pairs with a route.
    generated_demands : int
        Demands emitted into the selected profile.
    """

    model_config = ConfigDict(frozen=True)

    demand_class: str
    candidate_pairs: int
    reachable_pairs: int
    generated_demands: int


class RoutingTerminalRole(StrEnum):
    """Semantic terminal roles discovered from FABulous objects."""

    BEL_INPUT = "bel_input"
    BEL_OUTPUT = "bel_output"
    TILE_INPUT = "tile_input"
    TILE_OUTPUT = "tile_output"
    JUMP_BEGIN = "jump_begin"
    JUMP_END = "jump_end"
    CONSTANT = "constant"
    CARRY_INPUT = "carry_input"
    CARRY_OUTPUT = "carry_output"
    LOCAL_RESET = "local_reset"
    LOCAL_ENABLE = "local_enable"
    SHARED_RESET = "shared_reset"
    SHARED_ENABLE = "shared_enable"
    IO_INPUT = "io_input"
    IO_OUTPUT = "io_output"
    EXTERNAL_INPUT = "external_input"
    EXTERNAL_OUTPUT = "external_output"


class RoutingTerminalSource(StrEnum):
    """Source object family for one classified terminal."""

    BEL = "bel"
    TILE_PORT = "tile_port"
    GENERATED = "generated"


class RouterName(StrEnum):
    """Built-in routing algorithm names."""

    PATHFINDER = "pathfinder"


class OptimizerName(StrEnum):
    """Built-in optimizer names."""

    NONE = "none"
    GREEDY = "greedy"
    MONTE_CARLO = "monte_carlo"


class FabulousRoutingKeyword(StrEnum):
    """FABulous annotation keywords used by routing-demand classification."""

    NULL = "NULL"
    RESET = "RESET"
    ENABLE = "ENABLE"


class RoutingDemandEvaluatorOptions(BaseModel):
    """Options for one routing-demand evaluator run.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    tile_name : str
        FABulous tile to evaluate.
    demand_profile : DemandProfileName
        Demand profile to generate.
    demand_iterations : int
        Target number of generated demands.
    random_demand_ratio : float
        Fraction of demands reserved for random soft demands.
    seed : int
        Random seed for reproducible profiles.
    opt : bool
        Whether to run an optimizer.
    optimizer : OptimizerName
        Optimizer implementation name.
    opt_target_pip_reduction : float
        Target PIP reduction for optimizers.
    opt_max_soft_failure_rate : float
        Maximum optimizer-added soft-demand failure rate.
    opt_max_hard_failure_rate : float
        Maximum optimizer-added hard-demand failure rate.
    opt_use_baseline_failure_rates : bool
        Whether optimizer failure-rate limits are added to the baseline rates.
    apply_to_tile_model : bool
        Whether optimizer changes update the in-memory FabGraph tile model.
    opt_max_iterations : int
        Maximum optimizer pruning iterations.
    opt_clean_mux : bool
        Whether greedy optimization should prefer mux bucket cleanup.
    opt_power_of_two_muxes : bool
        Whether mux cleanup should require power-of-two mux fanins where possible.
    report_max_soft_failure_rate : float
        Maximum soft-demand failure rate before the report status becomes a warning.
    router : RouterName
        Router implementation name.
    router_max_iterations : int
        Maximum PathFinder negotiation iterations.
    router_present_cost_multiplier : float
        Present congestion cost multiplier.
    router_history_cost_increment : float
        Historical congestion cost increment for overused resources.
    router_base_resource_capacity : int
        Default resource capacity before a node is considered congested.
    fanout_targets : list[int]
        Fanout sink counts used by fanout-style demand classes.
    max_net_sinks : int
        Maximum sinks allowed on one generated net demand.
    config_bit_margin : int
        Reserved config-bit margin.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of optimizer iterations between progress updates.
    """

    model_config = ConfigDict(frozen=True)

    tile_name: str
    demand_profile: DemandProfileName = DemandProfileName.DEFAULT
    demand_iterations: int = 1000
    random_demand_ratio: float = 0.25
    seed: int = 1
    opt: bool = False
    optimizer: OptimizerName = OptimizerName.NONE
    opt_target_pip_reduction: float = 0.20
    opt_max_soft_failure_rate: float = 0.05
    opt_max_hard_failure_rate: float = 0.0
    opt_use_baseline_failure_rates: bool = True
    apply_to_tile_model: bool = False
    opt_max_iterations: int = 50
    opt_clean_mux: bool = False
    opt_power_of_two_muxes: bool = False
    report_max_soft_failure_rate: float = 0.05
    router: RouterName = RouterName.PATHFINDER
    router_max_iterations: int = 30
    router_present_cost_multiplier: float = 1.3
    router_history_cost_increment: float = 1.0
    router_base_resource_capacity: int = 1
    fanout_targets: list[int] = Field(default_factory=lambda: [2, 4, 8])
    max_net_sinks: int = 8
    config_bit_margin: int = 0
    track_progress: bool = True
    progress_chunk_size: int = 10

    @model_validator(mode="before")
    @classmethod
    def _normalize_disabled_optimizer(cls, data: object) -> object:
        """Ignore optimizer selection when optimization is disabled.

        Parameters
        ----------
        data : object
            Raw model input.

        Returns
        -------
        object
            Normalized model input.
        """
        if isinstance(data, dict) and not data.get("opt", False):
            return {**data, "optimizer": OptimizerName.NONE}
        return data

    @model_validator(mode="before")
    @classmethod
    def _normalize_mux_optimizer_options(cls, data: object) -> object:
        """Normalize mux optimizer option dependencies.

        Parameters
        ----------
        data : object
            Raw model input.

        Returns
        -------
        object
            Normalized model input.
        """
        if isinstance(data, dict) and data.get("opt_power_of_two_muxes", False):
            return {**data, "opt_clean_mux": True}
        return data

    @field_validator("tile_name")
    @classmethod
    def _validate_tile_name(cls, value: str) -> str:
        """Validate that a tile name is provided.

        Parameters
        ----------
        value : str
            Tile name.

        Returns
        -------
        str
            Validated tile name.

        Raises
        ------
        ValueError
            If the tile name is empty.
        """
        if not value:
            raise ValueError("tile_name must not be empty")
        return value

    @field_validator(
        "demand_iterations",
        "router_max_iterations",
        "router_base_resource_capacity",
        "opt_max_iterations",
        "max_net_sinks",
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
            Validated value.

        Raises
        ------
        ValueError
            If the value is less than one.
        """
        if value < 1:
            raise ValueError("value must be at least 1")
        return value

    @field_validator("fanout_targets")
    @classmethod
    def _validate_fanout_targets(cls, value: list[int]) -> list[int]:
        """Validate requested fanout targets.

        Parameters
        ----------
        value : list[int]
            Fanout target list.

        Returns
        -------
        list[int]
            Validated fanout targets.

        Raises
        ------
        ValueError
            If the list is empty or contains values smaller than two.
        """
        if not value:
            raise ValueError("fanout_targets must not be empty")
        if any(target < 2 for target in value):
            raise ValueError("fanout_targets must be at least 2")
        return sorted(dict.fromkeys(value))

    @field_validator("config_bit_margin")
    @classmethod
    def _validate_non_negative_int(cls, value: int) -> int:
        """Validate non-negative integer options.

        Parameters
        ----------
        value : int
            Integer option.

        Returns
        -------
        int
            Validated value.

        Raises
        ------
        ValueError
            If the value is negative.
        """
        if value < 0:
            raise ValueError("value must be non-negative")
        return value

    @field_validator(
        "random_demand_ratio",
        "opt_target_pip_reduction",
        "opt_max_soft_failure_rate",
        "opt_max_hard_failure_rate",
        "report_max_soft_failure_rate",
    )
    @classmethod
    def _validate_unit_float(cls, value: float) -> float:
        """Validate values in the inclusive unit interval.

        Parameters
        ----------
        value : float
            Float option.

        Returns
        -------
        float
            Validated value.

        Raises
        ------
        ValueError
            If the value is outside ``[0.0, 1.0]``.
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError("value must be between 0.0 and 1.0")
        return value

    @field_validator(
        "router_present_cost_multiplier",
        "router_history_cost_increment",
    )
    @classmethod
    def _validate_positive_float(cls, value: float) -> float:
        """Validate positive floating-point router options.

        Parameters
        ----------
        value : float
            Float option.

        Returns
        -------
        float
            Validated value.

        Raises
        ------
        ValueError
            If the value is not positive.
        """
        if value <= 0.0:
            raise ValueError("value must be positive")
        return value


class MatrixData(BaseModel):
    """Loaded switch-matrix data.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    tile_name : str
        Tile name.
    matrix_source : str
        Human-readable source of the evaluated matrix snapshot.
    columns : list[str]
        Switch-matrix source columns from FabGraph.
    rows : list[str]
        Switch-matrix destination rows from FabGraph.
    connections : dict[str, list[str]]
        Mapping from destination rows to selectable sources.
    delay_by_row : dict[str, dict[str, float]]
        Active PIP delays keyed by row and source.
    jump_edges : list[tuple[str, str]]
        Local JUMP resource edges.
    terminals : list[RoutingTerminal]
        Classified routing terminals discovered from FABulous objects.
    matrix_config_bits : int
        Matrix config bits reported by FABulous.
    total_config_bits : int
        Total tile config bits reported by FABulous.
    config_capacity : int
        Total config-bit capacity used by fabxplore.
    """

    model_config = ConfigDict(frozen=True)

    tile_name: str
    matrix_source: str
    columns: list[str]
    rows: list[str]
    connections: dict[str, list[str]]
    delay_by_row: dict[str, dict[str, float]] = Field(default_factory=dict)
    jump_edges: list[tuple[str, str]]
    terminals: list[RoutingTerminal] = Field(default_factory=list)
    matrix_config_bits: int
    total_config_bits: int
    config_capacity: int


class RoutingTerminal(BaseModel):
    """One classified routing endpoint.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    name : str
        Graph node name.
    role : RoutingTerminalRole
        Semantic terminal role.
    source : RoutingTerminalSource
        FABulous object family that produced the terminal.
    bel_name : str | None
        BEL instance/source name when applicable.
    bel_module : str | None
        BEL module name when applicable.
    bel_prefix : str | None
        BEL prefix when applicable.
    port_name : str | None
        Original FABulous port name when applicable.
    direction : str | None
        FABulous direction value when applicable.
    x_offset : int
        FABulous port X offset.
    y_offset : int
        FABulous port Y offset.
    wire_count : int
        FABulous port wire count.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    role: RoutingTerminalRole
    source: RoutingTerminalSource
    bel_name: str | None = None
    bel_module: str | None = None
    bel_prefix: str | None = None
    port_name: str | None = None
    direction: str | None = None
    x_offset: int = 0
    y_offset: int = 0
    wire_count: int = 1


class RoutingTerminalCatalog(BaseModel):
    """Classified terminal collection.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    terminals : list[RoutingTerminal]
        Classified terminals.
    warnings : list[str]
        Non-fatal classification warnings.
    """

    model_config = ConfigDict(frozen=True)

    terminals: list[RoutingTerminal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def by_role(self, role: RoutingTerminalRole) -> list[RoutingTerminal]:
        """Return terminals with one role.

        Parameters
        ----------
        role : RoutingTerminalRole
            Role to filter.

        Returns
        -------
        list[RoutingTerminal]
            Matching terminals.
        """
        return [terminal for terminal in self.terminals if terminal.role == role]

    def names_by_role(self, role: RoutingTerminalRole) -> list[str]:
        """Return unique node names with one role.

        Parameters
        ----------
        role : RoutingTerminalRole
            Role to filter.

        Returns
        -------
        list[str]
            Matching node names.
        """
        return sorted({terminal.name for terminal in self.by_role(role)})


class RoutingDemand(BaseModel):
    """One synthetic routing demand.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    demand_id : str
        Stable demand identifier.
    demand_class : str
        Demand class name.
    kind : DemandKind
        Hard or soft demand kind.
    source : str
        Source routing node.
    sink : str
        Primary sink routing node.
    sinks : list[str]
        All sink nodes driven by this demand.
    weight : float
        Demand weight for future optimizer scoring.
    """

    model_config = ConfigDict(frozen=True)

    demand_id: str
    demand_class: str
    kind: DemandKind
    source: str
    sink: str
    sinks: list[str] = Field(default_factory=list)
    weight: float = 1.0

    @model_validator(mode="before")
    @classmethod
    def _fill_sinks(cls, data: object) -> object:
        """Populate the sink list for pair-style demands.

        Parameters
        ----------
        data : object
            Raw model input.

        Returns
        -------
        object
            Updated model input.
        """
        if not isinstance(data, dict):
            return data
        sink = data.get("sink")
        sinks = list(data.get("sinks") or [])
        if sink is None:
            return data
        if not sinks:
            data["sinks"] = [sink]
        elif sink not in sinks:
            data["sinks"] = [sink, *sinks]
        return data


class DemandProfileResult(BaseModel):
    """Generated demand profile data.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    profile_name : str
        Profile name.
    demands : list[RoutingDemand]
        Generated demands.
    warnings : list[str]
        Non-fatal profile generation warnings.
    """

    model_config = ConfigDict(frozen=True)

    profile_name: str
    demands: list[RoutingDemand]
    warnings: list[str] = Field(default_factory=list)


class RoutedPath(BaseModel):
    """One routed path.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    demand_id : str
        Demand identifier.
    nodes : list[str]
        Ordered routing nodes.
    cost : float
        Final path cost.
    """

    model_config = ConfigDict(frozen=True)

    demand_id: str
    nodes: list[str]
    cost: float


class DemandRouteResult(BaseModel):
    """Routing result for one demand.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    demand : RoutingDemand
        Original demand.
    routed : bool
        Whether a route was found.
    path : RoutedPath | None
        First routed path if successful.
    paths : list[RoutedPath]
        Routed paths for all sinks that were reached.
    failed_sinks : list[str]
        Sinks not reached by the router.
    failure_reason : str | None
        Failure reason if not routed.
    """

    model_config = ConfigDict(frozen=True)

    demand: RoutingDemand
    routed: bool
    path: RoutedPath | None = None
    paths: list[RoutedPath] = Field(default_factory=list)
    failed_sinks: list[str] = Field(default_factory=list)
    failure_reason: str | None = None


class DemandClassStats(BaseModel):
    """Aggregate statistics for one demand class.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    demand_class : str
        Demand class name.
    kind : DemandKind
        Demand kind.
    total : int
        Total demands in the class.
    passed : int
        Routed demands.
    failed : int
        Failed demands.
    average_path_length : float
        Average routed path length in node hops.
    """

    model_config = ConfigDict(frozen=True)

    demand_class: str
    kind: DemandKind
    total: int
    passed: int
    failed: int
    average_path_length: float

    @property
    def pass_rate(self) -> float:
        """Return the class pass rate.

        Returns
        -------
        float
            Pass rate in ``[0.0, 1.0]``.
        """
        if self.total == 0:
            return 1.0
        return self.passed / self.total


class RouterRunStats(BaseModel):
    """PathFinder router run statistics.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    iterations_used : int
        Negotiation iterations used.
    congested_resources : int
        Number of resources still over capacity.
    max_resource_usage : int
        Maximum observed resource usage count.
    failed_sinks : int
        Number of unrouted sinks in the final iteration.
    """

    model_config = ConfigDict(frozen=True)

    iterations_used: int
    congested_resources: int
    max_resource_usage: int
    failed_sinks: int = 0


class RoutingDemandEvaluationStats(BaseModel):
    """Top-level evaluation statistics.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    total_demands : int
        Total generated demands.
    hard_demands : int
        Total hard demands.
    soft_demands : int
        Total soft demands.
    hard_failed : int
        Failed hard demands.
    soft_failed : int
        Failed soft demands.
    failed_sinks : int
        Failed sinks across routed net demands.
    original_pips : int
        Original routing graph edges, including switch-matrix PIPs and JUMP wires.
    final_pips : int
        Final routing graph edges, including switch-matrix PIPs and JUMP wires.
    original_routing_pips : int
        Original selectable switch-matrix routing PIPs.
    final_routing_pips : int
        Final selectable switch-matrix routing PIPs.
    jump_wires : int
        Fixed local JUMP edges added to the routing graph.
    original_graph_edges : int
        Original routing graph edge count.
    final_graph_edges : int
        Final routing graph edge count.
    matrix_config_bits : int
        Matrix config bits.
    total_config_bits : int
        Total tile config bits.
    config_capacity : int
        Config-bit capacity.
    average_path_length : float
        Average routed path length.
    """

    model_config = ConfigDict(frozen=True)

    total_demands: int
    hard_demands: int
    soft_demands: int
    hard_failed: int
    soft_failed: int
    failed_sinks: int
    original_pips: int
    final_pips: int
    original_routing_pips: int
    final_routing_pips: int
    jump_wires: int
    original_graph_edges: int
    final_graph_edges: int
    matrix_config_bits: int
    total_config_bits: int
    config_capacity: int
    average_path_length: float

    @property
    def hard_passed(self) -> bool:
        """Return whether all hard demands passed.

        Returns
        -------
        bool
            Whether no hard demand failed.
        """
        return self.hard_failed == 0

    @property
    def hard_passed_count(self) -> int:
        """Return the number of passed hard demands.

        Returns
        -------
        int
            Passed hard demands.
        """
        return self.hard_demands - self.hard_failed

    @property
    def hard_pass_rate(self) -> float:
        """Return the hard-demand pass rate.

        Returns
        -------
        float
            Hard pass rate.
        """
        if self.hard_demands == 0:
            return 1.0
        return self.hard_passed_count / self.hard_demands

    @property
    def hard_failure_rate(self) -> float:
        """Return the hard-demand failure rate.

        Returns
        -------
        float
            Hard failure rate.
        """
        if self.hard_demands == 0:
            return 0.0
        return self.hard_failed / self.hard_demands

    @property
    def soft_passed_count(self) -> int:
        """Return the number of passed soft demands.

        Returns
        -------
        int
            Passed soft demands.
        """
        return self.soft_demands - self.soft_failed

    @property
    def soft_pass_rate(self) -> float:
        """Return the soft-demand pass rate.

        Returns
        -------
        float
            Soft pass rate.
        """
        if self.soft_demands == 0:
            return 1.0
        return self.soft_passed_count / self.soft_demands

    @property
    def soft_failure_rate(self) -> float:
        """Return the soft-demand failure rate.

        Returns
        -------
        float
            Soft failure rate.
        """
        if self.soft_demands == 0:
            return 0.0
        return self.soft_failed / self.soft_demands


class MuxBucketStats(BaseModel):
    """Mux implementation bucket row counts.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    bucket : str
        Bucket label, such as ``direct`` or ``mux8``.
    before_rows : int
        Rows in this bucket before optimization.
    after_rows : int
        Rows in this bucket after optimization.
    """

    model_config = ConfigDict(frozen=True)

    bucket: str
    before_rows: int
    after_rows: int

    @property
    def delta(self) -> int:
        """Return row-count delta after optimization.

        Returns
        -------
        int
            Difference between after and before row counts.
        """
        return self.after_rows - self.before_rows


class MuxCleanupRowStats(BaseModel):
    """Per-row mux implementation change.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    row : str
        Matrix row name.
    fanin_before : int
        Row fanin before optimization.
    fanin_after : int
        Row fanin after optimization.
    bucket_before : str
        Implementation bucket before optimization.
    bucket_after : str
        Implementation bucket after optimization.
    removed_pips : int
        Removed PIPs from this row.
    config_bits_saved : int
        Estimated matrix config bits saved in this row.
    mux_cost_saved : int
        Estimated mux bucket cost saved in this row.
    """

    model_config = ConfigDict(frozen=True)

    row: str
    fanin_before: int
    fanin_after: int
    bucket_before: str
    bucket_after: str
    removed_pips: int
    config_bits_saved: int
    mux_cost_saved: int


class MuxCleanupStats(BaseModel):
    """Mux-cost reporting statistics.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    baseline_mux_cost : int
        Estimated mux bucket cost before optimization.
    final_mux_cost : int
        Estimated mux bucket cost after optimization.
    mux_cost_reduction : float
        Fractional mux-cost reduction.
    rows_crossing_thresholds : int
        Rows whose implementation bucket changed.
    direct_wire_conversions : int
        Rows converted to direct wires.
    config_bit_reduction : int
        Estimated matrix config-bit reduction.
    non_power_of_two_mux_rows_before : int
        Non-power-of-two mux rows before optimization.
    non_power_of_two_mux_rows_after : int
        Non-power-of-two mux rows after optimization.
    buckets : list[MuxBucketStats]
        Per-bucket row counts.
    changed_rows : list[MuxCleanupRowStats]
        Rows whose implementation bucket changed.
    """

    model_config = ConfigDict(frozen=True)

    baseline_mux_cost: int
    final_mux_cost: int
    mux_cost_reduction: float
    rows_crossing_thresholds: int
    direct_wire_conversions: int
    config_bit_reduction: int
    non_power_of_two_mux_rows_before: int
    non_power_of_two_mux_rows_after: int
    buckets: list[MuxBucketStats]
    changed_rows: list[MuxCleanupRowStats]


class OptimizerStats(BaseModel):
    """Optimizer summary statistics.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    enabled : bool
        Whether optimization ran.
    optimizer : str
        Optimizer implementation name.
    applied_to_tile_model : bool
        Whether optimizer changes updated the in-memory FabGraph tile model.
    baseline_pips : int
        PIPs before optimization.
    final_pips : int
        PIPs after optimization.
    removed_pips : int
        Accepted removed PIPs.
    baseline_matrix_config_bits : int
        Matrix config bits before optimization.
    final_matrix_config_bits_estimate : int
        Estimated matrix config bits after optimization.
    baseline_total_config_bits : int
        Total config bits before optimization.
    final_total_config_bits_estimate : int
        Estimated total config bits after optimization.
    pip_reduction : float
        Fraction of baseline PIPs removed.
    target_pip_reduction : float
        Requested PIP reduction target.
    baseline_hard_failure_rate : float
        Hard-demand failure rate before optimization.
    baseline_soft_failure_rate : float
        Soft-demand failure rate before optimization.
    allowed_hard_failure_rate : float
        Final hard-demand failure-rate limit.
    allowed_soft_failure_rate : float
        Final soft-demand failure-rate limit.
    final_hard_failure_rate : float
        Final hard-demand failure rate.
    final_soft_failure_rate : float
        Final soft-demand failure rate.
    attempted_iterations : int
        Optimizer iterations used.
    attempted_batches : int
        Candidate batches evaluated.
    accepted_batches : int
        Candidate batches accepted.
    rejected_batches : int
        Candidate batches rejected.
    attempted_pips : int
        Candidate PIP removals attempted.
    accepted_pips : int
        Candidate PIP removals accepted.
    rejected_pips : int
        Candidate PIP removals rejected.
    stop_reason : str
        Reason optimization stopped.
    mux_cleanup : MuxCleanupStats
        Mux bucket/cost changes from accepted optimization.
    sampled_batches : int
        Monte Carlo ablation batches evaluated for importance estimation.
    importance_rounds : int
        Monte Carlo importance-estimation rounds.
    learning_iterations : int
        Monte Carlo temporary ablation evaluations.
    pruning_iterations : int
        Monte Carlo checked pruning evaluations.
    average_sample_loss : float
        Average loss observed while learning PIP importance.
    max_sample_loss : float
        Maximum loss observed while learning PIP importance.
    weight_change_rate : float
        Relative final change in learned PIP importance weights.
    sampled_pips : int
        Removable PIPs seen in at least one learning sample.
    unsampled_pips : int
        Removable PIPs not seen in learning samples.
    sampled_pip_rate : float
        Fraction of removable PIPs sampled during learning.
    min_samples_per_pip : int
        Minimum learning sample count across removable PIPs.
    average_samples_per_pip : float
        Average learning sample count across removable PIPs.
    max_samples_per_pip : int
        Maximum learning sample count across removable PIPs.
    best_iteration : int | None
        Optimizer iteration that produced the best accepted result.
    pip_importance_matrix : dict[str, dict[str, float]]
        Per-row, per-source PIP importance values from Monte Carlo sampling.
    pip_importance_file : Path | None
        Optional text file containing the PIP importance matrix.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool
    optimizer: str
    applied_to_tile_model: bool
    baseline_pips: int
    final_pips: int
    removed_pips: int
    baseline_matrix_config_bits: int
    final_matrix_config_bits_estimate: int
    baseline_total_config_bits: int
    final_total_config_bits_estimate: int
    pip_reduction: float
    target_pip_reduction: float
    baseline_hard_failure_rate: float
    baseline_soft_failure_rate: float
    allowed_hard_failure_rate: float
    allowed_soft_failure_rate: float
    final_hard_failure_rate: float
    final_soft_failure_rate: float
    attempted_iterations: int
    attempted_batches: int
    accepted_batches: int
    rejected_batches: int
    attempted_pips: int
    accepted_pips: int
    rejected_pips: int
    stop_reason: str
    mux_cleanup: MuxCleanupStats
    sampled_batches: int = 0
    importance_rounds: int = 0
    learning_iterations: int = 0
    pruning_iterations: int = 0
    average_sample_loss: float = 0.0
    max_sample_loss: float = 0.0
    weight_change_rate: float = 0.0
    sampled_pips: int = 0
    unsampled_pips: int = 0
    sampled_pip_rate: float = 0.0
    min_samples_per_pip: int = 0
    average_samples_per_pip: float = 0.0
    max_samples_per_pip: int = 0
    best_iteration: int | None = None
    pip_importance_matrix: dict[str, dict[str, float]] = Field(default_factory=dict)
    pip_importance_file: Path | None = None


class RoutingDemandEvaluatorResult(BaseModel):
    """Structured result returned by routing-demand evaluation.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    options : RoutingDemandEvaluatorOptions
        Normalized pass options.
    matrix : MatrixData
        Loaded matrix metadata.
    demand_profile : DemandProfileResult
        Generated demands.
    demand_results : list[DemandRouteResult]
        Per-demand route results.
    stats : RoutingDemandEvaluationStats
        Top-level evaluation statistics.
    class_stats : list[DemandClassStats]
        Aggregated demand-class statistics.
    router_stats : RouterRunStats
        Router run statistics.
    resource_usage : dict[str, int]
        Resource usage by node.
    pip_usage : dict[str, int]
        PIP usage by ``source->sink`` string.
    warnings : list[str]
        Warnings from loading, generation, or evaluation.
    random_bucket_stats : list[RandomDemandBucketStats]
        Candidate statistics for random demand buckets.
    optimizer_stats : OptimizerStats | None
        Optional optimizer summary.
    report_summary : str
        Rendered human-readable report.
    """

    model_config = ConfigDict(frozen=True)

    options: RoutingDemandEvaluatorOptions
    matrix: MatrixData
    demand_profile: DemandProfileResult
    demand_results: list[DemandRouteResult]
    stats: RoutingDemandEvaluationStats
    class_stats: list[DemandClassStats]
    router_stats: RouterRunStats
    resource_usage: dict[str, int]
    pip_usage: dict[str, int]
    warnings: list[str]
    random_bucket_stats: list[RandomDemandBucketStats] = Field(default_factory=list)
    optimizer_stats: OptimizerStats | None = None
    report_summary: str = ""

    @property
    def hard_demands_passed(self) -> bool:
        """Return whether all hard demands passed.

        Returns
        -------
        bool
            Whether all hard demands passed.
        """
        return all(
            result.routed
            for result in self.demand_results
            if result.demand.kind == DemandKind.HARD
        )

    @property
    def soft_failure_rate(self) -> float:
        """Return the soft-demand failure rate.

        Returns
        -------
        float
            Soft failure rate.
        """
        soft = [
            result
            for result in self.demand_results
            if result.demand.kind == DemandKind.SOFT
        ]
        if not soft:
            return 0.0
        return sum(1 for result in soft if not result.routed) / len(soft)
