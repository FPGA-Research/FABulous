"""Data models for FF materialization.

The FF materializer replaces standalone one-bit FF cells with architecture tile
instances configured as register lanes. The reader builds pure-Python design and tile
models, the materializer plans replacements, and the writer mutates the live pyosys
design.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
    ConfigValue,
    FfPortsInput,
    FfPortSpec,
    FfResetKind,
    ParamValue,
    SignalBit,
    normalize_ff_ports,
)

if TYPE_CHECKING:
    from pathlib import Path


class FfMaterializerDepthOption(BaseModel):
    """Describe one legal latency mode for a materializer lane.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    depth : int
        Number of netlist FFs this option consumes.
    mode_config : dict[str, ConfigValue]
        Config bits required to select this latency mode.
    """

    model_config = ConfigDict(frozen=True)

    depth: int = 1
    mode_config: dict[str, ConfigValue] = Field(default_factory=dict)

    @field_validator("depth")
    @classmethod
    def _validate_depth(cls, value: int) -> int:
        """Validate that lane depth is positive.

        Parameters
        ----------
        value : int
            User-provided depth.

        Returns
        -------
        int
            Validated depth.

        Raises
        ------
        ValueError
            If the depth is less than one.
        """
        if value < 1:
            raise ValueError("depth must be at least 1")
        return value


def _default_depth_options() -> tuple[FfMaterializerDepthOption, ...]:
    """Return the default single-FF depth option.

    Returns
    -------
    tuple[FfMaterializerDepthOption, ...]
        Default depth option tuple.
    """
    return (FfMaterializerDepthOption(depth=1),)


class FfMaterializerLane(BaseModel):
    """Describe one one-bit register lane inside the replacement tile.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    data_port : str
        Tile input port driven by the old FF data input.
    output_port : str
        Tile output port connected to the old FF output net.
    clock_port : str | None
        Optional tile clock port driven by the old FF clock.
    include_enable_ff : bool
        Whether variable-enable FFs may use this lane.
    enable_tile_port : str | None
        Optional tile enable port.
    enable_neutral : ConfigValue | None
        Constant used on ``enable_tile_port`` when the FF has no enable.
    include_reset_ff : bool
        Whether variable-reset FFs may use this lane.
    reset_tile_port : str | None
        Optional tile reset port.
    reset_neutral : ConfigValue | None
        Constant used on ``reset_tile_port`` when the FF has no reset.
    reset_kind : FfResetKind | None
        Optional reset timing required by the lane.
    reset_value : int | None
        Optional reset value required by the lane.
    depth_options : tuple[FfMaterializerDepthOption, ...]
        Legal latency modes for this lane.
    config : dict[str, ConfigValue]
        Tile config updates needed for this lane to act as an FF path.
    attributes : dict[str, ParamValue]
        Tile attribute updates needed for this lane.
    """

    model_config = ConfigDict(frozen=True)

    data_port: str
    output_port: str
    clock_port: str | None = None
    include_enable_ff: bool = False
    enable_tile_port: str | None = None
    enable_neutral: ConfigValue | None = None
    include_reset_ff: bool = False
    reset_tile_port: str | None = None
    reset_neutral: ConfigValue | None = None
    reset_kind: FfResetKind | None = None
    reset_value: int | None = None
    depth_options: tuple[FfMaterializerDepthOption, ...] = Field(
        default_factory=_default_depth_options
    )
    config: dict[str, ConfigValue] = Field(default_factory=dict)
    attributes: dict[str, ParamValue] = Field(default_factory=dict)

    @field_validator("reset_kind", mode="before")
    @classmethod
    def _coerce_reset_kind(cls, value: object) -> FfResetKind | None:
        """Coerce reset timing values into an enum.

        Parameters
        ----------
        value : object
            User-provided reset kind.

        Returns
        -------
        FfResetKind | None
            Normalized reset kind.
        """
        if value is None:
            return None
        return FfResetKind(value)

    @field_validator("depth_options", mode="before")
    @classmethod
    def _coerce_depth_options(cls, value: object) -> object:
        """Normalize missing depth options.

        Parameters
        ----------
        value : object
            User-provided depth option payload.

        Returns
        -------
        object
            Payload for pydantic's nested model validation.
        """
        if value is None:
            return list(_default_depth_options())
        return value

    @field_validator("depth_options")
    @classmethod
    def _validate_depth_options(
        cls,
        value: tuple[FfMaterializerDepthOption, ...],
    ) -> tuple[FfMaterializerDepthOption, ...]:
        """Validate depth option list.

        Parameters
        ----------
        value : tuple[FfMaterializerDepthOption, ...]
            Validated depth options.

        Returns
        -------
        tuple[FfMaterializerDepthOption, ...]
            Validated depth options.

        Raises
        ------
        ValueError
            If the option list is empty or contains duplicate depths.
        """
        if not value:
            raise ValueError("depth_options must contain at least one option")
        depths = [option.depth for option in value]
        if len(depths) != len(set(depths)):
            raise ValueError("depth_options cannot contain duplicate depths")
        return tuple(sorted(value, key=lambda option: option.depth, reverse=True))


@dataclass(frozen=True)
class FfMaterializerTileModel:
    """Describe the replacement tile used for FF materialization.

    Attributes
    ----------
    top_name : str
        Tile module name used as the replacement cell type.
    verilog_path : Path
        Verilog source that defines the replacement tile.
    blif_text : str
        BLIF emitted from the tile Verilog.
    inputs : tuple[str, ...]
        Scalar tile input ports that the materializer may connect.
    outputs : tuple[str, ...]
        Scalar tile output ports that the materializer may connect.
    config_bits : tuple[str, ...]
        Scalar configuration bits discovered from prefixes and explicit names.
    config_prefixes : tuple[str, ...]
        Prefixes used to classify tile inputs as configuration bits.
    """

    top_name: str
    verilog_path: Path
    blif_text: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    config_bits: tuple[str, ...]
    config_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class FfMaterializerCell:
    """Represent one netlist cell.

    Attributes
    ----------
    cell_id : str
        Cell instance name.
    cell_type : str
        Cell type without a leading Yosys escape backslash.
    parameters : dict[str, str]
        Existing parameter values.
    connections : dict[str, tuple[SignalBit, ...]]
        Port connections as stable string signal bits.
    port_directions : dict[str, str]
        Port direction metadata from the Yosys object model.
    """

    cell_id: str
    cell_type: str
    parameters: dict[str, str]
    connections: dict[str, tuple[SignalBit, ...]]
    port_directions: dict[str, str]


@dataclass(frozen=True)
class FfMaterializerDesign:
    """Internal design view for FF materialization.

    Attributes
    ----------
    top_name : str
        Top module name.
    cells : tuple[FfMaterializerCell, ...]
        Cells in stable reader order.
    """

    top_name: str
    cells: tuple[FfMaterializerCell, ...]


@dataclass(frozen=True)
class FfLaneBinding:
    """Bind one FF cell to one replacement tile lane.

    Attributes
    ----------
    ff_cell_id : str
        FF cell being replaced.
    ff_type : str
        FF cell type.
    lane_index : int
        Index of the selected lane.
    lane : FfMaterializerLane
        Selected lane configuration.
    depth_option : FfMaterializerDepthOption
        Selected latency mode for this binding.
    ff_cell_ids : tuple[str, ...]
        FF cells consumed by this binding in chain order.
    ff_types : tuple[str, ...]
        FF cell types consumed by this binding in chain order.
    ff_clock_port : str
        FF clock port name.
    ff_data_port : str
        FF data port name.
    ff_output_port : str
        FF output port name.
    ff_enable_port : str | None
        FF enable port when one is wired into the tile.
    ff_reset_port : str | None
        FF reset port when one is wired into the tile.
    ff_clock_bit : SignalBit
        FF clock signal bit.
    ff_data_bit : SignalBit
        FF data input signal bit.
    ff_output_bit : SignalBit
        FF output signal bit.
    ff_enable_bit : SignalBit | None
        FF enable signal bit when present.
    ff_reset_bit : SignalBit | None
        FF reset signal bit when present.
    """

    ff_cell_id: str
    ff_type: str
    lane_index: int
    lane: FfMaterializerLane
    depth_option: FfMaterializerDepthOption
    ff_cell_ids: tuple[str, ...]
    ff_types: tuple[str, ...]
    ff_clock_port: str
    ff_data_port: str
    ff_output_port: str
    ff_enable_port: str | None
    ff_reset_port: str | None
    ff_clock_bit: SignalBit
    ff_data_bit: SignalBit
    ff_output_bit: SignalBit
    ff_enable_bit: SignalBit | None
    ff_reset_bit: SignalBit | None


@dataclass(frozen=True)
class FfMaterialization:
    """One inserted replacement tile instance.

    Attributes
    ----------
    replacement_cell_id : str
        New tile instance name.
    tile_type : str
        Replacement tile module type.
    bindings : tuple[FfLaneBinding, ...]
        FF-to-lane bindings contained in this tile instance.
    config : dict[str, ConfigValue]
        Merged config updates for the replacement.
    attributes : dict[str, ParamValue]
        Merged attribute updates for the replacement.
    """

    replacement_cell_id: str
    tile_type: str
    bindings: tuple[FfLaneBinding, ...]
    config: dict[str, ConfigValue]
    attributes: dict[str, ParamValue]


@dataclass(frozen=True)
class FfMaterializerStats:
    """Summary counters for one FF materializer run.

    Attributes
    ----------
    ff_cells : int
        Supported FF cells considered.
    materialized_ffs : int
        FFs replaced by tile lanes.
    inserted_tiles : int
        Number of replacement tile instances inserted.
    skipped_no_lane : int
        FFs skipped because no lane was compatible.
    skipped_control_mismatch : int
        FFs skipped because enable/reset semantics were incompatible.
    skipped_config_conflict : int
        FFs skipped because packing would conflict on config or attributes.
    skipped_limit : int
        FFs skipped after ``max_replacements`` was reached.
    """

    ff_cells: int = 0
    materialized_ffs: int = 0
    inserted_tiles: int = 0
    skipped_no_lane: int = 0
    skipped_control_mismatch: int = 0
    skipped_config_conflict: int = 0
    skipped_limit: int = 0


@dataclass(frozen=True)
class FfMaterializerOptions:
    """Pass-level options used for one FF materialization run.

    Attributes
    ----------
    pack_multiple_ffs_per_tile : bool
        Whether multiple FFs may be packed into one replacement tile.
    auto_config : bool
        Whether SAT-fab solves replacement tile config for identity paths.
    auto_config_overwrites : dict[str, ConfigValue]
        Fixed config constraints used when auto-config is enabled.
    max_replacements : int | None
        Optional cap on materialized FFs.
    fail_on_invalid_lane : bool
        Whether invalid lanes/config references raise instead of being skipped.
    fail_on_auto_config_unsat : bool
        Whether an unsatisfied auto-config group raises instead of skipping.
    fail_on_pack_conflict : bool
        Whether config, attribute, or shared-port packing conflicts raise.
    fail_on_unmaterialized_ff : bool
        Whether any remaining supported FF raises after planning.
    progress_chunk_size : int
        Number of FFs between progress messages.
    """

    pack_multiple_ffs_per_tile: bool
    auto_config: bool
    auto_config_overwrites: dict[str, ConfigValue]
    max_replacements: int | None
    fail_on_invalid_lane: bool
    fail_on_auto_config_unsat: bool
    fail_on_pack_conflict: bool
    fail_on_unmaterialized_ff: bool
    progress_chunk_size: int


@dataclass(frozen=True)
class FfMaterializerResult:
    """Result of FF materialization.

    Attributes
    ----------
    top_name : str
        Processed top module.
    tile : FfMaterializerTileModel
        Replacement tile model.
    lanes : tuple[FfMaterializerLane, ...]
        Normalized lane definitions.
    ff_ports : dict[str, FfPortSpec]
        Supported FF cell types.
    options : FfMaterializerOptions
        Pass-level options used for this run.
    materializations : tuple[FfMaterialization, ...]
        Planned and applied materializations.
    stats : FfMaterializerStats
        Summary counters.
    report_summary : str
        Human-readable report.
    """

    top_name: str
    tile: FfMaterializerTileModel
    lanes: tuple[FfMaterializerLane, ...]
    ff_ports: dict[str, FfPortSpec]
    options: FfMaterializerOptions
    materializations: tuple[FfMaterialization, ...]
    stats: FfMaterializerStats
    report_summary: str = ""


LaneInput = FfMaterializerLane | dict[str, object]
FfPortsInputAlias = FfPortsInput
ResetKindLiteral = Literal["sync", "async"]


@dataclass
class MutableStats:
    """Mutable counter container used while planning."""

    ff_cells: int = 0
    materialized_ffs: int = 0
    inserted_tiles: int = 0
    skipped_no_lane: int = 0
    skipped_control_mismatch: int = 0
    skipped_config_conflict: int = 0
    skipped_limit: int = 0

    def frozen(self) -> FfMaterializerStats:
        """Return an immutable snapshot.

        Returns
        -------
        FfMaterializerStats
            Immutable stats object.
        """
        return FfMaterializerStats(**self.__dict__)


def normalize_lanes(lanes: list[LaneInput]) -> tuple[FfMaterializerLane, ...]:
    """Normalize lane payloads into pydantic models.

    Parameters
    ----------
    lanes : list[LaneInput]
        User-provided lanes.

    Returns
    -------
    tuple[FfMaterializerLane, ...]
        Validated lanes.

    Raises
    ------
    ValueError
        When a lane contains invalid keys or an ``auto_config`` key is found.
    """
    normalized = []
    for lane in lanes:
        if isinstance(lane, dict) and "auto_config" in lane:
            raise ValueError(
                "auto_config is a pass-level option; remove it from lane definitions"
            )
        normalized.append(
            lane
            if isinstance(lane, FfMaterializerLane)
            else FfMaterializerLane.model_validate(lane)
        )
    return tuple(normalized)


def split_indexed_name(name: str) -> tuple[str, int | None]:
    """Split ``Port[3]`` style names.

    Parameters
    ----------
    name : str
        Scalar or indexed port name.

    Returns
    -------
    tuple[str, int | None]
        Base name and optional index.
    """
    if not name.endswith("]") or "[" not in name:
        return name, None
    base, raw_index = name.rsplit("[", 1)
    return base, int(raw_index[:-1])


def one_bit(connection: tuple[SignalBit, ...] | None) -> SignalBit | None:
    """Return a single-bit connection if present.

    Parameters
    ----------
    connection : tuple[SignalBit, ...] | None
        Port connection.

    Returns
    -------
    SignalBit | None
        Signal bit when the connection is exactly one bit.
    """
    if connection is None or len(connection) != 1:
        return None
    return connection[0]


def normalize_ports(ff_ports: FfPortsInput | None) -> dict[str, FfPortSpec]:
    """Normalize supported FF port definitions.

    Parameters
    ----------
    ff_ports : FfPortsInput | None
        User-provided FF port mapping. ``None`` selects defaults.

    Returns
    -------
    dict[str, FfPortSpec]
        Validated FF port mapping.
    """
    return normalize_ff_ports(ff_ports)


def count_materializations_by_size(
    materializations: tuple[FfMaterialization, ...],
) -> dict[str, int]:
    """Count replacement tile instances by number of occupied lanes.

    Parameters
    ----------
    materializations : tuple[FfMaterialization, ...]
        Planned materializations.

    Returns
    -------
    dict[str, int]
        Lane-count label to replacement count.
    """
    counts: dict[str, int] = {}
    for materialization in materializations:
        label = str(len(materialization.bindings))
        counts[label] = counts.get(label, 0) + 1
    return counts


def count_bindings_by_depth(
    materializations: tuple[FfMaterialization, ...],
) -> dict[str, int]:
    """Count materialized chain chunks by selected depth.

    Parameters
    ----------
    materializations : tuple[FfMaterialization, ...]
        Planned materializations.

    Returns
    -------
    dict[str, int]
        Depth label to binding count.
    """
    counts: dict[str, int] = {}
    for materialization in materializations:
        for binding in materialization.bindings:
            label = str(binding.depth_option.depth)
            counts[label] = counts.get(label, 0) + 1
    return counts
