"""Morph-tile circuit adapter for generic ``__chain`` cells.

The chain mapper emits target-independent ``__chain`` cells for reduction and
ALU/carry structures. This adapter treats each emitted cell as a fixed
multi-output truth table and asks SAT-fab whether the target morph tile can
realize that local chain step. Reduction modes constrain only ``CO`` because
``Y`` is intentionally unused by the chain mapper. ``ADD`` constrains the
connected outputs among ``Y`` and ``CO``.
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


class ChainCircuitOptions(BaseModel):
    """Options for the generic ``__chain`` circuit adapter.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    cell_types : list[str]
        Netlist cell types recognized as generic chain cells.
    enable_permute_cache : bool
        Whether input-permutation-equivalent chain truth tables may share cache
        entries.
    """

    model_config = ConfigDict(frozen=True)

    cell_types: list[str] = Field(default_factory=lambda: ["__chain"])
    enable_permute_cache: bool = True


@dataclass(frozen=True)
class ChainCandidate:
    """Represent one emitted generic chain candidate.

    Attributes
    ----------
    cell_id : str
        Cell name in the selected top module.
    mode : str
        Chain mode, for example ``"REDUCE_OR"`` or ``"ADD"``.
    n : int
        Local chain input width.
    init : int
        Local INIT truth table used by the chain cell.
    alu_init_mode : str
        ALU INIT encoding mode from the source cell.
    spec_inputs : list[str]
        Input names used by the generated SAT-fab spec.
    spec_input_refs : dict[str, ReplacementPortRef]
        Mapping from spec input name to original chain-cell input port.
    output_inits : dict[str, int]
        Multi-output truth-table INITs keyed by spec output name.
    output_refs : dict[str, ReplacementPortRef]
        Mapping from spec output name to original chain-cell output port.
    """

    cell_id: str
    mode: str
    n: int
    init: int
    alu_init_mode: str
    spec_inputs: list[str]
    spec_input_refs: dict[str, ReplacementPortRef]
    output_inits: dict[str, int]
    output_refs: dict[str, ReplacementPortRef]


class ChainCircuit(MorphCircuitAdapter[ChainCandidate]):
    """Describe and solve generic ``__chain`` morph candidates.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared adapter environment.
    options : ChainCircuitOptions
        Adapter-local configuration.

    Attributes
    ----------
    kind
        Adapter kind identifier.
    """

    kind = MorphCircuitKind.CHAIN

    def __init__(
        self,
        env: MorphCircuitEnvironment,
        options: ChainCircuitOptions,
    ) -> None:
        super().__init__(env)
        self.options = options
        self._cell_type_set = set(options.cell_types)

    def filter_summary(self) -> dict[str, list[str]]:
        """Return selected chain filters.

        Returns
        -------
        dict[str, list[str]]
            Selected cell types and cache options.
        """
        return {
            "chain.cell_types": list(self.options.cell_types),
            "chain.enable_permute_cache": [str(self.options.enable_permute_cache)],
        }

    def iter_candidates(self, context: MorphTileContext) -> Iterable[ChainCandidate]:
        """Yield generic chain candidates from the design.

        Parameters
        ----------
        context : MorphTileContext
            Runtime mapping context.

        Yields
        ------
        ChainCandidate
            Parsed chain candidates in reader order.
        """
        for cell in context.design.cells:
            candidate = self._parse_candidate(cell)
            if candidate is not None:
                yield candidate

    def is_enabled_candidate(self, candidate: ChainCandidate) -> bool:
        """Return whether a chain candidate should be attempted.

        Parameters
        ----------
        candidate : ChainCandidate
            Chain candidate.

        Returns
        -------
        bool
            ``True`` for all parsed chain candidates.
        """
        return candidate.n >= 1 and bool(candidate.output_inits)

    def solve(self, candidate: ChainCandidate) -> MorphSolveOutcome:
        """Solve one generic chain candidate.

        Parameters
        ----------
        candidate : ChainCandidate
            Candidate to solve.

        Returns
        -------
        MorphSolveOutcome
            SAT result plus cache status.
        """
        return self.solve_truth_table_cached(
            name="chain_spec",
            input_names=candidate.spec_inputs,
            output_inits=candidate.output_inits,
            enable_permute_cache=self.options.enable_permute_cache,
            reduce_lut_symmetry=False,
        )

    def make_replacement(
        self,
        candidate: ChainCandidate,
        result: CutSolveResult,
    ) -> MorphTileReplacement:
        """Build a replacement for one solved chain candidate.

        Parameters
        ----------
        candidate : ChainCandidate
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
            width=candidate.n,
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

    def width_label(self, candidate: ChainCandidate) -> str:
        """Return the report width label for a chain candidate.

        Parameters
        ----------
        candidate : ChainCandidate
            Candidate to label.

        Returns
        -------
        str
            Human-readable width label.
        """
        return f"CHAIN:{candidate.mode}:N{candidate.n}"

    def init_label(self, candidate: ChainCandidate) -> str:
        """Return the report INIT label for a chain candidate.

        Parameters
        ----------
        candidate : ChainCandidate
            Candidate to label.

        Returns
        -------
        str
            Human-readable INIT label.
        """
        return f"CHAIN:{candidate.mode}:N{candidate.n}:0x{candidate.init:x}"

    def _parse_candidate(
        self,
        cell: MorphTileNetlistCell,
    ) -> ChainCandidate | None:
        """Parse one generic cell into a chain candidate.

        Parameters
        ----------
        cell : MorphTileNetlistCell
            Generic source-design cell.

        Returns
        -------
        ChainCandidate | None
            Parsed candidate, or ``None`` for non-chain cells.
        """
        if cell.cell_type not in self._cell_type_set:
            return None

        n = _parse_int_parameter(cell.parameters, "N", default=1)
        mode = _clean_parameter_text(cell.parameters.get("MODE", "REDUCE_OR"))
        init = parse_init_literal(str(cell.parameters.get("INIT", "0")), n)
        alu_init_mode = _clean_parameter_text(
            cell.parameters.get("ALU_INIT_MODE", "xor")
        )

        input_view = _ChainInputView(self, cell, n, ("I", "CI"))
        output_refs = _parse_output_refs(self, cell, mode)
        if not output_refs:
            return None

        output_inits = _build_output_inits(
            mode=mode,
            n=n,
            init=init,
            alu_init_mode=alu_init_mode,
            spec_inputs=input_view.spec_inputs,
            value_for=input_view.value_for,
            output_names=tuple(output_refs),
        )
        return ChainCandidate(
            cell_id=cell.cell_id,
            mode=mode,
            n=n,
            init=init,
            alu_init_mode=alu_init_mode,
            spec_inputs=input_view.spec_inputs,
            spec_input_refs=input_view.spec_input_refs,
            output_inits=output_inits,
            output_refs=output_refs,
        )


class _ChainInputView:
    """Create a variable view over chain-cell input port connections.

    Parameters
    ----------
    adapter : ChainCircuit
        Adapter used to build replacement references.
    cell : MorphTileNetlistCell
        Chain source cell.
    n : int
        Local chain input width.
    ports : tuple[str, ...]
        Input ports that contribute to the modeled chain behavior.
    """

    def __init__(
        self,
        adapter: ChainCircuit,
        cell: MorphTileNetlistCell,
        n: int,
        ports: tuple[str, ...],
    ) -> None:
        self._adapter = adapter
        self._cell = cell
        self._n = n
        self.spec_inputs: list[str] = []
        self.spec_input_refs: dict[str, ReplacementPortRef] = {}
        self._source_by_token: dict[str, str] = {}
        self._values: dict[tuple[str, int], str | int] = {}
        for port in ports:
            width = 1 if port == "CI" else n
            for index in range(width):
                self._values[(port, index)] = self._source_for_port_bit(port, index)

    def value_for(
        self,
        port: str,
        index: int,
        values: dict[str, bool],
    ) -> bool:
        """Return one port-bit value for a truth-table assignment.

        Parameters
        ----------
        port : str
            Chain input port.
        index : int
            Bit index within ``port``.
        values : dict[str, bool]
            Current truth-table input assignment.

        Returns
        -------
        bool
            Boolean port-bit value.
        """
        source = self._values.get((port, index), 0)
        if isinstance(source, int):
            return bool(source)
        return bool(values[source])

    def _source_for_port_bit(self, port: str, index: int) -> str | int:
        """Return the logical source backing one chain input bit.

        Parameters
        ----------
        port : str
            Chain input port.
        index : int
            Bit index within ``port``.

        Returns
        -------
        str | int
            Spec input name for variable sources, or integer constant ``0`` or
            ``1`` for tied ports.
        """
        token = _connection_bit(self._cell, port, index, allow_missing=True)
        if token in {"0", "1"}:
            return int(token)

        source_name = self._source_name_for_token(token)
        if source_name not in self.spec_input_refs:
            self.spec_inputs.append(source_name)
            self.spec_input_refs[source_name] = self._adapter.src_port(port, index)
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


def _parse_output_refs(
    adapter: ChainCircuit,
    cell: MorphTileNetlistCell,
    mode: str,
) -> dict[str, ReplacementPortRef]:
    """Parse connected chain outputs relevant for the mode.

    Parameters
    ----------
    adapter : ChainCircuit
        Adapter used to build replacement references.
    cell : MorphTileNetlistCell
        Chain source cell.
    mode : str
        Chain mode.

    Returns
    -------
    dict[str, ReplacementPortRef]
        Mapping from modeled chain output names to original-cell output refs.
    """
    ports = ("Y", "CO") if mode == "ADD" else ("CO",)
    output_refs: dict[str, ReplacementPortRef] = {}
    for port in ports:
        if port not in cell.connections:
            continue
        _scalar_connection(cell, port)
        output_refs[port] = adapter.src_port(port, 0)
    return output_refs


def _build_output_inits(
    mode: str,
    n: int,
    init: int,
    alu_init_mode: str,
    spec_inputs: list[str],
    value_for: Callable[[str, int, dict[str, bool]], bool],
    output_names: tuple[str, ...],
) -> dict[str, int]:
    """Build fixed output truth tables for one chain cell.

    Parameters
    ----------
    mode : str
        Chain mode.
    n : int
        Local chain input width.
    init : int
        Local INIT truth table.
    alu_init_mode : str
        ALU INIT encoding mode.
    spec_inputs : list[str]
        Ordered spec input names.
    value_for : Callable[[str, int, dict[str, bool]], bool]
        Port-bit value lookup callback.
    output_names : tuple[str, ...]
        Connected output ports to model.

    Returns
    -------
    dict[str, int]
        INIT value per modeled output.
    """
    output_inits = {output: 0 for output in output_names}
    for assignment_index in range(1 << len(spec_inputs)):
        values = {
            name: bool((assignment_index >> bit_index) & 1)
            for bit_index, name in enumerate(spec_inputs)
        }
        outputs = _eval_outputs(
            mode=mode,
            n=n,
            init=init,
            alu_init_mode=alu_init_mode,
            value_for=value_for,
            values=values,
        )
        for output_name in output_names:
            if outputs[output_name]:
                output_inits[output_name] |= 1 << assignment_index
    return output_inits


def _eval_outputs(
    mode: str,
    n: int,
    init: int,
    alu_init_mode: str,
    value_for: Callable[[str, int, dict[str, bool]], bool],
    values: dict[str, bool],
) -> dict[str, bool]:
    """Evaluate chain outputs for one truth-table assignment.

    Parameters
    ----------
    mode : str
        Chain mode.
    n : int
        Local chain input width.
    init : int
        Local INIT truth table.
    alu_init_mode : str
        ALU INIT encoding mode.
    value_for : Callable[[str, int, dict[str, bool]], bool]
        Port-bit value lookup callback.
    values : dict[str, bool]
        Current truth-table assignment.

    Returns
    -------
    dict[str, bool]
        Evaluated ``Y`` and ``CO`` values.
    """
    local = _eval_init(init, n, value_for, values)
    ci = value_for("CI", 0, values)
    if mode == "REDUCE_OR":
        return {"Y": local, "CO": ci or local}
    if mode == "REDUCE_AND":
        return {"Y": local, "CO": ci and local}
    if mode == "REDUCE_XOR":
        return {"Y": local, "CO": ci ^ local}
    if mode == "ADD":
        return _eval_add_outputs(
            n=n,
            local=local,
            alu_init_mode=alu_init_mode,
            value_for=value_for,
            values=values,
        )
    return {"Y": local, "CO": local}


def _eval_add_outputs(
    n: int,
    local: bool,
    alu_init_mode: str,
    value_for: Callable[[str, int, dict[str, bool]], bool],
    values: dict[str, bool],
) -> dict[str, bool]:
    """Evaluate ADD-mode chain outputs.

    Parameters
    ----------
    n : int
        Local chain input width.
    local : bool
        INIT result for the local input vector.
    alu_init_mode : str
        ALU INIT encoding mode.
    value_for : Callable[[str, int, dict[str, bool]], bool]
        Port-bit value lookup callback.
    values : dict[str, bool]
        Current truth-table assignment.

    Returns
    -------
    dict[str, bool]
        Evaluated ``Y`` and ``CO`` values.
    """
    ci = value_for("CI", 0, values)
    if alu_init_mode == "full_adder" and n >= 3:
        a = value_for("I", 1, values)
        b = value_for("I", 0, values)
        return {"Y": local, "CO": (a and b) or (a and ci) or (b and ci)}

    a = value_for("I", 1 if n > 1 else 0, values)
    b = value_for("I", 0, values)
    return {"Y": local ^ ci, "CO": (a and b) or (a and ci) or (b and ci)}


def _eval_init(
    init: int,
    n: int,
    value_for: Callable[[str, int, dict[str, bool]], bool],
    values: dict[str, bool],
) -> bool:
    """Evaluate one local chain INIT.

    Parameters
    ----------
    init : int
        INIT truth table.
    n : int
        Local input width.
    value_for : Callable[[str, int, dict[str, bool]], bool]
        Port-bit value lookup callback.
    values : dict[str, bool]
        Current truth-table assignment.

    Returns
    -------
    bool
        Evaluated INIT bit.
    """
    index = 0
    for bit_index in range(n):
        if value_for("I", bit_index, values):
            index |= 1 << bit_index
    return bool((init >> index) & 1)


def _scalar_connection(cell: MorphTileNetlistCell, port: str) -> str:
    """Return one scalar connection token.

    Parameters
    ----------
    cell : MorphTileNetlistCell
        Source cell.
    port : str
        Port name.

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
        raise RuntimeError(f"Chain '{cell.cell_id}' is missing port {port}")
    if len(bits) != 1:
        raise RuntimeError(f"Chain '{cell.cell_id}' port {port} must be scalar")
    return bits[0]


def _connection_bit(
    cell: MorphTileNetlistCell,
    port: str,
    index: int,
    allow_missing: bool = False,
) -> str:
    """Return one vector connection token.

    Parameters
    ----------
    cell : MorphTileNetlistCell
        Source cell.
    port : str
        Port name.
    index : int
        Bit index within ``port``.
    allow_missing : bool
        Whether missing or short ports should be treated as constant zero.

    Returns
    -------
    str
        Connection token.

    Raises
    ------
    RuntimeError
        If the requested bit is absent and ``allow_missing`` is ``False``.
    """
    bits = cell.connections.get(port)
    if bits is None or index >= len(bits):
        if allow_missing:
            return "0"
        raise RuntimeError(f"Chain '{cell.cell_id}' is missing {port}[{index}]")
    return bits[index]


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
            raise RuntimeError(f"Missing chain parameter {name}")
        return default
    text = _clean_parameter_text(parameters[name])
    if text.startswith("0x"):
        return int(text, 16)
    if "'" in text:
        return parse_init_literal(text, width=32)
    if text and all(ch in "01_" for ch in text):
        return int(text.replace("_", ""), 2)
    return int(text or "0", 10)


def _clean_parameter_text(value: object) -> str:
    """Normalize a parameter value emitted by Yosys JSON.

    Parameters
    ----------
    value : object
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
