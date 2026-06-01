"""PCF generation helpers for FABulous nextpnr routing.

FABulous exposes legal IO sites through the routing model's template PCF text.
This module keeps PCF handling in memory: the router receives ``template_pcf``
and ``bel_v2`` from the current routing metadata, extracts real IO sites,
flattens top-level Yosys JSON ports, and emits the concrete ``set_io``
constraints consumed by the FABulous nextpnr fork.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TILE_PIN_RE = re.compile(r"^Tile_X(?P<x>\d+)Y(?P<y>\d+)[./](?P<bel>[A-Za-z]+)$")
_FAB_PIN_RE = re.compile(r"^X(?P<x>\d+)Y(?P<y>\d+)[./](?P<bel>[A-Za-z]+)$")
DEFAULT_IO_BEL_TYPES = frozenset({"IO_1_bidirectional_frame_config_pass"})


@dataclass(frozen=True)
class PcfIoSite:
    """One legal FABulous IO site from a template PCF.

    Attributes
    ----------
    template_cell : str
        Placeholder cell name emitted by FABulous in the template PCF.
    template_pin : str
        Pin name emitted by FABulous in the template PCF.
    nextpnr_bel : str
        BEL name normalized for the nextpnr FABulous uarch.
    """

    template_cell: str
    template_pin: str
    nextpnr_bel: str


def extract_template_io_sites(template_pcf: str) -> list[PcfIoSite]:
    """Extract legal IO sites from FABulous template PCF text.

    Parameters
    ----------
    template_pcf : str
        Template PCF text from the current FABulous routing metadata.

    Returns
    -------
    list[PcfIoSite]
        Legal IO sites in template order.

    Raises
    ------
    ValueError
        If no IO sites can be found.
    """
    sites: list[PcfIoSite] = []
    for raw_line in template_pcf.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3 or parts[0] != "set_io":
            continue
        sites.append(
            PcfIoSite(
                template_cell=parts[1],
                template_pin=parts[2],
                nextpnr_bel=normalize_template_pin(parts[2]),
            )
        )

    if not sites:
        raise ValueError("template_pcf does not contain any set_io entries")
    return sites


def filter_io_sites_by_bel_v2(
    sites: list[PcfIoSite],
    bel_v2: str,
    io_bel_types: frozenset[str] = DEFAULT_IO_BEL_TYPES,
) -> list[PcfIoSite]:
    """Filter template sites to actual IO BELs from BEL v2 metadata.

    Parameters
    ----------
    sites : list[PcfIoSite]
        Candidate template sites.
    bel_v2 : str
        BEL v2 text from the current FABulous routing metadata.
    io_bel_types : frozenset[str]
        BEL types accepted as user IO pads.

    Returns
    -------
    list[PcfIoSite]
        Sites whose normalized nextpnr BEL names exist in ``bel_v2`` with an
        accepted IO BEL type.

    Raises
    ------
    ValueError
        If no usable IO BELs remain after filtering.
    """
    io_bels = _extract_io_bels_from_bel_v2(bel_v2, io_bel_types)
    filtered = [site for site in sites if site.nextpnr_bel in io_bels]
    if not filtered:
        raise ValueError("BEL v2 metadata does not contain any usable IO BELs")
    return filtered


def extract_json_ports(json_path: Path | str, top_name: str) -> list[str]:
    """Return flattened top-level port names from a Yosys JSON netlist.

    Parameters
    ----------
    json_path : Path | str
        Existing Yosys JSON netlist path.
    top_name : str
        Top module name to inspect.

    Returns
    -------
    list[str]
        Flattened port names, using ``name[index]`` for vector ports.

    Raises
    ------
    ValueError
        If the top module is not present in the JSON netlist.
    """
    netlist = _read_json_netlist(json_path)
    modules = netlist.get("modules", {})
    if top_name not in modules:
        raise ValueError(f"top module {top_name!r} not found in JSON netlist")
    return _flatten_module_ports(modules[top_name])


def auto_assign_pcf_for_ports(
    ports: list[str],
    template_pcf: str,
    bel_v2: str | None = None,
    pcf_assignment_seed: int = 1,
) -> str:
    """Generate concrete PCF text by assigning named ports to IO sites.

    Parameters
    ----------
    ports : list[str]
        Flattened top-level port names in assignment order.
    template_pcf : str
        Template PCF text from the current FABulous routing metadata.
    bel_v2 : str | None
        Optional BEL v2 text from the current FABulous routing metadata. When
        provided, template sites are filtered to real IO BELs so pass-through
        interface BELs are not used as top-level IO pins.
    pcf_assignment_seed : int
        Positive deterministic assignment seed. Seed ``1`` preserves template
        order. Any other seed permutes legal IO sites before assigning ports.

    Returns
    -------
    str
        Concrete PCF text with one ``set_io`` line per port.

    Raises
    ------
    ValueError
        If there are more ports than available IO sites, or if
        ``pcf_assignment_seed`` is not positive.
    """
    if pcf_assignment_seed <= 0:
        raise ValueError("pcf_assignment_seed must be greater than 0")
    sites = extract_template_io_sites(template_pcf)
    if bel_v2 is not None:
        sites = filter_io_sites_by_bel_v2(sites, bel_v2)
    if pcf_assignment_seed != 1:
        random.Random(pcf_assignment_seed).shuffle(sites)
    if len(ports) > len(sites):
        raise ValueError(
            f"design has {len(ports)} top-level port(s), but template PCF "
            f"contains only {len(sites)} legal IO site(s)"
        )
    return "\n".join(
        f"set_io {port} {site.nextpnr_bel}"
        for port, site in zip(ports, sites, strict=False)
    ) + ("\n" if ports else "")


def normalize_template_pin(pin: str) -> str:
    """Normalize a FABulous template pin to a nextpnr BEL name.

    Parameters
    ----------
    pin : str
        Template pin, such as ``Tile_X0Y1.A`` or ``X0Y1/A``.

    Returns
    -------
    str
        Normalized BEL name, such as ``X0Y1/A``.

    Raises
    ------
    ValueError
        If the pin format is not recognized.
    """
    tile_match = _TILE_PIN_RE.match(pin)
    if tile_match:
        return _format_bel(
            tile_match.group("x"),
            tile_match.group("y"),
            tile_match.group("bel"),
        )

    fab_match = _FAB_PIN_RE.match(pin)
    if fab_match:
        return _format_bel(
            fab_match.group("x"),
            fab_match.group("y"),
            fab_match.group("bel"),
        )

    raise ValueError(f"unsupported FABulous IO pin format: {pin!r}")


def _format_bel(x: str, y: str, bel: str) -> str:
    """Format one coordinate and BEL letter as a nextpnr BEL name.

    Parameters
    ----------
    x : str
        X coordinate.
    y : str
        Y coordinate.
    bel : str
        BEL letter.

    Returns
    -------
    str
        nextpnr BEL name.
    """
    return f"X{x}Y{y}/{bel}"


def _read_json_netlist(json_path: Path | str) -> dict[str, Any]:
    """Read one Yosys JSON netlist.

    Parameters
    ----------
    json_path : Path | str
        JSON netlist path.

    Returns
    -------
    dict[str, Any]
        Parsed JSON object.
    """
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def _flatten_module_ports(module: dict[str, Any]) -> list[str]:
    """Flatten scalar and vector module ports in Yosys JSON order.

    Parameters
    ----------
    module : dict[str, Any]
        Yosys JSON module object.

    Returns
    -------
    list[str]
        Flattened port names.
    """
    ports: list[str] = []
    for port_name, port in module.get("ports", {}).items():
        bits = port.get("bits", [])
        if len(bits) <= 1:
            ports.append(port_name)
        else:
            ports.extend(f"{port_name}[{index}]" for index in range(len(bits)))
    return ports


def _extract_io_bels_from_bel_v2(
    bel_v2: str,
    io_bel_types: frozenset[str],
) -> set[str]:
    """Extract IO BEL names from BEL v2 metadata.

    Parameters
    ----------
    bel_v2 : str
        BEL v2 metadata text.
    io_bel_types : frozenset[str]
        BEL types accepted as user IO pads.

    Returns
    -------
    set[str]
        Normalized nextpnr BEL names for accepted IO BELs.
    """
    io_bels: set[str] = set()
    for raw_line in bel_v2.splitlines():
        line = raw_line.strip()
        if not line.startswith("BelBegin,"):
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        _, tile, bel, bel_type, *_ = parts
        if bel_type in io_bel_types:
            io_bels.add(f"{tile}/{bel}")
    return io_bels
