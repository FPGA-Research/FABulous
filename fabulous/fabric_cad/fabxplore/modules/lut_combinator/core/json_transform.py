"""Rewrite Yosys JSON netlists with mapped fractional LUT macro cells.

This module takes mapping results produced by the packer and applies them to a JSON
netlist model by removing original LUT instances and inserting packed macro instances.
It also preserves Yosys bit encoding conventions.
"""

import copy

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    MappingResult,
)


def apply_mapping_to_json(model_json: dict, mapping: MappingResult) -> dict:
    """Apply mapped-cell replacement to a Yosys JSON design dictionary.

    The function deep-copies the input JSON, removes source LUT cells that
    were consumed by packing, and inserts packed macro cells with updated
    port directions, parameters, and encoded connections.

    Parameters
    ----------
    model_json : dict
        Original Yosys JSON design dictionary.
    mapping : MappingResult
        Mapping output containing packed cells and placement ownership.

    Returns
    -------
    dict
        New JSON dictionary with mapped cells applied to ``mapping.top_name``.
        If the requested top module is not present, a deep copy is returned
        unchanged.
    """
    out: dict = copy.deepcopy(model_json)
    modules: dict = out.get("modules", {})

    if mapping.top_name not in modules:
        return out

    top: dict = modules[mapping.top_name]
    cells: dict = top.setdefault("cells", {})

    remove_ids: set[str] = {
        plc.cell.cell_id for mapped in mapping.mapped_cells for plc in mapped.placements
    }

    for cid in list(remove_ids):
        cells.pop(cid, None)

    for mapped in mapping.mapped_cells:
        conns: dict[str, list[int | str]] = {
            pin: [_to_json_bit(net)] for pin, net in (mapped.external_pin_nets.items())
        }

        for pin, net in mapped.output_pin_nets.items():
            conns[pin] = [_to_json_bit(net)]

        # Yosys JSON uses string bits for constants
        # and integer ids for wires. The _to_json_bit
        # function handles this conversion.
        cells[mapped.packed_id] = {
            "hide_name": 0,
            "type": mapped.architecture_name,
            "parameters": dict(mapped.parameters),
            "attributes": {},
            "port_directions": {
                **{k: "input" for k in mapped.external_pin_nets},
                **{k: "output" for k in mapped.output_pin_nets},
            },
            "connections": conns,
        }

    return out


def _to_json_bit(net: str) -> str | int:
    """Convert an internal net token to a Yosys JSON bit representation.

    Yosys JSON encodes constants as one-character strings
    (``"0"``, ``"1"``, ``"x"``, ``"z"``) and signal bits as integer IDs.
    This helper normalizes constants and converts decimal wire IDs.

    Parameters
    ----------
    net : str
        Internal net token from mapping data.

    Returns
    -------
    str | int
        Lower-cased constant token for constants, integer for purely
        decimal wire IDs, otherwise the original token string.
    """
    if net in {"0", "1", "x", "z", "X", "Z"}:
        return net.lower()
    if net.isdigit():
        return int(net)
    return net
