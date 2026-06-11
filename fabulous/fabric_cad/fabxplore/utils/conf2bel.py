"""Conversion of FABulous config-bit ports into BEL parameters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge

FABULOUS_USER_CLK_PORT = "UserCLK"
CLK_PORT = "CLK"


@dataclass(frozen=True)
class Conf2BelParameter:
    """Mapping from config-vector bits to one emitted BEL parameter.

    Attributes
    ----------
    name : str
        Parameter name to emit on the BEL cell.
    width : int
        Parameter width in bits.
    config_to_parameter_bits : dict[int, int]
        Mapping from flat config-vector bit index to parameter bit index.
    default_value : int
        Default value for blackbox parameters derived from the BEL definition.
    """

    name: str
    width: int
    config_to_parameter_bits: dict[int, int]
    default_value: int = 0


@dataclass
class Conf2BelModel:
    """Config-to-parameter model derived from one FABulous BEL Verilog file.

    Attributes
    ----------
    module_name : str
        Name of the BEL module.
    config_ports : dict[str, int]
        GLOBAL config carrier ports and their widths.
    parameters : dict[str, Conf2BelParameter]
        Parameter groups keyed by emitted parameter name.
    blackbox_bridge : PyosysBridge
        Bridge containing the derived blackbox module with config ports removed
        and parameter defaults added.
    blackbox_verilog : str
        Verilog text used to replace the parsed BEL model in `blackbox_bridge`.
    """

    module_name: str
    config_ports: dict[str, int]
    parameters: dict[str, Conf2BelParameter]
    blackbox_bridge: PyosysBridge
    blackbox_verilog: str


def normalize_belmap_feature(name: str) -> str:
    """Normalize FABulous BelMap feature names to bel.v2.txt spelling.

    The FABulous parser converts one trailing ``_<number>`` suffix into vector
    syntax. For example, ``INIT0_11`` becomes ``INIT0[11]`` while names without
    a numeric suffix are preserved.

    Parameters
    ----------
    name : str
        Raw BelMap attribute name from Yosys.

    Returns
    -------
    str
        Normalized feature name.
    """
    base, separator, suffix = name.rpartition("_")
    if separator and suffix.isdigit():
        return f"{base}[{suffix}]"
    return name


def derive_conf2bel_from_verilog(verilog_path: Path) -> Conf2BelModel:
    """Read a FABulous BEL Verilog file and derive config-to-BEL parameters.

    This function only inspects and mutates the pyosys design object held by a
    local `PyosysBridge`. It reads module attributes directly from
    ``design.modules_``, finds GLOBAL config carrier ports through wire
    attributes, removes those config ports from the derived blackbox module, and
    returns the grouped parameter mapping needed by netlist conversion.

    Parameters
    ----------
    verilog_path : Path
        BEL Verilog source file.

    Returns
    -------
    Conf2BelModel
        Derived conversion model.

    Raises
    ------
    FileNotFoundError
        If `verilog_path` does not exist.
    ValueError
        If the file does not define exactly one module with BelMap and GLOBAL
        config information, or if the BelMap indices are malformed.
    """
    verilog_path = Path(verilog_path)
    if not verilog_path.exists():
        raise FileNotFoundError(verilog_path)

    bridge = PyosysBridge()
    bridge.read_verilog_paths([verilog_path], replace_design=True)
    bridge.run_pass("proc")

    modules = list(bridge.design.modules_.values())
    if len(modules) != 1:
        raise ValueError(
            f"Expected exactly one BEL module in {verilog_path}, found {len(modules)}."
        )
    module = modules[0]
    module_name = str(module.name).removeprefix("\\")

    config_ports: dict[str, int] = {}
    config_wires = ys.WirePtrPool()
    port_lines: list[str] = []
    for port_id in module.ports:
        wire = module.wire(port_id)
        wire_name = str(wire.name).removeprefix("\\")
        attr_names = {
            str(attr_name).removeprefix("\\").casefold()
            for attr_name in wire.attributes
        }
        if "fabulous" in attr_names and "global" in attr_names:
            config_ports[wire_name] = wire.width
            config_wires.add(wire)
            continue

        if wire.port_input and wire.port_output:
            direction = "inout"
        elif wire.port_output:
            direction = "output"
        else:
            direction = "input"
        port_name = _conf2bel_port_name(wire_name)
        if wire.width == 1:
            port_lines.append(f"{direction} {port_name}")
        else:
            port_lines.append(f"{direction} [{wire.width - 1}:0] {port_name}")

    if not config_ports:
        raise ValueError(f"BEL module {module_name} has no FABulous GLOBAL port.")

    exclude_attrs = {
        "belmap",
        "fabulous",
        "dynports",
        "cells_not_processed",
        "src",
        "top",
    }
    raw_entries: dict[str, int] = {}
    for raw_attr_name, raw_attr_value in module.attributes.items():
        attr_name = str(raw_attr_name).removeprefix("\\")
        if attr_name.casefold().startswith("fab_attr_"):
            attr_name = attr_name[len("fab_attr_") :]
        if attr_name.casefold() in exclude_attrs:
            continue
        if hasattr(raw_attr_value, "as_int"):
            attr_value = raw_attr_value.as_int()
        elif isinstance(raw_attr_value, int):
            attr_value = raw_attr_value
        elif str(raw_attr_value).isdigit():
            attr_value = int(str(raw_attr_value))
        else:
            raise ValueError(
                f"BelMap attribute {attr_name} is not an integer: {raw_attr_value!r}."
            )
        raw_entries[normalize_belmap_feature(attr_name)] = attr_value

    if not raw_entries:
        raise ValueError(f"BEL module {module_name} has no BelMap attributes.")

    indices = sorted(raw_entries.values())
    if indices != list(range(len(indices))):
        raise ValueError(f"BelMap config indices must be contiguous; got {indices}.")

    indexed_re = re.compile(r"^(?P<base>.+)\[(?P<index>\d+)\]$")
    grouped: dict[str, dict[int, int]] = {}
    for feature_name, config_index in sorted(
        raw_entries.items(), key=lambda item: item[1]
    ):
        match = indexed_re.match(feature_name)
        if match is None:
            parameter_name = feature_name
            parameter_index = 0
        else:
            parameter_name = match.group("base")
            parameter_index = int(match.group("index"))
        grouped.setdefault(parameter_name, {})[config_index] = parameter_index

    parameters = {
        parameter_name: Conf2BelParameter(
            name=parameter_name,
            width=max(parameter_bits.values()) + 1,
            config_to_parameter_bits=dict(parameter_bits),
        )
        for parameter_name, parameter_bits in grouped.items()
    }

    config_width = sum(config_ports.values())
    max_config_bit = max(
        config_bit
        for parameter in parameters.values()
        for config_bit in parameter.config_to_parameter_bits
    )
    if max_config_bit >= config_width:
        raise ValueError(
            f"BelMap references config bit {max_config_bit}, "
            f"but GLOBAL config width is only {config_width}."
        )

    module.remove(config_wires)
    module.fixup_ports()

    parameter_lines: list[str] = []
    for parameter in sorted(parameters.values(), key=lambda item: item.name):
        if parameter.width == 1:
            parameter_lines.append(f"parameter {parameter.name} = 1'b0")
        else:
            parameter_lines.append(
                f"parameter [{parameter.width - 1}:0] {parameter.name} = "
                f"{parameter.width}'b{'0' * parameter.width}"
            )

    blackbox_verilog = f"module {module_name}"
    if parameter_lines:
        blackbox_verilog += " #(\n  " + ",\n  ".join(parameter_lines) + "\n)"
    if port_lines:
        blackbox_verilog += " (\n  " + ",\n  ".join(port_lines) + "\n)"
    blackbox_verilog += ";\nendmodule\n"

    bridge.read_verilog_string(
        blackbox_verilog,
        replace_design=True,
        blackbox=True,
    )

    return Conf2BelModel(
        module_name=module_name,
        config_ports=config_ports,
        parameters=parameters,
        blackbox_bridge=bridge,
        blackbox_verilog=blackbox_verilog,
    )


def apply_conf2bel_to_design(bridge: PyosysBridge, model: Conf2BelModel) -> None:
    """Convert matching BEL cells in a pyosys netlist from config ports to params.

    This function walks and mutates only ``bridge.design``. Matching cells are
    found through ``module.cells_``. Their config carrier ports are read as
    direct ``SigSpec`` objects, packed into pyosys parameters, and removed from
    the cell with ``unsetPort``.

    Parameters
    ----------
    bridge : PyosysBridge
        Active design containing a synthesized netlist.
    model : Conf2BelModel
        Conversion model from `derive_conf2bel_from_verilog`.

    Raises
    ------
    ValueError
        If a matching BEL cell has an incomplete or non-constant config carrier.
    """
    for module in bridge.design.modules_.values():
        for cell in module.cells_.values():
            if str(cell.type).removeprefix("\\") != model.module_name:
                continue

            _rename_cell_port(
                cell=cell,
                old_port=FABULOUS_USER_CLK_PORT,
                new_port=CLK_PORT,
            )

            present_config_ports = [
                port_name
                for port_name in model.config_ports
                if cell.hasPort(ys.IdString(f"\\{port_name}"))
            ]
            if not present_config_ports:
                continue
            if len(present_config_ports) != len(model.config_ports):
                missing = sorted(set(model.config_ports) - set(present_config_ports))
                raise ValueError(
                    f"Cell {cell.name} of type {model.module_name} is missing "
                    f"config port(s): {', '.join(missing)}."
                )

            config_bits: list[int] = []
            for port_name, width in model.config_ports.items():
                port_id = ys.IdString(f"\\{port_name}")
                signal = cell.getPort(port_id)
                if signal.size() != width:
                    raise ValueError(
                        f"Config port {port_name} has width {signal.size()}, "
                        f"expected {width}."
                    )
                if not signal.is_fully_const():
                    raise ValueError(
                        f"Cell {cell.name} of type {model.module_name} must have "
                        "constant config bits."
                    )
                for bit in signal.to_sigbit_vector():
                    if bit.data == ys.State.S0:
                        config_bits.append(0)
                    elif bit.data == ys.State.S1:
                        config_bits.append(1)
                    else:
                        raise ValueError(
                            f"Cell {cell.name} of type {model.module_name} must have "
                            "0/1 config bits."
                        )

            for parameter in model.parameters.values():
                value = 0
                for (
                    config_bit,
                    parameter_bit,
                ) in parameter.config_to_parameter_bits.items():
                    value |= config_bits[config_bit] << parameter_bit
                cell.setParam(
                    ys.IdString(f"\\{parameter.name}"),
                    ys.Const(value, parameter.width),
                )
            for port_name in model.config_ports:
                cell.unsetPort(ys.IdString(f"\\{port_name}"))


def _conf2bel_port_name(port_name: str) -> str:
    """Return the nextpnr-facing port name for one BEL RTL port.

    Parameters
    ----------
    port_name : str
        Port name from the FABulous BEL RTL.

    Returns
    -------
    str
        Port name used in the derived blackbox and converted cells.
    """
    if port_name == FABULOUS_USER_CLK_PORT:
        return CLK_PORT
    return port_name


def _rename_cell_port(cell: ys.Cell, old_port: str, new_port: str) -> None:
    """Rename one cell port while preserving its connected signal.

    Parameters
    ----------
    cell : ys.Cell
        Cell to mutate.
    old_port : str
        Existing port name to move from.
    new_port : str
        Replacement port name to move to.
    """
    if old_port == new_port:
        return

    old_port_id = ys.IdString(f"\\{old_port}")
    if not cell.hasPort(old_port_id):
        return

    new_port_id = ys.IdString(f"\\{new_port}")
    signal = cell.getPort(old_port_id)
    cell.setPort(new_port_id, signal)
    cell.unsetPort(old_port_id)
