"""Circuit graph and builder API.

This module defines the flat Boolean circuit representation consumed by the SAT encoder
and the convenience builders used by examples and importers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.sat_fab.config import ConfigKey
from fabulous.fabric_cad.fabxplore.modules.sat_fab.constants import ConfigKind, NodeKind
from fabulous.fabric_cad.fabxplore.modules.sat_fab.functions import Func, init_from_func
from fabulous.fabric_cad.fabxplore.modules.sat_fab.truth import (
    TruthTableSpec,
    init_from_function,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@dataclass(frozen=True)
class Signal:
    """One named one-bit signal.

    Attributes
    ----------
    name : str
        Stable signal name.
    """

    name: str


@dataclass
class Node:
    """One flat Boolean netlist node.

    Attributes
    ----------
    kind : NodeKind
        Node kind.
    name : str
        Instance name.
    ins : list[Signal]
        Input signals.
    out : Signal
        Output signal.
    k : int | None
        LUT or truth-table input count when applicable.
    init : int | None
        Fixed truth-table INIT for ``"TTABLE"`` nodes.
    """

    kind: NodeKind
    name: str
    ins: list[Signal]
    out: Signal
    k: int | None = None
    init: int | None = None


class _LutDispatcher:
    """Descriptor for class-level fast LUT and instance-level configurable LUT.

    The descriptor allows ``Circuit.lut(...)`` to create a fast truth-table
    target while ``circuit.lut(...)`` adds a configurable LUT node.
    """

    def __get__(self, obj: Circuit | None, owner: type[Circuit]) -> object:
        """Bind the LUT helper to either the class or an instance.

        Parameters
        ----------
        obj : Circuit | None
            Circuit instance, or ``None`` for class access.
        owner : type[Circuit]
            Owning class.

        Returns
        -------
        object
            Fast LUT constructor or configurable LUT builder.
        """
        if obj is None:
            return owner.fast_lut
        return obj.configurable_lut


class Circuit:
    """Flat combinational circuit.

    Parameters
    ----------
    name: str
        Circuit name.

    Attributes
    ----------
    lut: _LutDispatcher
        LUT helper descriptor.
    truth_table: TruthTableSpec
        Fast truth-table constructor.
    lut_truth_table: TruthTableSpec
        Fast truth-table constructor alias.
    NOT: Signal
        NOT gate signal.
    AND: Signal
        AND gate signal.
    OR: Signal
        OR gate signal.
    XOR: Signal
        XOR gate signal.
    MUX2: Signal
        2-to-1 multiplexer signal.
    ROUTE: Signal
        Route signal.
    LUT_NETWORK: list[Signal]
        List of LUT network signals.
    """

    lut: _LutDispatcher = _LutDispatcher()

    def __init__(self, name: str) -> None:
        self.name = name
        self.inputs_map: dict[str, Signal] = {}
        self.configs_map: dict[str, Signal] = {}
        self.internals_map: dict[str, Signal] = {}
        self.nodes: list[Node] = []
        self.outputs_map: dict[str, Signal] = {}
        self._net_id = 0

    @staticmethod
    def fast_lut(
        name: str,
        inputs: list[str],
        init: int | None = None,
        output: str = "Y",
        outputs: dict[str, int | Func | Callable[..., bool]] | None = None,
        function: Callable[[dict[str, bool]], bool] | None = None,
        reduce_lut_symmetry: bool = True,
    ) -> TruthTableSpec:
        """Create a fast fixed LUT/truth-table circuit.

        Parameters
        ----------
        name : str
            Target circuit name.
        inputs : list[str]
            Ordered input names. Input zero is the least significant INIT bit.
        init : int | None
            Single-output LSB-first INIT integer.
        output : str
            Single-output name used with ``init`` or ``function``.
        outputs : dict[str, int | Func | Callable[..., bool]] | None
            Multi-output mapping from output name to INIT integer.
        function : Callable[[dict[str, bool]], bool] | None
            Optional callable used to generate a single-output INIT.
        reduce_lut_symmetry : bool
            Whether CEGIS may canonicalize symmetric input examples.

        Returns
        -------
        TruthTableSpec
            Fast truth-table circuit.

        Raises
        ------
        ValueError
            If the output description is ambiguous or missing.
        """
        if outputs is not None and (init is not None or function is not None):
            raise ValueError("use either outputs= or init=/function=, not both")
        if outputs is None:
            if function is not None:
                init = init_from_function(inputs, function)
            if init is None:
                raise ValueError("fast LUT requires init=, outputs=, or function=")
            outputs = {output: init}
        init_outputs = {
            out_name: _coerce_output_init(inputs, out_value)
            for out_name, out_value in outputs.items()
        }
        return TruthTableSpec(
            name=name,
            inputs=inputs[:],
            outputs=init_outputs,
            reduce_lut_symmetry=reduce_lut_symmetry,
        )

    truth_table: TruthTableSpec = fast_lut
    lut_truth_table: TruthTableSpec = fast_lut

    @classmethod
    def from_blif(
        cls,
        path: str | Path,
        name: str | None = None,
        top: str | None = None,
        inputs: list[str] | None = None,
        configs: list[str] | None = None,
        config_prefixes: list[str] | None = None,
        outputs: list[str] | None = None,
        flatten: bool = True,
        max_truth_table_inputs: int = 12,
    ) -> Circuit:
        """Load a circuit from a BLIF file.

        Parameters
        ----------
        path : str | Path
            BLIF file path.
        name : str | None
            Optional circuit name.
        top : str | None
            Optional top model name.
        inputs : list[str] | None
            Normal input names.
        configs : list[str] | None
            Explicit external configuration names.
        config_prefixes : list[str] | None
            Prefixes used to classify model inputs as config bits.
        outputs : list[str] | None
            Output names.
        flatten : bool
            Whether to flatten defined ``.subckt`` instances.
        max_truth_table_inputs : int
            Maximum imported ``.names`` input count.

        Returns
        -------
        Circuit
            Imported flat circuit.
        """
        from fabulous.fabric_cad.fabxplore.modules.sat_fab.import_blif import (
            circuit_from_blif,
        )

        return circuit_from_blif(
            path,
            name=name,
            top=top,
            inputs=inputs,
            configs=configs,
            config_prefixes=config_prefixes,
            outputs=outputs,
            flatten=flatten,
            max_truth_table_inputs=max_truth_table_inputs,
        )

    def input(self, name: str) -> Signal:
        """Create or return a primary input signal.

        Parameters
        ----------
        name : str
            Primary input name.

        Returns
        -------
        Signal
            Input signal.
        """
        if name not in self.inputs_map:
            self.inputs_map[name] = Signal(name)
        return self.inputs_map[name]

    def inputs(self, *names: str) -> tuple[Signal, ...]:
        """Create or return several primary input signals.

        Parameters
        ----------
        *names : str
            Primary input names.

        Returns
        -------
        tuple[Signal, ...]
            Input signals in the requested order.
        """
        return tuple(self.input(name) for name in names)

    def config(self, name: str) -> Signal:
        """Create or return an external configuration input signal.

        Parameters
        ----------
        name : str
            External configuration input name.

        Returns
        -------
        Signal
            Configuration signal.
        """
        if name not in self.configs_map:
            self.configs_map[name] = Signal(name)
        return self.configs_map[name]

    def configs(self, *names: str) -> tuple[Signal, ...]:
        """Create or return several external configuration signals.

        Parameters
        ----------
        *names : str
            External configuration input names.

        Returns
        -------
        tuple[Signal, ...]
            Configuration signals in the requested order.
        """
        return tuple(self.config(name) for name in names)

    def signal(self, name: str) -> Signal:
        """Return any known signal or create an internal signal.

        Parameters
        ----------
        name : str
            Signal name.

        Returns
        -------
        Signal
            Existing primary input, config input, or internal signal.
        """
        if name in self.inputs_map:
            return self.inputs_map[name]
        if name in self.configs_map:
            return self.configs_map[name]
        if name not in self.internals_map:
            self.internals_map[name] = Signal(f"{self.name}.{name}")
        return self.internals_map[name]

    def wire(self, name: str | None = None) -> Signal:
        """Create an internal wire.

        Parameters
        ----------
        name : str | None
            Optional local wire name.

        Returns
        -------
        Signal
            Internal signal.
        """
        if name is None:
            self._net_id += 1
            name = f"n{self._net_id}"
        return self.signal(name)

    def const(self, value: bool | int, name: str | None = None) -> Signal:
        """Add a constant node.

        Parameters
        ----------
        value : bool | int
            Boolean-like constant value.
        name : str | None
            Optional local instance name.

        Returns
        -------
        Signal
            Constant output signal.
        """
        inst = name or f"const_{int(bool(value))}_{len(self.nodes)}"
        out = self.wire(inst)
        kind = NodeKind.CONST1 if value else NodeKind.CONST0
        self.nodes.append(Node(kind, inst, [], out))
        return out

    def output(self, name: str, signal: Signal) -> None:
        """Register a circuit output.

        Parameters
        ----------
        name : str
            Output port name.
        signal : Signal
            Signal that drives the output.
        """
        self.outputs_map[name] = signal

    def output_names(self) -> list[str]:
        """Return ordered output names.

        Returns
        -------
        list[str]
            Output names in insertion order.
        """
        return list(self.outputs_map.keys())

    def input_names(self) -> list[str]:
        """Return ordered input names.

        Returns
        -------
        list[str]
            Input names in insertion order.
        """
        return list(self.inputs_map.keys())

    def config_names(self) -> list[str]:
        """Return ordered external configuration input names.

        Returns
        -------
        list[str]
            External configuration input names in insertion order.
        """
        return list(self.configs_map.keys())

    def not_(self, arg: Signal, name: str | None = None) -> Signal:
        """Add a NOT gate.

        Parameters
        ----------
        arg : Signal
            Input signal.
        name : str | None
            Optional instance name.

        Returns
        -------
        Signal
            Gate output.
        """
        return self._node(NodeKind.NOT, [arg], name)

    def and_(self, left: Signal, right: Signal, name: str | None = None) -> Signal:
        """Add an AND gate.

        Parameters
        ----------
        left : Signal
            First input signal.
        right : Signal
            Second input signal.
        name : str | None
            Optional instance name.

        Returns
        -------
        Signal
            Gate output.
        """
        return self._node(NodeKind.AND, [left, right], name)

    def or_(self, left: Signal, right: Signal, name: str | None = None) -> Signal:
        """Add an OR gate.

        Parameters
        ----------
        left : Signal
            First input signal.
        right : Signal
            Second input signal.
        name : str | None
            Optional instance name.

        Returns
        -------
        Signal
            Gate output.
        """
        return self._node(NodeKind.OR, [left, right], name)

    def xor(self, left: Signal, right: Signal, name: str | None = None) -> Signal:
        """Add an XOR gate.

        Parameters
        ----------
        left : Signal
            First input signal.
        right : Signal
            Second input signal.
        name : str | None
            Optional instance name.

        Returns
        -------
        Signal
            Gate output.
        """
        return self._node(NodeKind.XOR, [left, right], name)

    def mux(
        self,
        sel: Signal,
        d0: Signal,
        d1: Signal,
        name: str | None = None,
    ) -> Signal:
        """Add a two-input mux.

        Parameters
        ----------
        sel : Signal
            Selector signal.
        d0 : Signal
            Data selected when ``sel`` is false.
        d1 : Signal
            Data selected when ``sel`` is true.
        name : str | None
            Optional instance name.

        Returns
        -------
        Signal
            Mux output.
        """
        return self._node(NodeKind.ITE, [sel, d1, d0], name)

    def route(self, candidates: list[Signal], name: str) -> Signal:
        """Add a configurable one-hot routing mux.

        Parameters
        ----------
        candidates : list[Signal]
            Candidate signals the route may select.
        name : str
            Route instance name.

        Returns
        -------
        Signal
            Route output signal.

        Raises
        ------
        ValueError
            If fewer than two candidates are provided.
        """
        if len(candidates) < 2:
            raise ValueError("route needs at least two candidates")
        out = self.wire(f"{name}_Y")
        self.nodes.append(Node(NodeKind.ROUTE, name, candidates[:], out))
        return out

    def routed_lut(
        self,
        name: str,
        k: int,
        candidates: list[Signal],
        allow_reuse: bool = True,
    ) -> Signal:
        """Add a LUT whose input pins are driven by configurable routes.

        Parameters
        ----------
        name : str
            LUT instance name.
        k : int
            Number of LUT input pins.
        candidates : list[Signal]
            Candidate signals for each input route.
        allow_reuse : bool
            Whether multiple pins may select the same signal. The current SAT
            encoding allows reuse; this flag is reserved for stricter future
            encodings.

        Returns
        -------
        Signal
            LUT output signal.
        """
        _ = allow_reuse
        pins = [
            self.route(candidates, name=f"{name}.a{pin_index}")
            for pin_index in range(k)
        ]
        return self.lut(pins, name=name)

    def mux_tree(
        self,
        data: list[Signal],
        sels: list[Signal],
        name: str | None = None,
    ) -> Signal:
        """Build an LSB-first mux tree.

        Parameters
        ----------
        data : list[Signal]
            Data signals where index zero is selected by all-zero selectors.
        sels : list[Signal]
            LSB-first selector signals.
        name : str | None
            Optional instance prefix.

        Returns
        -------
        Signal
            Mux tree output.

        Raises
        ------
        ValueError
            If the data count is not ``2 ** len(sels)``.
        """
        if len(data) != (1 << len(sels)):
            raise ValueError("mux_tree data count must be 2 ** len(sels)")
        level = data[:]
        prefix = name or "mux_tree"
        for sel_index, sel in enumerate(sels):
            nxt: list[Signal] = []
            for pair_index in range(0, len(level), 2):
                nxt.append(
                    self.mux(
                        sel,
                        d0=level[pair_index],
                        d1=level[pair_index + 1],
                        name=f"{prefix}_{sel_index}_{pair_index // 2}",
                    )
                )
            level = nxt
        return level[0]

    def reduce_xor(self, signals: list[Signal], name: str | None = None) -> Signal:
        """Build an XOR reduction.

        Parameters
        ----------
        signals : list[Signal]
            Signals to reduce.
        name : str | None
            Optional instance prefix.

        Returns
        -------
        Signal
            Reduction output.
        """
        return self._reduce(signals, self.xor, "xor", name)

    def reduce_or(self, signals: list[Signal], name: str | None = None) -> Signal:
        """Build an OR reduction.

        Parameters
        ----------
        signals : list[Signal]
            Signals to reduce.
        name : str | None
            Optional instance prefix.

        Returns
        -------
        Signal
            Reduction output.
        """
        return self._reduce(signals, self.or_, "or", name)

    def reduce_and(self, signals: list[Signal], name: str | None = None) -> Signal:
        """Build an AND reduction.

        Parameters
        ----------
        signals : list[Signal]
            Signals to reduce.
        name : str | None
            Optional instance prefix.

        Returns
        -------
        Signal
            Reduction output.
        """
        return self._reduce(signals, self.and_, "and", name)

    def truth_block(
        self,
        name: str,
        inputs: list[Signal],
        outputs: dict[str, int | Func | Callable[..., bool]],
    ) -> tuple[Signal, ...]:
        """Add a fixed multi-output truth-table block.

        Parameters
        ----------
        name : str
            Block instance prefix.
        inputs : list[Signal]
            Ordered input signals.
        outputs : dict[str, int | Func | Callable[..., bool]]
            Mapping from output suffix to INIT, Func, or callable.

        Returns
        -------
        tuple[Signal, ...]
            Output signals in mapping order.
        """
        input_names = [_pretty_signal_name(signal) for signal in inputs]
        result: list[Signal] = []
        for output_name, output_func in outputs.items():
            init = _coerce_output_init(input_names, output_func)
            result.append(self.ttable(inputs, init, name=f"{name}.{output_name}"))
        return tuple(result)

    def lut_network(
        self,
        name: str,
        inputs: list[Signal],
        lut_sizes: list[int],
        outputs: int = 1,
        allow_routes: bool = True,
    ) -> list[Signal]:
        """Build a configurable cascaded LUT network.

        Parameters
        ----------
        name : str
            Network instance prefix.
        inputs : list[Signal]
            Initial candidate input signals.
        lut_sizes : list[int]
            LUT sizes to instantiate in order.
        outputs : int
            Number of final LUT outputs to return.
        allow_routes : bool
            Whether each LUT pin is driven through a configurable route.

        Returns
        -------
        list[Signal]
            Requested network output signals.

        Raises
        ------
        ValueError
            If no LUTs are requested or too many outputs are requested.
        """
        if not lut_sizes:
            raise ValueError("lut_network needs at least one LUT")
        if outputs < 1 or outputs > len(lut_sizes):
            raise ValueError("outputs must be between 1 and number of LUTs")
        available = inputs[:]
        lut_outputs: list[Signal] = []
        for lut_index, k in enumerate(lut_sizes):
            inst = f"{name}_LUT{lut_index}"
            if allow_routes:
                out = self.routed_lut(inst, k=k, candidates=available)
            else:
                pins = available[:k]
                while len(pins) < k:
                    pins.append(self.const(False, name=f"{inst}_pad{len(pins)}"))
                out = self.lut(pins, name=inst)
            available.append(out)
            lut_outputs.append(out)
        return lut_outputs[-outputs:]

    def ttable(
        self,
        inputs: list[Signal],
        init: int,
        name: str,
        output: Signal | None = None,
    ) -> Signal:
        """Add a fixed truth-table node.

        Parameters
        ----------
        inputs : list[Signal]
            Ordered input signals. Input zero is the least significant index bit.
        init : int
            LSB-first truth-table INIT.
        name : str
            Node instance name.
        output : Signal | None
            Optional pre-existing output signal.

        Returns
        -------
        Signal
            Truth-table output.
        """
        out = output or self.wire(f"{name}_Y")
        self.nodes.append(
            Node("TTABLE", name, inputs[:], out, k=len(inputs), init=init)
        )
        return out

    def config_keys(self, role: str) -> list[ConfigKey]:
        """Return all configuration keys owned by this circuit.

        Parameters
        ----------
        role : str
            Circuit role used to scope the keys.

        Returns
        -------
        list[ConfigKey]
            Configuration keys for external configs, LUT INITs, and routes.
        """
        keys = [
            ConfigKey(role, ConfigKind.INPUT, name, 0) for name in self.config_names()
        ]
        for node in self.nodes:
            if node.kind == NodeKind.LUT:
                assert node.k is not None
                keys.extend(
                    ConfigKey(role, ConfigKind.LUT, node.name, index)
                    for index in range(1 << node.k)
                )
            elif node.kind == NodeKind.ROUTE:
                keys.extend(
                    ConfigKey(role, ConfigKind.ROUTE, node.name, index)
                    for index in range(len(node.ins))
                )
        return keys

    def cone_nodes(self, output_names: list[str] | None = None) -> list[Node]:
        """Return nodes in the transitive fan-in cone of selected outputs.

        Parameters
        ----------
        output_names : list[str] | None
            Output names to keep. ``None`` keeps all outputs.

        Returns
        -------
        list[Node]
            Topologically ordered cone nodes.
        """
        selected = output_names or self.output_names()
        needed_signals = set()
        for name in selected:
            needed_signals.add(self.outputs_map[name].name)
        needed_nodes: set[int] = set()
        for index in range(len(self.nodes) - 1, -1, -1):
            node = self.nodes[index]
            if node.out.name in needed_signals:
                needed_nodes.add(index)
                needed_signals.update(sig.name for sig in node.ins)
        return [node for index, node in enumerate(self.nodes) if index in needed_nodes]

    def eval_concrete(
        self,
        inputs: dict[str, bool],
        config: dict[ConfigKey, bool],
        role: str,
    ) -> dict[str, bool]:
        """Evaluate the circuit concretely.

        Parameters
        ----------
        inputs : dict[str, bool]
            Primary input values.
        config : dict[ConfigKey, bool]
            Concrete configuration values keyed by role-scoped config keys.
        role : str
            Circuit role used to look up configuration keys.

        Returns
        -------
        dict[str, bool]
            Concrete output values.

        Raises
        ------
        KeyError
            If a required input or configuration bit is missing.
        ValueError
            If the circuit contains an unknown node kind.
        """
        values: dict[str, bool] = {}
        for name in self.input_names():
            values[name] = bool(inputs[name])
        for name in self.config_names():
            values[name] = bool(config[ConfigKey(role, ConfigKind.INPUT, name, 0)])
        for node in self.nodes:
            in_vals = [values[sig.name] for sig in node.ins]
            if node.kind == NodeKind.CONST0:
                out = False
            elif node.kind == NodeKind.CONST1:
                out = True
            elif node.kind == NodeKind.NOT:
                out = not in_vals[0]
            elif node.kind == NodeKind.AND:
                out = in_vals[0] and in_vals[1]
            elif node.kind == NodeKind.OR:
                out = in_vals[0] or in_vals[1]
            elif node.kind == NodeKind.XOR:
                out = in_vals[0] ^ in_vals[1]
            elif node.kind == NodeKind.ITE:
                out = in_vals[1] if in_vals[0] else in_vals[2]
            elif node.kind == NodeKind.TTABLE:
                assert node.init is not None
                idx = _index_from_bits(in_vals)
                out = bool((node.init >> idx) & 1)
            elif node.kind == NodeKind.LUT:
                assert node.k is not None
                idx = _index_from_bits(in_vals)
                out = bool(config[ConfigKey(role, ConfigKind.LUT, node.name, idx)])
            elif node.kind == NodeKind.ROUTE:
                selected = None
                for idx, value in enumerate(in_vals):
                    key = ConfigKey(role, ConfigKind.ROUTE, node.name, idx)
                    if config[key]:
                        selected = value
                        break
                if selected is None:
                    raise KeyError(f"no selected route value for {node.name}")
                out = selected
            else:
                raise ValueError(f"unknown node kind {node.kind}")
            values[node.out.name] = bool(out)
        return {name: values[sig.name] for name, sig in self.outputs_map.items()}

    def configurable_lut(self, inputs: list[Signal], name: str) -> Signal:
        """Add a configurable LUT node.

        Parameters
        ----------
        inputs : list[Signal]
            Ordered LUT input signals.
        name : str
            LUT instance name.

        Returns
        -------
        Signal
            LUT output signal.
        """
        out = self.wire(f"{name}_Y")
        self.nodes.append(Node(NodeKind.LUT, name, inputs[:], out, k=len(inputs)))
        return out

    def _node(self, kind: NodeKind, inputs: list[Signal], name: str | None) -> Signal:
        """Add a generic primitive node.

        Parameters
        ----------
        kind : NodeKind
            Primitive kind.
        inputs : list[Signal]
            Input signals.
        name : str | None
            Optional instance name.

        Returns
        -------
        Signal
            Node output signal.
        """
        inst = name or f"{kind.lower()}_{len(self.nodes)}"
        out = self.wire(inst)
        self.nodes.append(Node(kind, inst, inputs[:], out))
        return out

    def _reduce(
        self,
        signals: list[Signal],
        op: Callable[..., Signal],
        prefix: str,
        name: str | None,
    ) -> Signal:
        """Build a binary tree reduction.

        Parameters
        ----------
        signals : list[Signal]
            Signals to reduce.
        op : Callable[..., Signal]
            Binary builder method.
        prefix : str
            Default name prefix.
        name : str | None
            Optional name prefix.

        Returns
        -------
        Signal
            Reduction output.

        Raises
        ------
        ValueError
            If ``signals`` is empty.
        """
        if not signals:
            raise ValueError("reduction needs at least one signal")
        if len(signals) == 1:
            return signals[0]
        acc = signals[0]
        base = name or prefix
        for index, signal in enumerate(signals[1:], start=1):
            acc = op(acc, signal, name=f"{base}_{index}")
        return acc

    NOT: Signal = not_
    AND: Signal = and_
    OR: Signal = or_
    XOR: Signal = xor
    MUX2: Signal = mux
    ROUTE: Signal = route
    LUT_NETWORK: list[Signal] = lut_network


def _index_from_bits(bits: list[bool]) -> int:
    """Build an LSB-first truth-table index.

    Parameters
    ----------
    bits : list[bool]
        Boolean input bits.

    Returns
    -------
    int
        LSB-first index.
    """
    index = 0
    for bit_index, value in enumerate(bits):
        if value:
            index |= 1 << bit_index
    return index


def _coerce_output_init(
    inputs: list[str],
    value: int | Func | Callable[..., bool],
) -> int:
    """Convert a truth-table output description to an INIT integer.

    Parameters
    ----------
    inputs : list[str]
        Ordered input names.
    value : int | Func | Callable[..., bool]
        INIT integer, Func expression, or Python callable.

    Returns
    -------
    int
        LSB-first INIT integer.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, Func):
        return init_from_func(inputs, value)
    return init_from_func(inputs, value)


def _pretty_signal_name(signal: Signal) -> str:
    """Return a user-facing signal name.

    Parameters
    ----------
    signal : Signal
        Signal to name.

    Returns
    -------
    str
        Local signal name with circuit prefix removed when present.
    """
    return signal.name.split(".")[-1]
