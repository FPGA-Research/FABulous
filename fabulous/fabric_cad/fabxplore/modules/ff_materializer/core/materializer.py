"""Plan and apply FF materialization rewrites."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.models import (
    FfLaneBinding,
    FfMaterialization,
    FfMaterializerCell,
    FfMaterializerDesign,
    FfMaterializerLane,
    FfMaterializerOptions,
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
from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.tile_compiler import (
    FfMaterializerTileCompiler,
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
from fabulous.fabric_cad.fabxplore.modules.sat_fab.cegis import Equiv
from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import Circuit
from fabulous.fabric_cad.fabxplore.modules.sat_fab.functions import Func

if TYPE_CHECKING:
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
    auto_config : bool
        Whether SAT-fab should solve one shared identity-path config for each
        materialized lane set.
    auto_config_overwrites : dict[str, ConfigValue] | None
        Optional fixed config bits applied as constraints when ``auto_config``
        is enabled. These values override SAT choices in the emitted tile.
    max_replacements : int | None
        Optional cap on replaced FFs.
    fail_on_invalid_lane : bool
        Whether invalid lane definitions should raise instead of being ignored.
    fail_on_auto_config_unsat : bool
        Whether unsatisfiable auto-config attempts should raise.
    fail_on_pack_conflict : bool
        Whether config, parameter, or shared-port packing conflicts should raise.
    fail_on_unmaterialized_ff : bool
        Whether any supported FF left unreplaced should raise.
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
        auto_config: bool = False,
        auto_config_overwrites: dict[str, ConfigValue] | None = None,
        max_replacements: int | None = None,
        fail_on_invalid_lane: bool = True,
        fail_on_auto_config_unsat: bool = False,
        fail_on_pack_conflict: bool = False,
        fail_on_unmaterialized_ff: bool = False,
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
        self.auto_config = auto_config
        self.auto_config_overwrites = dict(auto_config_overwrites or {})
        self._auto_config_cache: dict[_AutoConfigKey, dict[str, ConfigValue] | None]
        self._auto_config_cache = {}
        self.max_replacements = max_replacements
        self.fail_on_invalid_lane = fail_on_invalid_lane
        self.fail_on_auto_config_unsat = fail_on_auto_config_unsat
        self.fail_on_pack_conflict = fail_on_pack_conflict
        self.fail_on_unmaterialized_ff = fail_on_unmaterialized_ff
        self._tracker = FfMaterializerProcessTracker(
            enabled=track_progress,
            chunk_size=progress_chunk_size,
        )
        self._validate_lanes()
        self._validate_auto_config()

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

        Raises
        ------
        RuntimeError
            If ``fail_on_unmaterialized_ff`` is set and any supported FFs are left
            unreplaced.
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
        if self.fail_on_unmaterialized_ff and materialized_count != len(ff_cells):
            skipped = len(ff_cells) - materialized_count
            raise RuntimeError(
                "FF materialization left supported FFs unreplaced: "
                f"materialized={materialized_count}, skipped={skipped}, "
                f"total={len(ff_cells)}"
            )

        result = FfMaterializerResult(
            top_name=design.top_name,
            tile=self.tile,
            lanes=self.lanes,
            ff_ports=self.ff_ports,
            options=FfMaterializerOptions(
                pack_multiple_ffs_per_tile=self.pack_multiple_ffs_per_tile,
                auto_config=self.auto_config,
                auto_config_overwrites=dict(self.auto_config_overwrites),
                max_replacements=self.max_replacements,
                fail_on_invalid_lane=self.fail_on_invalid_lane,
                fail_on_auto_config_unsat=self.fail_on_auto_config_unsat,
                fail_on_pack_conflict=self.fail_on_pack_conflict,
                fail_on_unmaterialized_ff=self.fail_on_unmaterialized_ff,
                progress_chunk_size=self._tracker.chunk_size,
            ),
            materializations=tuple(materializations),
            stats=stats.frozen(),
        )
        return replace(result, report_summary=render_ff_materializer_report(result))

    def _validate_lanes(self) -> None:
        """Validate lane port and config references against the tile model.

        Raises
        ------
        RuntimeError
            If an invalid lane is found and ``fail_on_invalid_lane`` is set.
        """
        valid_lanes: list[FfMaterializerLane] = []
        inputs = set(self.tile.inputs)
        outputs = set(self.tile.outputs)
        config_bits = set(self.tile.config_bits)
        config_prefixes = set(self.tile.config_prefixes)
        for index, lane in enumerate(self.lanes):
            invalid_reason = None
            for port in _lane_input_ports(lane):
                if port not in inputs:
                    invalid_reason = f"Lane {index} input port '{port}' is not exposed"
                    break
            if invalid_reason is None and lane.output_port not in outputs:
                invalid_reason = (
                    f"Lane {index} output port '{lane.output_port}' is not exposed"
                )
            if invalid_reason is None:
                invalid_reason = _invalid_lane_config_reason(
                    index=index,
                    lane=lane,
                    config_bits=config_bits,
                    config_prefixes=config_prefixes,
                )
            if invalid_reason is not None:
                if self.fail_on_invalid_lane:
                    raise RuntimeError(invalid_reason)
                continue
            valid_lanes.append(lane)
        self.lanes = tuple(valid_lanes)
        _validate_shared_control_settings(self.lanes)

    def _validate_auto_config(self) -> None:
        """Validate global auto-config settings.

        ``auto_config`` solves one shared config for a full packed lane set.
        Lane-local config would make that ambiguous, so fixed config bits must
        be provided through ``auto_config_overwrites`` instead.

        Raises
        ------
        RuntimeError
            If global auto-config settings are inconsistent and
            ``fail_on_invalid_lane`` is set.
        """
        if not self.auto_config:
            return
        valid_lanes: list[FfMaterializerLane] = []
        for index, lane in enumerate(self.lanes):
            if lane.config:
                message = (
                    f"Lane {index} config is not allowed when auto_config=True; "
                    "use auto_config_overwrites for fixed config constraints"
                )
                if self.fail_on_invalid_lane:
                    raise RuntimeError(message)
                continue
            valid_lanes.append(lane)
        self.lanes = tuple(valid_lanes)
        for index, lane in enumerate(self.lanes):
            if lane.enable_tile_port is not None and lane.enable_neutral is None:
                message = (
                    f"Lane {index} enable_neutral is required when "
                    "auto_config=True and enable_tile_port is set"
                )
                if self.fail_on_invalid_lane:
                    raise RuntimeError(message)
                continue
            if lane.reset_tile_port is not None and lane.reset_neutral is None:
                message = (
                    f"Lane {index} reset_neutral is required when "
                    "auto_config=True and reset_tile_port is set"
                )
                if self.fail_on_invalid_lane:
                    raise RuntimeError(message)
                continue
        config_bits = set(self.tile.config_bits)
        config_prefixes = set(self.tile.config_prefixes)
        valid_overwrites: dict[str, ConfigValue] = {}
        for name, value in self.auto_config_overwrites.items():
            invalid_reason = _invalid_config_name_reason(
                name=name,
                label="auto_config_overwrite",
                config_bits=config_bits,
                config_prefixes=config_prefixes,
            )
            if invalid_reason is not None:
                if self.fail_on_invalid_lane:
                    raise RuntimeError(invalid_reason)
                continue
            valid_overwrites[name] = value
        self.auto_config_overwrites = valid_overwrites

    def _solve_group_auto_config(
        self,
        bindings: tuple[FfLaneBinding, ...],
    ) -> dict[str, ConfigValue] | None:
        """Find a shared config implementing all lane identities.

        Parameters
        ----------
        bindings : tuple[FfLaneBinding, ...]
            Bindings that would occupy one replacement tile.

        Returns
        -------
        dict[str, ConfigValue] | None
            SAT-found config bits, or ``None`` when no shared solution exists.
        """
        fixed_controls = _neutral_controls_for_bindings(bindings)
        key = _AutoConfigKey.from_bindings(
            bindings,
            self.auto_config_overwrites,
            fixed_controls,
        )
        if key in self._auto_config_cache:
            cached = self._auto_config_cache[key]
            return dict(cached) if cached is not None else None
        input_ports = tuple(
            dict.fromkeys(binding.lane.data_port for binding in bindings)
        )
        output_ports = tuple(binding.lane.output_port for binding in bindings)
        with TemporaryDirectory(prefix="ff_materializer_auto_config_") as td:
            blif_path = Path(td) / "tile.blif"
            self._write_auto_config_blif(blif_path, fixed_controls)
            candidate = Circuit.from_blif(
                blif_path,
                top=self.tile.top_name,
                inputs=list(self.tile.inputs),
                configs=list(self.tile.config_bits),
                outputs=list(output_ports),
                sequential_mode="passthrough",
            )
        target = Circuit.truth_table(
            name="ff_materializer_auto_config",
            inputs=list(input_ports),
            outputs={
                binding.lane.output_port: Func.var(binding.lane.data_port)
                for binding in bindings
            },
        )
        problem = Equiv.check(target, candidate).match_inputs_by_name()
        if self.auto_config_overwrites:
            problem.fix_config(candidate, self.auto_config_overwrites)
        result = problem.solve()
        if not result.sat:
            self._auto_config_cache[key] = None
            return None
        config = result.config_for(candidate)
        solved: dict[str, ConfigValue] = {}
        for name in candidate.config_names():
            value = config.external_value(name)
            if value is not None:
                solved[name] = bool(value)
        for name, value in self.auto_config_overwrites.items():
            solved[name] = bool(value)
        self._auto_config_cache[key] = dict(solved)
        return solved

    def _write_auto_config_blif(
        self,
        blif_path: Path,
        fixed_controls: dict[str, ConfigValue],
    ) -> None:
        """Write the candidate BLIF used for an auto-config SAT solve.

        Parameters
        ----------
        blif_path : Path
            Destination BLIF path.
        fixed_controls : dict[str, ConfigValue]
            Tile control input ports that should be tied to neutral values
            before importing the BLIF into SAT-fab.
        """
        if not fixed_controls:
            blif_path.write_text(self.tile.blif_text, encoding="utf-8")
            return
        FfMaterializerTileCompiler().write_blif_path(
            verilog_path=self.tile.verilog_path,
            top_name=self.tile.top_name,
            blif_path=blif_path,
            fixed_ports=fixed_controls,
        )

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
            config_override = self._config_for_group_add(group, outcome.binding, ff)
            if config_override is None:
                saw_config_conflict = True
                continue
            group.add(outcome.binding, config_override=config_override)
            return outcome.binding
        if saw_config_conflict:
            stats.skipped_config_conflict += 1
        elif saw_control_mismatch:
            stats.skipped_control_mismatch += 1
        else:
            stats.skipped_no_lane += 1
        return None

    def _config_for_group_add(
        self,
        group: _OpenMaterialization,
        binding: FfLaneBinding,
        ff: FfMaterializerCell,
    ) -> dict[str, ConfigValue] | None:
        """Return the config that permits adding ``binding`` to ``group``.

        Parameters
        ----------
        group : _OpenMaterialization
            Open replacement tile group.
        binding : FfLaneBinding
            Candidate lane binding.
        ff : FfMaterializerCell
            FF candidate, used only for error context.

        Returns
        -------
        dict[str, ConfigValue] | None
            Replacement config after adding the binding, or ``None`` when the
            binding cannot be packed into this group.

        Raises
        ------
        RuntimeError
            If ``fail_on_pack_conflict`` is set and a config, parameter, or
            shared-port conflict prevents packing this binding into the group.
        """
        if not group.can_add(binding, check_config=not self.auto_config):
            if self.fail_on_pack_conflict:
                raise RuntimeError(
                    f"Config, parameter, or port conflict while packing FF "
                    f"'{ff.cell_id}' into lane {binding.lane_index}"
                )
            return None
        if not self.auto_config:
            return {**group.config, **binding.lane.config}
        bindings = tuple((*group.bindings, binding))
        solved = self._solve_group_auto_config(bindings)
        if solved is None:
            if self.fail_on_auto_config_unsat:
                raise RuntimeError(
                    "auto_config cannot implement identity for lanes "
                    f"{[item.lane_index for item in bindings]}"
                )
            return None
        return solved

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


@dataclass
class _OpenMaterialization:
    """Mutable replacement tile group used during packing."""

    index: int
    bindings: list[FfLaneBinding] = field(default_factory=list)
    config: dict[str, ConfigValue] = field(default_factory=dict)
    params: dict[str, ParamValue] = field(default_factory=dict)
    port_sources: dict[str, tuple[str, ...]] = field(default_factory=dict)
    used_lanes: set[int] = field(default_factory=set)

    def can_add(self, binding: FfLaneBinding, check_config: bool = True) -> bool:
        """Return whether a binding can be packed into this group.

        Parameters
        ----------
        binding : FfLaneBinding
            Candidate lane binding.
        check_config : bool
            Whether lane-local config conflicts should be checked. Global
            auto-config uses SAT to replace this config test.

        Returns
        -------
        bool
            ``True`` if no lane, config, param, or shared-port conflict exists.
        """
        if binding.lane_index in self.used_lanes:
            return False
        if check_config and _updates_conflict(self.config, binding.lane.config):
            return False
        if _updates_conflict(self.params, binding.lane.params):
            return False
        for port, source in _binding_port_sources(binding).items():
            if port in self.port_sources and self.port_sources[port] != source:
                return False
        return True

    def add(
        self,
        binding: FfLaneBinding,
        config_override: dict[str, ConfigValue] | None = None,
    ) -> None:
        """Add a compatible binding.

        Parameters
        ----------
        binding : FfLaneBinding
            Binding to add.
        config_override : dict[str, ConfigValue] | None
            Complete config to store after this add. ``None`` keeps manual lane
            config merging behavior.
        """
        self.bindings.append(binding)
        self.used_lanes.add(binding.lane_index)
        if config_override is None:
            self.config.update(binding.lane.config)
        else:
            self.config = dict(config_override)
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
class _AutoConfigKey:
    """Cache key for one global auto-config SAT query.

    Attributes
    ----------
    lanes : tuple[tuple[int, str, str], ...]
        Lane index, data port, and output port tuples in packed order.
    overwrites : tuple[tuple[str, bool], ...]
        Fixed config constraints used during the solve.
    controls : tuple[tuple[str, bool], ...]
        Fixed neutral control values used to specialize sequential paths.
    """

    lanes: tuple[tuple[int, str, str], ...]
    overwrites: tuple[tuple[str, bool], ...]
    controls: tuple[tuple[str, bool], ...]

    @classmethod
    def from_bindings(
        cls,
        bindings: tuple[FfLaneBinding, ...],
        overwrites: dict[str, ConfigValue],
        controls: dict[str, ConfigValue],
    ) -> _AutoConfigKey:
        """Build a cache key for a prospective packed lane set.

        Parameters
        ----------
        bindings : tuple[FfLaneBinding, ...]
            Prospective bindings in one replacement tile.
        overwrites : dict[str, ConfigValue]
            Global fixed config constraints.
        controls : dict[str, ConfigValue]
            Fixed neutral control values.

        Returns
        -------
        _AutoConfigKey
            Stable cache key.
        """
        return cls(
            lanes=tuple(
                (binding.lane_index, binding.lane.data_port, binding.lane.output_port)
                for binding in bindings
            ),
            overwrites=tuple(
                sorted((name, bool(value)) for name, value in overwrites.items())
            ),
            controls=tuple(
                sorted((name, bool(value)) for name, value in controls.items())
            ),
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


def _validate_shared_control_settings(
    lanes: tuple[FfMaterializerLane, ...],
) -> None:
    """Validate that reused physical control ports have one meaning.

    Parameters
    ----------
    lanes : tuple[FfMaterializerLane, ...]
        Normalized lane definitions.
    """
    enable_settings: dict[str, tuple[ConfigValue | None]] = {}
    reset_settings: dict[
        str,
        tuple[ConfigValue | None, object, int | None],
    ] = {}
    for index, lane in enumerate(lanes):
        if lane.enable_tile_port is not None:
            setting = (lane.enable_neutral,)
            _record_control_setting(
                settings=enable_settings,
                port=lane.enable_tile_port,
                setting=setting,
                label="enable",
                lane_index=index,
            )
        if lane.reset_tile_port is not None:
            setting = (lane.reset_neutral, lane.reset_kind, lane.reset_value)
            _record_control_setting(
                settings=reset_settings,
                port=lane.reset_tile_port,
                setting=setting,
                label="reset",
                lane_index=index,
            )


def _record_control_setting(
    settings: dict[str, tuple[object, ...]],
    port: str,
    setting: tuple[object, ...],
    label: str,
    lane_index: int,
) -> None:
    """Record one lane control setting and reject conflicts.

    Parameters
    ----------
    settings : dict[str, tuple[object, ...]]
        Already-seen settings keyed by tile port.
    port : str
        Physical tile control port.
    setting : tuple[object, ...]
        Lane setting tuple for the port.
    label : str
        Human-readable control kind.
    lane_index : int
        Lane index used in error messages.

    Raises
    ------
    RuntimeError
        If ``port`` was already seen with a different setting.
    """
    known = settings.get(port)
    if known is None:
        settings[port] = setting
        return
    if known != setting:
        raise RuntimeError(
            f"Lane {lane_index} reuses {label} port '{port}' with settings "
            f"{setting}, but an earlier lane uses {known}"
        )


def _neutral_controls_for_bindings(
    bindings: tuple[FfLaneBinding, ...],
) -> dict[str, ConfigValue]:
    """Return neutral tile control values for one auto-config group.

    Parameters
    ----------
    bindings : tuple[FfLaneBinding, ...]
        Prospective bindings in one replacement tile.

    Returns
    -------
    dict[str, ConfigValue]
        Tile control ports fixed to neutral values while solving the data-path
        identity.

    Raises
    ------
    RuntimeError
        If a referenced control port has no neutral value or if two lanes need
        incompatible neutral values for one physical port.
    """
    controls: dict[str, ConfigValue] = {}
    for binding in bindings:
        lane = binding.lane
        if lane.enable_tile_port is not None:
            if lane.enable_neutral is None:
                raise RuntimeError(
                    f"Lane {binding.lane_index} enable_neutral is required "
                    "for auto_config"
                )
            _record_neutral_control(
                controls,
                lane.enable_tile_port,
                lane.enable_neutral,
                binding.lane_index,
            )
        if lane.reset_tile_port is not None:
            if lane.reset_neutral is None:
                raise RuntimeError(
                    f"Lane {binding.lane_index} reset_neutral is required "
                    "for auto_config"
                )
            _record_neutral_control(
                controls,
                lane.reset_tile_port,
                lane.reset_neutral,
                binding.lane_index,
            )
    return controls


def _record_neutral_control(
    controls: dict[str, ConfigValue],
    port: str,
    value: ConfigValue,
    lane_index: int,
) -> None:
    """Record one fixed neutral control value.

    Parameters
    ----------
    controls : dict[str, ConfigValue]
        Control map being built.
    port : str
        Tile control port.
    value : ConfigValue
        Neutral value to drive on ``port``.
    lane_index : int
        Lane index used in error messages.

    Raises
    ------
    RuntimeError
        If another lane already fixed ``port`` to a different value.
    """
    known = controls.get(port)
    if known is None:
        controls[port] = value
        return
    if bool(known) != bool(value):
        raise RuntimeError(
            f"Lane {lane_index} needs neutral control {port}={int(bool(value))}, "
            f"but the group already fixes {port}={int(bool(known))}"
        )


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


def _invalid_lane_config_reason(
    index: int,
    lane: FfMaterializerLane,
    config_bits: set[str],
    config_prefixes: set[str],
) -> str | None:
    """Return the validation error for lane config names.

    Parameters
    ----------
    index : int
        Lane index used in error messages.
    lane : FfMaterializerLane
        Lane to validate.
    config_bits : set[str]
        Exposed scalar config bit names.
    config_prefixes : set[str]
        Exposed config prefixes.

    Returns
    -------
    str | None
        Error message when invalid, otherwise ``None``.
    """
    for name in lane.config:
        reason = _invalid_config_name_reason(
            name=name,
            label=f"Lane {index} config",
            config_bits=config_bits,
            config_prefixes=config_prefixes,
        )
        if reason is not None:
            return reason
    return None


def _invalid_config_name_reason(
    name: str,
    label: str,
    config_bits: set[str],
    config_prefixes: set[str],
) -> str | None:
    """Return the validation error for one config reference.

    Parameters
    ----------
    name : str
        Config name to validate.
    label : str
        Human-readable label used in the error message.
    config_bits : set[str]
        Exposed scalar config bit names.
    config_prefixes : set[str]
        Exposed config prefixes.

    Returns
    -------
    str | None
        Error message when invalid, otherwise ``None``.
    """
    _base, bit_index = split_indexed_name(name)
    if bit_index is None:
        if name not in config_bits and name not in config_prefixes:
            return f"{label} '{name}' is unknown"
    elif name not in config_bits:
        return f"{label} bit '{name}' is unknown"
    return None


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
