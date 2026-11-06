"""Pip delays of one tile type, read from the timing of its macro.

A pip whose two wires meet on one switch-matrix mux is internal: its delay is
the path through that mux. Every other pip is external: a tile output stitched
to the next tile, a tile input routed to its nearest output, or a mux output
followed to the next mux input. External delays reuse the mux each internal
pip resolved, so all internal pips are timed first.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from loguru import logger

from fabulous.fabric_cad.timing_db import Ns, Pip
from fabulous.fabric_cad.timing_model.config import scale_delay
from fabulous.fabric_cad.timing_model.macro import (
    MacroTiming,
    PhysicalMacro,
    StructuralMacro,
    TileMacro,
)
from fabulous.fabric_cad.timing_model.netlist import HierPath, NetlistIndex
from fabulous.fabric_cad.timing_model.sdf_timing_graph import SdfTimingGraph

# Delay of a pip with no timed path in the macro, such as a tile output
# stitched to the next tile; not 0, so that no pip is free.
DEFAULT_PIP_DELAY = Decimal("0.001")
# A followed mux-to-mux wire faster than this gets `DEFAULT_PIP_DELAY`.
_MIN_WIRE_DELAY = Decimal("1e-5")


@dataclass(frozen=True, slots=True)
class _Mux:
    """A switch-matrix mux, located in the graph the pip delays are read from.

    Attributes
    ----------
    inputs : dict[str, str]
        Node where the path from each mux net starts.
    output : str
        Output pin of the mux.
    """

    inputs: dict[str, str]
    output: str


def _wire_port_pins(netlist: NetlistIndex) -> dict[str, str]:
    """Return the SDF pin of each top-level port bit, by fabric wire name.

    The fabric names bit `i` of port `N2BEG` as wire `N2BEG{i}`; the SDF pin of
    that bit is `N2BEG[i]`. A one-bit port keeps its name.

    Parameters
    ----------
    netlist : NetlistIndex
        The macro netlist.

    Returns
    -------
    dict[str, str]
        SDF pin of each port bit, keyed by wire name.

    Raises
    ------
    ValueError
        If two port bits have the same wire name.
    """
    pins: dict[str, str] = {}
    for bit in netlist.top_port_bits():
        if bit.index is None:
            wire, pin = bit.port, bit.port
        else:
            wire, pin = f"{bit.port}{bit.index}", f"{bit.port}[{bit.index}]"
        if wire in pins:
            raise ValueError(
                f"Port bits {pins[wire]!r} and {pin!r} share the wire name {wire!r}."
            )
        pins[wire] = pin
    return pins


def _nearest_ports(
    graph: SdfTimingGraph, net_pins: dict[str, list[str]], *, reverse: bool
) -> dict[str, str]:
    """Return the nearest top-level port of each net, from its first leaf pin.

    Parameters
    ----------
    graph : SdfTimingGraph
        Timing graph of the netlist.
    net_pins : dict[str, list[str]]
        Leaf pins of each net.
    reverse : bool
        Search towards the input ports if set, else towards the output ports.

    Returns
    -------
    dict[str, str]
        Nearest port of each net that reaches one, by hop count.
    """
    targets = graph.input_ports if reverse else graph.output_ports
    ports: dict[str, str] = {}
    for net, pins in net_pins.items():
        if not pins:
            continue
        _, port = graph.path_to_nearest_target_sentinel(
            pins[0], targets, reverse=reverse
        )
        if port is not None:
            ports[net] = port
    return ports


def _resolve_mux(timing: MacroTiming, *, mux: HierPath, dst: str) -> _Mux:
    """Locate switch-matrix mux `mux`, which drives wire `dst`.

    In the synthesised netlist the mux pins are its leaf pins. In the
    post-layout netlist the mux hierarchy is gone: each net starts at its
    nearest synthesised input port, and the output is the earliest node all
    those ports converge on. A mux with a single input port (a buffer)
    converges on itself; then the output is three steps along the path to the
    nearest output port of `dst`.

    Parameters
    ----------
    timing : MacroTiming
        Timing of the macro.
    mux : HierPath
        Path of the mux instance in the synthesised netlist.
    dst : str
        Wire the mux drives.

    Returns
    -------
    _Mux
        The located mux.
    """
    pins = timing.synth.netlist.net_leaf_pins(mux)
    match timing:
        case StructuralMacro():
            return _Mux(
                inputs={net: net_pins[0] for net, net_pins in pins.items() if net_pins},
                output=pins[dst][0],
            )
        case PhysicalMacro(synth=synth, layout=layout):
            inputs = _nearest_ports(synth.graph, pins, reverse=True)
            sources = list(dict.fromkeys(inputs.values()))
            sentinel = None
            if len(sources) == 1:
                sentinel = _nearest_ports(synth.graph, pins, reverse=False)[dst]
            best_nodes, _, _ = layout.earliest_common_nodes(
                sources=sources,
                mode="max",
                sentinel=sentinel,
                prefer_sentinel_for_single_source=True,
                follow_steps_to_sentinel=3,
            )
            return _Mux(inputs=inputs, output=best_nodes[0])


def _external_delay(
    graph: SdfTimingGraph,
    *,
    pip: Pip,
    port_pin: str | None,
    mux_output: str | None,
) -> Decimal:
    """Return the delay of a pip that does not cross a switch-matrix mux.

    Parameters
    ----------
    graph : SdfTimingGraph
        Timing graph the delay is read from.
    pip : Pip
        The pip.
    port_pin : str | None
        SDF pin of `pip.src` if it is a top-level port bit.
    mux_output : str | None
        Output pin of the mux that drives `pip.src`, if an internal pip
        resolved it.

    Returns
    -------
    Decimal
        Unscaled delay in nanoseconds.
    """
    if port_pin in graph.output_ports:
        logger.info(
            f"Tile output {pip.src} to next tile input {pip.dst} "
            f"stitched delay: {DEFAULT_PIP_DELAY} ns"
        )
        return DEFAULT_PIP_DELAY
    if port_pin is not None and port_pin in graph.input_ports:
        _, out_port = graph.path_to_nearest_target_sentinel(
            port_pin, graph.output_ports
        )
        if out_port is None:
            logger.warning(
                f"No nearest port found for tile input {port_pin}. "
                f"Using default delay {DEFAULT_PIP_DELAY} ns"
            )
            return DEFAULT_PIP_DELAY
        return graph.single_delay(port_pin, out_port)
    if mux_output is None:
        logger.info(
            f"SWMy output {pip.src} to next SWMy input {pip.dst} directly "
            f"connected delay: {DEFAULT_PIP_DELAY} ns"
        )
        return DEFAULT_PIP_DELAY
    # Follow the wire to the next mux input, through a buffer if there is one.
    next_input = graph.follow_first_fanout_from_pins(
        hier_pin_path=mux_output, num_follow=2
    )
    delay = graph.single_delay(mux_output, next_input)
    if delay < _MIN_WIRE_DELAY:
        return DEFAULT_PIP_DELAY
    return delay


def characterize_tile_pips(
    timing: MacroTiming, *, macro: TileMacro, pips: Iterable[Pip], scale: Decimal
) -> dict[Pip, Ns]:
    """Return the delay of each pip of one tile type.

    Parameters
    ----------
    timing : MacroTiming
        Timing of the tile's macro.
    macro : TileMacro
        The tile type and its place in the macro.
    pips : Iterable[Pip]
        Pips of the tile type, in emission order.
    scale : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    dict[Pip, Ns]
        Scaled delay of each pip.

    Raises
    ------
    ValueError
        If the synthesised netlist has no instance of the tile's switch matrix.
    """
    netlist = timing.synth.netlist
    switch_matrix = (*macro.scope, macro.tile.switch_matrix_instance_name)
    if switch_matrix not in netlist:
        raise ValueError(
            f"Switch matrix instance {'/'.join(switch_matrix)!r} of tile "
            f"{macro.tile.name!r} not found in the {macro.top!r} netlist."
        )
    mux_nets = netlist.child_nets(switch_matrix)
    port_pins = _wire_port_pins(netlist)

    internal: dict[Pip, list[HierPath]] = {}
    external: list[Pip] = []
    for pip in dict.fromkeys(pips):
        muxes: list[HierPath] = [
            (*switch_matrix, mux)
            for mux, nets in mux_nets.items()
            if pip.src in nets and pip.dst in nets
        ]
        if pip.src != pip.dst and muxes:
            internal[pip] = muxes
        else:
            external.append(pip)

    match timing:
        case StructuralMacro(synth=synth):
            graph = synth.graph
        case PhysicalMacro(layout=layout):
            graph = layout
    # Pips that share a destination share its mux: the first pip locates it.
    located: dict[str, _Mux] = {}
    delays: dict[Pip, Ns] = {}
    for pip, muxes in internal.items():
        if len(muxes) > 1:
            logger.warning(
                f"Multiple switch matrix mux instances found for PIPs {pip.src} -> "
                f"{pip.dst}. Using the first one: {muxes[0]}"
            )
        mux = located.get(pip.dst)
        if mux is None:
            mux = _resolve_mux(timing, mux=muxes[0], dst=pip.dst)
            located[pip.dst] = mux
        delay = graph.single_delay(mux.inputs[pip.src], mux.output)
        delays[pip] = scale_delay(delay, factor=scale)
    for pip in external:
        mux = located.get(pip.src)
        delay = _external_delay(
            graph,
            pip=pip,
            port_pin=port_pins.get(pip.src),
            mux_output=None if mux is None else mux.output,
        )
        delays[pip] = scale_delay(delay, factor=scale)
    return delays
