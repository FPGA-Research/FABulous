"""Apply register absorption rewrites to a live pyosys design."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
    RegAbsorberResult,
    RegAbsorption,
    RegisterAbsorptionSide,
    split_indexed_name,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge

_INDEXED_PORT_RE = re.compile(r"^(?P<base>.+)\[(?P<index>\d+)\]$")


class RegAbsorberWriter:
    """Apply register absorption plans to pyosys modules."""

    def apply(self, design: PyosysBridge, result: RegAbsorberResult) -> None:
        """Apply all absorptions in ``result``.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        result : RegAbsorberResult
            Absorption plan.
        """
        module = _find_module(design, result.top_name)
        for absorption in result.absorptions:
            self._apply_one(module, absorption)
        module.fixup_ports()

    def _apply_one(self, module: ys.Module, absorption: RegAbsorption) -> None:
        """Apply one absorption.

        Parameters
        ----------
        module : ys.Module
            Module containing the primitive and FF.
        absorption : RegAbsorption
            Absorption to apply.
        """
        primitive = _find_cell(module, absorption.primitive_cell_id)
        ff = _find_cell(module, absorption.ff_cell_id)
        rule = absorption.rule

        if absorption.side == RegisterAbsorptionSide.OUTPUT:
            primitive.setPort(
                _id(f"\\{rule.seq_port}"),
                ff.getPort(_id(f"\\{absorption.ff_output_port}")),
            )
        else:
            primitive.setPort(
                _id(f"\\{rule.seq_port}"),
                ff.getPort(_id(f"\\{absorption.ff_data_port}")),
            )

        if rule.clock_port is not None:
            clock_id = _id(f"\\{rule.clock_port}")
            if (
                not primitive.hasPort(clock_id)
                or primitive.getPort(clock_id).size() == 0
            ):
                primitive.setPort(
                    clock_id,
                    ff.getPort(_id(f"\\{absorption.ff_clock_port}")),
                )

        _connect_optional_control(
            primitive=primitive,
            ff=ff,
            tile_port=rule.enable_tile_port,
            ff_port=absorption.ff_enable_port,
            neutral=rule.enable_neutral,
        )
        _connect_optional_control(
            primitive=primitive,
            ff=ff,
            tile_port=rule.reset_tile_port,
            ff_port=absorption.ff_reset_port,
            neutral=rule.reset_neutral,
        )

        if (
            rule.remove_disconnected_comb_port
            and rule.comb_port != rule.seq_port
            and primitive.hasPort(_id(f"\\{rule.comb_port}"))
        ):
            primitive.unsetPort(_id(f"\\{rule.comb_port}"))

        _add_config_ports(primitive, rule.config)
        _add_params(primitive, rule.params)
        module.remove(ff)


def _connect_optional_control(
    primitive: ys.Cell,
    ff: ys.Cell,
    tile_port: str | None,
    ff_port: str | None,
    neutral: int | bool | None,
) -> None:
    """Connect or neutralize one optional tile control port.

    Parameters
    ----------
    primitive : ys.Cell
        Primitive absorbing the FF.
    ff : ys.Cell
        FF being removed.
    tile_port : str | None
        Optional tile control port.
    ff_port : str | None
        Optional source FF control port.
    neutral : int | bool | None
        Neutral constant when the FF has no matching control.
    """
    if tile_port is None:
        return
    if ff_port is not None:
        primitive.setPort(_id(f"\\{tile_port}"), ff.getPort(_id(f"\\{ff_port}")))
        return
    if neutral is not None:
        primitive.setPort(_id(f"\\{tile_port}"), _const_signal(int(bool(neutral)), 1))


def _find_module(design: PyosysBridge, top_name: str) -> ys.Module:
    """Find a module by clean name.

    Parameters
    ----------
    design : PyosysBridge
        Design containing the module.
    top_name : str
        Clean module name.

    Returns
    -------
    ys.Module
        Matching module.

    Raises
    ------
    RuntimeError
        If the module is absent.
    """
    for module in design.design.modules_.values():
        if _clean_name(module.name) == top_name:
            return module
    raise RuntimeError(f"Top module '{top_name}' not found")


def _find_cell(module: ys.Module, cell_id: str) -> ys.Cell:
    """Find one cell by clean name.

    Parameters
    ----------
    module : ys.Module
        Module containing the cell.
    cell_id : str
        Clean cell name.

    Returns
    -------
    ys.Cell
        Matching cell.

    Raises
    ------
    RuntimeError
        If the cell is absent.
    """
    clean_cell_id = _clean_name(cell_id)
    for cell in module.cells_.values():
        if _clean_name(cell.name) == clean_cell_id:
            return cell
    raise RuntimeError(f"Cell '{cell_id}' not found in module '{module.name}'")


def _add_config_ports(cell: ys.Cell, config_bits: dict[str, int | bool]) -> None:
    """Merge config-bit updates into a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Cell receiving config ports.
    config_bits : dict[str, int | bool]
        Config updates keyed by scalar or indexed port names.
    """
    grouped: dict[str, dict[int, int]] = {}
    scalar: dict[str, int] = {}
    for name, value in config_bits.items():
        bit = 1 if bool(value) else 0
        base, index = split_indexed_name(name)
        if index is None:
            scalar[base] = bit
        else:
            grouped.setdefault(base, {})[index] = bit

    for port, bit in scalar.items():
        cell.setPort(_id(f"\\{port}"), _const_signal(bit, 1))
    for port, indexed_bits in grouped.items():
        existing = (
            cell.getPort(_id(f"\\{port}"))
            if cell.hasPort(_id(f"\\{port}"))
            else ys.SigSpec()
        )
        width = max([existing.size(), *(index + 1 for index in indexed_bits)])
        bits = [
            existing.at(index) if index < existing.size() else ys.SigBit(ys.State.S0)
            for index in range(width)
        ]
        for index, bit in indexed_bits.items():
            bits[index] = ys.SigBit(ys.State.S1 if bit else ys.State.S0)
        cell.setPort(_id(f"\\{port}"), _indexed_signal(bits))


def _add_params(cell: ys.Cell, params: dict[str, str | int | bool]) -> None:
    """Set parameter updates on a pyosys cell.

    Parameters
    ----------
    cell : ys.Cell
        Cell receiving parameter updates.
    params : dict[str, str | int | bool]
        Parameter updates.
    """
    for name, value in params.items():
        cell.setParam(_id(f"\\{name}"), ys.Const(value))


def _indexed_signal(bits: list[ys.SigBit]) -> ys.SigSpec:
    """Return a vector signal from individual bits.

    Parameters
    ----------
    bits : list[ys.SigBit]
        Bits in LSB-first order.

    Returns
    -------
    ys.SigSpec
        Vector signal.
    """
    signal = ys.SigSpec()
    for bit in bits:
        signal.append(bit)
    return signal


def _const_signal(value: int, width: int) -> ys.SigSpec:
    """Return a constant signal.

    Parameters
    ----------
    value : int
        Constant value.
    width : int
        Constant width.

    Returns
    -------
    ys.SigSpec
        Constant signal.
    """
    return ys.SigSpec(ys.Const(value, width))


def _id(name: str) -> ys.IdString:
    """Return a pyosys identifier.

    Parameters
    ----------
    name : str
        Identifier text.

    Returns
    -------
    ys.IdString
        Identifier.
    """
    return ys.IdString(name)


def _clean_name(name: object) -> str:
    """Return a clean Yosys name.

    Parameters
    ----------
    name : object
        Yosys identifier-like object.

    Returns
    -------
    str
        Name without a leading backslash.
    """
    text = str(name)
    return text.removeprefix("\\")
