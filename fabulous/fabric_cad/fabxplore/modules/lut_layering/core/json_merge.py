"""Yosys JSON helpers for safe overlay/base design merging."""

import copy
from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    PackedCell,
)


@dataclass(frozen=True)
class PreparedOverlayJson:
    """Hold a prefixed and bit-remapped overlay module.

    Attributes
    ----------
    netlist_json : dict
        Overlay JSON with the top module replaced by the prepared module.
    top_name : str
        Original overlay top module key.
    module : dict
        Prepared overlay top module dictionary.
    """

    netlist_json: dict
    top_name: str
    module: dict


def prepare_overlay_json(
    overlay_json: dict,
    overlay_top_name: str,
    prefix: str,
    fresh_bit_start: int,
) -> PreparedOverlayJson:
    """Prefix overlay names and remap signal bits into a fresh namespace.

    Parameters
    ----------
    overlay_json : dict
        Yosys JSON dictionary for the overlay design.
    overlay_top_name : str
        Overlay top module name.
    prefix : str
        Prefix applied to overlay ports, netnames, and cell names.
    fresh_bit_start : int
        First integer bit ID available in the base design.

    Returns
    -------
    PreparedOverlayJson
        Prepared overlay JSON/module data.

    Raises
    ------
    RuntimeError
        If ``overlay_top_name`` is not present.
    """
    modules = overlay_json.get("modules", {})
    if overlay_top_name not in modules:
        available = ", ".join(sorted(modules))
        raise RuntimeError(
            f"Overlay top module '{overlay_top_name}' not found. Available: {available}"
        )

    out = copy.deepcopy(overlay_json)
    module = copy.deepcopy(modules[overlay_top_name])
    bit_map = _build_bit_map(module, fresh_bit_start)

    module["ports"] = {
        f"{prefix}{name}": _remap_port(port, bit_map)
        for name, port in module.get("ports", {}).items()
    }
    module["netnames"] = {
        f"{prefix}{name}": _remap_netname(netname, bit_map)
        for name, netname in module.get("netnames", {}).items()
    }
    module["cells"] = {
        f"{prefix}{cell_id}": _remap_cell(cell, bit_map)
        for cell_id, cell in module.get("cells", {}).items()
    }

    out.setdefault("modules", {})[overlay_top_name] = module
    return PreparedOverlayJson(
        netlist_json=out,
        top_name=overlay_top_name,
        module=module,
    )


def prefix_base_top_names(
    base_json: dict,
    top_name: str,
    prefix: str | None,
) -> dict:
    """Return ``base_json`` with optional top port/netname prefixes applied.

    Parameters
    ----------
    base_json : dict
        Base design JSON dictionary.
    top_name : str
        Base top module name.
    prefix : str | None
        Prefix to apply. ``None`` or an empty prefix leaves the JSON unchanged.

    Returns
    -------
    dict
        Deep-copied JSON dictionary with renamed top ports and netnames.
    """
    out = copy.deepcopy(base_json)
    if not prefix:
        return out

    modules = out.get("modules", {})
    if top_name not in modules:
        return out

    top = modules[top_name]
    top["ports"] = {
        f"{prefix}{name}": port for name, port in top.get("ports", {}).items()
    }
    top["netnames"] = {
        f"{prefix}{name}": netname for name, netname in top.get("netnames", {}).items()
    }
    return out


def merge_overlay_module(
    base_json: dict,
    top_name: str,
    overlay: PreparedOverlayJson,
    removed_overlay_lut_ids: set[str],
) -> dict:
    """Merge prepared overlay ports, netnames, and non-injected cells into base.

    Parameters
    ----------
    base_json : dict
        Base design JSON dictionary to copy and extend.
    top_name : str
        Base top module name.
    overlay : PreparedOverlayJson
        Prepared overlay module data.
    removed_overlay_lut_ids : set[str]
        Prefixed overlay LUT cell IDs that were absorbed into FRAC cells.

    Returns
    -------
    dict
        Merged JSON dictionary.

    Raises
    ------
    RuntimeError
        If ``top_name`` is missing from the base design.
    """
    out = copy.deepcopy(base_json)
    modules = out.get("modules", {})
    if top_name not in modules:
        available = ", ".join(sorted(modules))
        raise RuntimeError(
            f"Base top module '{top_name}' not found. Available: {available}"
        )

    top = modules[top_name]
    top.setdefault("ports", {}).update(copy.deepcopy(overlay.module.get("ports", {})))
    top.setdefault("netnames", {}).update(
        copy.deepcopy(overlay.module.get("netnames", {}))
    )

    cells = top.setdefault("cells", {})
    for cell_id, cell in overlay.module.get("cells", {}).items():
        if cell_id in removed_overlay_lut_ids:
            continue
        cells[cell_id] = copy.deepcopy(cell)

    return out


def replace_packed_cells(
    model_json: dict,
    top_name: str,
    replacements: dict[str, PackedCell],
) -> dict:
    """Replace existing packed FRAC cell entries with rebuilt cells.

    Parameters
    ----------
    model_json : dict
        JSON dictionary containing already mapped FRAC cells.
    top_name : str
        Top module name to edit.
    replacements : dict[str, PackedCell]
        Rebuilt cells keyed by old packed instance name.

    Returns
    -------
    dict
        Deep-copied JSON dictionary with replacement cells applied.
    """
    out = copy.deepcopy(model_json)
    modules = out.get("modules", {})
    if top_name not in modules:
        return out

    cells = modules[top_name].setdefault("cells", {})
    for packed_id, mapped in replacements.items():
        conns: dict[str, list[int | str]] = {
            pin: [_to_json_bit(net)] for pin, net in mapped.external_pin_nets.items()
        }
        for pin, net in mapped.output_pin_nets.items():
            conns[pin] = [_to_json_bit(net)]

        cells[packed_id] = {
            "hide_name": 0,
            "type": mapped.architecture_name,
            "parameters": dict(mapped.parameters),
            "attributes": {},
            "port_directions": {
                **{pin: "input" for pin in mapped.external_pin_nets},
                **{pin: "output" for pin in mapped.output_pin_nets},
            },
            "connections": conns,
        }

    return out


def max_integer_bit(model_json: dict) -> int:
    """Return the maximum integer bit ID in a Yosys JSON dictionary.

    Parameters
    ----------
    model_json : dict
        Yosys JSON dictionary to scan.

    Returns
    -------
    int
        Maximum integer bit ID, or zero when no integer bits are present.
    """
    max_bit = 0
    for module in model_json.get("modules", {}).values():
        max_bit = max(max_bit, _max_bits_in_obj(module))
    return max_bit


def _build_bit_map(module: dict, fresh_bit_start: int) -> dict[int, int]:
    """Build old-to-new integer bit mapping for one module."""
    bits = sorted(_collect_integer_bits(module))
    return {bit: fresh_bit_start + idx for idx, bit in enumerate(bits)}


def _collect_integer_bits(obj: object) -> set[int]:
    """Collect integer bit IDs recursively from a JSON-like object."""
    if isinstance(obj, int):
        return {obj}
    if isinstance(obj, list):
        bits: set[int] = set()
        for value in obj:
            bits.update(_collect_integer_bits(value))
        return bits
    if isinstance(obj, dict):
        bits = set()
        for value in obj.values():
            bits.update(_collect_integer_bits(value))
        return bits
    return set()


def _max_bits_in_obj(obj: object) -> int:
    """Return the maximum integer bit inside a JSON-like object."""
    bits = _collect_integer_bits(obj)
    return max(bits) if bits else 0


def _remap_port(port: dict, bit_map: dict[int, int]) -> dict:
    """Return one port dictionary with remapped bits."""
    out = copy.deepcopy(port)
    out["bits"] = [_remap_bit(bit, bit_map) for bit in out.get("bits", [])]
    return out


def _remap_netname(netname: dict, bit_map: dict[int, int]) -> dict:
    """Return one netname dictionary with remapped bits."""
    out = copy.deepcopy(netname)
    out["bits"] = [_remap_bit(bit, bit_map) for bit in out.get("bits", [])]
    return out


def _remap_cell(cell: dict, bit_map: dict[int, int]) -> dict:
    """Return one cell dictionary with remapped connections."""
    out = copy.deepcopy(cell)
    conns = out.get("connections", {})
    out["connections"] = {
        pin: [_remap_bit(bit, bit_map) for bit in bits] for pin, bits in conns.items()
    }
    return out


def _remap_bit(bit: int | str, bit_map: dict[int, int]) -> int | str:
    """Return a remapped integer bit or unchanged constant string."""
    if isinstance(bit, int):
        return bit_map[bit]
    return bit


def _to_json_bit(net: str) -> str | int:
    """Convert a mapping net token to a Yosys JSON bit token."""
    if net in {"0", "1", "x", "z", "X", "Z"}:
        return net.lower()
    if net.isdigit():
        return int(net)
    return net
