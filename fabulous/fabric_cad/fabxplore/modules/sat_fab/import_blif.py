"""BLIF import and flattening.

This module parses a practical combinational BLIF subset and converts it into
the internal flat :class:`Circuit` representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import Circuit, Signal


@dataclass
class BlifNames:
    """Raw BLIF ``.names`` block.

    Attributes
    ----------
    inputs : list[str]
        Input net names.
    output : str
        Output net name.
    rows : list[tuple[str, str]]
        Truth-table rows as ``(pattern, value)`` pairs.
    """

    inputs: list[str]
    output: str
    rows: list[tuple[str, str]]


@dataclass
class BlifSubckt:
    """Raw BLIF ``.subckt`` instance.

    Attributes
    ----------
    model : str
        Referenced model name.
    conns : dict[str, str]
        Mapping from formal pin name to actual net name.
    """

    model: str
    conns: dict[str, str]


@dataclass
class BlifModel:
    """Raw BLIF model.

    Attributes
    ----------
    name : str
        Model name.
    inputs : list[str]
        Input port names.
    outputs : list[str]
        Output port names.
    names_blocks : list[BlifNames]
        ``.names`` blocks contained in the model.
    subckts : list[BlifSubckt]
        ``.subckt`` instances contained in the model.
    """

    name: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    names_blocks: list[BlifNames] = field(default_factory=list)
    subckts: list[BlifSubckt] = field(default_factory=list)


def parse_blif(path: str | Path) -> dict[str, BlifModel]:
    """Parse a BLIF file into raw models.

    Parameters
    ----------
    path : str | Path
        BLIF file path.

    Returns
    -------
    dict[str, BlifModel]
        Parsed models keyed by model name.

    Raises
    ------
    ValueError
        If the file has malformed commands.
    """
    lines = _logical_lines(Path(path).read_text().splitlines())
    models: dict[str, BlifModel] = {}
    current: BlifModel | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == ".model":
            if len(parts) != 2:
                raise ValueError(".model requires one name")
            current = BlifModel(parts[1])
            models[current.name] = current
            index += 1
        elif cmd == ".inputs":
            _require_model(current, cmd).inputs.extend(parts[1:])
            index += 1
        elif cmd == ".outputs":
            _require_model(current, cmd).outputs.extend(parts[1:])
            index += 1
        elif cmd == ".names":
            model = _require_model(current, cmd)
            if len(parts) < 2:
                raise ValueError(".names requires at least an output")
            pins = parts[1:]
            rows: list[tuple[str, str]] = []
            index += 1
            while index < len(lines) and not lines[index].startswith("."):
                row = lines[index].split()
                if row:
                    if len(row) == 1:
                        rows.append(("", row[0]))
                    elif len(row) == 2:
                        rows.append((row[0], row[1]))
                    else:
                        raise ValueError(f"malformed .names row: {lines[index]}")
                index += 1
            model.names_blocks.append(BlifNames(pins[:-1], pins[-1], rows))
        elif cmd == ".subckt":
            model = _require_model(current, cmd)
            if len(parts) < 2:
                raise ValueError(".subckt requires a model name")
            conns: dict[str, str] = {}
            for token in parts[2:]:
                if "=" not in token:
                    raise ValueError(f"malformed .subckt connection: {token}")
                formal, actual = token.split("=", 1)
                conns[formal] = actual
            model.subckts.append(BlifSubckt(parts[1], conns))
            index += 1
        elif cmd == ".end":
            current = None
            index += 1
        elif cmd in {".latch", ".gate"}:
            raise ValueError(f"{cmd} is not supported by sat_fab BLIF import yet")
        else:
            raise ValueError(f"unsupported BLIF command: {cmd}")
    return models


def circuit_from_blif(
    path: str | Path,
    name: str | None = None,
    top: str | None = None,
    inputs: list[str] | None = None,
    configs: list[str] | None = None,
    config_prefixes: list[str] | None = None,
    outputs: list[str] | None = None,
    flatten: bool = True,
    max_truth_table_inputs: int = 12,
) -> Circuit:
    """Load a BLIF file into a flat circuit.

    Parameters
    ----------
    path : str | Path
        BLIF file path.
    name : str | None
        Optional circuit name.
    top : str | None
        Optional top model name.
    inputs : list[str] | None
        Normal input names and order.
    configs : list[str] | None
        Explicit external configuration input names.
    config_prefixes : list[str] | None
        Prefixes used to classify model inputs as configuration bits.
    outputs : list[str] | None
        Output names to expose.
    flatten : bool
        Whether to flatten defined ``.subckt`` instances.
    max_truth_table_inputs : int
        Maximum ``.names`` input count converted into a truth table.

    Returns
    -------
    Circuit
        Imported flat circuit.

    Raises
    ------
    ValueError
        If the BLIF contains unsupported hierarchy or oversized truth tables.
    """
    models = parse_blif(path)
    if not models:
        raise ValueError("BLIF file contains no models")
    top_name = top or next(iter(models))
    top_model = models[top_name]
    circuit = Circuit(name or top_model.name)
    config_names = set(configs or [])
    input_names = inputs or [
        port
        for port in top_model.inputs
        if port not in config_names and not _matches_prefix(port, config_prefixes or [])
    ]
    if config_prefixes:
        config_names.update(
            port for port in top_model.inputs if _matches_prefix(port, config_prefixes)
        )
    for input_name in input_names:
        circuit.input(input_name)
    for config_name in configs or []:
        circuit.config(config_name)
    for config_name in sorted(config_names - set(configs or [])):
        circuit.config(config_name)
    output_names = outputs or top_model.outputs[:]
    flat_names: list[BlifNames] = []
    if flatten:
        _flatten_model(models, top_name, {}, "", flat_names)
    elif top_model.subckts:
        raise ValueError("flatten=False does not support .subckt instances")
    else:
        flat_names.extend(top_model.names_blocks)
    flat_names = _prune_names_to_output_cone(flat_names, output_names)
    flat_names = _topological_sort_names_blocks(
        flat_names,
        available=set(input_names) | config_names,
    )
    for block in flat_names:
        if len(block.inputs) > max_truth_table_inputs:
            raise ValueError(
                f".names block for {block.output} has {len(block.inputs)} inputs; "
                f"limit is {max_truth_table_inputs}"
            )
        in_signals = [_net_signal(circuit, net) for net in block.inputs]
        out_signal = _net_signal(circuit, block.output)
        init = blif_names_to_init(len(block.inputs), block.rows)
        circuit.ttable(
            in_signals,
            init,
            name=block.output.replace(".", "_"),
            output=out_signal,
        )
    for output_name in output_names:
        circuit.output(output_name, _net_signal(circuit, output_name))
    return circuit


def _prune_names_to_output_cone(
    blocks: list[BlifNames],
    outputs: list[str],
) -> list[BlifNames]:
    """Keep only ``.names`` blocks that can affect selected outputs.

    Parameters
    ----------
    blocks : list[BlifNames]
        Flattened ``.names`` blocks.
    outputs : list[str]
        Output nets whose transitive fan-in cone should be retained.

    Returns
    -------
    list[BlifNames]
        Blocks in original order, pruned to the selected output cone.

    Raises
    ------
    ValueError
        If a net has multiple drivers.
    """
    driver_by_net: dict[str, int] = {}
    for index, block in enumerate(blocks):
        if block.output in driver_by_net:
            raise ValueError(f"multiple BLIF drivers for net {block.output!r}")
        driver_by_net[block.output] = index

    kept: set[int] = set()
    pending = list(outputs)
    while pending:
        net = pending.pop()
        driver_index = driver_by_net.get(net)
        if driver_index is None or driver_index in kept:
            continue
        kept.add(driver_index)
        pending.extend(blocks[driver_index].inputs)
    return [block for index, block in enumerate(blocks) if index in kept]


def _topological_sort_names_blocks(
    blocks: list[BlifNames],
    available: set[str],
) -> list[BlifNames]:
    """Sort flattened BLIF ``.names`` blocks by net dependencies.

    Parameters
    ----------
    blocks : list[BlifNames]
        Flattened ``.names`` blocks in file order.
    available : set[str]
        Nets that are available before any ``.names`` block is evaluated.

    Returns
    -------
    list[BlifNames]
        Blocks ordered so each internal driver appears before its users.

    Raises
    ------
    ValueError
        If a net has multiple drivers, a dependency has no source, or the
        blocks contain a combinational cycle.
    """
    driver_by_net: dict[str, int] = {}
    for index, block in enumerate(blocks):
        if block.output in driver_by_net:
            raise ValueError(f"multiple BLIF drivers for net {block.output!r}")
        driver_by_net[block.output] = index

    visiting: set[int] = set()
    visited: set[int] = set()
    ordered: list[BlifNames] = []

    def visit(index: int) -> None:
        """Visit one block after recursively visiting its drivers."""
        if index in visited:
            return
        if index in visiting:
            raise ValueError(
                f"combinational cycle involving BLIF net {blocks[index].output!r}"
            )
        visiting.add(index)
        for net in blocks[index].inputs:
            if net in available:
                continue
            driver_index = driver_by_net.get(net)
            if driver_index is not None:
                visit(driver_index)
            else:
                raise ValueError(
                    f"BLIF net {net!r} is used by {blocks[index].output!r} "
                    "but is not a model input, config input, or .names output"
                )
        visiting.remove(index)
        visited.add(index)
        ordered.append(blocks[index])

    for index in range(len(blocks)):
        visit(index)
    return ordered


def blif_names_to_init(num_inputs: int, rows: list[tuple[str, str]]) -> int:
    """Convert BLIF ``.names`` rows to an INIT integer.

    Parameters
    ----------
    num_inputs : int
        Number of input pins in the ``.names`` block.
    rows : list[tuple[str, str]]
        BLIF truth-table rows. Pattern character zero corresponds to input zero,
        which is also the least significant INIT index bit.

    Returns
    -------
    int
        LSB-first truth-table INIT integer.

    Raises
    ------
    ValueError
        If a pattern does not match the input count.
    """
    if num_inputs == 0:
        return 1 if any(value == "1" for _, value in rows) else 0
    init = 0
    for pattern, value in rows:
        if value != "1":
            continue
        if len(pattern) != num_inputs:
            raise ValueError(f"pattern {pattern!r} does not match {num_inputs} inputs")
        for index in range(1 << num_inputs):
            if _pattern_matches(pattern, index):
                init |= 1 << index
    return init


def _logical_lines(lines: list[str]) -> list[str]:
    """Build comment-free logical BLIF lines.

    Parameters
    ----------
    lines : list[str]
        Physical input lines.

    Returns
    -------
    list[str]
        Logical lines after comments and continuations are processed.
    """
    out: list[str] = []
    pending = ""
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        line = pending + line
        pending = ""
        out.append(line.strip())
    if pending:
        out.append(pending.strip())
    return out


def _require_model(model: BlifModel | None, command: str) -> BlifModel:
    """Return the active model or raise.

    Parameters
    ----------
    model : BlifModel | None
        Current model.
    command : str
        Command requiring a model.

    Returns
    -------
    BlifModel
        Active model.

    Raises
    ------
    ValueError
        If no model is active.
    """
    if model is None:
        raise ValueError(f"{command} outside .model")
    return model


def _flatten_model(
    models: dict[str, BlifModel],
    model_name: str,
    port_map: dict[str, str],
    prefix: str,
    out: list[BlifNames],
) -> None:
    """Flatten a model into ``.names`` blocks.

    Parameters
    ----------
    models : dict[str, BlifModel]
        Parsed model dictionary.
    model_name : str
        Model to flatten.
    port_map : dict[str, str]
        Formal-to-actual net mapping.
    prefix : str
        Internal-net prefix for this instance.
    out : list[BlifNames]
        Destination list of flattened ``.names`` blocks.

    Raises
    ------
    ValueError
        If a referenced subckt model is undefined.
    """
    if model_name not in models:
        raise ValueError(f"undefined .subckt model: {model_name}")
    model = models[model_name]
    for block in model.names_blocks:
        mapped_inputs = [_map_net(net, model, port_map, prefix) for net in block.inputs]
        mapped_output = _map_net(block.output, model, port_map, prefix)
        out.append(BlifNames(mapped_inputs, mapped_output, block.rows[:]))
    for index, subckt in enumerate(model.subckts):
        sub_prefix = f"{prefix}u{index}."
        sub_map = {
            formal: _map_net(actual, model, port_map, prefix)
            for formal, actual in subckt.conns.items()
        }
        _flatten_model(models, subckt.model, sub_map, sub_prefix, out)


def _map_net(net: str, model: BlifModel, port_map: dict[str, str], prefix: str) -> str:
    """Map a local BLIF net into the flattened namespace.

    Parameters
    ----------
    net : str
        Local net name.
    model : BlifModel
        Model that owns the net.
    port_map : dict[str, str]
        Formal-to-actual port map.
    prefix : str
        Internal-net prefix.

    Returns
    -------
    str
        Flattened net name.
    """
    if net in port_map:
        return port_map[net]
    if net in model.inputs or net in model.outputs:
        return net
    return f"{prefix}{net}" if prefix else net


def _net_signal(circuit: Circuit, net: str) -> Signal:
    """Return the circuit signal for a BLIF net.

    Parameters
    ----------
    circuit : Circuit
        Destination circuit.
    net : str
        BLIF net name.

    Returns
    -------
    Signal
        Circuit signal for the net.
    """
    if net in circuit.inputs_map:
        return circuit.input(net)
    if net in circuit.configs_map:
        return circuit.config(net)
    return circuit.signal(net)


def _pattern_matches(pattern: str, index: int) -> bool:
    """Check whether a BLIF pattern covers an INIT row index.

    Parameters
    ----------
    pattern : str
        BLIF pattern containing ``0``, ``1``, and ``-``.
    index : int
        LSB-first row index.

    Returns
    -------
    bool
        True if the pattern covers the row.
    """
    for bit_index, char in enumerate(pattern):
        bit = (index >> bit_index) & 1
        if char == "0" and bit != 0:
            return False
        if char == "1" and bit != 1:
            return False
    return True


def _matches_prefix(name: str, prefixes: list[str]) -> bool:
    """Check whether a name matches one of several prefixes.

    Parameters
    ----------
    name : str
        Name to classify.
    prefixes : list[str]
        Prefix strings.

    Returns
    -------
    bool
        True when the name starts with one of the prefixes.
    """
    return any(name.startswith(prefix) for prefix in prefixes)
