"""The ports of a supertile member tile, in its synthesised and post-layout graphs.

A supertile is hardened as one macro. When its synthesis keeps the member tile
modules (`SYNTH_KEEP_HIERARCHY_MODULES`), the flat post-layout netlist still
prefixes each member cell with its member instance, and each wire between two
members keeps the name the supertile module gives it. A member port bit is found
in the layout through that net name.

Each member port bit with leaf pins in the synthesised member becomes one port
node, named like a top-level port pin (`N1END[0]`), in both graphs. In the layout
graph an input port node carries the wire into each member load, so a wire
between two members is charged once, at the member that receives it. An output
port node carries the wire to the supertile port it drives, or nothing when the
wire only goes to a sibling member.
"""

from dataclasses import dataclass

from fabulous.fabric_cad.timing_model.macro import PhysicalMacro
from fabulous.fabric_cad.timing_model.netlist import (
    HierPath,
    PortBit,
    PortDirection,
    sdf_identifier,
    sdf_path,
)
from fabulous.fabric_cad.timing_model.sdf_timing_graph import (
    Component,
    SDFCellType,
    SdfTimingGraph,
)

_KEEP_HIERARCHY = (
    "Harden the supertile with SYNTH_KEEP_HIERARCHY_MODULES set to its member tile "
    "modules, as FABulous does unless the GDS config replaces it."
)


@dataclass(frozen=True, slots=True)
class MemberViews:
    """The timing graphs of one member tile, each with the member's port nodes.

    Attributes
    ----------
    synth : SdfTimingGraph
        The synthesised member.
    layout : SdfTimingGraph
        The member in the post-layout graph.
    ports : dict[PortBit, str]
        Port node of each member port bit with a pin in the member, in port order.
    """

    synth: SdfTimingGraph
    layout: SdfTimingGraph
    ports: dict[PortBit, str]


def member_views(timing: PhysicalMacro, member: HierPath) -> MemberViews:
    """Return the synthesised and the post-layout views of a member tile.

    Parameters
    ----------
    timing : PhysicalMacro
        Timing of the supertile macro.
    member : HierPath
        Path of the member tile instance in the supertile module.

    Returns
    -------
    MemberViews
        Both views, with the same port nodes.

    Raises
    ------
    ValueError
        If the post-layout netlist has no cell of the member, or a member port
        bit cannot be found on one net with a pin in the member.
    """
    netlist = timing.synth.netlist
    synth = timing.synth.graph.within(f"{sdf_path(member)}/")
    # OpenROAD links flat, so the member instance is part of each cell name.
    layout_prefix = "".join(f"{sdf_identifier(name)}\\/" for name in member)
    layout = timing.layout.within(layout_prefix)
    if layout.graph.number_of_nodes() == 0:
        raise ValueError(
            f"The post-layout {netlist.top!r} netlist has no cell of member tile "
            f"{'/'.join(member)!r}: the supertile was hardened with its members "
            f"flattened. {_KEEP_HIERARCHY}"
        )
    ports: dict[PortBit, str] = {}
    synth_ports: dict[PortDirection, dict[str, dict[str, Component | None]]] = {
        "input": {},
        "output": {},
    }
    layout_ports: dict[PortDirection, dict[str, dict[str, Component | None]]] = {
        "input": {},
        "output": {},
    }
    for direction in ("input", "output"):
        for bit in netlist.port_bits(member, direction=direction):
            pins = [pin for pin in netlist.leaf_pins(member, bit) if pin in synth.graph]
            if not pins:
                continue
            node = bit.port if bit.index is None else f"{bit.port}[{bit.index}]"
            ports[bit] = node
            synth_ports[direction][node] = dict.fromkeys(pins)
            member_pins = _layout_member_pins(timing, member, bit, layout_prefix)
            if direction == "input":
                layout_ports[direction][node] = {
                    pin: _wire_into(timing.layout, pin, layout_prefix)
                    for pin in member_pins
                }
            else:
                driver, wire = _wire_out_of(timing.layout, member_pins)
                layout_ports[direction][node] = {driver: wire}
    return MemberViews(
        synth=synth.with_ports(
            inputs=synth_ports["input"], outputs=synth_ports["output"]
        ),
        layout=layout.with_ports(
            inputs=layout_ports["input"], outputs=layout_ports["output"]
        ),
        ports=ports,
    )


def _layout_member_pins(
    timing: PhysicalMacro, member: HierPath, bit: PortBit, prefix: str
) -> list[str]:
    """Return the member's leaf pins on the post-layout net of a member port bit.

    Parameters
    ----------
    timing : PhysicalMacro
        Timing of the supertile macro.
    member : HierPath
        Path of the member tile instance.
    bit : PortBit
        Port bit of the member.
    prefix : str
        Prefix of the member's pins in the post-layout graph.

    Returns
    -------
    list[str]
        The pins, in post-layout netlist order.

    Raises
    ------
    ValueError
        If no post-layout net has a name of the synthesised net, two nets do,
        or the net has no pin in the member.
    """
    names = timing.synth.netlist.parent_net_names(member, bit)
    port = f"{'/'.join(member)}/{bit.port}" + (
        "" if bit.index is None else f"[{bit.index}]"
    )
    nets: dict[tuple[str, ...], str] = {}
    for name in names:
        pins = timing.layout_netlist.top_net_leaf_pins(name)
        if pins is not None:
            nets.setdefault(tuple(pins), name)
    if not nets:
        raise ValueError(
            f"Member port {port!r} is on the net named {names} in the synthesised "
            f"netlist, but the post-layout {timing.layout_netlist.top!r} netlist "
            f"has no net of that name. {_KEEP_HIERARCHY}"
        )
    if len(nets) > 1:
        raise ValueError(
            f"Member port {port!r} matches the different post-layout nets "
            f"{list(nets.values())}."
        )
    ((pins, name),) = nets.items()
    member_pins = [pin for pin in pins if pin.startswith(prefix)]
    if not member_pins:
        raise ValueError(
            f"Member port {port!r} is on post-layout net {name!r}, which has no pin "
            f"inside the member: a cell sits between the member and the net. "
            f"{_KEEP_HIERARCHY}"
        )
    return member_pins


def _wires(graph: SdfTimingGraph, pin: str, *, into: bool) -> list[Component]:
    """Return the INTERCONNECT components into or out of a pin."""
    if pin not in graph.graph:
        return []
    edges = graph.graph.in_edges(pin) if into else graph.graph.out_edges(pin)
    components = [graph.graph.edges[edge]["component"] for edge in edges]
    return [wire for wire in components if wire.c_type == SDFCellType.INTERCONNECT]


def _wire_into(graph: SdfTimingGraph, load: str, prefix: str) -> Component:
    """Return the one wire that drives a member load from outside the member.

    Parameters
    ----------
    graph : SdfTimingGraph
        The post-layout graph.
    load : str
        Member pin on the net of a member input.
    prefix : str
        Prefix of the member's pins.

    Returns
    -------
    Component
        The wire.

    Raises
    ------
    ValueError
        If the load is not driven by exactly one wire, or the wire comes from
        inside the member.
    """
    wires = _wires(graph, load, into=True)
    if len(wires) != 1:
        raise ValueError(
            f"Member input pin {load!r} is driven by {len(wires)} wires in the "
            "post-layout SDF, not one."
        )
    (wire,) = wires
    if wire.from_cell_instance.startswith(prefix):
        raise ValueError(
            f"Member input pin {load!r} is driven from inside its own member, by "
            f"{wire.from_cell_instance}/{wire.from_cell_pin}."
        )
    return wire


def _wire_out_of(
    graph: SdfTimingGraph, pins: list[str]
) -> tuple[str, Component | None]:
    """Return the driver of a member output and its wire to a supertile port.

    Parameters
    ----------
    graph : SdfTimingGraph
        The post-layout graph.
    pins : list[str]
        Member pins on the net of a member output.

    Returns
    -------
    tuple[str, Component | None]
        The driver pin, and its wire to the supertile output port, or `None` if
        the net only goes to sibling members.

    Raises
    ------
    ValueError
        If the net has not exactly one driver in the member, or drives two
        supertile ports.
    """
    drivers = [pin for pin in pins if _wires(graph, pin, into=False)]
    if len(drivers) != 1:
        raise ValueError(
            f"The post-layout net of member pins {pins} has {len(drivers)} drivers "
            "in the member, not one."
        )
    (driver,) = drivers
    top_ports = set(graph.output_ports)
    to_ports = [
        wire
        for wire in _wires(graph, driver, into=False)
        if wire.to_cell_instance == "" and wire.to_cell_pin in top_ports
    ]
    if len(to_ports) > 1:
        raise ValueError(
            f"Member output pin {driver!r} drives {len(to_ports)} supertile ports."
        )
    return driver, to_ports[0] if to_ports else None
