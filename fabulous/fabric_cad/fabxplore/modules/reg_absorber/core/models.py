"""Data models for register absorption.

The reg-absorber pass is intentionally split into internal Python models and a pyosys
writer. The reader builds the models from the Yosys object view, the absorber plans
legal rewrites, and the writer applies those rewrites to the live pyosys design.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SignalBit = str
ConfigValue = int | bool
ParamValue = str | int | bool


class RegisterAbsorptionSide(StrEnum):
    """Direction for one absorption rule."""

    INPUT = "input"
    OUTPUT = "output"


class FfRequiredPortValue(StrEnum):
    """Symbolic value required on an FF control port."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class FfResetKind(StrEnum):
    """Reset timing semantics for a supported FF cell."""

    ASYNC = "async"
    SYNC = "sync"


RequiredPortValue = ConfigValue | FfRequiredPortValue


class FfPortSpec(BaseModel):
    """Port names used by one supported FF cell type.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    clock : str
        Clock port name.
    data : str
        Data input port name.
    output : str
        Registered output port name.
    enable_port : str | None
        Optional FF enable port name.
    enable_polarity_param : str | None
        Optional FF enable polarity parameter name.
    reset_port : str | None
        Optional FF reset port name.
    reset_kind : FfResetKind | None
        Optional FF reset timing semantics.
    reset_polarity_param : str | None
        Optional FF reset polarity parameter name.
    reset_value_param : str | None
        Optional FF reset value parameter name.
    required_ports : dict[str, RequiredPortValue]
        Extra FF control ports that must be constant for the cell to behave
        like a plain DFF.
    polarity_params : dict[str, str]
        Mapping from control port name to polarity parameter name. This is used
        for symbolic ``active`` and ``inactive`` requirements.
    """

    model_config = ConfigDict(frozen=True)

    clock: str
    data: str
    output: str
    enable_port: str | None = None
    enable_polarity_param: str | None = None
    reset_port: str | None = None
    reset_kind: FfResetKind | None = None
    reset_polarity_param: str | None = None
    reset_value_param: str | None = None
    required_ports: dict[str, RequiredPortValue] = Field(default_factory=dict)
    polarity_params: dict[str, str] = Field(default_factory=dict)

    @field_validator("required_ports", mode="before")
    @classmethod
    def _coerce_required_ports(
        cls,
        value: object,
    ) -> dict[str, RequiredPortValue]:
        """Normalize symbolic required control values.

        Parameters
        ----------
        value : object
            User-provided required port mapping.

        Returns
        -------
        dict[str, RequiredPortValue]
            Normalized required port values.

        Raises
        ------
        TypeError
            If the required port payload is not a dictionary.
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            msg = "required_ports must be a dictionary"
            raise TypeError(msg)
        return {
            str(port): FfRequiredPortValue(raw_value)
            if isinstance(raw_value, str)
            and raw_value in {item.value for item in FfRequiredPortValue}
            else raw_value
            for port, raw_value in value.items()
        }

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


class RegisterAbsorptionRule(BaseModel):
    """Describe one primitive register absorption opportunity.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    side : RegisterAbsorptionSide
        Whether this is an input-side or output-side absorption rule.
    cell_type : str
        Primitive cell type the rule applies to.
    comb_port : str
        Existing combinational primitive port.
    seq_port : str
        Primitive port used after absorption.
    clock_port : str | None
        Optional primitive clock port that must match or receive the FF clock.
    include_enable_ff : bool
        Whether FFs with a variable enable may be absorbed.
    include_reset_ff : bool
        Whether FFs with a variable reset may be absorbed.
    enable_tile_port : str | None
        Optional tile enable port to wire or neutralize.
    enable_neutral : ConfigValue | None
        Constant used for the tile enable port when the absorbed FF has no
        enable.
    reset_tile_port : str | None
        Optional tile reset port to wire or neutralize.
    reset_neutral : ConfigValue | None
        Constant used for the tile reset port when the absorbed FF has no
        reset.
    reset_kind : FfResetKind | None
        Optional tile reset timing semantics.
    reset_value : int | None
        Optional tile reset value.
    config : dict[str, ConfigValue]
        Config bits to set after absorption.
    attributes : dict[str, ParamValue]
        Attributes to set after absorption.
    remove_disconnected_comb_port : bool
        Whether to disconnect ``comb_port`` when ``comb_port != seq_port``.
    """

    model_config = ConfigDict(frozen=True)

    side: RegisterAbsorptionSide
    cell_type: str
    comb_port: str
    seq_port: str
    clock_port: str | None = None
    include_enable_ff: bool = False
    include_reset_ff: bool = False
    enable_tile_port: str | None = None
    enable_neutral: ConfigValue | None = None
    reset_tile_port: str | None = None
    reset_neutral: ConfigValue | None = None
    reset_kind: FfResetKind | None = None
    reset_value: int | None = None
    config: dict[str, ConfigValue] = Field(default_factory=dict)
    attributes: dict[str, ParamValue] = Field(default_factory=dict)
    remove_disconnected_comb_port: bool = True

    @field_validator("side", mode="before")
    @classmethod
    def _coerce_side(cls, value: object) -> RegisterAbsorptionSide:
        """Coerce string rule directions into the enum.

        Parameters
        ----------
        value : object
            User-provided direction.

        Returns
        -------
        RegisterAbsorptionSide
            Normalized direction.
        """
        return RegisterAbsorptionSide(value)

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


@dataclass(frozen=True)
class RegAbsorberCell:
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
class RegAbsorberDesign:
    """Internal design view for register absorption.

    Attributes
    ----------
    top_name : str
        Top module name.
    cells : tuple[RegAbsorberCell, ...]
        Cells in stable reader order.
    module_output_bits : frozenset[SignalBit]
        Signal bits that drive selected top-module outputs.
    """

    top_name: str
    cells: tuple[RegAbsorberCell, ...]
    module_output_bits: frozenset[SignalBit] = frozenset()


@dataclass(frozen=True)
class RegAbsorption:
    """One planned FF absorption.

    Attributes
    ----------
    primitive_cell_id : str
        Primitive absorbing the FF.
    ff_cell_id : str
        FF cell to remove.
    rule : RegisterAbsorptionRule
        Rule that matched.
    ff_type : str
        FF cell type.
    ff_clock_port : str
        FF clock port name.
    ff_data_port : str
        FF data port name.
    ff_output_port : str
        FF output port name.
    ff_enable_port : str | None
        FF enable port name when the matched FF has one.
    ff_reset_port : str | None
        FF reset port name when the matched FF has one.
    ff_clock_bit : SignalBit
        FF clock signal bit.
    ff_data_bit : SignalBit
        FF data input signal bit.
    ff_output_bit : SignalBit
        FF output signal bit.
    comb_bit : SignalBit
        Primitive combinational port signal bit before absorption.
    side : RegisterAbsorptionSide
        Absorption direction.
    """

    primitive_cell_id: str
    ff_cell_id: str
    rule: RegisterAbsorptionRule
    ff_type: str
    ff_clock_port: str
    ff_data_port: str
    ff_output_port: str
    ff_enable_port: str | None
    ff_reset_port: str | None
    ff_clock_bit: SignalBit
    ff_data_bit: SignalBit
    ff_output_bit: SignalBit
    comb_bit: SignalBit
    side: RegisterAbsorptionSide


@dataclass(frozen=True)
class RegAbsorberStats:
    """Summary counters for one reg-absorber run.

    Attributes
    ----------
    primitive_cells : int
        Number of primitive cells matching selected types.
    ff_cells : int
        Number of supported FF cells found.
    output_absorptions : int
        Output-side FF absorptions.
    input_absorptions : int
        Input-side FF absorptions.
    skipped_no_match : int
        Rule checks that found no matching FF.
    skipped_extra_fanout : int
        Rule checks skipped because fanout was not clean.
    skipped_clock_mismatch : int
        Rule checks skipped because the primitive clock conflicted with the FF.
    skipped_config_conflict : int
        Rule checks skipped because requested config conflicted.
    skipped_already_used : int
        Rule checks skipped because a cell was already consumed by a previous
        absorption.
    """

    primitive_cells: int = 0
    ff_cells: int = 0
    output_absorptions: int = 0
    input_absorptions: int = 0
    skipped_no_match: int = 0
    skipped_extra_fanout: int = 0
    skipped_clock_mismatch: int = 0
    skipped_config_conflict: int = 0
    skipped_already_used: int = 0


@dataclass(frozen=True)
class RegAbsorberResult:
    """Result of register absorption.

    Attributes
    ----------
    top_name : str
        Processed top module.
    rules : tuple[RegisterAbsorptionRule, ...]
        Normalized rule list.
    ff_ports : dict[str, FfPortSpec]
        Supported FF cell types.
    absorptions : tuple[RegAbsorption, ...]
        Planned and applied absorptions.
    stats : RegAbsorberStats
        Summary counters.
    report_summary : str
        Human-readable report.
    """

    top_name: str
    rules: tuple[RegisterAbsorptionRule, ...]
    ff_ports: dict[str, FfPortSpec]
    absorptions: tuple[RegAbsorption, ...]
    stats: RegAbsorberStats
    report_summary: str = ""


RuleInput = RegisterAbsorptionRule | dict[str, object]
FfPortsInput = dict[str, FfPortSpec | dict[str, object]]
SideLiteral = Literal["input", "output"]


@dataclass
class _MutableStats:
    """Mutable counter container used while planning."""

    primitive_cells: int = 0
    ff_cells: int = 0
    output_absorptions: int = 0
    input_absorptions: int = 0
    skipped_no_match: int = 0
    skipped_extra_fanout: int = 0
    skipped_clock_mismatch: int = 0
    skipped_config_conflict: int = 0
    skipped_already_used: int = 0

    def frozen(self) -> RegAbsorberStats:
        """Return an immutable snapshot.

        Returns
        -------
        RegAbsorberStats
            Immutable stats object.
        """
        return RegAbsorberStats(**self.__dict__)


DEFAULT_FF_PORTS: FfPortsInput = {
    "LUTFF": {"clock": "CLK", "data": "D", "output": "O"},
    "$dff": {"clock": "CLK", "data": "D", "output": "Q"},
    "$adff": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "reset_port": "ARST",
        "reset_kind": "async",
        "reset_polarity_param": "ARST_POLARITY",
        "reset_value_param": "ARST_VALUE",
    },
    "$sdff": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "reset_port": "SRST",
        "reset_kind": "sync",
        "reset_polarity_param": "SRST_POLARITY",
        "reset_value_param": "SRST_VALUE",
    },
    "$dffe": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "enable_port": "EN",
        "enable_polarity_param": "EN_POLARITY",
    },
    "$adffe": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "enable_port": "EN",
        "enable_polarity_param": "EN_POLARITY",
        "reset_port": "ARST",
        "reset_kind": "async",
        "reset_polarity_param": "ARST_POLARITY",
        "reset_value_param": "ARST_VALUE",
    },
    "$aldff": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "required_ports": {"ALOAD": "inactive"},
        "polarity_params": {"ALOAD": "ALOAD_POLARITY"},
    },
    "$aldffe": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "enable_port": "EN",
        "enable_polarity_param": "EN_POLARITY",
        "required_ports": {"ALOAD": "inactive"},
        "polarity_params": {"ALOAD": "ALOAD_POLARITY"},
    },
    "$dffsr": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "required_ports": {"SET": "inactive", "CLR": "inactive"},
        "polarity_params": {"SET": "SET_POLARITY", "CLR": "CLR_POLARITY"},
    },
    "$dffsre": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "enable_port": "EN",
        "enable_polarity_param": "EN_POLARITY",
        "required_ports": {"SET": "inactive", "CLR": "inactive"},
        "polarity_params": {
            "SET": "SET_POLARITY",
            "CLR": "CLR_POLARITY",
        },
    },
    "$sdffe": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "enable_port": "EN",
        "enable_polarity_param": "EN_POLARITY",
        "reset_port": "SRST",
        "reset_kind": "sync",
        "reset_polarity_param": "SRST_POLARITY",
        "reset_value_param": "SRST_VALUE",
    },
    "$sdffce": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "enable_port": "EN",
        "enable_polarity_param": "EN_POLARITY",
        "reset_port": "SRST",
        "reset_kind": "sync",
        "reset_polarity_param": "SRST_POLARITY",
        "reset_value_param": "SRST_VALUE",
    },
    "$_DFF_P_": {"clock": "C", "data": "D", "output": "Q"},
    "$_DFF_N_": {"clock": "C", "data": "D", "output": "Q"},
}


def normalize_rules(rules: list[RuleInput]) -> tuple[RegisterAbsorptionRule, ...]:
    """Normalize rule payloads into pydantic models.

    Parameters
    ----------
    rules : list[RuleInput]
        User-provided rules.

    Returns
    -------
    tuple[RegisterAbsorptionRule, ...]
        Validated rules.
    """
    return tuple(
        rule
        if isinstance(rule, RegisterAbsorptionRule)
        else RegisterAbsorptionRule.model_validate(rule)
        for rule in rules
    )


def normalize_ff_ports(
    ff_ports: FfPortsInput | None,
) -> dict[str, FfPortSpec]:
    """Normalize FF port payloads into pydantic models.

    Parameters
    ----------
    ff_ports : FfPortsInput | None
        User-provided FF port mapping. ``None`` selects defaults.

    Returns
    -------
    dict[str, FfPortSpec]
        Validated FF port mapping.
    """
    raw = DEFAULT_FF_PORTS if ff_ports is None else ff_ports
    return {
        cell_type: spec
        if isinstance(spec, FfPortSpec)
        else FfPortSpec.model_validate(spec)
        for cell_type, spec in raw.items()
    }


def config_updates_conflict(
    cell: RegAbsorberCell,
    config: dict[str, ConfigValue],
) -> bool:
    """Return whether config updates conflict with known constants.

    Parameters
    ----------
    cell : RegAbsorberCell
        Primitive cell being updated.
    config : dict[str, ConfigValue]
        Requested config updates.

    Returns
    -------
    bool
        ``True`` if a requested bit conflicts with an existing constant.
    """
    for name, value in config.items():
        bit = "1" if bool(value) else "0"
        base, index = split_indexed_name(name)
        if index is None:
            current = cell.connections.get(base)
            if current is not None and len(current) == 1 and current[0] in {"0", "1"}:
                return current[0] != bit
            continue
        current = cell.connections.get(base)
        if current is None or index >= len(current):
            continue
        if current[index] in {"0", "1"} and current[index] != bit:
            return True
    return False


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


def fanout_key(cell_id: str, port: str) -> tuple[str, str]:
    """Return a stable cell-port key.

    Parameters
    ----------
    cell_id : str
        Cell instance name.
    port : str
        Port name.

    Returns
    -------
    tuple[str, str]
        Hashable key.
    """
    return (cell_id, port)


def count_absorptions_by_type(
    absorptions: tuple[RegAbsorption, ...],
) -> dict[str, int]:
    """Count absorptions by primitive cell type.

    Parameters
    ----------
    absorptions : tuple[RegAbsorption, ...]
        Planned absorptions.

    Returns
    -------
    dict[str, int]
        Cell type to count.
    """
    counts: dict[str, int] = {}
    for absorption in absorptions:
        cell_type = absorption.rule.cell_type
        counts[cell_type] = counts.get(cell_type, 0) + 1
    return counts
