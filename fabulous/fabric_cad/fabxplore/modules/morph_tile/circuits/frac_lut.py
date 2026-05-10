"""Morph-tile circuit adapter for LUT-combinator fractional LUT cells.

The adapter consumes emitted ``__frac_lut``-style cells directly from the
generic morph-tile netlist view. It reconstructs the same fixed multi-output
truth table as the LUT-combinator behavioral model, asks SAT-fab whether the
target morph tile can implement that cut, and then replaces the whole fractional
cell when a solution exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.truth_table import (
    parse_init_literal,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphCircuitAdapter,
    MorphCircuitEnvironment,
    MorphCircuitKind,
    MorphSolveOutcome,
    MorphTileContext,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
        CutSolveResult,
        MorphTileNetlistCell,
        MorphTileReplacement,
        ReplacementPortRef,
    )


class FracLutCircuitOptions(BaseModel):
    """Options for the fractional-LUT circuit adapter.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    modes : list[str]
        LUT-combinator mapping modes selected for morphing.
    cell_types : list[str]
        Netlist cell types recognized as fractional LUT cells.
    enable_permute_cache : bool
        Whether input-permutation-equivalent multi-output truth tables may share
        cache entries.
    """

    model_config = ConfigDict(frozen=True)

    modes: list[str] = Field(
        default_factory=lambda: ["single", "dual", "dual_select_as_data"]
    )
    cell_types: list[str] = Field(default_factory=lambda: ["__frac_lut"])
    enable_permute_cache: bool = True


@dataclass(frozen=True)
class FracLutCandidate:
    """Represent one emitted fractional-LUT candidate.

    Attributes
    ----------
    cell_id : str
        Cell name in the selected top module.
    mode : str
        LUT-combinator mapping mode, for example ``"single"`` or ``"dual"``.
    lut_size : int
        Internal LUT half width.
    num_shared_inputs : int
        Nominal number of shared input pins.
    l0_init : int
        LSB-first INIT value for the L0 half.
    l1_init : int
        LSB-first INIT value for the L1 half.
    select_as_data_used : bool
        Whether select-as-data wiring is active.
    mux_select_config : int
        Output mux configuration used by select-as-data mode.
    spec_inputs : list[str]
        Input names used by the generated SAT-fab spec.
    spec_input_refs : dict[str, ReplacementPortRef]
        Mapping from spec input name to original fractional-cell input port.
    output_inits : dict[str, int]
        Multi-output truth-table INITs keyed by spec output name.
    output_refs : dict[str, ReplacementPortRef]
        Mapping from spec output name to original fractional-cell output port.
    """

    cell_id: str
    mode: str
    lut_size: int
    num_shared_inputs: int
    l0_init: int
    l1_init: int
    select_as_data_used: bool
    mux_select_config: int
    spec_inputs: list[str]
    spec_input_refs: dict[str, ReplacementPortRef]
    output_inits: dict[str, int]
    output_refs: dict[str, ReplacementPortRef]


class FracLutCircuit(MorphCircuitAdapter[FracLutCandidate]):
    """Describe and solve emitted ``__frac_lut`` morph candidates.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared adapter environment.
    options : FracLutCircuitOptions | None
        Adapter-local configuration. If omitted, options are read from the
        shared environment.

    Attributes
    ----------
    kind
        Adapter kind identifier.
    """

    kind = MorphCircuitKind.FRAC_LUT

    def __init__(
        self,
        env: MorphCircuitEnvironment,
        options: FracLutCircuitOptions | None = None,
    ) -> None:
        super().__init__(env)
        self.options = options or _options_from_environment(env)
        self._mode_set = set(self.options.modes)
        self._cell_type_set = set(self.options.cell_types)

    def filter_summary(self) -> dict[str, list[str]]:
        """Return selected fractional-LUT filters.

        Returns
        -------
        dict[str, list[str]]
            Selected modes and cell types.
        """
        return {
            "frac_lut.cell_types": list(self.options.cell_types),
            "frac_lut.enable_permute_cache": [str(self.options.enable_permute_cache)],
            "frac_lut.modes": list(self.options.modes),
        }

    def iter_candidates(self, context: MorphTileContext) -> Iterable[FracLutCandidate]:
        """Yield fractional-LUT candidates from the design.

        Parameters
        ----------
        context : MorphTileContext
            Runtime mapping context.

        Yields
        ------
        FracLutCandidate
            Parsed fractional-LUT candidates in reader order.
        """
        for cell in context.design.cells:
            candidate = self._parse_candidate(cell)
            if candidate is not None:
                yield candidate

    def is_enabled_candidate(self, candidate: FracLutCandidate) -> bool:
        """Return whether the candidate mode is selected.

        Parameters
        ----------
        candidate : FracLutCandidate
            Fractional-LUT candidate.

        Returns
        -------
        bool
            ``True`` if the candidate mode is enabled.
        """
        return candidate.mode in self._mode_set

    def solve(self, candidate: FracLutCandidate) -> MorphSolveOutcome:
        """Solve one fractional-LUT candidate.

        Parameters
        ----------
        candidate : FracLutCandidate
            Candidate to solve.

        Returns
        -------
        MorphSolveOutcome
            SAT result plus cache status.
        """
        return self.solve_truth_table_cached(
            name="frac_lut_spec",
            input_names=candidate.spec_inputs,
            output_inits=candidate.output_inits,
            enable_permute_cache=self.options.enable_permute_cache,
            reduce_lut_symmetry=False,
        )

    def make_replacement(
        self,
        candidate: FracLutCandidate,
        result: CutSolveResult,
    ) -> MorphTileReplacement:
        """Build a replacement for one solved fractional-LUT candidate.

        Parameters
        ----------
        candidate : FracLutCandidate
            Candidate that was solved.
        result : CutSolveResult
            SAT result for the candidate.

        Returns
        -------
        MorphTileReplacement
            Replacement payload consumed by the writer.
        """
        return self.replacement(
            original_cell_id=candidate.cell_id,
            width=len(candidate.spec_inputs),
            init=_combined_init_signature(candidate.output_inits),
            result=result,
            input_ports={
                tile_input: candidate.spec_input_refs[source]
                if source in candidate.spec_input_refs
                else self.const(int(source))
                for tile_input, source in result.input_mapping.items()
                if source in candidate.spec_input_refs or source in {"0", "1"}
            },
            output_ports={
                tile_output: candidate.output_refs[spec_output]
                for spec_output, tile_output in result.output_mapping.items()
            },
        )

    def width_label(self, candidate: FracLutCandidate) -> str:
        """Return the report width label for a fractional-LUT candidate.

        Parameters
        ----------
        candidate : FracLutCandidate
            Candidate to label.

        Returns
        -------
        str
            Human-readable width label.
        """
        return f"FRAC_LUT{candidate.lut_size}:{candidate.mode}"

    def init_label(self, candidate: FracLutCandidate) -> str:
        """Return the report INIT label for a fractional-LUT candidate.

        Parameters
        ----------
        candidate : FracLutCandidate
            Candidate to label.

        Returns
        -------
        str
            Human-readable INIT label.
        """
        return (
            f"FRAC_LUT{candidate.lut_size}:{candidate.mode}:"
            f"L0=0x{candidate.l0_init:x}:L1=0x{candidate.l1_init:x}"
        )

    def _parse_candidate(
        self,
        cell: MorphTileNetlistCell,
    ) -> FracLutCandidate | None:
        """Parse one generic cell into a fractional-LUT candidate.

        Parameters
        ----------
        cell : MorphTileNetlistCell
            Generic source-design cell.

        Returns
        -------
        FracLutCandidate | None
            Parsed candidate, or ``None`` for non-fractional-LUT cells.
        """
        if cell.cell_type not in self._cell_type_set:
            return None

        lut_size = _parse_int_parameter(cell.parameters, "LUT_SIZE")
        num_shared_inputs = _parse_int_parameter(cell.parameters, "NUM_SHARED_INPUTS")
        mode = _metadata_field(cell.parameters.get("META_DATA", ""), "lut_mapping")
        if mode is None:
            mode = "single" if "O1" not in cell.connections else "dual"

        l0_init = parse_init_literal(
            str(cell.parameters.get("L0_INIT", "0")),
            lut_size,
        )
        l1_init = parse_init_literal(
            str(cell.parameters.get("L1_INIT", "0")),
            lut_size,
        )
        select_as_data_used = _parse_bool_parameter(
            cell.parameters,
            "SELECT_AS_DATA_USED",
        )
        mux_select_config = _parse_int_parameter(
            cell.parameters,
            "MUX_SELECT_CONFIG",
            default=0,
        )

        input_view = _InputView(self, cell, lut_size, num_shared_inputs)
        output_refs = _parse_output_refs(self, cell)
        if not output_refs:
            return None
        output_inits = _build_output_inits(
            lut_size=lut_size,
            num_shared_inputs=num_shared_inputs,
            l0_init=l0_init,
            l1_init=l1_init,
            select_as_data_used=select_as_data_used,
            mux_select_config=mux_select_config,
            spec_inputs=input_view.spec_inputs,
            value_for_port=input_view.value_for_port,
            output_names=tuple(output_refs),
        )

        return FracLutCandidate(
            cell_id=cell.cell_id,
            mode=mode,
            lut_size=lut_size,
            num_shared_inputs=num_shared_inputs,
            l0_init=l0_init,
            l1_init=l1_init,
            select_as_data_used=select_as_data_used,
            mux_select_config=mux_select_config,
            spec_inputs=input_view.spec_inputs,
            spec_input_refs=input_view.spec_input_refs,
            output_inits=output_inits,
            output_refs=output_refs,
        )


class _InputView:
    """Create a variable view over fractional-LUT input port connections.

    Parameters
    ----------
    adapter : FracLutCircuit
        Adapter used to build replacement references.
    cell : MorphTileNetlistCell
        Fractional-LUT source cell.
    lut_size : int
        Internal LUT half width.
    num_shared_inputs : int
        Nominal number of shared input pins.
    """

    def __init__(
        self,
        adapter: FracLutCircuit,
        cell: MorphTileNetlistCell,
        lut_size: int,
        num_shared_inputs: int,
    ) -> None:
        self._adapter = adapter
        self._cell = cell
        self.spec_inputs: list[str] = []
        self.spec_input_refs: dict[str, ReplacementPortRef] = {}
        self._port_sources: dict[str, str | int] = {}
        self._source_by_token: dict[str, str] = {}
        for port in _input_port_order(lut_size, num_shared_inputs):
            self._port_sources[port] = self._source_for_port(port)

    def value_for_port(self, port: str, values: dict[str, bool]) -> bool:
        """Return one port value for a truth-table assignment.

        Parameters
        ----------
        port : str
            Fractional-LUT input port name.
        values : dict[str, bool]
            Current truth-table input assignment.

        Returns
        -------
        bool
            Boolean port value.
        """
        source = self._port_sources.get(port, 0)
        if isinstance(source, int):
            return bool(source)
        return bool(values[source])

    def _source_for_port(self, port: str) -> str | int:
        """Return the logical source backing one fractional-LUT input port.

        Parameters
        ----------
        port : str
            Fractional-LUT input port name.

        Returns
        -------
        str | int
            Spec input name for variable sources, or integer constant ``0`` or
            ``1`` for tied ports.
        """
        token = _scalar_connection(self._cell, port, allow_missing=True)
        if token in {"0", "1"}:
            return int(token)

        source_name = self._source_name_for_token(token)
        if source_name not in self.spec_input_refs:
            self.spec_inputs.append(source_name)
            self.spec_input_refs[source_name] = self._adapter.src_port(port, 0)
        return source_name

    def _source_name_for_token(self, token: str) -> str:
        """Return a stable spec input name for one source net token.

        Parameters
        ----------
        token : str
            Source net token from the generic netlist view.

        Returns
        -------
        str
            Stable generated spec input name.
        """
        source_name = self._source_by_token.get(token)
        if source_name is not None:
            return source_name
        source_name = f"N{len(self.spec_inputs)}"
        self._source_by_token[token] = source_name
        return source_name


def _options_from_environment(env: MorphCircuitEnvironment) -> FracLutCircuitOptions:
    """Build fractional-LUT options from the shared environment.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared adapter environment.

    Returns
    -------
    FracLutCircuitOptions
        Adapter options.
    """
    raw_options = env.options.get("circuit_options")
    options = raw_options if isinstance(raw_options, dict) else {}
    frac_lut_options = options.get("frac_lut", {})
    return FracLutCircuitOptions.model_validate(frac_lut_options)


def _build_output_inits(
    lut_size: int,
    num_shared_inputs: int,
    l0_init: int,
    l1_init: int,
    select_as_data_used: bool,
    mux_select_config: int,
    spec_inputs: list[str],
    value_for_port: Callable[[str, dict[str, bool]], bool],
    output_names: tuple[str, ...],
) -> dict[str, int]:
    """Build fixed output truth tables for one fractional-LUT cell.

    Parameters
    ----------
    lut_size : int
        Internal LUT half width.
    num_shared_inputs : int
        Nominal shared input count.
    l0_init : int
        L0 INIT value.
    l1_init : int
        L1 INIT value.
    select_as_data_used : bool
        Whether select-as-data mode is active.
    mux_select_config : int
        Select-as-data output mux configuration.
    spec_inputs : list[str]
        Ordered spec input names.
    value_for_port : Callable[[str, dict[str, bool]], bool]
        Port-value lookup callback.
    output_names : tuple[str, ...]
        Connected output ports to model.

    Returns
    -------
    dict[str, int]
        INIT value per connected output.
    """
    output_inits = {output: 0 for output in output_names}
    for assignment_index in range(1 << len(spec_inputs)):
        values = {
            name: bool((assignment_index >> bit_index) & 1)
            for bit_index, name in enumerate(spec_inputs)
        }
        l0 = _eval_lut_init(
            l0_init,
            _index_bits_for_l0(lut_size, num_shared_inputs, select_as_data_used),
            value_for_port,
            values,
        )
        l1 = _eval_lut_init(
            l1_init,
            _index_bits_for_l1(lut_size, num_shared_inputs, select_as_data_used),
            value_for_port,
            values,
        )
        select = value_for_port("S", values)
        if select_as_data_used:
            o0 = l1 if mux_select_config else l0
        else:
            o0 = l1 if select else l0
        outputs = {"O0": o0, "O1": l1}
        for output_name in output_names:
            if outputs[output_name]:
                output_inits[output_name] |= 1 << assignment_index
    return output_inits


def _eval_lut_init(
    init: int,
    bit_ports: list[str],
    value_for_port: Callable[[str, dict[str, bool]], bool],
    values: dict[str, bool],
) -> bool:
    """Evaluate one LUT INIT from ordered bit ports.

    Parameters
    ----------
    init : int
        LSB-first LUT INIT value.
    bit_ports : list[str]
        Input port names in INIT-index bit order.
    value_for_port : Callable[[str, dict[str, bool]], bool]
        Callback that returns a port value for the current assignment.
    values : dict[str, bool]
        Current truth-table assignment keyed by spec input name.

    Returns
    -------
    bool
        Evaluated LUT output bit.
    """
    index = 0
    for bit_index, port in enumerate(bit_ports):
        if value_for_port(port, values):
            index |= 1 << bit_index
    return bool((init >> index) & 1)


def _index_bits_for_l0(
    lut_size: int,
    num_shared_inputs: int,
    select_as_data_used: bool,
) -> list[str]:
    """Return L0 input-index ports in least-significant-bit order.

    Parameters
    ----------
    lut_size : int
        Internal LUT half width.
    num_shared_inputs : int
        Nominal number of shared input pins.
    select_as_data_used : bool
        Whether select-as-data wiring is active.

    Returns
    -------
    list[str]
        L0 port names in INIT-index bit order.
    """
    if select_as_data_used:
        return _select_as_data_bits(lut_size, num_shared_inputs, "A")
    private_count = lut_size - num_shared_inputs
    return [f"I{i}" for i in range(num_shared_inputs)] + [
        f"A{i}" for i in range(private_count)
    ]


def _index_bits_for_l1(
    lut_size: int,
    num_shared_inputs: int,
    select_as_data_used: bool,
) -> list[str]:
    """Return L1 input-index ports in least-significant-bit order.

    Parameters
    ----------
    lut_size : int
        Internal LUT half width.
    num_shared_inputs : int
        Nominal number of shared input pins.
    select_as_data_used : bool
        Whether select-as-data wiring is active.

    Returns
    -------
    list[str]
        L1 port names in INIT-index bit order.
    """
    if select_as_data_used:
        return _select_as_data_bits(lut_size, num_shared_inputs, "B")
    private_count = lut_size - num_shared_inputs
    return [f"I{i}" for i in range(num_shared_inputs)] + [
        f"B{i}" for i in range(private_count)
    ]


def _select_as_data_bits(
    lut_size: int,
    num_shared_inputs: int,
    private_prefix: str,
) -> list[str]:
    """Return select-as-data index ports in least-significant-bit order.

    Parameters
    ----------
    lut_size : int
        Internal LUT half width.
    num_shared_inputs : int
        Nominal number of shared input pins.
    private_prefix : str
        Private input prefix for the selected LUT half, usually ``"A"`` or
        ``"B"``.

    Returns
    -------
    list[str]
        Port names in INIT-index bit order for select-as-data mode.
    """
    normal_private_count = lut_size - num_shared_inputs
    if num_shared_inputs == 0:
        return [f"{private_prefix}{i}" for i in range(normal_private_count)]

    bits = [f"I{i}" for i in range(num_shared_inputs - 1)]
    bits.extend(f"{private_prefix}{i}" for i in range(normal_private_count))
    if private_prefix == "A":
        bits.append("S")
    else:
        bits.append(f"I{num_shared_inputs - 1}")
    return bits


def _input_port_order(lut_size: int, num_shared_inputs: int) -> tuple[str, ...]:
    """Return deterministic fractional-LUT input port order.

    Parameters
    ----------
    lut_size : int
        Internal LUT half width.
    num_shared_inputs : int
        Nominal number of shared input pins.

    Returns
    -------
    tuple[str, ...]
        Shared inputs, private inputs, and select input in stable order.
    """
    private_count = lut_size - num_shared_inputs
    return (
        *(f"I{i}" for i in range(num_shared_inputs)),
        *(f"A{i}" for i in range(private_count)),
        *(f"B{i}" for i in range(private_count)),
        "S",
    )


def _parse_output_refs(
    adapter: FracLutCircuit,
    cell: MorphTileNetlistCell,
) -> dict[str, ReplacementPortRef]:
    """Parse connected scalar output ports.

    Parameters
    ----------
    adapter : FracLutCircuit
        Adapter used to build replacement references.
    cell : MorphTileNetlistCell
        Fractional-LUT source cell.

    Returns
    -------
    dict[str, ReplacementPortRef]
        Mapping from connected FRAC output port names to original-cell output
        references.
    """
    output_refs: dict[str, ReplacementPortRef] = {}
    for port in ("O0", "O1"):
        if port not in cell.connections:
            continue
        _scalar_connection(cell, port)
        output_refs[port] = adapter.src_port(port, 0)
    return output_refs


def _scalar_connection(
    cell: MorphTileNetlistCell,
    port: str,
    allow_missing: bool = False,
) -> str:
    """Return one scalar connection token.

    Parameters
    ----------
    cell : MorphTileNetlistCell
        Source cell.
    port : str
        Port name.
    allow_missing : bool
        Whether a missing port should be treated as constant zero.

    Returns
    -------
    str
        Connection token.

    Raises
    ------
    RuntimeError
        If the port is not scalar.
    """
    bits = cell.connections.get(port)
    if bits is None:
        if allow_missing:
            return "0"
        raise RuntimeError(f"Fractional LUT '{cell.cell_id}' is missing port {port}")
    if len(bits) != 1:
        raise RuntimeError(
            f"Fractional LUT '{cell.cell_id}' port {port} must be scalar"
        )
    return bits[0]


def _parse_int_parameter(
    parameters: dict[str, str],
    name: str,
    default: int | None = None,
) -> int:
    """Parse an integer-like parameter value.

    Parameters
    ----------
    parameters : dict[str, str]
        Cell parameter dictionary.
    name : str
        Parameter name to parse.
    default : int | None
        Optional value returned when the parameter is missing.

    Returns
    -------
    int
        Parsed integer value.

    Raises
    ------
    RuntimeError
        If the parameter is missing and no default is provided.
    """
    if name not in parameters:
        if default is None:
            raise RuntimeError(f"Missing fractional-LUT parameter {name}")
        return default
    text = _clean_parameter_text(parameters[name])
    if text.startswith("0x"):
        return int(text, 16)
    if "'" in text:
        return parse_init_literal(text, width=32)
    return int(text or "0", 10)


def _parse_bool_parameter(parameters: dict[str, str], name: str) -> bool:
    """Parse a Boolean-like parameter value.

    Parameters
    ----------
    parameters : dict[str, str]
        Cell parameter dictionary.
    name : str
        Parameter name to parse.

    Returns
    -------
    bool
        Parsed Boolean value.
    """
    return bool(_parse_int_parameter(parameters, name, default=0))


def _metadata_field(meta_data: str, key: str) -> str | None:
    """Return one semicolon-separated metadata value.

    Parameters
    ----------
    meta_data : str
        Metadata string emitted by the LUT combinator.
    key : str
        Metadata key to look up.

    Returns
    -------
    str | None
        Metadata value, or ``None`` when the key is absent.
    """
    meta_data = _clean_parameter_text(meta_data)
    for item in meta_data.split(";"):
        if "=" not in item:
            continue
        left, right = item.split("=", 1)
        if left == key:
            return right
    return None


def _clean_parameter_text(value: str) -> str:
    """Normalize a parameter value emitted by Yosys JSON.

    Parameters
    ----------
    value : str
        Raw parameter text.

    Returns
    -------
    str
        Parameter text with surrounding quotes removed.
    """
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1]
    return text


def _combined_init_signature(output_inits: dict[str, int]) -> int:
    """Combine multi-output INITs into one compact report signature.

    Parameters
    ----------
    output_inits : dict[str, int]
        Output INIT values keyed by output name.

    Returns
    -------
    int
        Deterministic compact signature used only for reports and summaries.
    """
    value = 0
    shift = 0
    for _name, init in sorted(output_inits.items()):
        width = max(1, init.bit_length())
        value |= init << shift
        shift += width
    return value
