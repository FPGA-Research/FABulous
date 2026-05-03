"""Result objects for SAT fabric equivalence.

This module decodes SAT models into LUT INIT values, route selections, and external
configuration input values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.sat_fab.cnf import bits_to_int_lsb0
from fabulous.fabric_cad.fabxplore.modules.sat_fab.constants import ConfigKind, NodeKind

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import Circuit
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.config import ConfigKey
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.input_mapping import (
        InputRouteSpec,
        InputSource,
    )


@dataclass
class CircuitConfig:
    """Decoded configuration for one circuit role.

    Attributes
    ----------
    bits : dict[ConfigKey, bool]
        Concrete values for all decoded configuration keys.
    """

    bits: dict[ConfigKey, bool] = field(default_factory=dict)

    def lut_bits(self, inst: str) -> list[bool]:
        """Return LUT INIT bits for an instance.

        Parameters
        ----------
        inst : str
            LUT instance name.

        Returns
        -------
        list[bool]
            LSB-first LUT INIT bits.
        """
        selected = sorted(
            (key.index, value)
            for key, value in self.bits.items()
            if key.kind == ConfigKind.LUT and key.inst == inst
        )
        return [value for _, value in selected]

    def lut_init(self, inst: str) -> int:
        """Return a LUT INIT integer.

        Parameters
        ----------
        inst : str
            LUT instance name.

        Returns
        -------
        int
            LSB-first INIT integer.
        """
        return bits_to_int_lsb0(self.lut_bits(inst))

    def route_index(self, inst: str) -> int | None:
        """Return the selected route index.

        Parameters
        ----------
        inst : str
            ROUTE instance name.

        Returns
        -------
        int | None
            Selected candidate index, or ``None`` if the route is absent.
        """
        selected = [
            key.index
            for key, value in self.bits.items()
            if key.kind == ConfigKind.ROUTE and key.inst == inst and value
        ]
        return selected[0] if selected else None

    def external_value(self, name: str) -> bool | None:
        """Return an external configuration input value.

        Parameters
        ----------
        name : str
            External configuration input name.

        Returns
        -------
        bool | None
            Config value, or ``None`` if absent.
        """
        for key, value in self.bits.items():
            if key.kind == ConfigKind.INPUT and key.inst == name:
                return value
        return None


@dataclass
class EquivResult:
    """Equivalence synthesis result.

    Attributes
    ----------
    sat : bool
        Whether a satisfying configuration was found.
    configs : dict[str, CircuitConfig]
        Decoded configuration by role.
    circuit_roles : dict[int, str]
        Mapping from circuit object id to role.
    iterations : int
        Number of CEGIS iterations.
    examples : list[dict[str, bool]]
        Counterexample/input examples used by the outer solver.
    circuits : dict[str, Circuit]
        Circuit objects by role.
    input_connections : dict[str, dict[str, InputSource]]
        Fixed input connections by role.
    input_routes : dict[str, InputRouteSpec]
        Virtual input-route specifications by role.
    """

    sat: bool
    configs: dict[str, CircuitConfig] = field(default_factory=dict)
    circuit_roles: dict[int, str] = field(default_factory=dict)
    iterations: int = 0
    examples: list[dict[str, bool]] = field(default_factory=list)
    circuits: dict[str, Circuit] = field(default_factory=dict)
    input_connections: dict[str, dict[str, InputSource]] = field(default_factory=dict)
    input_routes: dict[str, InputRouteSpec] = field(default_factory=dict)

    def config_for(self, circuit: Circuit) -> CircuitConfig:
        """Return decoded config for a circuit object.

        Parameters
        ----------
        circuit : Circuit
            Circuit whose role should be resolved.

        Returns
        -------
        CircuitConfig
            Decoded configuration for the circuit role.
        """
        role = self.circuit_roles[id(circuit)]
        return self.configs[role]

    def lut_init(self, circuit: Circuit, inst: str) -> int:
        """Return the solved LUT INIT for a circuit instance.

        Parameters
        ----------
        circuit : Circuit
            Circuit that owns the LUT.
        inst : str
            LUT instance name.

        Returns
        -------
        int
            LSB-first INIT integer.
        """
        return self.config_for(circuit).lut_init(inst)

    def route(self, circuit: Circuit, inst: str) -> int | None:
        """Return the solved route selection for a circuit instance.

        Parameters
        ----------
        circuit : Circuit
            Circuit that owns the route.
        inst : str
            ROUTE instance name.

        Returns
        -------
        int | None
            Selected candidate index, or ``None``.
        """
        return self.config_for(circuit).route_index(inst)

    def pinmap(self, circuit: Circuit, lut: str) -> dict[str, str]:
        """Return solved routed-LUT pin mapping.

        Parameters
        ----------
        circuit : Circuit
            Circuit that owns the routed LUT.
        lut : str
            LUT instance name.

        Returns
        -------
        dict[str, str]
            Mapping from pin names such as ``"a0"`` to selected signal names.
        """
        config = self.config_for(circuit)
        mapping: dict[str, str] = {}
        for node in circuit.nodes:
            prefix = f"{lut}."
            if node.kind != NodeKind.ROUTE or not node.name.startswith(prefix):
                continue
            selected = config.route_index(node.name)
            if selected is None:
                continue
            pin = node.name.removeprefix(prefix)
            mapping[pin] = _pretty_signal(node.ins[selected].name)
        return mapping

    def input_mapping(
        self,
        circuit: Circuit,
        scoped: bool = False,
        separator: str = "/",
    ) -> dict[str, str]:
        """Return solved virtual input mapping for a circuit.

        Parameters
        ----------
        circuit : Circuit
            Circuit whose routed input ports should be decoded.
        scoped : bool
            Whether to include circuit roles in destination and source names.
        separator : str
            Separator between role and local port name when ``scoped`` is true.

        Returns
        -------
        dict[str, str]
            Mapping from circuit input port name to selected source name.
        """
        role = self.circuit_roles[id(circuit)]
        return self._input_mapping_for_role(
            role,
            scoped=scoped,
            separator=separator,
        )

    def _input_mapping_for_role(
        self,
        role: str,
        scoped: bool = False,
        separator: str = "/",
    ) -> dict[str, str]:
        """Return solved virtual input mapping for one role.

        Parameters
        ----------
        role : str
            Circuit role.
        scoped : bool
            Whether to include circuit roles in destination and source names.
        separator : str
            Separator between role and local port name when ``scoped`` is true.

        Returns
        -------
        dict[str, str]
            Mapping from circuit input port name to selected source name.
        """
        mapping: dict[str, str] = {}
        for port, source in self.input_connections.get(role, {}).items():
            mapping[_display_port(role, port, scoped, separator)] = source.display(
                scoped=scoped,
                separator=separator,
            )
        spec = self.input_routes.get(role)
        if spec is None or role not in self.configs:
            return mapping
        config = self.configs[role]
        for route in spec.routes:
            selected = config.route_index(route.inst)
            if selected is None:
                continue
            mapping[_display_port(role, route.port, scoped, separator)] = route.sources[
                selected
            ].display(
                scoped=scoped,
                separator=separator,
            )
        return mapping

    def print(self, verbose: bool = False) -> None:
        """Print a readable result report.

        Parameters
        ----------
        verbose : bool
            Whether to include examples and pin maps.
        """
        print(self.summary(verbose=verbose))  # noqa: T201

    def write_json(self, path: str | Path) -> Path:
        """Write the decoded result to JSON.

        Parameters
        ----------
        path : str | Path
            Destination path.

        Returns
        -------
        Path
            Written path.
        """
        out_path = Path(path)
        data = {
            "sat": self.sat,
            "iterations": self.iterations,
            "examples": self.examples,
            "configs": {
                role: {
                    "bits": [
                        {
                            "kind": key.kind.value,
                            "inst": key.inst,
                            "index": key.index,
                            "value": value,
                        }
                        for key, value in sorted(config.bits.items())
                    ]
                }
                for role, config in self.configs.items()
            },
            "input_mappings": {
                role: self._input_mapping_for_role(role)
                for role in set(self.input_routes) | set(self.input_connections)
            },
        }
        out_path.write_text(json.dumps(data, indent=2))
        return out_path

    def emit_verilog_config(self) -> str:
        """Emit a simple Verilog-style config summary.

        Returns
        -------
        str
            Text containing localparams for LUT INITs.
        """
        lines: list[str] = []
        for role, config in sorted(self.configs.items()):
            lut_names = sorted(
                {key.inst for key in config.bits if key.kind == ConfigKind.LUT}
            )
            for inst in lut_names:
                bits = config.lut_bits(inst)
                width = len(bits)
                lines.append(
                    f"localparam [{width - 1}:0] {role}_{inst}_INIT = "
                    f"{width}'h{config.lut_init(inst):X};"
                )
        return "\n".join(lines)

    def summary(self, verbose: bool = False) -> str:
        """Build a human-readable result summary.

        Parameters
        ----------
        verbose : bool
            Whether to include examples and pin maps.

        Returns
        -------
        str
            Multi-line summary.
        """
        if not self.sat:
            return "UNSAT"
        lines = [f"SAT after {self.iterations} CEGIS iterations"]
        for role, config in sorted(self.configs.items()):
            lines.append(f"[{role}]")
            lut_names = sorted(
                {key.inst for key in config.bits if key.kind == ConfigKind.LUT}
            )
            for inst in lut_names:
                bits = config.lut_bits(inst)
                width = max(1, (len(bits) + 3) // 4)
                lines.append(f"  {inst}: INIT=0x{config.lut_init(inst):0{width}X}")
            route_names = sorted(
                {
                    key.inst
                    for key in config.bits
                    if key.kind == ConfigKind.ROUTE
                    and not _is_input_route(self.input_routes.get(role), key.inst)
                }
            )
            for inst in route_names:
                lines.append(f"  {inst}: select {config.route_index(inst)}")
            if role in self.input_routes or role in self.input_connections:
                mapping = self._input_mapping_for_role(role)
                if mapping:
                    lines.append(f"  input mapping: {mapping}")
            input_names = sorted(
                {key.inst for key in config.bits if key.kind == ConfigKind.INPUT}
            )
            for name in input_names:
                lines.append(f"  {name}: {int(bool(config.external_value(name)))}")
            if verbose and role in self.circuits:
                for lut_name in lut_names:
                    pins = self.pinmap(self.circuits[role], lut_name)
                    if pins:
                        lines.append(f"  {lut_name} pins: {pins}")
        if verbose and self.examples:
            lines.append("examples:")
            for example in self.examples:
                lines.append(f"  {example}")
        return "\n".join(lines)


def _pretty_signal(name: str) -> str:
    """Return a concise signal display name.

    Parameters
    ----------
    name : str
        Internal signal name.

    Returns
    -------
    str
        User-facing signal name.
    """
    return name.split(".")[-1]


def _display_port(role: str, port: str, scoped: bool, separator: str = "/") -> str:
    """Return a display name for a circuit input port.

    Parameters
    ----------
    role : str
        Circuit role.
    port : str
        Local port name.
    scoped : bool
        Whether to include the role.
    separator : str
        Separator between role and local port name.

    Returns
    -------
    str
        Display name.
    """
    return f"{role}{separator}{port}" if scoped else port


def _is_input_route(spec: InputRouteSpec | None, inst: str) -> bool:
    """Check whether an instance name belongs to a virtual input route.

    Parameters
    ----------
    spec : InputRouteSpec | None
        Optional input-route specification.
    inst : str
        Route configuration instance name.

    Returns
    -------
    bool
        True when the instance is a virtual input route.
    """
    return spec is not None and inst in set(spec.config_instances())
