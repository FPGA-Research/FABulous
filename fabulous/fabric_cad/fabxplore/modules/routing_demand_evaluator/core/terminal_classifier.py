"""Classify FABulous tile resources into routing-demand terminals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    FabulousRoutingKeyword,
    RoutingTerminal,
    RoutingTerminalCatalog,
    RoutingTerminalRole,
    RoutingTerminalSource,
)
from fabulous.fabric_definition.define import IO, Direction

if TYPE_CHECKING:
    from fabulous.fabric_definition.bel import Bel
    from fabulous.fabric_definition.port import Port
    from fabulous.fabric_definition.tile import Tile


def classify_tile_terminals(
    tile: Tile,
    carry_port_roles: dict[str, RoutingTerminalRole] | None = None,
) -> RoutingTerminalCatalog:
    """Classify terminals for one FABulous tile.

    Parameters
    ----------
    tile : Tile
        Loaded FABulous tile.
    carry_port_roles : dict[str, RoutingTerminalRole] | None
        Optional carry roles discovered from carry-annotated tile CSV ports.

    Returns
    -------
    RoutingTerminalCatalog
        Classified terminal catalog.
    """
    terminals: list[RoutingTerminal] = []
    for port in tile.portsInfo:
        terminals.extend(_terminals_from_port(port))
    for bel in tile.bels:
        terminals.extend(_terminals_from_bel(bel))
    return RoutingTerminalCatalog(
        terminals=_dedupe_terminals(
            _apply_carry_port_roles(terminals, carry_port_roles or {})
        )
    )


def _terminals_from_port(port: Port) -> list[RoutingTerminal]:
    """Classify expanded terminals from a FABulous port.

    Parameters
    ----------
    port : Port
        FABulous port.

    Returns
    -------
    list[RoutingTerminal]
        Classified port terminals.
    """
    terminals: list[RoutingTerminal] = []
    sources, sinks = port.expandPortInfo("AutoSwitchMatrix")
    if port.wireDirection == Direction.JUMP:
        terminals.extend(
            _make_port_terminal(port, source, RoutingTerminalRole.JUMP_BEGIN)
            for source in sources
        )
        role = (
            RoutingTerminalRole.CONSTANT
            if not sources and sinks
            else RoutingTerminalRole.JUMP_END
        )
        terminals.extend(_make_port_terminal(port, sink, role) for sink in sinks)
        return terminals

    terminals.extend(
        _make_port_terminal(port, source, RoutingTerminalRole.TILE_OUTPUT)
        for source in sources
        if source != FabulousRoutingKeyword.NULL
    )
    terminals.extend(
        _make_port_terminal(port, sink, RoutingTerminalRole.TILE_INPUT)
        for sink in sinks
        if sink != FabulousRoutingKeyword.NULL
    )
    return terminals


def _make_port_terminal(
    port: Port,
    name: str,
    role: RoutingTerminalRole,
) -> RoutingTerminal:
    """Build one terminal from a FABulous port.

    Parameters
    ----------
    port : Port
        FABulous port.
    name : str
        Expanded node name.
    role : RoutingTerminalRole
        Terminal role.

    Returns
    -------
    RoutingTerminal
        Classified terminal.
    """
    return RoutingTerminal(
        name=name,
        role=role,
        source=RoutingTerminalSource.TILE_PORT,
        port_name=port.name,
        direction=port.wireDirection.value,
        x_offset=port.xOffset,
        y_offset=port.yOffset,
        wire_count=port.wireCount,
    )


def _terminals_from_bel(bel: Bel) -> list[RoutingTerminal]:
    """Classify terminals from a FABulous BEL.

    Parameters
    ----------
    bel : Bel
        FABulous BEL.

    Returns
    -------
    list[RoutingTerminal]
        Classified BEL terminals.
    """
    terminals: list[RoutingTerminal] = []
    carry_inputs, carry_outputs = _carry_terminal_names(bel)
    local_shared = _local_shared_terminal_roles(bel)
    shared = _shared_terminal_roles(bel)

    for port in bel.inputs:
        terminals.append(
            _make_bel_terminal(
                bel,
                port,
                local_shared.get(
                    port,
                    shared.get(
                        port,
                        RoutingTerminalRole.CARRY_INPUT
                        if port in carry_inputs
                        else RoutingTerminalRole.BEL_INPUT,
                    ),
                ),
            )
        )
    for port in bel.outputs:
        terminals.append(
            _make_bel_terminal(
                bel,
                port,
                RoutingTerminalRole.CARRY_OUTPUT
                if port in carry_outputs
                else RoutingTerminalRole.BEL_OUTPUT,
            )
        )
    for port in bel.externalInput:
        terminals.append(
            _make_bel_terminal(bel, port, RoutingTerminalRole.EXTERNAL_INPUT)
        )
    for port in bel.externalOutput:
        terminals.append(
            _make_bel_terminal(bel, port, RoutingTerminalRole.EXTERNAL_OUTPUT)
        )
    return terminals


def _make_bel_terminal(
    bel: Bel,
    name: str,
    role: RoutingTerminalRole,
) -> RoutingTerminal:
    """Build one terminal from a FABulous BEL.

    Parameters
    ----------
    bel : Bel
        FABulous BEL.
    name : str
        BEL port name.
    role : RoutingTerminalRole
        Terminal role.

    Returns
    -------
    RoutingTerminal
        Classified terminal.
    """
    return RoutingTerminal(
        name=name,
        role=role,
        source=RoutingTerminalSource.BEL,
        bel_name=bel.name,
        bel_module=bel.module_name,
        bel_prefix=bel.prefix,
        port_name=name.removeprefix(bel.prefix),
    )


def _carry_terminal_names(bel: Bel) -> tuple[set[str], set[str]]:
    """Return carry input and output terminal names.

    Parameters
    ----------
    bel : Bel
        FABulous BEL.

    Returns
    -------
    tuple[set[str], set[str]]
        Carry input names and carry output names.
    """
    inputs: set[str] = set()
    outputs: set[str] = set()
    for carry in bel.carry.values():
        if input_name := carry.get(IO.INPUT):
            inputs.add(input_name)
        if output_name := carry.get(IO.OUTPUT):
            outputs.add(output_name)
    return inputs, outputs


def _local_shared_terminal_roles(bel: Bel) -> dict[str, RoutingTerminalRole]:
    """Return local shared BEL terminal roles.

    Parameters
    ----------
    bel : Bel
        FABulous BEL.

    Returns
    -------
    dict[str, RoutingTerminalRole]
        Mapping from BEL port name to terminal role.
    """
    roles: dict[str, RoutingTerminalRole] = {}
    for feature, (port_name, _io) in bel.localShared.items():
        if feature == FabulousRoutingKeyword.RESET:
            roles[port_name] = RoutingTerminalRole.LOCAL_RESET
        elif feature == FabulousRoutingKeyword.ENABLE:
            roles[port_name] = RoutingTerminalRole.LOCAL_ENABLE
    return roles


def _shared_terminal_roles(bel: Bel) -> dict[str, RoutingTerminalRole]:
    """Return shared BEL terminal roles.

    Parameters
    ----------
    bel : Bel
        FABulous BEL.

    Returns
    -------
    dict[str, RoutingTerminalRole]
        Mapping from BEL port name to terminal role.
    """
    roles: dict[str, RoutingTerminalRole] = {}
    for port_name, _io in bel.sharedPort:
        local_name = port_name.removeprefix(bel.prefix)
        if local_name == FabulousRoutingKeyword.RESET:
            roles[port_name] = RoutingTerminalRole.SHARED_RESET
        elif local_name == FabulousRoutingKeyword.ENABLE:
            roles[port_name] = RoutingTerminalRole.SHARED_ENABLE
    return roles


def _apply_carry_port_roles(
    terminals: list[RoutingTerminal],
    carry_port_roles: dict[str, RoutingTerminalRole],
) -> list[RoutingTerminal]:
    """Apply carry roles discovered from tile CSV port annotations.

    Parameters
    ----------
    terminals : list[RoutingTerminal]
        Terminals classified from FABulous objects.
    carry_port_roles : dict[str, RoutingTerminalRole]
        Mapping from expanded tile-port node name to carry role.

    Returns
    -------
    list[RoutingTerminal]
        Terminals with carry-annotated tile ports reclassified.
    """
    if not carry_port_roles:
        return terminals
    return [
        terminal.model_copy(update={"role": carry_port_roles[terminal.name]})
        if terminal.name in carry_port_roles
        and terminal.source == RoutingTerminalSource.TILE_PORT
        else terminal
        for terminal in terminals
    ]


def _dedupe_terminals(terminals: list[RoutingTerminal]) -> list[RoutingTerminal]:
    """Deduplicate terminals while preserving order.

    Parameters
    ----------
    terminals : list[RoutingTerminal]
        Terminal list.

    Returns
    -------
    list[RoutingTerminal]
        Deduplicated terminals.
    """
    seen: set[tuple[str, RoutingTerminalRole]] = set()
    result: list[RoutingTerminal] = []
    for terminal in terminals:
        key = (terminal.name, terminal.role)
        if key in seen:
            continue
        seen.add(key)
        result.append(terminal)
    return result
