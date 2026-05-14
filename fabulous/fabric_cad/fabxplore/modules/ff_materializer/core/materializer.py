"""Plan and apply FF materialization rewrites."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.models import (
    FfLaneBinding,
    FfMaterialization,
    FfMaterializerCell,
    FfMaterializerDesign,
    FfMaterializerLane,
    FfMaterializerResult,
    FfPortsInputAlias,
    LaneInput,
    MutableStats,
    normalize_lanes,
    normalize_ports,
    one_bit,
    split_indexed_name,
)
from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.process_tracker import (
    FfMaterializerProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.reader import (
    FfMaterializerReader,
)
from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.report import (
    render_ff_materializer_report,
)
from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.writer import (
    FfMaterializerWriter,
)
from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
    ConfigValue,
    FfPortSpec,
    FfRequiredPortValue,
    ParamValue,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class FfMaterializer:
    """Replace standalone one-bit FFs with configured tile register lanes.

    Parameters
    ----------
    tile_verilog_path : Path
        Verilog file containing the replacement tile.
    tile_top_name : str
        Replacement tile module name.
    tile_inputs : list[str]
        Scalar tile input ports exposed to the pass.
    tile_outputs : list[str]
        Scalar tile output ports exposed to the pass.
    lanes : list[LaneInput]
        Register lanes available inside the tile.
    tile_configs : list[str] | None
        Explicit scalar tile config bits.
    tile_config_prefixes : list[str] | None
        Prefixes used to discover tile config bits from BLIF inputs.
    ff_ports : FfPortsInputAlias | None
        Supported FF port descriptions. ``None`` selects default FF types.
    pack_multiple_ffs_per_tile : bool
        Whether multiple lanes may be filled in one replacement tile instance.
    max_replacements : int | None
        Optional cap on replaced FFs.
    strict : bool
        Whether skipped invalid matches should raise.
    track_progress : bool
        Whether to emit progress messages.
    progress_chunk_size : int
        Number of processed FFs between progress updates.
    """

    def __init__(
        self,
        tile_verilog_path: Path,
        tile_top_name: str,
        tile_inputs: list[str],
        tile_outputs: list[str],
        lanes: list[LaneInput],
        tile_configs: list[str] | None = None,
        tile_config_prefixes: list[str] | None = None,
        ff_ports: FfPortsInputAlias | None = None,
        pack_multiple_ffs_per_tile: bool = True,
        max_replacements: int | None = None,
        strict: bool = False,
        track_progress: bool = True,
        progress_chunk_size: int = 100,
    ) -> None:
        self.tile = FfMaterializerReader().read_tile_model(
            verilog_path=tile_verilog_path,
            top_name=tile_top_name,
            inputs=tile_inputs,
            outputs=tile_outputs,
            configs=tile_configs,
            config_prefixes=tile_config_prefixes,
        )
        self.lanes = normalize_lanes(lanes)
        self.ff_ports = normalize_ports(ff_ports)
        self.pack_multiple_ffs_per_tile = pack_multiple_ffs_per_tile
        self.max_replacements = max_replacements
        self.strict = strict
        self._tracker = FfMaterializerProcessTracker(
            enabled=track_progress,
            chunk_size=progress_chunk_size,
        )
        self._validate_lanes()

    def map_from_design(
        self,
        design: PyosysBridge,
        top_name: str | None = None,
    ) -> FfMaterializerResult:
        """Plan and apply FF materialization to a live design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        top_name : str | None
            Top module to process. ``None`` uses the current design top.

        Returns
        -------
        FfMaterializerResult
            Applied materialization result.
        """
        selected_top = top_name or design.top_name()
        ff_design = FfMaterializerReader().read_design(design, selected_top)
        result = self.plan(ff_design)
        FfMaterializerWriter(tile=self.tile).apply(design, result)
        return result

    def plan(self, design: FfMaterializerDesign) -> FfMaterializerResult:
        """Build a pure-Python materialization plan.

        Parameters
        ----------
        design : FfMaterializerDesign
            Internal design view.

        Returns
        -------
        FfMaterializerResult
            Planned materialization result.
        """
        ff_cells = [cell for cell in design.cells if cell.cell_type in self.ff_ports]
        stats = MutableStats(ff_cells=len(ff_cells))
        self._tracker.start(len(ff_cells))

        materializations: list[FfMaterialization] = []
        current = _OpenMaterialization(index=0)
        materialized_count = 0
        for ff in ff_cells:
            if (
                self.max_replacements is not None
                and materialized_count >= self.max_replacements
            ):
                stats.skipped_limit += 1
                self._tracker.record(
                    materialized=False,
                    inserted_tiles=len(materializations),
                )
                continue

            binding = self._try_ff_in_group(ff=ff, group=current, stats=stats)
            if binding is None and self.pack_multiple_ffs_per_tile and current.bindings:
                materializations.append(current.freeze(self.tile.top_name))
                current = _OpenMaterialization(index=len(materializations))
                binding = self._try_ff_in_group(ff=ff, group=current, stats=stats)

            if binding is None:
                self._tracker.record(
                    materialized=False,
                    inserted_tiles=len(materializations),
                )
                continue

            materialized_count += 1
            if not self.pack_multiple_ffs_per_tile:
                materializations.append(current.freeze(self.tile.top_name))
                current = _OpenMaterialization(index=len(materializations))
            self._tracker.record(
                materialized=True,
                inserted_tiles=len(materializations) + bool(current.bindings),
            )

        if current.bindings:
            materializations.append(current.freeze(self.tile.top_name))
        stats.materialized_ffs = materialized_count
        stats.inserted_tiles = len(materializations)
        self._tracker.done()

        result = FfMaterializerResult(
            top_name=design.top_name,
            tile=self.tile,
            lanes=self.lanes,
            ff_ports=self.ff_ports,
            materializations=tuple(materializations),
            stats=stats.frozen(),
        )
        return replace(result, report_summary=render_ff_materializer_report(result))

    def _validate_lanes(self) -> None:
        """Validate lane port and config references against the tile model.

        Raises
        ------
        RuntimeError
            If a lane references a tile port or config bit that is not exposed.
        """
        inputs = set(self.tile.inputs)
        outputs = set(self.tile.outputs)
        config_bits = set(self.tile.config_bits)
        config_prefixes = set(self.tile.config_prefixes)
        for index, lane in enumerate(self.lanes):
            for port in _lane_input_ports(lane):
                if port not in inputs:
                    raise RuntimeError(
                        f"Lane {index} input port '{port}' is not exposed"
                    )
            if lane.output_port not in outputs:
                raise RuntimeError(
                    f"Lane {index} output port '{lane.output_port}' is not exposed"
                )
            for name in lane.config:
                base, bit_index = split_indexed_name(name)
                if bit_index is None:
                    if name not in config_bits and name not in config_prefixes:
                        raise RuntimeError(f"Lane {index} config '{name}' is unknown")
                elif name not in config_bits:
                    raise RuntimeError(f"Lane {index} config bit '{name}' is unknown")

    def _try_ff_in_group(
        self,
        ff: FfMaterializerCell,
        group: _OpenMaterialization,
        stats: MutableStats,
    ) -> FfLaneBinding | None:
        """Try to bind one FF to any free lane in ``group``.

        Parameters
        ----------
        ff : FfMaterializerCell
            FF candidate.
        group : _OpenMaterialization
            Open replacement tile group.
        stats : MutableStats
            Mutable stats counters.

        Returns
        -------
        FfLaneBinding | None
            Binding if a compatible lane exists.
        """
        saw_control_mismatch = False
        saw_config_conflict = False
        for index, lane in enumerate(self.lanes):
            if index in group.used_lanes:
                continue
            outcome = self._build_binding(ff=ff, lane=lane, lane_index=index)
            if outcome.reason == _RejectReason.CONTROL:
                saw_control_mismatch = True
                continue
            if outcome.binding is None:
                continue
            if not group.can_add(outcome.binding):
                saw_config_conflict = True
                continue
            group.add(outcome.binding)
            return outcome.binding
        if saw_config_conflict:
            stats.skipped_config_conflict += 1
            self._maybe_raise(
                f"Config or port conflict while packing FF '{ff.cell_id}'"
            )
        elif saw_control_mismatch:
            stats.skipped_control_mismatch += 1
        else:
            stats.skipped_no_lane += 1
        return None

    def _build_binding(
        self,
        ff: FfMaterializerCell,
        lane: FfMaterializerLane,
        lane_index: int,
    ) -> _BindingOutcome:
        """Build a lane binding if one FF is compatible.

        Parameters
        ----------
        ff : FfMaterializerCell
            FF candidate.
        lane : FfMaterializerLane
            Candidate lane.
        lane_index : int
            Candidate lane index.

        Returns
        -------
        _BindingOutcome
            Binding or rejection reason.
        """
        spec = self.ff_ports[ff.cell_type]
        ff_clock = one_bit(ff.connections.get(spec.clock))
        ff_data = one_bit(ff.connections.get(spec.data))
        ff_output = one_bit(ff.connections.get(spec.output))
        if ff_clock is None or ff_data is None or ff_output is None:
            return _BindingOutcome(reason=_RejectReason.NO_LANE)
        if not _required_ff_ports_match(ff, spec):
            return _BindingOutcome(reason=_RejectReason.CONTROL)
        if not _enable_is_compatible(ff, spec, lane):
            return _BindingOutcome(reason=_RejectReason.CONTROL)
        if not _reset_is_compatible(ff, spec, lane):
            return _BindingOutcome(reason=_RejectReason.CONTROL)
        return _BindingOutcome(
            binding=FfLaneBinding(
                ff_cell_id=ff.cell_id,
                ff_type=ff.cell_type,
                lane_index=lane_index,
                lane=lane,
                ff_clock_port=spec.clock,
                ff_data_port=spec.data,
                ff_output_port=spec.output,
                ff_enable_port=spec.enable_port
                if _has_control_port(ff, spec.enable_port)
                else None,
                ff_reset_port=spec.reset_port
                if _has_control_port(ff, spec.reset_port)
                else None,
                ff_clock_bit=ff_clock,
                ff_data_bit=ff_data,
                ff_output_bit=ff_output,
                ff_enable_bit=one_bit(ff.connections.get(spec.enable_port))
                if spec.enable_port is not None
                else None,
                ff_reset_bit=one_bit(ff.connections.get(spec.reset_port))
                if spec.reset_port is not None
                else None,
            )
        )

    def _maybe_raise(self, message: str) -> None:
        """Raise in strict mode.

        Parameters
        ----------
        message : str
            Error text.

        Raises
        ------
        RuntimeError
            If strict mode is enabled.
        """
        if self.strict:
            raise RuntimeError(message)


@dataclass
class _OpenMaterialization:
    """Mutable replacement tile group used during packing."""

    index: int
    bindings: list[FfLaneBinding] = field(default_factory=list)
    config: dict[str, ConfigValue] = field(default_factory=dict)
    params: dict[str, ParamValue] = field(default_factory=dict)
    port_sources: dict[str, tuple[str, ...]] = field(default_factory=dict)
    used_lanes: set[int] = field(default_factory=set)

    def can_add(self, binding: FfLaneBinding) -> bool:
        """Return whether a binding can be packed into this group.

        Parameters
        ----------
        binding : FfLaneBinding
            Candidate lane binding.

        Returns
        -------
        bool
            ``True`` if no lane, config, param, or shared-port conflict exists.
        """
        if binding.lane_index in self.used_lanes:
            return False
        if _updates_conflict(self.config, binding.lane.config):
            return False
        if _updates_conflict(self.params, binding.lane.params):
            return False
        for port, source in _binding_port_sources(binding).items():
            if port in self.port_sources and self.port_sources[port] != source:
                return False
        return True

    def add(self, binding: FfLaneBinding) -> None:
        """Add a compatible binding.

        Parameters
        ----------
        binding : FfLaneBinding
            Binding to add.
        """
        self.bindings.append(binding)
        self.used_lanes.add(binding.lane_index)
        self.config.update(binding.lane.config)
        self.params.update(binding.lane.params)
        self.port_sources.update(_binding_port_sources(binding))

    def freeze(self, tile_type: str) -> FfMaterialization:
        """Return an immutable materialization.

        Parameters
        ----------
        tile_type : str
            Replacement tile module type.

        Returns
        -------
        FfMaterialization
            Frozen replacement plan.
        """
        return FfMaterialization(
            replacement_cell_id=f"__ff_materialized_pack_{self.index}",
            tile_type=tile_type,
            bindings=tuple(self.bindings),
            config=dict(self.config),
            params=dict(self.params),
        )


@dataclass(frozen=True)
class _BindingOutcome:
    """Outcome of one FF/lane compatibility check."""

    binding: FfLaneBinding | None = None
    reason: _RejectReason | None = None


class _RejectReason:
    """Internal lane rejection labels."""

    NO_LANE = "no_lane"
    CONTROL = "control"


def _lane_input_ports(lane: FfMaterializerLane) -> tuple[str, ...]:
    """Return tile input ports referenced by one lane.

    Parameters
    ----------
    lane : FfMaterializerLane
        Lane to inspect.

    Returns
    -------
    tuple[str, ...]
        Referenced input ports.
    """
    return tuple(
        port
        for port in (
            lane.data_port,
            lane.clock_port,
            lane.enable_tile_port,
            lane.reset_tile_port,
        )
        if port is not None
    )


def _binding_port_sources(binding: FfLaneBinding) -> dict[str, tuple[str, ...]]:
    """Return shared tile-port source signatures for one binding.

    Parameters
    ----------
    binding : FfLaneBinding
        Lane binding.

    Returns
    -------
    dict[str, tuple[str, ...]]
        Tile input port to source signature.
    """
    lane = binding.lane
    sources = {
        lane.data_port: ("signal", binding.ff_data_bit),
    }
    if lane.clock_port is not None:
        sources[lane.clock_port] = ("signal", binding.ff_clock_bit)
    if lane.enable_tile_port is not None:
        sources[lane.enable_tile_port] = (
            ("signal", binding.ff_enable_bit)
            if binding.ff_enable_port is not None
            else ("const", str(int(bool(lane.enable_neutral))))
        )
    if lane.reset_tile_port is not None:
        sources[lane.reset_tile_port] = (
            ("signal", binding.ff_reset_bit)
            if binding.ff_reset_port is not None
            else ("const", str(int(bool(lane.reset_neutral))))
        )
    return sources


def _updates_conflict(
    known: dict[str, ConfigValue | ParamValue],
    updates: dict[str, ConfigValue | ParamValue],
) -> bool:
    """Return whether new updates conflict with planned updates.

    Parameters
    ----------
    known : dict[str, ConfigValue | ParamValue]
        Already planned values.
    updates : dict[str, ConfigValue | ParamValue]
        New requested values.

    Returns
    -------
    bool
        ``True`` if any key is requested with a different value.
    """
    return any(
        name in known and known[name] != value for name, value in updates.items()
    )


def _required_ff_ports_match(ff: FfMaterializerCell, spec: FfPortSpec) -> bool:
    """Return whether FF required ports are statically compatible.

    Parameters
    ----------
    ff : FfMaterializerCell
        FF cell being considered.
    spec : FfPortSpec
        Port and control-port description.

    Returns
    -------
    bool
        ``True`` if every required control port has a matching constant.
    """
    for port, requirement in spec.required_ports.items():
        bit = one_bit(ff.connections.get(port))
        if bit not in {"0", "1"}:
            return False
        expected = _expected_control_bit(ff, spec, port, requirement)
        if expected is None or bit != expected:
            return False
    return True


def _enable_is_compatible(
    ff: FfMaterializerCell,
    spec: FfPortSpec,
    lane: FfMaterializerLane,
) -> bool:
    """Return whether an FF enable can use ``lane``.

    Parameters
    ----------
    ff : FfMaterializerCell
        FF cell being considered.
    spec : FfPortSpec
        FF port description.
    lane : FfMaterializerLane
        Candidate tile lane.

    Returns
    -------
    bool
        ``True`` if the enable is absent, neutral, or explicitly allowed.
    """
    if spec.enable_port is None or not _has_control_port(ff, spec.enable_port):
        return lane.enable_tile_port is None or lane.enable_neutral is not None
    if lane.include_enable_ff:
        return True
    bit = one_bit(ff.connections.get(spec.enable_port))
    return bit == _expected_polarity_bit(ff, spec.enable_polarity_param, active=True)


def _reset_is_compatible(
    ff: FfMaterializerCell,
    spec: FfPortSpec,
    lane: FfMaterializerLane,
) -> bool:
    """Return whether an FF reset can use ``lane``.

    Parameters
    ----------
    ff : FfMaterializerCell
        FF cell being considered.
    spec : FfPortSpec
        FF port description.
    lane : FfMaterializerLane
        Candidate tile lane.

    Returns
    -------
    bool
        ``True`` if the reset is absent, neutral, or explicitly allowed.
    """
    if spec.reset_port is None or not _has_control_port(ff, spec.reset_port):
        return lane.reset_tile_port is None or lane.reset_neutral is not None
    if not lane.include_reset_ff:
        bit = one_bit(ff.connections.get(spec.reset_port))
        return bit == _expected_polarity_bit(
            ff,
            spec.reset_polarity_param,
            active=False,
        )
    if lane.reset_kind is not None and spec.reset_kind != lane.reset_kind:
        return False
    if lane.reset_value is not None and spec.reset_value_param is not None:
        ff_reset_value = _parameter_int(ff, spec.reset_value_param)
        if ff_reset_value is None or ff_reset_value != lane.reset_value:
            return False
    return True


def _has_control_port(ff: FfMaterializerCell, port: str | None) -> bool:
    """Return whether a control port has a one-bit connection.

    Parameters
    ----------
    ff : FfMaterializerCell
        FF cell being considered.
    port : str | None
        Optional control port name.

    Returns
    -------
    bool
        ``True`` when the port exists and is one bit wide.
    """
    return port is not None and one_bit(ff.connections.get(port)) is not None


def _expected_control_bit(
    ff: FfMaterializerCell,
    spec: FfPortSpec,
    port: str,
    requirement: int | bool | FfRequiredPortValue,
) -> str | None:
    """Return expected constant bit for one FF control requirement.

    Parameters
    ----------
    ff : FfMaterializerCell
        FF cell being considered.
    spec : FfPortSpec
        Port and control-port description.
    port : str
        Control port name.
    requirement : int | bool | FfRequiredPortValue
        Required value.

    Returns
    -------
    str | None
        Expected ``"0"`` or ``"1"`` bit.
    """
    if isinstance(requirement, FfRequiredPortValue):
        polarity = _parameter_bool(ff, spec.polarity_params.get(port))
        if polarity is None:
            return None
        active_value = "1" if polarity else "0"
        inactive_value = "0" if polarity else "1"
        if requirement == FfRequiredPortValue.ACTIVE:
            return active_value
        return inactive_value
    return "1" if bool(requirement) else "0"


def _expected_polarity_bit(
    ff: FfMaterializerCell,
    parameter_name: str | None,
    active: bool,
) -> str | None:
    """Return the active or inactive constant for a polarity parameter.

    Parameters
    ----------
    ff : FfMaterializerCell
        FF cell being considered.
    parameter_name : str | None
        Polarity parameter name.
    active : bool
        Whether to return the active or inactive value.

    Returns
    -------
    str | None
        Expected constant bit.
    """
    polarity = _parameter_bool(ff, parameter_name)
    if polarity is None:
        return None
    active_value = "1" if polarity else "0"
    inactive_value = "0" if polarity else "1"
    return active_value if active else inactive_value


def _parameter_bool(
    ff: FfMaterializerCell,
    parameter_name: str | None,
) -> bool | None:
    """Parse one boolean parameter.

    Parameters
    ----------
    ff : FfMaterializerCell
        FF cell being considered.
    parameter_name : str | None
        Parameter name.

    Returns
    -------
    bool | None
        Parsed value if available.
    """
    if parameter_name is None or parameter_name not in ff.parameters:
        return None
    raw = ff.parameters[parameter_name]
    if raw in {"1", "1'1", "1'h1", "1'b1", "true", "True"}:
        return True
    if raw in {"0", "1'0", "1'h0", "1'b0", "false", "False"}:
        return False
    try:
        return bool(int(raw, 0))
    except ValueError:
        return None


def _parameter_int(ff: FfMaterializerCell, parameter_name: str) -> int | None:
    """Parse one integer parameter.

    Parameters
    ----------
    ff : FfMaterializerCell
        FF cell being considered.
    parameter_name : str
        Parameter name.

    Returns
    -------
    int | None
        Parsed value if available.
    """
    if parameter_name not in ff.parameters:
        return None
    raw = ff.parameters[parameter_name]
    try:
        return int(raw, 0)
    except ValueError:
        if "'b" in raw:
            return int(raw.split("'b", 1)[1], 2)
        if "'h" in raw:
            return int(raw.split("'h", 1)[1], 16)
    return None
