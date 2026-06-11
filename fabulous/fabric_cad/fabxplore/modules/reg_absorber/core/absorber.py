"""Plan register absorption rewrites."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
    FfPortSpec,
    FfRequiredPortValue,
    RegAbsorberCell,
    RegAbsorberDesign,
    RegAbsorberResult,
    RegAbsorption,
    RegisterAbsorptionRule,
    RegisterAbsorptionSide,
    RuleInput,
    _MutableStats,
    fanout_key,
    normalize_ff_ports,
    normalize_rules,
    one_bit,
)
from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.process_tracker import (
    RegAbsorberProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.reader import (
    RegAbsorberReader,
)
from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.report import (
    render_reg_absorber_report,
)
from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.writer import (
    RegAbsorberWriter,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class RegAbsorber:
    """Absorb adjacent FFs into primitive sequential ports.

    Parameters
    ----------
    cell_types : list[str]
        Primitive cell types that may absorb FFs.
    rules : list[RuleInput]
        Absorption rules. Dict payloads are validated as pydantic models.
    ff_ports : dict[str, object] | None
        Supported FF port descriptions. ``None`` selects default FF types.
    allow_extra_fanout : bool
        Whether ambiguous fanout is allowed.
    strict : bool
        Whether skipped invalid matches should raise.
    track_progress : bool
        Whether to emit progress messages.
    progress_chunk_size : int
        Number of processed checks between progress updates.
    """

    def __init__(
        self,
        cell_types: list[str],
        rules: list[RuleInput],
        ff_ports: dict[str, object] | None = None,
        allow_extra_fanout: bool = False,
        strict: bool = False,
        track_progress: bool = True,
        progress_chunk_size: int = 100,
    ) -> None:
        self.cell_types = set(cell_types)
        self.rules = normalize_rules(rules)
        self.ff_ports = normalize_ff_ports(ff_ports)
        self.allow_extra_fanout = allow_extra_fanout
        self.strict = strict
        self._tracker = RegAbsorberProcessTracker(
            enabled=track_progress,
            chunk_size=progress_chunk_size,
        )

    def map_from_design(
        self,
        design: PyosysBridge,
        top_name: str | None = None,
    ) -> RegAbsorberResult:
        """Plan and apply register absorption to a live design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        top_name : str | None
            Top module to process. ``None`` uses the current design top.

        Returns
        -------
        RegAbsorberResult
            Applied absorption result.
        """
        selected_top = top_name or design.top_name()
        reg_design = RegAbsorberReader().read_design(design, selected_top)
        result = self.plan(reg_design)
        RegAbsorberWriter().apply(design, result)
        return result

    def plan(self, design: RegAbsorberDesign) -> RegAbsorberResult:
        """Build a pure-Python absorption plan.

        Parameters
        ----------
        design : RegAbsorberDesign
            Internal design view.

        Returns
        -------
        RegAbsorberResult
            Planned absorption result.
        """
        primitives = [
            cell for cell in design.cells if cell.cell_type in self.cell_types
        ]
        ff_cells = {
            cell.cell_id: cell
            for cell in design.cells
            if cell.cell_type in self.ff_ports
        }
        ff_match_index = _build_ff_match_index(ff_cells, self.ff_ports)
        stats = _MutableStats(
            primitive_cells=len(primitives),
            ff_cells=len(ff_cells),
        )
        fanout = _build_fanout(design)
        rule_count = sum(
            1
            for cell in primitives
            for rule in self.rules
            if rule.cell_type == cell.cell_type
        )
        self._tracker.start(rule_count)

        used_ffs: set[str] = set()
        used_primitive_ports: set[tuple[str, str]] = set()
        primitive_config_updates: dict[str, dict[str, bool]] = {}
        absorptions: list[RegAbsorption] = []
        for primitive in primitives:
            for rule in self.rules:
                if rule.cell_type != primitive.cell_type:
                    continue
                rule_ports = {
                    fanout_key(primitive.cell_id, rule.comb_port),
                    fanout_key(primitive.cell_id, rule.seq_port),
                }
                if used_primitive_ports & rule_ports:
                    stats.skipped_already_used += 1
                    self._tracker.record(absorbed=False)
                    continue
                match = self._try_rule(
                    primitive=primitive,
                    rule=rule,
                    ff_match_index=ff_match_index,
                    fanout=fanout,
                    module_output_bits=design.module_output_bits,
                    used_ffs=used_ffs,
                    known_config=primitive_config_updates.setdefault(
                        primitive.cell_id,
                        {},
                    ),
                    stats=stats,
                )
                if match is None:
                    self._tracker.record(absorbed=False)
                    continue
                absorptions.append(match)
                used_primitive_ports.update(rule_ports)
                used_ffs.add(match.ff_cell_id)
                primitive_config_updates.setdefault(match.primitive_cell_id, {}).update(
                    {name: bool(value) for name, value in match.rule.config.items()}
                )
                if match.side == RegisterAbsorptionSide.OUTPUT:
                    stats.output_absorptions += 1
                else:
                    stats.input_absorptions += 1
                self._tracker.record(absorbed=True)

        self._tracker.done()
        result = RegAbsorberResult(
            top_name=design.top_name,
            rules=self.rules,
            ff_ports=self.ff_ports,
            absorptions=tuple(absorptions),
            stats=stats.frozen(),
        )
        return replace(result, report_summary=render_reg_absorber_report(result))

    def _try_rule(
        self,
        primitive: RegAbsorberCell,
        rule: RegisterAbsorptionRule,
        ff_match_index: _FfMatchIndex,
        fanout: dict[str, set[tuple[str, str]]],
        module_output_bits: frozenset[str],
        used_ffs: set[str],
        known_config: dict[str, bool],
        stats: _MutableStats,
    ) -> RegAbsorption | None:
        """Try one rule on one primitive.

        Parameters
        ----------
        primitive : RegAbsorberCell
            Candidate primitive cell.
        rule : RegisterAbsorptionRule
            Rule to test.
        ff_match_index : _FfMatchIndex
            Supported FF cells indexed by data and output bits.
        fanout : dict[str, set[tuple[str, str]]]
            Signal-bit fanout map.
        module_output_bits : frozenset[str]
            Top-level output signal bits.
        used_ffs : set[str]
            FFs already consumed by previous absorptions.
        known_config : dict[str, bool]
            Config updates already planned for this primitive.
        stats : _MutableStats
            Mutable stats counters.

        Returns
        -------
        RegAbsorption | None
            Absorption if the rule matches.
        """
        if _updates_conflict(known_config, rule.config):
            stats.skipped_config_conflict += 1
            self._maybe_raise(
                f"Config conflict for cell '{primitive.cell_id}' and rule {rule}"
            )
            return None

        if rule.side == RegisterAbsorptionSide.OUTPUT:
            return self._try_output_rule(
                primitive=primitive,
                rule=rule,
                ff_match_index=ff_match_index,
                fanout=fanout,
                module_output_bits=module_output_bits,
                used_ffs=used_ffs,
                stats=stats,
            )
        return self._try_input_rule(
            primitive=primitive,
            rule=rule,
            ff_match_index=ff_match_index,
            fanout=fanout,
            module_output_bits=module_output_bits,
            used_ffs=used_ffs,
            stats=stats,
        )

    def _try_output_rule(
        self,
        primitive: RegAbsorberCell,
        rule: RegisterAbsorptionRule,
        ff_match_index: _FfMatchIndex,
        fanout: dict[str, set[tuple[str, str]]],
        module_output_bits: frozenset[str],
        used_ffs: set[str],
        stats: _MutableStats,
    ) -> RegAbsorption | None:
        """Try to absorb ``primitive.comb_port -> FF``.

        Parameters
        ----------
        primitive : RegAbsorberCell
            Candidate primitive cell.
        rule : RegisterAbsorptionRule
            Output-side rule.
        ff_match_index : _FfMatchIndex
            Supported FF cells indexed by data and output bits.
        fanout : dict[str, set[tuple[str, str]]]
            Signal-bit fanout map.
        module_output_bits : frozenset[str]
            Top-level output signal bits.
        used_ffs : set[str]
            Already used FF ids.
        stats : _MutableStats
            Mutable stats.

        Returns
        -------
        RegAbsorption | None
            Absorption if legal.
        """
        comb_bit = one_bit(primitive.connections.get(rule.comb_port))
        if comb_bit is None:
            stats.skipped_no_match += 1
            return None
        matches = _available_matches(ff_match_index.by_data_bit, comb_bit, used_ffs)
        if len(matches) != 1:
            stats.skipped_no_match += 1
            return None
        ff, spec = matches[0]
        extra_fanout = _extra_fanout(
            fanout=fanout,
            bit=comb_bit,
            allowed={
                fanout_key(primitive.cell_id, rule.comb_port),
                fanout_key(ff.cell_id, spec.data),
            },
            module_output_bits=module_output_bits,
        )
        if extra_fanout and not self.allow_extra_fanout:
            stats.skipped_extra_fanout += 1
            self._maybe_raise(
                f"Extra fanout prevents output absorption of '{ff.cell_id}'"
            )
            return None
        return self._build_absorption(
            primitive=primitive,
            ff=ff,
            rule=rule,
            spec=spec,
            comb_bit=comb_bit,
            side=RegisterAbsorptionSide.OUTPUT,
            stats=stats,
        )

    def _try_input_rule(
        self,
        primitive: RegAbsorberCell,
        rule: RegisterAbsorptionRule,
        ff_match_index: _FfMatchIndex,
        fanout: dict[str, set[tuple[str, str]]],
        module_output_bits: frozenset[str],
        used_ffs: set[str],
        stats: _MutableStats,
    ) -> RegAbsorption | None:
        """Try to absorb ``FF -> primitive.comb_port``.

        Parameters
        ----------
        primitive : RegAbsorberCell
            Candidate primitive cell.
        rule : RegisterAbsorptionRule
            Input-side rule.
        ff_match_index : _FfMatchIndex
            Supported FF cells indexed by data and output bits.
        fanout : dict[str, set[tuple[str, str]]]
            Signal-bit fanout map.
        module_output_bits : frozenset[str]
            Top-level output signal bits.
        used_ffs : set[str]
            Already used FF ids.
        stats : _MutableStats
            Mutable stats.

        Returns
        -------
        RegAbsorption | None
            Absorption if legal.
        """
        comb_bit = one_bit(primitive.connections.get(rule.comb_port))
        if comb_bit is None:
            stats.skipped_no_match += 1
            return None
        matches = _available_matches(ff_match_index.by_output_bit, comb_bit, used_ffs)
        if len(matches) != 1:
            stats.skipped_no_match += 1
            return None
        ff, spec = matches[0]
        extra_fanout = _extra_fanout(
            fanout=fanout,
            bit=comb_bit,
            allowed={
                fanout_key(ff.cell_id, spec.output),
                fanout_key(primitive.cell_id, rule.comb_port),
            },
            module_output_bits=module_output_bits,
        )
        if extra_fanout and not self.allow_extra_fanout:
            stats.skipped_extra_fanout += 1
            self._maybe_raise(
                f"Extra fanout prevents input absorption of '{ff.cell_id}'"
            )
            return None
        return self._build_absorption(
            primitive=primitive,
            ff=ff,
            rule=rule,
            spec=spec,
            comb_bit=comb_bit,
            side=RegisterAbsorptionSide.INPUT,
            stats=stats,
        )

    def _build_absorption(
        self,
        primitive: RegAbsorberCell,
        ff: RegAbsorberCell,
        rule: RegisterAbsorptionRule,
        spec: FfPortSpec,
        comb_bit: str,
        side: RegisterAbsorptionSide,
        stats: _MutableStats,
    ) -> RegAbsorption | None:
        """Build an absorption after structural matching.

        Parameters
        ----------
        primitive : RegAbsorberCell
            Primitive cell.
        ff : RegAbsorberCell
            FF cell.
        rule : RegisterAbsorptionRule
            Matched rule.
        spec : FfPortSpec
            FF port description.
        comb_bit : str
            Primitive combinational-port bit.
        side : RegisterAbsorptionSide
            Absorption direction.
        stats : _MutableStats
            Mutable stats.

        Returns
        -------
        RegAbsorption | None
            Absorption if clock and ports are legal.
        """
        ff_clock = one_bit(ff.connections.get(spec.clock))
        ff_data = one_bit(ff.connections.get(spec.data))
        ff_output = one_bit(ff.connections.get(spec.output))
        if ff_clock is None or ff_data is None or ff_output is None:
            stats.skipped_no_match += 1
            return None
        if rule.clock_port is not None:
            primitive_clock = one_bit(primitive.connections.get(rule.clock_port))
            if primitive_clock is not None and primitive_clock != ff_clock:
                stats.skipped_clock_mismatch += 1
                self._maybe_raise(
                    f"Clock mismatch between '{primitive.cell_id}' and '{ff.cell_id}'"
                )
                return None
        if not _required_ff_ports_match(ff, spec):
            stats.skipped_no_match += 1
            return None
        if not _enable_is_compatible(ff, spec, rule):
            stats.skipped_no_match += 1
            return None
        if not _reset_is_compatible(ff, spec, rule):
            stats.skipped_no_match += 1
            return None
        return RegAbsorption(
            primitive_cell_id=primitive.cell_id,
            ff_cell_id=ff.cell_id,
            rule=rule,
            ff_type=ff.cell_type,
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
            comb_bit=comb_bit,
            side=side,
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


_FfMatch = tuple[RegAbsorberCell, FfPortSpec]


@dataclass(frozen=True)
class _FfMatchIndex:
    """Index supported FF cells by the scalar bits used in absorption matching.

    Attributes
    ----------
    by_data_bit : dict[str, tuple[_FfMatch, ...]]
        FFs keyed by their one-bit data input.
    by_output_bit : dict[str, tuple[_FfMatch, ...]]
        FFs keyed by their one-bit registered output.
    """

    by_data_bit: dict[str, tuple[_FfMatch, ...]]
    by_output_bit: dict[str, tuple[_FfMatch, ...]]


def _build_ff_match_index(
    ff_cells: dict[str, RegAbsorberCell],
    ff_ports: dict[str, FfPortSpec],
) -> _FfMatchIndex:
    """Build data/output-bit indexes for supported FF cells.

    Parameters
    ----------
    ff_cells : dict[str, RegAbsorberCell]
        Supported FF cells keyed by instance name.
    ff_ports : dict[str, FfPortSpec]
        Supported FF port descriptions keyed by FF cell type.

    Returns
    -------
    _FfMatchIndex
        FF lookup tables used by rule checks.
    """
    by_data_bit: dict[str, list[_FfMatch]] = {}
    by_output_bit: dict[str, list[_FfMatch]] = {}

    for ff in ff_cells.values():
        spec = ff_ports[ff.cell_type]
        data_bit = one_bit(ff.connections.get(spec.data))
        if data_bit is not None:
            by_data_bit.setdefault(data_bit, []).append((ff, spec))
        output_bit = one_bit(ff.connections.get(spec.output))
        if output_bit is not None:
            by_output_bit.setdefault(output_bit, []).append((ff, spec))

    return _FfMatchIndex(
        by_data_bit={bit: tuple(matches) for bit, matches in by_data_bit.items()},
        by_output_bit={bit: tuple(matches) for bit, matches in by_output_bit.items()},
    )


def _available_matches(
    match_index: dict[str, tuple[_FfMatch, ...]],
    bit: str,
    used_ffs: set[str],
) -> list[_FfMatch]:
    """Return indexed FF matches that have not been consumed yet.

    Parameters
    ----------
    match_index : dict[str, tuple[_FfMatch, ...]]
        FF match index keyed by a signal bit.
    bit : str
        Signal bit to look up.
    used_ffs : set[str]
        FF instance names already consumed by earlier absorptions.

    Returns
    -------
    list[_FfMatch]
        Available matches in original reader order.
    """
    return [
        (ff, spec)
        for ff, spec in match_index.get(bit, ())
        if ff.cell_id not in used_ffs
    ]


def _build_fanout(
    design: RegAbsorberDesign,
) -> dict[str, set[tuple[str, str]]]:
    """Build a signal-bit to cell-port map.

    Parameters
    ----------
    design : RegAbsorberDesign
        Internal design view.

    Returns
    -------
    dict[str, set[tuple[str, str]]]
        Signal-bit fanout map.
    """
    fanout: dict[str, set[tuple[str, str]]] = {}
    for cell in design.cells:
        for port, bits in cell.connections.items():
            for bit in bits:
                fanout.setdefault(bit, set()).add(fanout_key(cell.cell_id, port))
    return fanout


def _extra_fanout(
    fanout: dict[str, set[tuple[str, str]]],
    bit: str,
    allowed: set[tuple[str, str]],
    module_output_bits: frozenset[str],
) -> bool:
    """Return whether a signal has non-allowed fanout.

    Parameters
    ----------
    fanout : dict[str, set[tuple[str, str]]]
        Signal-bit fanout map.
    bit : str
        Signal bit being checked.
    allowed : set[tuple[str, str]]
        Cell-port uses allowed by the candidate rewrite.
    module_output_bits : frozenset[str]
        Top-level output signal bits.

    Returns
    -------
    bool
        ``True`` if extra fanout exists.
    """
    if bit in module_output_bits:
        return True
    return bool(fanout.get(bit, set()) - allowed)


def _updates_conflict(
    known_config: dict[str, bool],
    updates: dict[str, int | bool],
) -> bool:
    """Return whether new config updates conflict with planned updates.

    Parameters
    ----------
    known_config : dict[str, bool]
        Already planned config values for one primitive.
    updates : dict[str, int | bool]
        New requested values.

    Returns
    -------
    bool
        ``True`` if the same config key is requested with different values.
    """
    return any(
        name in known_config and known_config[name] != bool(value)
        for name, value in updates.items()
    )


def _required_ff_ports_match(ff: RegAbsorberCell, spec: FfPortSpec) -> bool:
    """Return whether FF control ports are statically compatible.

    Parameters
    ----------
    ff : RegAbsorberCell
        FF cell being considered.
    spec : FfPortSpec
        Port and control-port description.

    Returns
    -------
    bool
        ``True`` if every required control port is a matching constant.
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
    ff: RegAbsorberCell,
    spec: FfPortSpec,
    rule: RegisterAbsorptionRule,
) -> bool:
    """Return whether an FF enable can be absorbed by ``rule``.

    Parameters
    ----------
    ff : RegAbsorberCell
        FF cell being considered.
    spec : FfPortSpec
        FF port description.
    rule : RegisterAbsorptionRule
        Candidate absorption rule.

    Returns
    -------
    bool
        ``True`` if the enable is absent, neutral, or explicitly allowed.
    """
    if spec.enable_port is None or not _has_control_port(ff, spec.enable_port):
        return rule.enable_tile_port is None or rule.enable_neutral is not None
    if rule.include_enable_ff:
        return True
    bit = one_bit(ff.connections.get(spec.enable_port))
    return bit == _expected_polarity_bit(ff, spec.enable_polarity_param, active=True)


def _reset_is_compatible(
    ff: RegAbsorberCell,
    spec: FfPortSpec,
    rule: RegisterAbsorptionRule,
) -> bool:
    """Return whether an FF reset can be absorbed by ``rule``.

    Parameters
    ----------
    ff : RegAbsorberCell
        FF cell being considered.
    spec : FfPortSpec
        FF port description.
    rule : RegisterAbsorptionRule
        Candidate absorption rule.

    Returns
    -------
    bool
        ``True`` if the reset is absent, neutral, or explicitly allowed.
    """
    if spec.reset_port is None or not _has_control_port(ff, spec.reset_port):
        return rule.reset_tile_port is None or rule.reset_neutral is not None
    if not rule.include_reset_ff:
        bit = one_bit(ff.connections.get(spec.reset_port))
        return bit == _expected_polarity_bit(
            ff,
            spec.reset_polarity_param,
            active=False,
        )
    if rule.reset_kind is not None and spec.reset_kind != rule.reset_kind:
        return False
    if rule.reset_value is not None and spec.reset_value_param is not None:
        ff_reset_value = _parameter_int(ff, spec.reset_value_param)
        if ff_reset_value is None or ff_reset_value != rule.reset_value:
            return False
    return True


def _has_control_port(ff: RegAbsorberCell, port: str | None) -> bool:
    """Return whether a control port has a one-bit connection.

    Parameters
    ----------
    ff : RegAbsorberCell
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
    ff: RegAbsorberCell,
    spec: FfPortSpec,
    port: str,
    requirement: int | bool | FfRequiredPortValue,
) -> str | None:
    """Return expected constant bit for one FF control requirement.

    Parameters
    ----------
    ff : RegAbsorberCell
        FF cell being considered.
    spec : FfPortSpec
        Port and control-port description.
    port : str
        Control port name.
    requirement : int | bool | FfRequiredPortValue
        Required value. Symbolic values are interpreted through the configured
        polarity parameter for the port.

    Returns
    -------
    str | None
        Expected ``"0"`` or ``"1"`` bit, or ``None`` if the requirement cannot
        be evaluated.
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
    ff: RegAbsorberCell,
    parameter_name: str | None,
    active: bool,
) -> str | None:
    """Return the active or inactive constant for a polarity parameter.

    Parameters
    ----------
    ff : RegAbsorberCell
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


def _parameter_bool(ff: RegAbsorberCell, parameter_name: str | None) -> bool | None:
    """Parse one boolean polarity parameter.

    Parameters
    ----------
    ff : RegAbsorberCell
        FF cell being considered.
    parameter_name : str | None
        Parameter to parse. ``None`` means active-high by default.

    Returns
    -------
    bool | None
        Parsed boolean, or ``None`` when the parameter is not a constant bit.
    """
    if parameter_name is None:
        return True
    raw_value = ff.parameters.get(parameter_name)
    if raw_value is None:
        return True
    normalized = raw_value.strip().lower().replace(" ", "")
    if normalized in {"1", "1'1", "1'b1", "1'h1", "true"}:
        return True
    if normalized in {"0", "1'0", "1'b0", "1'h0", "false"}:
        return False
    if normalized.endswith("1"):
        return True
    if normalized.endswith("0"):
        return False
    return None


def _parameter_int(ff: RegAbsorberCell, parameter_name: str) -> int | None:
    """Parse one integer parameter.

    Parameters
    ----------
    ff : RegAbsorberCell
        FF cell being considered.
    parameter_name : str
        Parameter to parse.

    Returns
    -------
    int | None
        Parsed integer value.
    """
    raw_value = ff.parameters.get(parameter_name)
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower().replace(" ", "")
    for prefix in ("1'b", "1'h", "32'"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
            break
    if normalized in {"0", "1"}:
        return int(normalized)
    return None
