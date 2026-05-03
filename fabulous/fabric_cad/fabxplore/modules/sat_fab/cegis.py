"""CEGIS solver for configurable circuit equivalence.

This module implements the exists-forall problem with a persistent outer SAT solver and
a counterexample checker.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from random import Random
from typing import Any

from pysat.formula import CNF, IDPool
from pysat.solvers import Solver

from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import Circuit, Node
from fabulous.fabric_cad.fabxplore.modules.sat_fab.cnf import (
    add_eq,
    add_or,
    add_xor,
    force_const,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.config import ConfigKey, ConfigSpec
from fabulous.fabric_cad.fabxplore.modules.sat_fab.constants import ConfigKind, Role
from fabulous.fabric_cad.fabxplore.modules.sat_fab.encoder import (
    EncodedOutputs,
    Encoder,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.input_mapping import (
    InputHandle,
    InputRoute,
    InputRouteSpec,
    InputSource,
    InputSourceKind,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.result import (
    CircuitConfig,
    EquivResult,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.truth import TruthTableSpec

CircuitLike = Circuit | TruthTableSpec


@dataclass
class EquivOptions:
    """Options for the CEGIS equivalence solver.

    Attributes
    ----------
    solver_name : str
        PySAT solver name.
    max_iters : int
        Maximum CEGIS iterations.
    brute_force_input_limit : int
        Use exhaustive concrete checking up to this number of inputs.
    random_examples : int
        Number of random examples to seed before CEGIS.
    verify : str
        Verification mode. Current values are ``"auto"``, ``"bruteforce"``, and
        ``"sat"``.
    """

    solver_name: str = "g3"
    max_iters: int = 10_000
    brute_force_input_limit: int = 10
    random_examples: int = 0
    verify: str = "auto"


class Equiv:
    """Configurable circuit equivalence/synthesis problem.

    Parameters
    ----------
    c1: CircuitLike
        Left circuit or fast truth-table spec.
    c2: CircuitLike
        Right circuit or fast truth-table spec.

    Attributes
    ----------
    symbolic_all : Equiv
        Mark all configuration bits of both sides symbolic.
    with_fixed : Equiv
        Fix all provided configuration bits for both sides. Alias for ``fixed_all``.
    """

    def __init__(self, c1: CircuitLike, c2: CircuitLike) -> None:
        self.c1 = c1
        self.c2 = c2
        self._roles = {id(c1): Role.C1.value, id(c2): Role.C2.value}
        self._specs = {
            Role.C1.value: ConfigSpec.empty(),
            Role.C2.value: ConfigSpec.empty(),
        }
        self._input_connections: dict[str, dict[str, InputSource]] = {}
        self._input_routes: dict[str, InputRouteSpec] = {}
        self.options_data = EquivOptions()

    @classmethod
    def check(cls, c1: CircuitLike, c2: CircuitLike) -> Equiv:
        """Create an equivalence problem.

        Parameters
        ----------
        c1 : CircuitLike
            Left side.
        c2 : CircuitLike
            Right side.

        Returns
        -------
        Equiv
            New problem object.
        """
        return cls(c1, c2)

    def options(
        self,
        solver_name: str | None = None,
        solver: str | None = None,
        max_iters: int | None = None,
        brute_force_input_limit: int | None = None,
        random_examples: int | None = None,
        verify: str | None = None,
        fast_truth_table: bool | None = None,
        reduce_truth_table_symmetry: bool | None = None,
    ) -> Equiv:
        """Update solver options.

        Parameters
        ----------
        solver_name : str | None
            Optional PySAT solver name.
        solver : str | None
            Alias for ``solver_name``.
        max_iters : int | None
            Optional maximum CEGIS iterations.
        brute_force_input_limit : int | None
            Optional exhaustive checking input limit.
        random_examples : int | None
            Optional number of random seed examples.
        verify : str | None
            Optional verification mode.
        fast_truth_table : bool | None
            Accepted for API clarity. TruthTableSpec sides are always fast.
        reduce_truth_table_symmetry : bool | None
            Optional truth-table symmetry flag for TruthTableSpec sides.

        Returns
        -------
        Equiv
            This problem object.
        """
        _ = fast_truth_table
        chosen_solver = solver_name if solver_name is not None else solver
        if chosen_solver is not None:
            self.options_data.solver_name = chosen_solver
        if max_iters is not None:
            self.options_data.max_iters = max_iters
        if brute_force_input_limit is not None:
            self.options_data.brute_force_input_limit = brute_force_input_limit
        if random_examples is not None:
            self.options_data.random_examples = random_examples
        if verify is not None:
            self.options_data.verify = verify
        if reduce_truth_table_symmetry is not None:
            for side in (self.c1, self.c2):
                if isinstance(side, TruthTableSpec):
                    side.reduce_lut_symmetry = reduce_truth_table_symmetry
        return self

    def fix_config(
        self,
        circuit: CircuitLike,
        config: ConfigSpec | dict[Any, Any],
    ) -> Equiv:
        """Fix configuration bits on one side.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit whose configuration is constrained.
        config : ConfigSpec | dict[Any, Any]
            ConfigSpec or mapping. String keys are interpreted as external
            configuration input names.

        Returns
        -------
        Equiv
            This problem object.
        """
        role = self._role(circuit)
        spec = self._coerce_config_spec(role, config)
        self._specs[role] = self._specs[role].merge(spec)
        return self

    def fix_lut(
        self,
        circuit: CircuitLike,
        inst: str,
        init: int,
        k: int | None = None,
    ) -> Equiv:
        """Fix a LUT INIT on one side.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit that owns the LUT.
        inst : str
            LUT instance name.
        init : int
            LSB-first INIT integer.
        k : int | None
            Optional LUT input count. Inferred for Circuit sides.

        Returns
        -------
        Equiv
            This problem object.
        """
        role = self._role(circuit)
        size = k if k is not None else _lut_size(circuit, inst)
        self._specs[role] = self._specs[role].merge(
            ConfigSpec.fixed_lut(role, inst, size, init)
        )
        return self

    def symbolic_config(self, circuit: CircuitLike) -> Equiv:
        """Mark all configuration bits of one circuit symbolic.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit whose configuration should be solver-controlled.

        Returns
        -------
        Equiv
            This problem object.
        """
        if isinstance(circuit, Circuit):
            role = self._role(circuit)
            self._specs[role] = self._specs[role].merge(
                ConfigSpec.symbolic_all(circuit, role)
            )
        return self

    symbolic_all: Equiv = symbolic_config

    def fixed_all(
        self,
        circuit: CircuitLike,
        config: ConfigSpec | dict[Any, Any],
    ) -> Equiv:
        """Fix all provided configuration bits for one side.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit whose configuration should be fixed.
        config : ConfigSpec | dict[Any, Any]
            Fixed configuration mapping or ConfigSpec.

        Returns
        -------
        Equiv
            This problem object.
        """
        return self.fix_config(circuit, config)

    with_fixed: Equiv = fixed_all

    def fix_route(
        self,
        circuit: CircuitLike,
        route: str,
        index: int | None = None,
        select: str | None = None,
    ) -> Equiv:
        """Fix one route mux selection.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit that owns the route.
        route : str
            Route instance name.
        index : int | None
            Candidate index to select.
        select : str | None
            Candidate signal name to select.

        Returns
        -------
        Equiv
            This problem object.
        """
        if not isinstance(circuit, Circuit):
            return self
        role = self._role(circuit)
        selected = _resolve_route_index(circuit, route, index, select)
        spec = ConfigSpec.empty()
        node = _find_route(circuit, route)
        for idx in range(len(node.ins)):
            spec.fix(ConfigKey(role, ConfigKind.ROUTE, route, idx), idx == selected)
        self._specs[role] = self._specs[role].merge(spec)
        return self

    def fix_pin(
        self,
        circuit: CircuitLike,
        lut: str,
        pin: str,
        signal: str,
    ) -> Equiv:
        """Fix a routed LUT pin to a named signal.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit that owns the routed LUT.
        lut : str
            LUT instance name.
        pin : str
            Pin name such as ``"a0"``.
        signal : str
            Candidate signal name to select.

        Returns
        -------
        Equiv
            This problem object.
        """
        return self.fix_route(circuit, f"{lut}.{pin}", select=signal)

    def fix(
        self,
        circuit: CircuitLike,
        lut: dict[str, int] | None = None,
        pins: dict[str, list[str]] | None = None,
        config: dict[Any, Any] | ConfigSpec | None = None,
    ) -> Equiv:
        """Apply compact fixed configuration data.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit to constrain.
        lut : dict[str, int] | None
            Mapping from LUT instance name to INIT integer.
        pins : dict[str, list[str]] | None
            Mapping from LUT instance name to selected pin signal names.
        config : dict[Any, Any] | ConfigSpec | None
            Additional fixed config data.

        Returns
        -------
        Equiv
            This problem object.
        """
        if config is not None:
            self.fix_config(circuit, config)
        if isinstance(circuit, Circuit) and lut:
            for inst, init in lut.items():
                self.fix_lut(circuit, inst, init)
        if pins:
            for inst, signals in pins.items():
                for index, signal in enumerate(signals):
                    self.fix_pin(circuit, inst, f"a{index}", signal)
        return self

    def route_inputs(
        self,
        circuit: CircuitLike,
        pool: list[str] | tuple[str, ...] | None = None,
        inputs: list[str] | tuple[str, ...] | None = None,
        allow_reuse: bool = True,
        allow_constants: bool = False,
        name: str = "input_map",
    ) -> Equiv:
        """Add a virtual configurable input crossbar before one circuit.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit whose normal input ports should be driven by routes.
        pool : list[str] | tuple[str, ...] | None
            Allowed source input names. Defaults to the other side's normal
            input names.
        inputs : list[str] | tuple[str, ...] | None
            Circuit input ports to route. Defaults to all normal inputs of the
            selected circuit.
        allow_reuse : bool
            Whether multiple routed ports may select the same source.
        allow_constants : bool
            Whether constant ``0`` and ``1`` are added to the source pool.
        name : str
            Prefix used for generated route configuration instance names.

        Returns
        -------
        Equiv
            This problem object.

        Raises
        ------
        TypeError
            If ``circuit`` is not a Circuit side.
        ValueError
            If selected ports are not circuit inputs or no sources are available.
        """
        if not isinstance(circuit, Circuit):
            raise TypeError("route_inputs requires a Circuit side")
        role = self._role(circuit)
        source_side = self._other_side(circuit)
        source_role = self._role(source_side)
        selected_inputs = list(inputs) if inputs is not None else circuit.input_names()
        missing = [port for port in selected_inputs if port not in circuit.inputs_map]
        if missing:
            raise ValueError(f"route_inputs ports are not circuit inputs: {missing}")
        source_names = list(pool) if pool is not None else self._other_inputs(circuit)
        available_sources = set(self._input_names(source_side))
        missing_sources = [
            source for source in source_names if source not in available_sources
        ]
        if missing_sources:
            raise ValueError(
                f"route_inputs sources are not source inputs: {missing_sources}"
            )
        sources = [
            InputSource.input(source, role=source_role) for source in source_names
        ]
        if allow_constants:
            sources.extend([InputSource.const(False), InputSource.const(True)])
        if not sources:
            raise ValueError("route_inputs requires at least one source")
        if not allow_reuse and len(selected_inputs) > len(set(sources)):
            raise ValueError(
                "route_inputs cannot be injective with fewer sources than inputs"
            )
        routes = tuple(
            InputRoute(
                port=port,
                inst=f"{name}.{port}",
                sources=tuple(sources),
            )
            for port in selected_inputs
        )
        self._input_routes[role] = InputRouteSpec(
            routes=routes,
            allow_reuse=allow_reuse,
        )
        return self

    def match_inputs_by_name(self) -> Equiv:
        """Connect right-side inputs to same-named left-side inputs.

        Returns
        -------
        Equiv
            This problem object.
        """
        left_names = set(self._input_names(self.c1))
        right_names = self._input_names(self.c2)
        mapping = {name: name for name in right_names if name in left_names}
        if mapping:
            self.map_inputs(self.c2, mapping, source=self.c1)
        return self

    def map_inputs(
        self,
        circuit: CircuitLike,
        mapping: dict[str, str],
        source: CircuitLike | None = None,
    ) -> Equiv:
        """Add fixed input connections before one circuit.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit whose input ports are driven by the mapping.
        mapping : dict[str, str]
            Mapping from destination input port name to source input name.
        source : CircuitLike | None
            Optional source side. Defaults to the opposite side.

        Returns
        -------
        Equiv
            This problem object.

        Raises
        ------
        TypeError
            If ``circuit`` is not a Circuit side.
        ValueError
            If a destination or source input name is invalid.
        """
        if not isinstance(circuit, Circuit):
            raise TypeError("map_inputs requires a Circuit side")
        role = self._role(circuit)
        source_side = source if source is not None else self._other_side(circuit)
        source_role = self._role(source_side)
        missing_dest = [port for port in mapping if port not in circuit.inputs_map]
        if missing_dest:
            raise ValueError(f"mapped ports are not circuit inputs: {missing_dest}")
        source_names = set(self._input_names(source_side))
        missing_source = [name for name in mapping.values() if name not in source_names]
        if missing_source:
            raise ValueError(f"mapping sources are not source inputs: {missing_source}")
        connections = dict(self._input_connections.get(role, {}))
        for port, source_name in mapping.items():
            connections[port] = InputSource.input(source_name, role=source_role)
        self._input_connections[role] = connections
        return self

    def solve(self) -> EquivResult:
        """Run SAT-based CEGIS equivalence synthesis.

        Returns
        -------
        EquivResult
            SAT/UNSAT result and decoded configuration.

        Raises
        ------
        RuntimeError
            If the CEGIS iteration limit is reached.
        """
        outputs = self._checked_outputs()
        input_names = self._all_inputs()
        vpool = IDPool(start_from=1)
        enc = Encoder(vpool)
        fixed, symbolic = self._final_config_sets()

        with Solver(name=self.options_data.solver_name) as outer:
            self._seed_outer_solver(outer, enc, fixed, symbolic)
            examples: list[dict[InputHandle, bool]] = []
            seen_examples: set[tuple[tuple[InputHandle, bool], ...]] = set()
            for example in self._initial_examples(input_names):
                seen_examples.add(self._example_key(example, input_names))
                examples.append(example)
                cex = self._example_constraints(
                    enc,
                    example,
                    len(examples) - 1,
                    outputs,
                )
                for clause in cex.clauses:
                    outer.add_clause(clause)
            for iteration in range(self.options_data.max_iters):
                if not outer.solve():
                    return EquivResult(
                        sat=False,
                        input_connections=dict(self._input_connections),
                        input_routes=dict(self._input_routes),
                        iterations=iteration,
                        examples=self._display_examples(examples),
                    )
                model = set(outer.get_model())
                candidate = dict(fixed)
                for key in symbolic:
                    candidate[key] = enc.config_var(key) in model
                bad_input = self._find_counterexample(
                    enc,
                    candidate,
                    input_names,
                    outputs,
                )
                if bad_input is None:
                    configs = self._decode_configs(candidate)
                    return EquivResult(
                        sat=True,
                        configs=configs,
                        circuit_roles=self._result_roles(),
                        circuits=self._result_circuits(),
                        input_connections=dict(self._input_connections),
                        input_routes=dict(self._input_routes),
                        iterations=iteration,
                        examples=self._display_examples(examples),
                    )
                key = self._example_key(bad_input, input_names)
                if key not in seen_examples:
                    seen_examples.add(key)
                    examples.append(bad_input)
                    cex = self._example_constraints(
                        enc,
                        bad_input,
                        len(examples) - 1,
                        outputs,
                    )
                    for clause in cex.clauses:
                        outer.add_clause(clause)
            raise RuntimeError(f"max_iters={self.options_data.max_iters} reached")

    def _role(self, circuit: CircuitLike) -> str:
        """Return the role for a circuit-like object.

        Parameters
        ----------
        circuit : CircuitLike
            Circuit-like object passed to the problem.

        Returns
        -------
        str
            Role name.

        Raises
        ------
        ValueError
            If the object is not one of the two problem sides.
        """
        try:
            return self._roles[id(circuit)]
        except KeyError as exc:
            raise ValueError("circuit is not part of this Equiv problem") from exc

    def _coerce_config_spec(
        self,
        role: str,
        config: ConfigSpec | dict[Any, Any],
    ) -> ConfigSpec:
        """Normalize user configuration data.

        Parameters
        ----------
        role : str
            Circuit role.
        config : ConfigSpec | dict[Any, Any]
            ConfigSpec or mapping.

        Returns
        -------
        ConfigSpec
            Normalized configuration specification.

        Raises
        ------
        TypeError
            If the config mapping contains unsupported key types.
        """
        if isinstance(config, ConfigSpec):
            return config
        fixed: dict[ConfigKey, bool] = {}
        for key, value in config.items():
            if isinstance(key, ConfigKey):
                fixed[key] = bool(value)
            elif isinstance(key, str):
                fixed[ConfigKey(role, ConfigKind.INPUT, key, 0)] = bool(value)
            elif isinstance(key, tuple):
                kind, inst, *rest = key
                index = rest[0] if rest else 0
                fixed[ConfigKey(role, ConfigKind(kind), inst, index)] = bool(value)
            else:
                raise TypeError(f"unsupported config key type: {type(key)!r}")
        return ConfigSpec(fixed=fixed)

    def _other_inputs(self, circuit: CircuitLike) -> list[str]:
        """Return normal input names from the opposite side.

        Parameters
        ----------
        circuit : CircuitLike
            One side of the equivalence problem.

        Returns
        -------
        list[str]
            Opposite-side input names.
        """
        if id(circuit) == id(self.c1):
            return self._input_names(self.c2)
        return self._input_names(self.c1)

    def _other_side(self, circuit: CircuitLike) -> CircuitLike:
        """Return the opposite side.

        Parameters
        ----------
        circuit : CircuitLike
            One side of the equivalence problem.

        Returns
        -------
        CircuitLike
            Opposite side.
        """
        return self.c2 if id(circuit) == id(self.c1) else self.c1

    def _other_role(self, circuit: CircuitLike) -> str:
        """Return the opposite side role.

        Parameters
        ----------
        circuit : CircuitLike
            One side of the equivalence problem.

        Returns
        -------
        str
            Opposite role.
        """
        return self._role(self._other_side(circuit))

    def _checked_outputs(self) -> list[str]:
        """Return output names that must match.

        Returns
        -------
        list[str]
            Ordered output names from the left side.

        Raises
        ------
        ValueError
            If the right side does not contain all left-side outputs.
        """
        left = self._output_names(self.c1)
        right = set(self._output_names(self.c2))
        missing = [name for name in left if name not in right]
        if missing:
            raise ValueError(f"right side is missing outputs: {missing}")
        return left

    def _all_inputs(self) -> list[InputHandle]:
        """Return the union of circuit-local normal inputs.

        Returns
        -------
        list[InputHandle]
            Stable ordered scoped input handles.
        """
        handles: list[InputHandle] = []
        for role, side in ((Role.C1.value, self.c1), (Role.C2.value, self.c2)):
            routed_ports = (
                self._input_routes[role].routed_ports()
                if role in self._input_routes
                else set()
            )
            connected_ports = set(self._input_connections.get(role, {}))
            for name in self._input_names(side):
                if name in routed_ports or name in connected_ports:
                    continue
                handle = InputHandle(role, name)
                if handle not in handles:
                    handles.append(handle)
            if role in self._input_routes:
                for route in self._input_routes[role].routes:
                    for source in route.sources:
                        if (
                            source.kind == InputSourceKind.INPUT
                            and source.role is not None
                            and InputHandle(source.role, source.name) not in handles
                        ):
                            handles.append(InputHandle(source.role, source.name))
            for source in self._input_connections.get(role, {}).values():
                if (
                    source.kind == InputSourceKind.INPUT
                    and source.role is not None
                    and InputHandle(source.role, source.name) not in handles
                ):
                    handles.append(InputHandle(source.role, source.name))
        return handles

    def _input_names(self, side: CircuitLike) -> list[str]:
        """Return normal input names for a side.

        Parameters
        ----------
        side : CircuitLike
            Circuit or truth-table spec.

        Returns
        -------
        list[str]
            Input names.
        """
        return side.input_names() if isinstance(side, Circuit) else side.input_names()

    def _output_names(self, side: CircuitLike) -> list[str]:
        """Return output names for a side.

        Parameters
        ----------
        side : CircuitLike
            Circuit or truth-table spec.

        Returns
        -------
        list[str]
            Output names.
        """
        return side.output_names() if isinstance(side, Circuit) else side.output_names()

    def _final_config_sets(self) -> tuple[dict[ConfigKey, bool], list[ConfigKey]]:
        """Compute fixed and symbolic configuration sets.

        Returns
        -------
        tuple[dict[ConfigKey, bool], list[ConfigKey]]
            Fixed values and symbolic keys.
        """
        fixed: dict[ConfigKey, bool] = {}
        symbolic: set[ConfigKey] = set()
        for role, side in ((Role.C1.value, self.c1), (Role.C2.value, self.c2)):
            spec = self._specs[role]
            fixed.update(spec.fixed)
            symbolic.update(spec.symbolic)
            if isinstance(side, Circuit):
                for key in side.config_keys(role):
                    if key not in spec.fixed:
                        symbolic.add(key)
            if role in self._input_routes:
                for route in self._input_routes[role].routes:
                    for index in range(len(route.sources)):
                        key = ConfigKey(role, ConfigKind.ROUTE, route.inst, index)
                        if key not in spec.fixed:
                            symbolic.add(key)
        symbolic.difference_update(fixed)
        return fixed, sorted(symbolic)

    def _seed_outer_solver(
        self,
        outer: Solver,
        enc: Encoder,
        fixed: dict[ConfigKey, bool],
        symbolic: list[ConfigKey],
    ) -> None:
        """Add configuration-domain clauses to the outer solver.

        Parameters
        ----------
        outer : Solver
            Persistent synthesis solver.
        enc : Encoder
            Shared encoder.
        fixed : dict[ConfigKey, bool]
            Fixed configuration values.
        symbolic : list[ConfigKey]
            Symbolic configuration keys.
        """
        for key, value in fixed.items():
            outer.add_clause([enc.config_var(key) if value else -enc.config_var(key)])
        for key in symbolic:
            var = enc.config_var(key)
            outer.add_clause([var, -var])
        for role, side in ((Role.C1.value, self.c1), (Role.C2.value, self.c2)):
            if isinstance(side, Circuit):
                for clause in enc.config_constraints(side, role).clauses:
                    outer.add_clause(clause)
            if role in self._input_routes:
                constraints = enc.input_route_config_constraints(
                    self._input_routes[role],
                    role,
                )
                for clause in constraints.clauses:
                    outer.add_clause(clause)

    def _example_constraints(
        self,
        enc: Encoder,
        example: dict[InputHandle, bool],
        index: int,
        outputs: list[str],
    ) -> CNF:
        """Build outer-solver equality constraints for one input example.

        Parameters
        ----------
        enc : Encoder
            Shared encoder.
        example : dict[InputHandle, bool]
            Concrete circuit-local input assignment.
        index : int
            Example index.
        outputs : list[str]
            Output names to compare.

        Returns
        -------
        CNF
            Clauses forcing both sides equal for the example.
        """
        scope = ("example", index)
        cnf = CNF()
        for handle, value in example.items():
            force_const(cnf, enc.input_var(scope, handle.role, handle.name), value)
        left = self._encode_side(enc, self.c1, "c1", scope, outputs)
        right = self._encode_side(enc, self.c2, "c2", scope, outputs)
        cnf.extend(left.cnf.clauses)
        cnf.extend(right.cnf.clauses)
        for name in outputs:
            add_eq(cnf, left.outputs[name], right.outputs[name])
        return cnf

    def _find_counterexample(
        self,
        enc: Encoder,
        candidate: dict[ConfigKey, bool],
        input_names: list[InputHandle],
        outputs: list[str],
    ) -> dict[InputHandle, bool] | None:
        """Find an input where the candidate configs differ.

        Parameters
        ----------
        enc : Encoder
            Shared encoder.
        candidate : dict[ConfigKey, bool]
            Concrete candidate configuration.
        input_names : list[InputHandle]
            Ordered circuit-local normal inputs.
        outputs : list[str]
            Output names to compare.

        Returns
        -------
        dict[InputHandle, bool] | None
            Counterexample input assignment, or ``None`` when equivalent.
        """
        if self.options_data.verify == "bruteforce":
            return self._bruteforce_counterexample(candidate, input_names, outputs)
        if self.options_data.verify == "sat":
            return self._sat_counterexample(enc, candidate, input_names, outputs)
        if len(input_names) <= self.options_data.brute_force_input_limit:
            return self._bruteforce_counterexample(candidate, input_names, outputs)
        return self._sat_counterexample(enc, candidate, input_names, outputs)

    def _bruteforce_counterexample(
        self,
        candidate: dict[ConfigKey, bool],
        input_names: list[InputHandle],
        outputs: list[str],
    ) -> dict[InputHandle, bool] | None:
        """Find a counterexample by exhaustive concrete simulation.

        Parameters
        ----------
        candidate : dict[ConfigKey, bool]
            Concrete candidate configuration.
        input_names : list[InputHandle]
            Ordered circuit-local normal inputs.
        outputs : list[str]
            Output names to compare.

        Returns
        -------
        dict[InputHandle, bool] | None
            Counterexample input assignment, or ``None``.
        """
        for bits in product([False, True], repeat=len(input_names)):
            values = dict(zip(input_names, bits, strict=True))
            left = self._eval_side(self.c1, "c1", values, candidate)
            right = self._eval_side(self.c2, "c2", values, candidate)
            if any(left[name] != right[name] for name in outputs):
                return values
        return None

    def _sat_counterexample(
        self,
        enc: Encoder,
        candidate: dict[ConfigKey, bool],
        input_names: list[InputHandle],
        outputs: list[str],
    ) -> dict[InputHandle, bool] | None:
        """Find a counterexample with a SAT miter.

        Parameters
        ----------
        enc : Encoder
            Shared encoder.
        candidate : dict[ConfigKey, bool]
            Concrete candidate configuration.
        input_names : list[InputHandle]
            Ordered circuit-local normal inputs.
        outputs : list[str]
            Output names to compare.

        Returns
        -------
        dict[InputHandle, bool] | None
            Counterexample input assignment, or ``None``.
        """
        scope = ("check", len(candidate))
        cnf = CNF()
        left = self._encode_side(enc, self.c1, "c1", scope, outputs)
        right = self._encode_side(enc, self.c2, "c2", scope, outputs)
        cnf.extend(left.cnf.clauses)
        cnf.extend(right.cnf.clauses)
        xors: list[int] = []
        for name in outputs:
            xor = enc.vpool.id((scope, "diff", name))
            add_xor(cnf, left.outputs[name], right.outputs[name], xor)
            xors.append(xor)
        diff = xors[0]
        for index, xor in enumerate(xors[1:], start=1):
            nxt = enc.vpool.id((scope, "diff_or", index))
            add_or(cnf, diff, xor, nxt)
            diff = nxt
        assumptions = [
            enc.config_var(key) if value else -enc.config_var(key)
            for key, value in candidate.items()
        ]
        assumptions.append(diff)
        with Solver(
            name=self.options_data.solver_name,
            bootstrap_with=cnf.clauses,
        ) as checker:
            if not checker.solve(assumptions=assumptions):
                return None
            model = set(checker.get_model())
            return {
                handle: enc.input_var(scope, handle.role, handle.name) in model
                for handle in input_names
            }

    def _encode_side(
        self,
        enc: Encoder,
        side: CircuitLike,
        role: str,
        scope: tuple,
        outputs: list[str],
    ) -> EncodedOutputs:
        """Encode one side of the equivalence problem.

        Parameters
        ----------
        enc : Encoder
            Shared encoder.
        side : CircuitLike
            Circuit or truth-table spec.
        role : str
            Circuit role.
        scope : tuple
            Encoding scope.
        outputs : list[str]
            Output names to encode.

        Returns
        -------
        EncodedOutputs
            Encoded outputs and clauses.
        """
        if isinstance(side, Circuit):
            return enc.encode_circuit(
                side,
                role,
                scope,
                outputs,
                input_connections=self._input_connections.get(role),
                input_routes=self._input_routes.get(role),
            )
        return enc.encode_truth_table(side, role, scope, outputs)

    def _eval_side(
        self,
        side: CircuitLike,
        role: str,
        inputs: dict[InputHandle, bool],
        config: dict[ConfigKey, bool],
    ) -> dict[str, bool]:
        """Evaluate one side concretely.

        Parameters
        ----------
        side : CircuitLike
            Circuit or truth-table spec.
        role : str
            Circuit role.
        inputs : dict[InputHandle, bool]
            Circuit-local normal input values.
        config : dict[ConfigKey, bool]
            Concrete configuration.

        Returns
        -------
        dict[str, bool]
            Output values.
        """
        if isinstance(side, Circuit):
            adapted_inputs = self._adapt_inputs_for_side(side, role, inputs, config)
            return side.eval_concrete(adapted_inputs, config, role)
        truth_inputs = {
            name: bool(inputs[InputHandle(role, name)]) for name in side.input_names()
        }
        return side.eval_concrete(truth_inputs)

    def _adapt_inputs_for_side(
        self,
        side: Circuit,
        role: str,
        inputs: dict[InputHandle, bool],
        config: dict[ConfigKey, bool],
    ) -> dict[str, bool]:
        """Apply fixed and routed input adapters to concrete values.

        Parameters
        ----------
        side : Circuit
            Circuit being evaluated.
        role : str
            Circuit role.
        inputs : dict[InputHandle, bool]
            Concrete circuit-local universal input assignment.
        config : dict[ConfigKey, bool]
            Concrete configuration assignment.

        Returns
        -------
        dict[str, bool]
            Input assignment keyed by the circuit's own port names.
        """
        connected_ports = set(self._input_connections.get(role, {}))
        routed_ports = (
            self._input_routes[role].routed_ports()
            if role in self._input_routes
            else set()
        )
        adapted = {
            name: bool(inputs[InputHandle(role, name)])
            for name in side.input_names()
            if name not in connected_ports and name not in routed_ports
        }
        for port, source in self._input_connections.get(role, {}).items():
            adapted[port] = _eval_input_source(source, inputs)
        spec = self._input_routes.get(role)
        if spec is None:
            return adapted
        for route in spec.routes:
            selected = _selected_input_route_source(config, role, route)
            adapted[route.port] = _eval_input_source(selected, inputs)
        return adapted

    def _decode_configs(
        self,
        candidate: dict[ConfigKey, bool],
    ) -> dict[str, CircuitConfig]:
        """Decode candidate bits by circuit role.

        Parameters
        ----------
        candidate : dict[ConfigKey, bool]
            Concrete candidate configuration.

        Returns
        -------
        dict[str, CircuitConfig]
            Decoded configs by role.
        """
        configs = {"c1": CircuitConfig(), "c2": CircuitConfig()}
        for key, value in candidate.items():
            configs.setdefault(key.role, CircuitConfig()).bits[key] = value
        return configs

    def _result_roles(self) -> dict[int, str]:
        """Return result-time circuit role lookup.

        Returns
        -------
        dict[int, str]
            Mapping from circuit object id to role.
        """
        roles: dict[int, str] = {}
        if isinstance(self.c1, Circuit):
            roles[id(self.c1)] = "c1"
        if isinstance(self.c2, Circuit):
            roles[id(self.c2)] = "c2"
        return roles

    def _result_circuits(self) -> dict[str, Circuit]:
        """Return circuit objects by role.

        Returns
        -------
        dict[str, Circuit]
            Circuit objects keyed by role.
        """
        circuits: dict[str, Circuit] = {}
        if isinstance(self.c1, Circuit):
            circuits[Role.C1.value] = self.c1
        if isinstance(self.c2, Circuit):
            circuits[Role.C2.value] = self.c2
        return circuits

    def _initial_examples(
        self,
        input_names: list[InputHandle],
    ) -> list[dict[InputHandle, bool]]:
        """Build initial examples for the outer solver.

        Parameters
        ----------
        input_names : list[InputHandle]
            Ordered circuit-local normal inputs.

        Returns
        -------
        list[dict[InputHandle, bool]]
            Seed examples.
        """
        examples: list[dict[InputHandle, bool]] = []
        if len(input_names) <= 2:
            for bits in product([False, True], repeat=len(input_names)):
                examples.append(dict(zip(input_names, bits, strict=True)))
        if self.options_data.random_examples > 0:
            random = Random(0)
            for _ in range(self.options_data.random_examples):
                examples.append(
                    {name: bool(random.getrandbits(1)) for name in input_names}
                )
        unique: dict[
            tuple[tuple[InputHandle, bool], ...],
            dict[InputHandle, bool],
        ] = {}
        for example in examples:
            unique.setdefault(self._example_key(example, input_names), example)
        return list(unique.values())

    def _example_key(
        self,
        example: dict[InputHandle, bool],
        input_names: list[InputHandle],
    ) -> tuple[tuple[InputHandle, bool], ...]:
        """Build a duplicate-detection key for an example.

        Parameters
        ----------
        example : dict[InputHandle, bool]
            Concrete input assignment.
        input_names : list[InputHandle]
            Ordered circuit-local normal inputs.

        Returns
        -------
        tuple[tuple[InputHandle, bool], ...]
            Stable example key.
        """
        return tuple((name, bool(example[name])) for name in input_names)

    def _display_examples(
        self,
        examples: list[dict[InputHandle, bool]],
    ) -> list[dict[str, bool]]:
        """Convert internal examples to result-friendly dictionaries.

        Parameters
        ----------
        examples : list[dict[InputHandle, bool]]
            Circuit-local input assignments.

        Returns
        -------
        list[dict[str, bool]]
            Display examples keyed by scoped input name.
        """
        return [
            {handle.display(): bool(value) for handle, value in example.items()}
            for example in examples
        ]


def _lut_size(circuit: CircuitLike, inst: str) -> int:
    """Find a LUT input count.

    Parameters
    ----------
    circuit : CircuitLike
        Circuit-like object.
    inst : str
        LUT instance name.

    Returns
    -------
    int
        LUT input count.

    Raises
    ------
    ValueError
        If the LUT cannot be found or inferred.
    """
    if isinstance(circuit, Circuit):
        for node in circuit.nodes:
            if node.name == inst and node.kind.value == "LUT":
                assert node.k is not None
                return node.k
    raise ValueError(f"cannot infer LUT size for {inst}")


def _selected_input_route_source(
    config: dict[ConfigKey, bool],
    role: str,
    route: InputRoute,
) -> InputSource:
    """Return the selected source for a virtual input route.

    Parameters
    ----------
    config : dict[ConfigKey, bool]
        Concrete configuration assignment.
    role : str
        Circuit role.
    route : InputRoute
        Input route to inspect.

    Returns
    -------
    InputSource
        Selected route source.

    Raises
    ------
    ValueError
        If no source is selected.
    """
    for index, source in enumerate(route.sources):
        key = ConfigKey(role, ConfigKind.ROUTE, route.inst, index)
        if config[key]:
            return source
    raise ValueError(f"no selected source for input route {route.inst}")


def _eval_input_source(source: InputSource, inputs: dict[InputHandle, bool]) -> bool:
    """Evaluate an input-route source for one assignment.

    Parameters
    ----------
    source : InputSource
        Source to evaluate.
    inputs : dict[InputHandle, bool]
        Concrete circuit-local universal input assignment.

    Returns
    -------
    bool
        Source value.

    Raises
    ------
    ValueError
        If the source kind is unknown.
    """
    if source.kind == InputSourceKind.INPUT:
        assert source.role is not None
        return bool(inputs[InputHandle(source.role, source.name)])
    if source.kind == InputSourceKind.CONST:
        assert source.value is not None
        return source.value
    raise ValueError(f"unknown input source kind {source.kind}")


def _find_route(circuit: Circuit, route: str) -> Node:
    """Find a route node by name.

    Parameters
    ----------
    circuit : Circuit
        Circuit that owns the route.
    route : str
        Route instance name.

    Returns
    -------
    Node
        Matching route node.

    Raises
    ------
    ValueError
        If the route is absent.
    """
    for node in circuit.nodes:
        if node.name == route and node.kind.value == "ROUTE":
            return node
    raise ValueError(f"route not found: {route}")


def _resolve_route_index(
    circuit: Circuit,
    route: str,
    index: int | None,
    select: str | None,
) -> int:
    """Resolve route selection by index or candidate name.

    Parameters
    ----------
    circuit : Circuit
        Circuit that owns the route.
    route : str
        Route instance name.
    index : int | None
        Explicit selected index.
    select : str | None
        Candidate signal name.

    Returns
    -------
    int
        Selected candidate index.

    Raises
    ------
    ValueError
        If selection arguments are invalid.
    """
    if (index is None) == (select is None):
        raise ValueError("provide exactly one of index= or select=")
    if index is not None:
        return index
    node = _find_route(circuit, route)
    for candidate_index, signal in enumerate(node.ins):
        if signal.name == select or signal.name.split(".")[-1] == select:
            return candidate_index
    raise ValueError(f"{select!r} is not a candidate for route {route}")
