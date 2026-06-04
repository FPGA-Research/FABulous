"""Basic Element of Logic (BEL) definition module.

This module contains the `Bel` class which represents a Basic Element of Logic in the
FPGA fabric.
BELs are the fundamental building blocks that can be placed and configured within tiles,
such as LUTs, flip-flops, and other logic elements.

A `Bel` is an immutable, Yosys-backed value object. It stores the top `YosysModule`
it was parsed from and derives every port collection lazily from that module. Each
derived collection is its own cached property that walks the module and classifies the
ports it cares about, so the logic lives next to the value it produces. The collections
are populated on first access and never mutated afterwards.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from pprint import pformat

from fabulous.custom_exception import FabricParsingError, InvalidBelDefinition
from fabulous.fabric_definition.define import (
    IO,
    BelType,
    FABulousAttribute,
    HDLType,
)
from fabulous.fabric_definition.port import (
    BelPort,
    ClockPort,
    ConfigPort,
    GenericPort,
    SharedPort,
)
from fabulous.fabric_definition.yosys_obj import YosysJson, YosysModule


def _process_bel_map(module: YosysModule) -> dict:
    """Extract and transform BEL mapping attributes from a `YosysModule`.

    Parameters
    ----------
    module : YosysModule
        The module whose attributes carry the BEL mapping information.

    Returns
    -------
    dict
        Dictionary containing the parsed bel mapping information.

    Raises
    ------
    ValueError
        If any BEL mapping attribute has an invalid format or index.
    """
    bel_map: dict = {}

    # Update attributes to remove the fab_attr_ prefix, ignoring case.
    fab_attrs = [key for key in module.attributes if "fab_attr_" in key.casefold()]
    for key in fab_attrs:
        attr = module.attributes.pop(key)
        key = re.sub(r"fab_attr_", "", key, flags=re.IGNORECASE)
        module.attributes[key] = attr

    # If BelMap not present, defaults to an empty map.
    if "belmap" not in (attr.casefold() for attr in module.attributes):
        return bel_map

    exclude_attributes = {
        "BelMap",
        "FABulous",
        "dynports",
        "cells_not_processed",
        "src",
        "top",
    }

    atters = {}
    for key, value in module.attributes.items():
        if key.casefold() in (item.casefold() for item in exclude_attributes):
            continue

        # The value specifies the bit position, so it must be an integer.
        if (type(value) is str and not value.isdigit()) and type(value) is not int:
            raise ValueError(
                f"BelMap attribute {key} does not have int / digit value:{value}."
            )

        # Convert vector notation SOME_KEY_NAME_123 -> SOME_KEY_NAME[123].
        parts = key.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            new_key = f"{parts[0]}[{parts[1]}]"
        else:
            new_key = key

        atters[new_key] = int(value)

    atters = dict(sorted(atters.items(), key=lambda item: item[1]))

    for i, (key, value) in enumerate(atters.items()):
        if i != value:
            raise ValueError(
                f"BelMap attribute {key} has incorrect index {value}."
                f" Expected value {i}."
            )
        bel_map[key] = {0: {0: "1"}}

    return bel_map


@dataclass(frozen=True)
class Bel:
    """Immutable, Yosys-backed description of a single BEL.

    A `Bel` stores the top `YosysModule` it was parsed from plus the few pieces of
    information that do not live in the module (the source path, the BEL prefix, and
    placement knobs). Every port collection is derived from the module on first
    access and cached in its own property. The BEL is validated at construction time
    and never mutated afterwards.

    Notes
    -----
    The `UserCLK` port, when present, is both listed in `inputs` (it carries no
    external, config, or shared attribute) and surfaced as a `ClockPort` in
    `clock_ports`. `clock_ports` is an additional derived view, not a
    reclassification, so HDL emission is unchanged.

    Parameters
    ----------
    src : Path
        The source file path of the BEL.
    prefix : str
        The prefix of the BEL, supplied by the CSV or YAML definition.
    module : YosysModule
        The top module of the BEL, the source of truth for its ports.
    module_name : str
        The name of the top module.
    bel_type : BelType
        The type of the BEL. Default is BelType.LOGIC.
    z : int
        The z-index for BEL placement. Default is 0.
    base_bel : bool
        Whether this is a base BEL. Default is False.
    param_override : dict[str, str]
        Dictionary of parameter overrides for the BEL.
    json_path : Path
        The path to the JSON file for the BEL.

    Attributes
    ----------
    src : Path
        The source file path of the BEL.
    prefix : str
        The prefix of the BEL.
    module : YosysModule
        The top module of the BEL.
    module_name : str
        The name of the top module.
    bel_type : BelType
        The type of the BEL.
    z : int
        The z-index for BEL placement.
    base_bel : bool
        Whether this is a base BEL.
    param_override : dict[str, str]
        Dictionary of parameter overrides for the BEL.
    json_path : Path
        The path to the JSON file for the BEL.

    Raises
    ------
    ValueError
        If the file type is not recognized (not .sv, .v, .vhd, or .vhdl), or if an
        IO BEL has more than one external input or output.
    InvalidBelDefinition
        If a port classification is invalid (see the port properties).
    """

    src: Path
    prefix: str
    module: YosysModule = field(compare=False, repr=False)
    module_name: str
    bel_type: BelType = BelType.LOGIC
    z: int = 0
    base_bel: bool = False
    param_override: dict[str, str] = field(default_factory=dict, compare=False)
    json_path: Path = field(default_factory=Path)

    def __post_init__(self) -> None:
        """Validate the source suffix and IO-BEL arity.

        Port collections are populated lazily on first access, so their per-port
        validation runs when a consumer first reads them rather than at construction.

        Raises
        ------
        ValueError
            If an IO BEL has more than one external input or output.
        """
        # Accessing filetype validates the source suffix.
        _ = self.filetype
        if self.bel_type == BelType.IO:
            if len(self.external_inputs) > 1:
                raise ValueError(
                    f"IO BEL '{self.name}' should have at most one external input, "
                    f"got {len(self.external_inputs)}"
                )
            if len(self.external_outputs) > 1:
                raise ValueError(
                    f"IO BEL '{self.name}' should have at most one external output, "
                    f"got {len(self.external_outputs)}"
                )

    @classmethod
    def from_hdl(cls, filename: Path, prefix: str = "") -> "Bel":
        """Build a Bel from a Verilog or VHDL BEL file.

        The file is run through Yosys and the resulting top module is wrapped in a
        Bel. All FABulous attributes (BelMap, EXTERNAL, SHARED_PORT, CONFIG_PORT,
        SHARED_ENABLE, SHARED_RESET, GLOBAL) are interpreted from the module.

        Parameters
        ----------
        filename : Path
            The BEL source file.
        prefix : str, optional
            The BEL prefix provided by the fabric definition. Defaults to "".

        Returns
        -------
        Bel
            A Bel wrapping the parsed top module.

        Raises
        ------
        FabricParsingError
            If the file does not contain any modules.
        ValueError
            If the bel map length does not match the config bit count.
        """
        yosys_json = YosysJson(filename)
        if len(yosys_json.modules) == 0:
            raise FabricParsingError(f"File {filename} does not contain any modules.")

        module_name, module = yosys_json.getTopModule()
        bel = cls(
            src=filename,
            prefix=prefix,
            module=module,
            module_name=module_name,
        )

        config_bits_port = module.ports.get("ConfigBits")
        no_config_bits = len(config_bits_port.bits) if config_bits_port else 0
        if len(bel.bel_feature_map) != no_config_bits:
            raise ValueError(
                f"NoConfigBits does not match with the BEL map in file {filename}, "
                f"length of BelMap is {len(bel.bel_feature_map)}, but with "
                f"{no_config_bits} config bits"
            )
        return bel

    def _iter_bit_ports(self) -> Iterator[tuple[str, str, IO, dict]]:
        """Yield the unrolled, per-bit ports of the module, excluding ConfigBits.

        Multi-bit ports are unrolled into one entry per bit, matching the naming the
        HDL emission expects (`<name><index>` for vectors, the bare name for scalars).

        Yields
        ------
        tuple[str, str, IO, dict]
            The original port name, the per-bit port name, the port direction, and
            the port's attribute dictionary.
        """
        for port_name, details in self.module.ports.items():
            if "ConfigBits" in port_name:
                continue
            direction = IO[details.direction.upper()]
            attributes = self.module.netnames[port_name].attributes
            width = len(details.bits)
            for index in range(width):
                bit_name = f"{port_name}{index}" if width > 1 else port_name
                yield port_name, bit_name, direction, attributes

    @staticmethod
    def _port_category(attributes: dict) -> str:
        """Return the classification bucket a port belongs to.

        Parameters
        ----------
        attributes : dict
            The port's attribute dictionary.

        Returns
        -------
        str
            One of "external", "config", "shared", or "internal". The precedence
            follows the FABulous attribute rules: an external, non-shared port is
            external; otherwise a config-bit port is config; otherwise a shared port
            is shared; everything else is internal.
        """
        if (
            FABulousAttribute.EXTERNAL in attributes
            and FABulousAttribute.SHARED_PORT not in attributes
        ):
            return "external"
        if FABulousAttribute.CONFIG_BIT in attributes:
            return "config"
        if FABulousAttribute.SHARED_PORT in attributes:
            return "shared"
        return "internal"

    @cached_property
    def inputs(self) -> list[BelPort]:
        """Return the internal input ports.

        Returns
        -------
        list[BelPort]
            The internal input ports.

        Raises
        ------
        InvalidBelDefinition
            If an internal port is bidirectional (INOUT).
        """
        inputs: list[BelPort] = []
        for _, bit_name, direction, attributes in self._iter_bit_ports():
            if self._port_category(attributes) != "internal":
                continue
            if direction == IO.INPUT:
                inputs.append(
                    BelPort(
                        name=bit_name,
                        io_direction=direction,
                        width=1,
                        prefix=self.prefix,
                    )
                )
            elif direction == IO.INOUT:
                raise InvalidBelDefinition(
                    f"Internal INOUT port '{bit_name}' in BEL {self.src} "
                    "is not supported: internal BEL ports connect to the "
                    "unidirectional switch matrix as either a source or a sink, "
                    "so a bidirectional (inout) port has no valid connection."
                )
        return inputs

    @cached_property
    def outputs(self) -> list[BelPort]:
        """Return the internal output ports.

        Returns
        -------
        list[BelPort]
            The internal output ports.

        Raises
        ------
        InvalidBelDefinition
            If an internal port is bidirectional (INOUT).
        """
        outputs: list[BelPort] = []
        for _, bit_name, direction, attributes in self._iter_bit_ports():
            if self._port_category(attributes) != "internal":
                continue
            if direction == IO.OUTPUT:
                outputs.append(
                    BelPort(
                        name=bit_name,
                        io_direction=direction,
                        width=1,
                        prefix=self.prefix,
                    )
                )
            elif direction == IO.INOUT:
                raise InvalidBelDefinition(
                    f"Internal INOUT port '{bit_name}' in BEL {self.src} "
                    "is not supported: internal BEL ports connect to the "
                    "unidirectional switch matrix as either a source or a sink, "
                    "so a bidirectional (inout) port has no valid connection."
                )
        return outputs

    @cached_property
    def external_inputs(self) -> list[BelPort]:
        """Return the external input ports.

        Returns
        -------
        list[BelPort]
            The external input ports.

        Raises
        ------
        InvalidBelDefinition
            If an external port is bidirectional (INOUT).
        """
        external_inputs: list[BelPort] = []
        for _, bit_name, direction, attributes in self._iter_bit_ports():
            if self._port_category(attributes) != "external":
                continue
            if direction == IO.INPUT:
                external_inputs.append(
                    BelPort(
                        name=bit_name,
                        io_direction=direction,
                        width=1,
                        prefix=self.prefix,
                        external=True,
                    )
                )
            elif direction == IO.INOUT:
                raise InvalidBelDefinition(
                    f"External INOUT port '{bit_name}' in BEL {self.src} "
                    "is not supported: external BEL ports are wired by "
                    "input/output list membership, which fixes their direction, "
                    "so a bidirectional (inout) external port cannot be emitted."
                )
        return external_inputs

    @cached_property
    def external_outputs(self) -> list[BelPort]:
        """Return the external output ports.

        Returns
        -------
        list[BelPort]
            The external output ports.

        Raises
        ------
        InvalidBelDefinition
            If an external port is bidirectional (INOUT).
        """
        external_outputs: list[BelPort] = []
        for _, bit_name, direction, attributes in self._iter_bit_ports():
            if self._port_category(attributes) != "external":
                continue
            if direction == IO.OUTPUT:
                external_outputs.append(
                    BelPort(
                        name=bit_name,
                        io_direction=direction,
                        width=1,
                        prefix=self.prefix,
                        external=True,
                    )
                )
            elif direction == IO.INOUT:
                raise InvalidBelDefinition(
                    f"External INOUT port '{bit_name}' in BEL {self.src} "
                    "is not supported: external BEL ports are wired by "
                    "input/output list membership, which fixes their direction, "
                    "so a bidirectional (inout) external port cannot be emitted."
                )
        return external_outputs

    @cached_property
    def config_port(self) -> list[ConfigPort]:
        """Return the configuration ports.

        Returns
        -------
        list[ConfigPort]
            The configuration ports, with the aggregate ConfigBits port first
            (when present) followed by the individual config-bit ports.
        """
        config_port: list[ConfigPort] = []
        config_bits_port = self.module.ports.get("ConfigBits")
        if config_bits_port:
            config_port.append(
                ConfigPort(
                    name=f"{self.prefix}ConfigBits",
                    io_direction=IO.INPUT,
                    width=len(config_bits_port.bits),
                )
            )
        for _, bit_name, direction, attributes in self._iter_bit_ports():
            if self._port_category(attributes) == "config":
                config_port.append(
                    ConfigPort(
                        name=f"{self.prefix}{bit_name}",
                        io_direction=direction,
                        width=1,
                    )
                )
        return config_port

    @cached_property
    def shared_port(self) -> list[SharedPort]:
        """Return the shared ports.

        Returns
        -------
        list[SharedPort]
            The shared ports.
        """
        shared_port: list[SharedPort] = []
        for _, bit_name, direction, attributes in self._iter_bit_ports():
            if self._port_category(attributes) == "shared":
                shared_port.append(
                    SharedPort(
                        name=bit_name,
                        io_direction=direction,
                        width=1,
                    )
                )
        return shared_port

    @cached_property
    def carry(self) -> dict[str, dict[IO, str]]:
        """Return the carry chains by prefix.

        Returns
        -------
        dict[str, dict[IO, str]]
            The carry chains keyed by prefix.

        Raises
        ------
        ValueError
            If a CARRY prefix is not a string, a CARRY port is INOUT, or a carry
            direction is reused within the same prefix.
        """
        carry: dict[str, dict[IO, str]] = {}
        for port_name, bit_name, direction, attributes in self._iter_bit_ports():
            if "CARRY" not in attributes:
                continue
            carry_prefix = attributes.get("CARRY")
            # Default carry prefix, yosys uses 1 if no value is specified.
            if carry_prefix == 1:
                carry_prefix = "FABulous_default"
            if type(carry_prefix) is not str:
                raise ValueError(
                    f"CARRY prefix attribute value must be a string for port "
                    f"{bit_name} in BEL {self.src}!"
                )
            if direction is IO.INOUT:
                raise ValueError(
                    f"CARRY can't be used with INOUT ports for port {bit_name}!"
                )
            if carry_prefix not in carry:
                carry[carry_prefix] = {}
            if direction not in carry[carry_prefix]:
                carry[carry_prefix][direction] = f"{self.prefix}{bit_name}"
            else:
                raise ValueError(
                    f"Port {port_name} with prefix {carry_prefix} can't be a "
                    f"carry {direction}, since port "
                    f"{carry[carry_prefix][direction]} already is!"
                )
        return carry

    @cached_property
    def local_shared(self) -> dict[str, tuple[str, IO]]:
        """Return the local shared ports.

        Returns
        -------
        dict[str, tuple[str, IO]]
            The local shared ports (ENABLE / RESET) of the BEL.

        Raises
        ------
        InvalidBelDefinition
            If a SHARED_ENABLE or SHARED_RESET port is not an input.
        """
        local_shared: dict[str, tuple[str, IO]] = {}
        for _, bit_name, direction, attributes in self._iter_bit_ports():
            if "SHARED_ENABLE" not in attributes and "SHARED_RESET" not in attributes:
                continue
            if direction is not IO.INPUT:
                raise InvalidBelDefinition(
                    "SHARED_ENABLE or SHARED_RESET can only be used with INPUT ports."
                )
            if "SHARED_ENABLE" in attributes:
                local_shared["ENABLE"] = (f"{self.prefix}{bit_name}", direction)
            elif "SHARED_RESET" in attributes:
                local_shared["RESET"] = (f"{self.prefix}{bit_name}", direction)
        return local_shared

    @cached_property
    def ports_vectors(self) -> dict[str, dict[str, tuple[IO, int]]]:
        """Return the vectorized port information.

        Returns
        -------
        dict[str, dict[str, tuple[IO, int]]]
            Vectorized port information bucketed by port class, keyed by the
            (non-unrolled) port name.
        """
        vectors: dict[str, dict[str, tuple[IO, int]]] = {
            "internal": {},
            "external": {},
            "config": {},
            "shared": {},
        }
        for port_name, details in self.module.ports.items():
            if "ConfigBits" in port_name:
                continue
            direction = IO[details.direction.upper()]
            attributes = self.module.netnames[port_name].attributes
            width = len(details.bits)
            if "EXTERNAL" in attributes and "SHARED_PORT" not in attributes:
                vectors["external"][port_name] = (direction, width)
            elif "CONFIG" in attributes:
                vectors["config"][port_name] = (direction, width)
            elif "SHARED_PORT" in attributes:
                vectors["shared"][port_name] = (direction, width)
            else:
                vectors["internal"][port_name] = (direction, width)
        return vectors

    @cached_property
    def clock_ports(self) -> list[ClockPort]:
        """Return the clock ports.

        Returns
        -------
        list[ClockPort]
            The clock ports of the BEL. Holds one `UserCLK` clock port when the
            module has one, otherwise empty.
        """
        for port_name in self.module.ports:
            if "UserCLK" in port_name:
                return [ClockPort()]
        return []

    @cached_property
    def bel_feature_map(self) -> dict:
        """Return the feature map of the BEL.

        Returns
        -------
        dict
            The parsed bel mapping information.
        """
        return _process_bel_map(self.module)

    @cached_property
    def filetype(self) -> HDLType:
        """Return the HDL file type of the BEL.

        Returns
        -------
        HDLType
            The HDL file type.

        Raises
        ------
        ValueError
            If the file suffix is not .sv, .v, .vhd, or .vhdl.
        """
        if self.src.suffix in (".sv", ".v"):
            return HDLType.VERILOG
        if self.src.suffix in (".vhd", ".vhdl"):
            return HDLType.VHDL
        raise ValueError(f"Unknown file type {self.src.suffix} for BEL {self.src}")

    @cached_property
    def language(self) -> str:
        """Return the language of the BEL.

        Returns
        -------
        str
            "verilog" or "vhdl".
        """
        return "verilog" if self.filetype == HDLType.VERILOG else "vhdl"

    @property
    def _name(self) -> str:
        """Return the bare BEL name from the source file stem.

        Returns
        -------
        str
            The source file stem.
        """
        return self.src.stem

    @property
    def name(self) -> str:
        """Return the BEL name, including parameter overrides if present.

        Returns
        -------
        str
            The BEL name, potentially including parameter override suffixes.
        """
        if len(self.param_override) == 0:
            return self._name
        suffix = "__".join([f"{k}_{v}" for k, v in self.param_override.items()])
        return f"{self._name}_{suffix}"

    @property
    def config_bits(self) -> int:
        """Return the total number of configuration bits.

        Returns
        -------
        int
            Sum of all config port widths.
        """
        return sum([i.width for i in self.config_port])

    @property
    def constant_bel(self) -> bool:
        """Check if this is a constant BEL (no inputs).

        Returns
        -------
        bool
            True if the BEL has no inputs (both internal and external).
        """
        return len(self.external_inputs) + len(self.inputs) == 0

    @property
    def input_names(self) -> list[str]:
        """Get input port names as strings.

        Returns
        -------
        list[str]
            List of input port names.
        """
        return [p.name for p in self.inputs]

    @property
    def output_names(self) -> list[str]:
        """Get output port names as strings.

        Returns
        -------
        list[str]
            List of output port names.
        """
        return [p.name for p in self.outputs]

    @property
    def with_user_clock(self) -> bool:
        """Check if the BEL has a user clock.

        Returns
        -------
        bool
            True if the BEL has at least one clock port.
        """
        return len(self.clock_ports) > 0

    @property
    def user_clk_port(self) -> ClockPort | None:
        """Return the single user clock port, or None if absent.

        Returns
        -------
        ClockPort | None
            The first clock port, or None when the BEL has no clock port.
        """
        return self.clock_ports[0] if self.clock_ports else None

    @property
    def external_input(self) -> list[str]:
        """Get external input port names as strings.

        Returns
        -------
        list[str]
            List of external input port names.
        """
        return [p.name for p in self.external_inputs]

    @property
    def external_output(self) -> list[str]:
        """Get external output port names as strings.

        Returns
        -------
        list[str]
            List of external output port names.
        """
        return [p.name for p in self.external_outputs]

    @property
    def config_bit(self) -> int:
        """Get the number of configuration bits (backward-compatible alias).

        Returns
        -------
        int
            The total number of configuration bits.
        """
        return self.config_bits

    def find_port_by_name(self, name: str) -> GenericPort:
        """Find a port by its name.

        Parameters
        ----------
        name : str
            The name of the port to find.

        Returns
        -------
        GenericPort
            The port with the matching name.

        Raises
        ------
        ValueError
            If no port with the given name is found.
        """
        for port in (
            self.inputs
            + self.outputs
            + self.external_inputs
            + self.external_outputs
            + self.config_port
            + self.shared_port
            + self.clock_ports
        ):
            if port.name == name:
                return port
        raise ValueError(f"Port '{name}' not found in BEL '{self.name}'")

    def serialize(self) -> dict:
        """Serialize the BEL to a dictionary.

        Returns
        -------
        dict
            A dictionary representation of the BEL.
        """
        return {
            "src": str(self.src),
            "json_path": str(self.json_path),
            "prefix": self.prefix,
            "name": self.name,
            "_name": self._name,
            "module_name": self.module_name,
            "bel_type": self.bel_type.value,
            "filetype": self.filetype.value,
            "inputs": [p.serialize() for p in self.inputs],
            "outputs": [p.serialize() for p in self.outputs],
            "external_inputs": [p.serialize() for p in self.external_inputs],
            "external_outputs": [p.serialize() for p in self.external_outputs],
            "config_port": [p.serialize() for p in self.config_port],
            "shared_port": [p.serialize() for p in self.shared_port],
            "user_clk_port": self.user_clk_port.serialize()
            if self.user_clk_port
            else None,
            "config_bits": self.config_bits,
            "constant_bel": self.constant_bel,
            "z": self.z,
            "base_bel": self.base_bel,
            "param_override": self.param_override,
            "language": self.language,
            "bel_feature_map": self.bel_feature_map,
            "ports_vectors": {
                k: {pk: (pv[0].value, pv[1]) for pk, pv in v.items()}
                for k, v in self.ports_vectors.items()
            },
            "carry": {
                k: {io.value: name for io, name in v.items()}
                for k, v in self.carry.items()
            },
            "local_shared": {
                k: (v[0], v[1].value) for k, v in self.local_shared.items()
            },
        }

    def __str__(self) -> str:
        """Return a string representation of the BEL.

        Returns
        -------
        str
            A formatted string representation of the BEL.
        """
        return pformat(self.serialize())
