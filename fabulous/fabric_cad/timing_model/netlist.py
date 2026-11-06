"""Hierarchy view of a structural netlist, read from Yosys JSON.

Instance paths hold the instance names of the Yosys JSON netlist. Leaf pins
come back in the spelling of the SDF timing graph, so they can be used as its
nodes.
"""

import shutil
import string
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Self

from fabulous.fabric_definition.yosys_obj import (
    YosysCellDetails,
    YosysJson,
    YosysModule,
)

type HierPath = tuple[str, ...]
"""Instance names from the top module down, outermost first."""

_SDF_PLAIN_CHARACTERS = frozenset(string.ascii_letters + string.digits + "_")


def sdf_identifier(name: str) -> str:
    r"""Return the SDF spelling of one Yosys JSON instance name.

    OpenSTA escapes every character that is not a letter, a digit or `_`, so
    `Q[0]$_DFF_P_` becomes `Q\[0\]\$_DFF_P_`. Yosys JSON keeps a leading
    backslash on a public name that starts with `$`, `\` or a digit; that
    backslash is not part of the name.

    Parameters
    ----------
    name : str
        Instance name as Yosys JSON spells it.

    Returns
    -------
    str
        Identifier spelling used by the SDF timing graph.
    """
    return "".join(
        character if character in _SDF_PLAIN_CHARACTERS else f"\\{character}"
        for character in name.removeprefix("\\")
    )


def sdf_path(instance: HierPath) -> str:
    """Return the SDF hierarchical name of an instance path.

    Parameters
    ----------
    instance : HierPath
        Instance path from the top module.

    Returns
    -------
    str
        The `/`-separated SDF instance name.
    """
    return "/".join(sdf_identifier(name) for name in instance)


@dataclass(frozen=True, slots=True)
class PortBit:
    """One bit of a module port.

    Attributes
    ----------
    port : str
        Port name.
    index : int | None
        HDL index of the bit, or `None` for a one-bit port.
    """

    port: str
    index: int | None


@dataclass(frozen=True, slots=True)
class _Terminal:
    """One bit of a cell connection: `cell.pin`, at `position` from the LSB."""

    cell: str
    pin: str
    position: int


def _hdl_index(*, position: int, offset: int, upto: int, width: int) -> int:
    """Return the HDL index of the bit at `position` from the LSB."""
    return offset + width - 1 - position if upto else offset + position


class NetlistIndex:
    """Connectivity of a hierarchical netlist, indexed by Yosys net bit.

    Two terminals are on the same net iff they share a Yosys bit id, so
    vector ports, part selects and `assign` aliases resolve per bit.

    Parameters
    ----------
    netlist : YosysJson
        The elaborated netlist.
    top : str
        Name of the top module.

    Raises
    ------
    ValueError
        If `top` is not a module of `netlist`.
    """

    def __init__(self, netlist: YosysJson, *, top: str) -> None:
        if top not in netlist.modules:
            raise ValueError(f"Top module {top!r} not found in {netlist.srcPath}.")
        self._top = top
        self._modules: dict[str, YosysModule] = netlist.modules
        self._terminals: dict[str, dict[int, list[_Terminal]]] = {}
        self._net_names: dict[str, dict[int, list[str]]] = {}
        for name, module in netlist.modules.items():
            terminals: dict[int, list[_Terminal]] = {}
            for cell_name, cell in module.cells.items():
                for pin, bits in cell.connections.items():
                    for position, bit in enumerate(bits):
                        if isinstance(bit, int):
                            terminal = _Terminal(cell_name, pin, position)
                            terminals.setdefault(bit, []).append(terminal)
            self._terminals[name] = terminals
            net_names: dict[int, list[str]] = {}
            for net_name, net in module.netnames.items():
                if net.hide_name:
                    continue
                for position, bit in enumerate(net.bits):
                    if not isinstance(bit, int):
                        continue
                    if len(net.bits) == 1:
                        spelled = net_name
                    else:
                        index = _hdl_index(
                            position=position,
                            offset=net.offset,
                            upto=net.upto,
                            width=len(net.bits),
                        )
                        spelled = f"{net_name}[{index}]"
                    net_names.setdefault(bit, []).append(spelled)
            self._net_names[name] = net_names

    @classmethod
    def read(cls, verilog: Path, *, top: str) -> Self:
        """Elaborate a structural Verilog netlist with Yosys and index it.

        Yosys runs on a copy in a scratch directory, so its JSON output does
        not land next to `verilog`.

        Parameters
        ----------
        verilog : Path
            Structural Verilog netlist.
        top : str
            Name of the top module.

        Returns
        -------
        Self
            Index of the netlist.
        """
        with TemporaryDirectory() as scratch:
            source = Path(scratch) / "netlist.v"
            shutil.copyfile(verilog, source)
            return cls(YosysJson(source), top=top)

    def __contains__(self, instance: HierPath) -> bool:
        """Return whether `instance` is a path of the netlist hierarchy."""
        try:
            self._parent_and_cell(instance)
        except KeyError:
            return False
        return True

    def _child(self, module: str, name: str) -> YosysCellDetails:
        """Return cell `name` of `module`, or raise `KeyError` naming both."""
        cell = self._modules[module].cells.get(name)
        if cell is None:
            raise KeyError(f"Instance {name!r} not found in module {module!r}.")
        return cell

    def _parent_and_cell(self, instance: HierPath) -> tuple[str, YosysCellDetails]:
        """Return the parent module and the cell of a path, or raise `KeyError`."""
        if not instance:
            raise KeyError("An empty path names the top module, not a cell.")
        parent = self._top
        for name in instance[:-1]:
            cell = self._child(parent, name)
            if cell.type not in self._modules:
                raise KeyError(f"Instance {name!r} is a leaf cell of {cell.type!r}.")
            parent = cell.type
        return parent, self._child(parent, instance[-1])

    @staticmethod
    def _leaf_pin(
        instance: HierPath, cell: YosysCellDetails, pin: str, position: int
    ) -> str:
        """Return the SDF name of one bit of a leaf cell pin."""
        if len(cell.connections[pin]) == 1:
            return f"{sdf_path(instance)}/{pin}"
        return f"{sdf_path(instance)}/{pin}[{position}]"

    def _leaf_pins_of_bit(self, module: str, bit: int, instance: HierPath) -> list[str]:
        """Return the leaf cell pins on net `bit` of `module`, below `instance`."""
        pins: list[str] = []
        for terminal in self._terminals[module].get(bit, []):
            cell = self._modules[module].cells[terminal.cell]
            child = (*instance, terminal.cell)
            if cell.type not in self._modules:
                pins.append(
                    self._leaf_pin(child, cell, terminal.pin, terminal.position)
                )
                continue
            port_bits = self._modules[cell.type].ports[terminal.pin].bits
            child_bit = port_bits[terminal.position]
            if isinstance(child_bit, int):
                pins.extend(self._leaf_pins_of_bit(cell.type, child_bit, child))
        return pins

    def _leaf_pins_at(
        self, instance: HierPath, cell: YosysCellDetails, pin: str, position: int
    ) -> list[str]:
        """Return the leaf cell pins reached from bit `position` of `pin`."""
        if cell.type not in self._modules:
            return [self._leaf_pin(instance, cell, pin, position)]
        bit = self._modules[cell.type].ports[pin].bits[position]
        if not isinstance(bit, int):
            return []
        return list(dict.fromkeys(self._leaf_pins_of_bit(cell.type, bit, instance)))

    def leaf_pins(self, instance: HierPath, port: PortBit) -> list[str]:
        """Return the leaf cell pins on one port bit of an instance.

        For a module instance, the pins are those of the cells below it that
        share the net of the port bit inside the module.

        Parameters
        ----------
        instance : HierPath
            Instance path from the top module.
        port : PortBit
            Port bit of the instance.

        Returns
        -------
        list[str]
            Leaf pins in SDF spelling, without duplicates.

        Raises
        ------
        KeyError
            If the instance, the port or the bit is absent.
        ValueError
            If `port.index` is `None` for a vector port.
        """
        _, cell = self._parent_and_cell(instance)
        name = f"{'/'.join(instance)}/{port.port}"
        if cell.type not in self._modules:
            if port.port not in cell.connections:
                raise KeyError(f"Pin {name!r} not found.")
            width, offset, upto = len(cell.connections[port.port]), 0, 0
        else:
            ports = self._modules[cell.type].ports
            if port.port not in ports:
                raise KeyError(f"Pin {name!r} not found.")
            details = ports[port.port]
            width, offset, upto = len(details.bits), details.offset, details.upto
        if port.index is None:
            if width != 1:
                raise ValueError(f"{name} has {width} bits; name one by index.")
            return self._leaf_pins_at(instance, cell, port.port, 0)
        for position in range(width):
            index = _hdl_index(position=position, offset=offset, upto=upto, width=width)
            if index == port.index:
                return self._leaf_pins_at(instance, cell, port.port, position)
        raise KeyError(f"Pin {name}[{port.index}] not found.")

    def top_port_bits(self) -> list[PortBit]:
        """Return every bit of the top module's ports.

        Returns
        -------
        list[PortBit]
            The bits in port order, LSB first; a one-bit port gives one bit
            with `index` `None`.
        """
        bits: list[PortBit] = []
        for name, details in self._modules[self._top].ports.items():
            width = len(details.bits)
            if width == 1:
                bits.append(PortBit(name, None))
                continue
            bits.extend(
                PortBit(
                    name,
                    _hdl_index(
                        position=position,
                        offset=details.offset,
                        upto=details.upto,
                        width=width,
                    ),
                )
                for position in range(width)
            )
        return bits

    def child_nets(self, instance: HierPath) -> dict[str, list[str]]:
        """Return the net names on each child cell of a module instance.

        Parameters
        ----------
        instance : HierPath
            Path of a module instance.

        Returns
        -------
        dict[str, list[str]]
            Child cell name to the names of the nets on its connections, as the
            instance's module names them.

        Raises
        ------
        KeyError
            If the path is absent or names a leaf cell.
        """
        _, cell = self._parent_and_cell(instance)
        if cell.type not in self._modules:
            raise KeyError(f"{'/'.join(instance)!r} is a leaf cell of {cell.type!r}.")
        net_names = self._net_names[cell.type]
        children: dict[str, list[str]] = {}
        for child, child_cell in self._modules[cell.type].cells.items():
            names: list[str] = []
            for bits in child_cell.connections.values():
                for bit in bits:
                    if isinstance(bit, int):
                        names.extend(net_names.get(bit, []))
            children[child] = list(dict.fromkeys(names))
        return children

    def net_leaf_pins(self, instance: HierPath) -> dict[str, list[str]]:
        """Return, per connected net, the leaf cell pins reached through the pin.

        An absent instance raises `KeyError`.

        Parameters
        ----------
        instance : HierPath
            Instance path from the top module.

        Returns
        -------
        dict[str, list[str]]
            Name of each net on the instance's connections, as its parent module
            names it, to the leaf pins reached through the instance pin on that
            net. When one net reaches several pins, the last pin wins.
        """
        parent, cell = self._parent_and_cell(instance)
        net_names = self._net_names[parent]
        resolved: dict[str, list[str]] = {}
        for pin, bits in cell.connections.items():
            for position, bit in enumerate(bits):
                if not isinstance(bit, int):
                    continue
                for name in net_names.get(bit, []):
                    resolved[name] = self._leaf_pins_at(instance, cell, pin, position)
        return resolved
