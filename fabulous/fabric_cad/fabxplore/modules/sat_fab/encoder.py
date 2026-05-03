"""Circuit-to-CNF encoder.

This module translates SAT fabric circuits and fast truth-table specs into PySAT CNF
formulas using scoped Tseitin variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pysat.formula import CNF, IDPool

from fabulous.fabric_cad.fabxplore.modules.sat_fab.cnf import (
    add_and,
    add_eq,
    add_exactly_one,
    add_ite,
    add_not,
    add_or,
    add_xor,
    force_const,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.config import ConfigKey
from fabulous.fabric_cad.fabxplore.modules.sat_fab.constants import ConfigKind, NodeKind
from fabulous.fabric_cad.fabxplore.modules.sat_fab.input_mapping import (
    InputRoute,
    InputRouteSpec,
    InputSource,
    InputSourceKind,
    OutputRoute,
    OutputRouteSpec,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import (
        Circuit,
        Node,
        Signal,
    )
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.truth import TruthTableSpec


@dataclass
class EncodedOutputs:
    """Encoded output variable mapping.

    Attributes
    ----------
    cnf : CNF
        Clauses emitted while encoding.
    outputs : dict[str, int]
        Mapping from output name to SAT variable.
    """

    cnf: CNF
    outputs: dict[str, int]


class Encoder:
    """Scoped CNF encoder.

    Parameters
    ----------
    vpool: IDPool
        PySAT variable pool used for all solver variables.
    """

    def __init__(self, vpool: IDPool) -> None:
        self.vpool = vpool

    def input_var(self, scope: tuple, role: str, name: str) -> int:
        """Return a scoped circuit-local primary input variable.

        Parameters
        ----------
        scope : tuple
            Encoding scope, such as a checker or CEGIS-example identifier.
        role : str
            Circuit role.
        name : str
            Local input name.

        Returns
        -------
        int
            SAT variable id.
        """
        return self.vpool.id((scope, role, "in", name))

    def config_var(self, key: ConfigKey) -> int:
        """Return a global configuration variable.

        Parameters
        ----------
        key : ConfigKey
            Configuration key.

        Returns
        -------
        int
            SAT variable id.
        """
        return self.vpool.id(("cfg", key))

    def net_var(self, scope: tuple, role: str, sig: Signal) -> int:
        """Return a scoped internal net variable.

        Parameters
        ----------
        scope : tuple
            Encoding scope.
        role : str
            Circuit role.
        sig : Signal
            Internal signal.

        Returns
        -------
        int
            SAT variable id.
        """
        return self.vpool.id((scope, role, "net", sig.name))

    def sig_var(self, scope: tuple, role: str, circuit: Circuit, sig: Signal) -> int:
        """Return the SAT variable for a circuit signal.

        Parameters
        ----------
        scope : tuple
            Encoding scope.
        role : str
            Circuit role.
        circuit : Circuit
            Circuit that owns the signal.
        sig : Signal
            Signal to encode.

        Returns
        -------
        int
            SAT variable id.
        """
        if sig.name in circuit.inputs_map:
            return self.input_var(scope, role, sig.name)
        if sig.name in circuit.configs_map:
            return self.config_var(ConfigKey(role, ConfigKind.INPUT, sig.name, 0))
        return self.net_var(scope, role, sig)

    def encode_circuit(
        self,
        circuit: Circuit,
        role: str,
        scope: tuple,
        output_names: list[str] | None = None,
        input_connections: dict[str, InputSource] | None = None,
        input_routes: InputRouteSpec | None = None,
    ) -> EncodedOutputs:
        """Encode a circuit into CNF.

        Parameters
        ----------
        circuit : Circuit
            Circuit to encode.
        role : str
            Circuit role for configuration variables.
        scope : tuple
            Encoding scope.
        output_names : list[str] | None
            Optional output names for cone-of-influence reduction.
        input_connections : dict[str, InputSource] | None
            Optional fixed sources that drive selected circuit input ports.
        input_routes : InputRouteSpec | None
            Optional virtual routes that drive selected circuit input ports.

        Returns
        -------
        EncodedOutputs
            CNF clauses and encoded output variables.
        """
        cnf = CNF()
        input_overrides = self._encode_input_connections(
            cnf,
            scope,
            input_connections,
        )
        input_overrides.update(
            self._encode_input_routes(cnf, role, scope, input_routes)
        )
        selected = output_names or circuit.output_names()
        for node in circuit.cone_nodes(selected):
            self._encode_node(cnf, circuit, role, scope, node, input_overrides)
        outputs = {
            name: self._sig_var_with_inputs(
                scope,
                role,
                circuit,
                circuit.outputs_map[name],
                input_overrides,
            )
            for name in selected
        }
        return EncodedOutputs(cnf=cnf, outputs=outputs)

    def encode_truth_table(
        self,
        spec: TruthTableSpec,
        role: str,
        scope: tuple,
        output_names: list[str] | None = None,
    ) -> EncodedOutputs:
        """Encode a fast truth-table spec for symbolic checking.

        Parameters
        ----------
        spec : TruthTableSpec
            Truth-table specification to encode.
        role : str
            Circuit role for local input variables.
        scope : tuple
            Encoding scope.
        output_names : list[str] | None
            Optional subset of output names.

        Returns
        -------
        EncodedOutputs
            CNF clauses and encoded output variables.
        """
        cnf = CNF()
        selected = output_names or spec.output_names()
        inputs = [self.input_var(scope, role, name) for name in spec.inputs]
        outputs: dict[str, int] = {}
        for name in selected:
            out = self.vpool.id((scope, spec.name, "truth_out", name))
            self.encode_fixed_table(
                cnf,
                inputs,
                spec.outputs[name],
                out,
                (scope, spec.name, name),
            )
            outputs[name] = out
        return EncodedOutputs(cnf=cnf, outputs=outputs)

    def encode_fixed_table(
        self,
        cnf: CNF,
        input_vars: list[int],
        init: int,
        out_var: int,
        key: tuple,
    ) -> None:
        """Encode a fixed truth table as a mux tree.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        input_vars : list[int]
            Ordered address variables.
        init : int
            LSB-first truth-table INIT.
        out_var : int
            Output variable.
        key : tuple
            Stable key prefix for intermediate variables.
        """
        level = [
            self.const_var(cnf, bool((init >> index) & 1))
            for index in range(1 << len(input_vars))
        ]
        if not level:
            force_const(cnf, out_var, False)
            return
        for bit_index, sel in enumerate(input_vars):
            nxt: list[int] = []
            for pair_index in range(0, len(level), 2):
                mux_out = self.vpool.id(("ttable_mux", key, bit_index, pair_index // 2))
                add_ite(cnf, sel, level[pair_index + 1], level[pair_index], mux_out)
                nxt.append(mux_out)
            level = nxt
        add_eq(cnf, out_var, level[0])

    def config_constraints(self, circuit: Circuit, role: str) -> CNF:
        """Return configuration-validity constraints.

        Parameters
        ----------
        circuit : Circuit
            Circuit whose configuration bits should be constrained.
        role : str
            Circuit role used to scope keys.

        Returns
        -------
        CNF
            Clauses such as exactly-one route constraints.
        """
        cnf = CNF()
        for node in circuit.nodes:
            if node.kind == NodeKind.ROUTE:
                add_exactly_one(
                    cnf,
                    [
                        self.config_var(
                            ConfigKey(role, ConfigKind.ROUTE, node.name, index)
                        )
                        for index in range(len(node.ins))
                    ],
                )
        return cnf

    def input_route_config_constraints(
        self,
        spec: InputRouteSpec,
        role: str,
    ) -> CNF:
        """Return global validity constraints for virtual input routes.

        Parameters
        ----------
        spec : InputRouteSpec
            Input-routing specification.
        role : str
            Circuit role used to scope keys.

        Returns
        -------
        CNF
            Clauses constraining input-route selectors.
        """
        cnf = CNF()
        for route in spec.routes:
            add_exactly_one(
                cnf,
                [
                    self.config_var(ConfigKey(role, ConfigKind.ROUTE, route.inst, idx))
                    for idx in range(len(route.sources))
                ],
            )
        if not spec.allow_reuse:
            self._add_no_reuse_constraints(cnf, spec, role)
        return cnf

    def output_route_config_constraints(
        self,
        spec: OutputRouteSpec,
        role: str,
    ) -> CNF:
        """Return global validity constraints for virtual output routes.

        Parameters
        ----------
        spec : OutputRouteSpec
            Output-routing specification.
        role : str
            Circuit role used to scope keys.

        Returns
        -------
        CNF
            Clauses constraining output-route selectors.
        """
        cnf = CNF()
        for route in spec.routes:
            add_exactly_one(
                cnf,
                [
                    self.config_var(ConfigKey(role, ConfigKind.ROUTE, route.inst, idx))
                    for idx in range(len(route.sources))
                ],
            )
        if not spec.allow_reuse:
            self._add_output_no_reuse_constraints(cnf, spec, role)
        return cnf

    def const_var(self, cnf: CNF, value: bool) -> int:
        """Return a global constant variable.

        Parameters
        ----------
        cnf : CNF
            Formula that receives the unit clause.
        value : bool
            Constant value.

        Returns
        -------
        int
            SAT variable fixed to ``value``.
        """
        var = self.vpool.id(("const", bool(value)))
        force_const(cnf, var, value)
        return var

    def _encode_node(
        self,
        cnf: CNF,
        circuit: Circuit,
        role: str,
        scope: tuple,
        node: Node,
        input_overrides: dict[str, int] | None = None,
    ) -> None:
        """Encode one circuit node.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        circuit : Circuit
            Circuit that owns the node.
        role : str
            Circuit role.
        scope : tuple
            Encoding scope.
        node : Node
            Node to encode.
        input_overrides : dict[str, int] | None
            Optional SAT variables for routed circuit input ports.

        Raises
        ------
        ValueError
            If the node kind is unknown.
        """
        out = self._sig_var_with_inputs(scope, role, circuit, node.out, input_overrides)
        ins = [
            self._sig_var_with_inputs(scope, role, circuit, sig, input_overrides)
            for sig in node.ins
        ]
        if node.kind == NodeKind.CONST0:
            force_const(cnf, out, False)
        elif node.kind == NodeKind.CONST1:
            force_const(cnf, out, True)
        elif node.kind == NodeKind.NOT:
            add_not(cnf, ins[0], out)
        elif node.kind == NodeKind.AND:
            add_and(cnf, ins[0], ins[1], out)
        elif node.kind == NodeKind.OR:
            add_or(cnf, ins[0], ins[1], out)
        elif node.kind == NodeKind.XOR:
            add_xor(cnf, ins[0], ins[1], out)
        elif node.kind == NodeKind.ITE:
            add_ite(cnf, ins[0], ins[1], ins[2], out)
        elif node.kind == NodeKind.TTABLE:
            assert node.init is not None
            self.encode_fixed_table(cnf, ins, node.init, out, (scope, role, node.name))
        elif node.kind == NodeKind.LUT:
            assert node.k is not None
            self._encode_lut(cnf, role, scope, node, ins, out)
        elif node.kind == NodeKind.ROUTE:
            self._encode_route(cnf, role, scope, node, ins, out)
        else:
            raise ValueError(f"unknown node kind {node.kind}")

    def _encode_lut(
        self,
        cnf: CNF,
        role: str,
        scope: tuple,
        node: Node,
        input_vars: list[int],
        out_var: int,
    ) -> None:
        """Encode a configurable LUT.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        role : str
            Circuit role.
        scope : tuple
            Encoding scope.
        node : Node
            LUT node.
        input_vars : list[int]
            Ordered address variables.
        out_var : int
            LUT output variable.
        """
        cfg = [
            self.config_var(ConfigKey(role, ConfigKind.LUT, node.name, index))
            for index in range(1 << len(input_vars))
        ]
        level = cfg
        for bit_index, sel in enumerate(input_vars):
            nxt: list[int] = []
            for pair_index in range(0, len(level), 2):
                mux_out = self.vpool.id(
                    ("lut_mux", scope, role, node.name, bit_index, pair_index // 2)
                )
                add_ite(cnf, sel, level[pair_index + 1], level[pair_index], mux_out)
                nxt.append(mux_out)
            level = nxt
        add_eq(cnf, out_var, level[0])

    def _encode_route(
        self,
        cnf: CNF,
        role: str,
        scope: tuple,
        node: Node,
        input_vars: list[int],
        out_var: int,
    ) -> None:
        """Encode a configurable one-hot route mux.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        role : str
            Circuit role.
        scope : tuple
            Encoding scope.
        node : Node
            ROUTE node.
        input_vars : list[int]
            Candidate input variables.
        out_var : int
            Route output variable.
        """
        selectors = [
            self.config_var(ConfigKey(role, ConfigKind.ROUTE, node.name, index))
            for index in range(len(input_vars))
        ]
        add_exactly_one(cnf, selectors)
        terms: list[int] = []
        for index, (sel, data) in enumerate(zip(selectors, input_vars, strict=True)):
            term = self.vpool.id(("route_term", scope, role, node.name, index))
            add_and(cnf, sel, data, term)
            terms.append(term)
        acc = terms[0]
        for index, term in enumerate(terms[1:], start=1):
            nxt = self.vpool.id(("route_or", scope, role, node.name, index))
            add_or(cnf, acc, term, nxt)
            acc = nxt
        add_eq(cnf, out_var, acc)

    def _sig_var_with_inputs(
        self,
        scope: tuple,
        role: str,
        circuit: Circuit,
        sig: Signal,
        input_overrides: dict[str, int] | None,
    ) -> int:
        """Return a signal variable with optional routed-input overrides.

        Parameters
        ----------
        scope : tuple
            Encoding scope.
        role : str
            Circuit role.
        circuit : Circuit
            Circuit that owns the signal.
        sig : Signal
            Signal to encode.
        input_overrides : dict[str, int] | None
            Optional SAT variables for routed input ports.

        Returns
        -------
        int
            SAT variable id.
        """
        if input_overrides and sig.name in input_overrides:
            return input_overrides[sig.name]
        return self.sig_var(scope, role, circuit, sig)

    def _encode_input_routes(
        self,
        cnf: CNF,
        role: str,
        scope: tuple,
        spec: InputRouteSpec | None,
    ) -> dict[str, int]:
        """Encode virtual input routes for one scope.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        role : str
            Circuit role.
        scope : tuple
            Encoding scope.
        spec : InputRouteSpec | None
            Optional input-routing specification.

        Returns
        -------
        dict[str, int]
            Mapping from circuit input port to routed SAT variable.
        """
        if spec is None:
            return {}
        overrides: dict[str, int] = {}
        for route in spec.routes:
            out = self.vpool.id((scope, role, "input_route", route.port))
            input_vars = [
                self._input_source_var(cnf, scope, source) for source in route.sources
            ]
            self._encode_virtual_route(cnf, role, scope, route, input_vars, out)
            overrides[route.port] = out
        return overrides

    def _input_source_var(self, cnf: CNF, scope: tuple, source: InputSource) -> int:
        """Return the SAT variable for an input-route source.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses for constants.
        scope : tuple
            Encoding scope.
        source : InputSource
            Input-route source.

        Returns
        -------
        int
            SAT variable id.

        Raises
        ------
        ValueError
            If the source kind is unknown.
        """
        if source.kind == InputSourceKind.INPUT:
            assert source.role is not None
            return self.input_var(scope, source.role, source.name)
        if source.kind == InputSourceKind.CONST:
            assert source.value is not None
            return self.const_var(cnf, source.value)
        raise ValueError(f"unknown input source kind {source.kind}")

    def _encode_input_connections(
        self,
        cnf: CNF,
        scope: tuple,
        connections: dict[str, InputSource] | None,
    ) -> dict[str, int]:
        """Encode fixed input connections as input overrides.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses for constants.
        scope : tuple
            Encoding scope.
        connections : dict[str, InputSource] | None
            Optional mapping from destination port to source.

        Returns
        -------
        dict[str, int]
            Mapping from destination input port to source SAT variable.
        """
        if not connections:
            return {}
        return {
            port: self._input_source_var(cnf, scope, source)
            for port, source in connections.items()
        }

    def _encode_virtual_route(
        self,
        cnf: CNF,
        role: str,
        scope: tuple,
        route: InputRoute,
        input_vars: list[int],
        out_var: int,
    ) -> None:
        """Encode one virtual input-route mux.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        role : str
            Circuit role.
        scope : tuple
            Encoding scope.
        route : InputRoute
            Input route to encode.
        input_vars : list[int]
            Candidate source variables.
        out_var : int
            Routed input variable.
        """
        selectors = [
            self.config_var(ConfigKey(role, ConfigKind.ROUTE, route.inst, index))
            for index in range(len(input_vars))
        ]
        add_exactly_one(cnf, selectors)
        terms: list[int] = []
        for index, (sel, data) in enumerate(zip(selectors, input_vars, strict=True)):
            term = self.vpool.id(("input_route_term", scope, role, route.inst, index))
            add_and(cnf, sel, data, term)
            terms.append(term)
        acc = terms[0]
        for index, term in enumerate(terms[1:], start=1):
            nxt = self.vpool.id(("input_route_or", scope, role, route.inst, index))
            add_or(cnf, acc, term, nxt)
            acc = nxt
        add_eq(cnf, out_var, acc)

    def encode_output_route(
        self,
        cnf: CNF,
        role: str,
        scope: tuple,
        route: OutputRoute,
        output_vars: dict[str, int],
    ) -> int:
        """Encode one virtual output-route mux.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        role : str
            Routed circuit role.
        scope : tuple
            Encoding scope.
        route : OutputRoute
            Output route to encode.
        output_vars : dict[str, int]
            Candidate source output variables.

        Returns
        -------
        int
            SAT variable for the selected output value.
        """
        out = self.vpool.id((scope, role, "output_route", route.target))
        input_vars = [output_vars[source] for source in route.sources]
        selectors = [
            self.config_var(ConfigKey(role, ConfigKind.ROUTE, route.inst, index))
            for index in range(len(input_vars))
        ]
        add_exactly_one(cnf, selectors)
        terms: list[int] = []
        for index, (sel, data) in enumerate(zip(selectors, input_vars, strict=True)):
            term = self.vpool.id(("output_route_term", scope, role, route.inst, index))
            add_and(cnf, sel, data, term)
            terms.append(term)
        acc = terms[0]
        for index, term in enumerate(terms[1:], start=1):
            nxt = self.vpool.id(("output_route_or", scope, role, route.inst, index))
            add_or(cnf, acc, term, nxt)
            acc = nxt
        add_eq(cnf, out, acc)
        return out

    def _add_no_reuse_constraints(
        self,
        cnf: CNF,
        spec: InputRouteSpec,
        role: str,
    ) -> None:
        """Prevent two input ports from selecting the same source.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        spec : InputRouteSpec
            Input-routing specification.
        role : str
            Circuit role used to scope keys.
        """
        for left_index, left_route in enumerate(spec.routes):
            for right_route in spec.routes[left_index + 1 :]:
                for left_source_index, left_source in enumerate(left_route.sources):
                    for right_source_index, right_source in enumerate(
                        right_route.sources
                    ):
                        if left_source != right_source:
                            continue
                        left_var = self.config_var(
                            ConfigKey(
                                role,
                                ConfigKind.ROUTE,
                                left_route.inst,
                                left_source_index,
                            )
                        )
                        right_var = self.config_var(
                            ConfigKey(
                                role,
                                ConfigKind.ROUTE,
                                right_route.inst,
                                right_source_index,
                            )
                        )
                        cnf.append([-left_var, -right_var])

    def _add_output_no_reuse_constraints(
        self,
        cnf: CNF,
        spec: OutputRouteSpec,
        role: str,
    ) -> None:
        """Prevent two target outputs from selecting the same source output.

        Parameters
        ----------
        cnf : CNF
            Formula that receives clauses.
        spec : OutputRouteSpec
            Output-routing specification.
        role : str
            Circuit role used to scope keys.
        """
        for left_index, left_route in enumerate(spec.routes):
            for right_route in spec.routes[left_index + 1 :]:
                for left_source_index, left_source in enumerate(left_route.sources):
                    for right_source_index, right_source in enumerate(
                        right_route.sources
                    ):
                        if left_source != right_source:
                            continue
                        left_var = self.config_var(
                            ConfigKey(
                                role,
                                ConfigKind.ROUTE,
                                left_route.inst,
                                left_source_index,
                            )
                        )
                        right_var = self.config_var(
                            ConfigKey(
                                role,
                                ConfigKind.ROUTE,
                                right_route.inst,
                                right_source_index,
                            )
                        )
                        cnf.append([-left_var, -right_var])
