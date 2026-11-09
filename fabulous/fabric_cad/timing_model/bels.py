"""Timing arcs of one BEL, read from the synthesised netlist of its macro."""

from decimal import Decimal

import networkx as nx
from loguru import logger

from fabulous.fabric_cad.timing_model.config import scale_delay
from fabulous.fabric_cad.timing_model.macro import TimedNetlist
from fabulous.fabric_cad.timing_model.netlist import HierPath, PortBit, sdf_path
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.timing import (
    BelArcs,
    BelPin,
    ClockArc,
    ClockToOutArc,
    Condition,
    DelayArc,
    FeatureIs,
    SetupHoldArc,
)


def characterize_bel(
    synth: TimedNetlist, bel: Bel, *, instance: HierPath, scale: Decimal
) -> BelArcs:
    """Return the combinational and sequential timing arcs of one BEL.

    Clocks are the BEL inputs with a path to a register clock pin. Setup and
    hold are characterised at register inputs and clock-to-output at register
    outputs independently; a register's other endpoint may connect to an
    external BEL port. Only the hierarchical synthesised netlist is read: the
    post-layout netlist flattens away the BEL instance.

    Parameters
    ----------
    synth : TimedNetlist
        The synthesised netlist of the BEL's macro and its timing.
    bel : Bel
        Fabric definition of the BEL.
    instance : HierPath
        Path of the BEL instance in the synthesised netlist.
    scale : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    BelArcs
        Timing arcs in BEL port names, scaled by `scale`.

    Raises
    ------
    ValueError
        If the BEL instance is absent from the synthesised netlist.
    """
    identifier = "/".join(instance)
    if instance not in synth.netlist:
        raise ValueError(f"BEL {identifier!r} not found in the synthesised netlist.")
    input_pins: dict[BelPin, list[str]] = {}
    output_pins: dict[BelPin, list[str]] = {}
    shared_inputs: dict[BelPin, list[str]] = {}
    for category in ("internal", "shared"):
        for port, (direction, width) in bel.ports_vectors.get(category, {}).items():
            if direction not in {IO.INPUT, IO.OUTPUT}:
                continue
            for index in range(width):
                name = BelPin(port, None if width == 1 else index)
                pins = synth.netlist.leaf_pins(instance, PortBit(port, name.bit))
                if direction == IO.INPUT:
                    if category == "shared":
                        shared_inputs[name] = pins
                    else:
                        input_pins[name] = pins
                elif category == "internal":
                    output_pins[name] = pins

    hierarchical_prefix = sdf_path(instance) + "/"
    # Routing feedback belongs to pip timing, not to the BEL's internal arcs.
    graph = synth.graph.within(hierarchical_prefix)
    register_pins = [
        (source, target)
        for source, target, data in graph.graph.edges(data=True)
        if data["component"].is_timing_check and target.startswith(hierarchical_prefix)
    ]
    logger.info(
        f"Extracting synthesis timing for BEL {identifier} "
        f"({len(register_pins)} register input checks)"
    )
    clock_sources: dict[str, list[tuple[BelPin, str]]] = {}
    clock_ports: set[BelPin] = set()
    for register_clock in dict.fromkeys(clock for _, clock in register_pins):
        for port, pins in (input_pins | shared_inputs).items():
            for pin in pins:
                if nx.has_path(graph.clock_graph, pin, register_clock):
                    clock_sources.setdefault(register_clock, []).append((port, pin))
                    clock_ports.add(port)

    has_ff = "FF" in bel.belFeatureMap
    ff_condition: Condition = (FeatureIs("FF", True),) if has_ff else ()

    def sequential_condition(port: BelPin) -> Condition:
        """Preserve the documented mode controls of the standard IOBUF and LC."""
        feature = f"{port.name}_REG"
        if bel.name == "IOBUF" and feature in bel.belFeatureMap:
            return (FeatureIs(feature, True),)
        return ff_condition

    setup_holds: dict[tuple[BelPin, BelPin], tuple[Decimal, Decimal]] = {}
    clock_delays: dict[tuple[BelPin, BelPin], Decimal] = {}
    for data_pin, register_clock in register_pins:
        for clock, clock_source in clock_sources.get(register_clock, []):
            for port, pins in input_pins.items():
                if port in clock_ports:
                    continue
                for pin in pins:
                    try:
                        paths = graph.query_register_input_timing(
                            pin, data_pin, register_clock, clock_source
                        )
                    except nx.NetworkXNoPath:
                        continue
                    for path in paths:
                        setups = [
                            value.maximum
                            for value in path.effective_setup
                            if value.maximum is not None
                        ]
                        holds = [
                            value.maximum
                            for value in path.effective_hold
                            if value.maximum is not None
                        ]
                        if not setups or not holds:
                            continue
                        key = (port, clock)
                        setup, hold = max(setups), max(holds)
                        if key in setup_holds:
                            setup = max(setup, setup_holds[key][0])
                            hold = max(hold, setup_holds[key][1])
                        setup_holds[key] = (setup, hold)

    for register_clock, sources in clock_sources.items():
        for clock, clock_source in sources:
            for port, pins in output_pins.items():
                for pin in pins:
                    try:
                        paths = graph.query_timing_paths(
                            register_clock,
                            pin,
                            clock_pin=clock_source,
                            include_timing_checks=False,
                        )
                    except nx.NetworkXNoPath:
                        continue
                    for path in paths:
                        delays = [
                            value.maximum
                            for value in (
                                path.clock_to_output_rise,
                                path.clock_to_output_fall,
                            )
                            if value is not None and value.maximum is not None
                        ]
                        if delays:
                            key = (port, clock)
                            delay = max(delays)
                            if key in clock_delays:
                                delay = max(delay, clock_delays[key])
                            clock_delays[key] = delay

    clock_arcs = tuple(
        ClockArc(clock, when=ff_condition)
        for clock in dict.fromkeys(clock for _, clock in [*setup_holds, *clock_delays])
    )
    delay_arcs: list[DelayArc] = []
    registered_outputs = {port for port, _ in clock_delays}
    for source, source_pins in input_pins.items():
        if source in clock_ports:
            continue
        for sink, sink_pins in output_pins.items():
            delays = []
            for source_pin in source_pins:
                for sink_pin in sink_pins:
                    try:
                        paths = graph.query_combinational_paths(source_pin, sink_pin)
                    except nx.NetworkXNoPath:
                        continue
                    for path in paths:
                        delays.extend(
                            value.maximum
                            for value in (path.rise, path.fall)
                            if value.maximum is not None
                        )
            if delays:
                condition: Condition = (
                    (FeatureIs("FF", False),)
                    if has_ff and sink in registered_outputs
                    else ()
                )
                delay_arcs.append(
                    DelayArc(
                        source,
                        sink,
                        scale_delay(max(delays), factor=scale),
                        when=condition,
                    )
                )

    setup_arcs = tuple(
        SetupHoldArc(
            port,
            clock,
            scale_delay(setup, factor=scale),
            scale_delay(hold, factor=scale),
            when=sequential_condition(port),
        )
        for (port, clock), (setup, hold) in setup_holds.items()
    )
    output_arcs = tuple(
        ClockToOutArc(
            port,
            clock,
            scale_delay(delay, factor=scale),
            when=sequential_condition(port),
        )
        for (port, clock), delay in clock_delays.items()
    )
    arcs = BelArcs(
        clocks=clock_arcs,
        delays=tuple(delay_arcs),
        checks=setup_arcs,
        clock_to_outs=output_arcs,
    )
    arc_count = len(clock_arcs) + len(delay_arcs) + len(setup_arcs) + len(output_arcs)
    logger.info(f"Completed timing extraction for BEL {identifier} ({arc_count} arcs)")
    return arcs
