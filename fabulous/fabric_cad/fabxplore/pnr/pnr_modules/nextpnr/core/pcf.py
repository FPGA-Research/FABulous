"""PCF generation helpers for FABulous nextpnr routing.

FABulous exposes legal IO sites through the routing model's template PCF text.
This module keeps PCF handling in memory: the router receives ``template_pcf``
and ``bel_v2`` from ``fab.genRoutingModel()``, extracts real IO sites, flattens
top-level pyosys ports, and emits the concrete ``set_io`` constraints consumed
by the FABulous nextpnr fork.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


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
        Template PCF returned by ``fab.genRoutingModel()``.

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
        BEL v2 text returned by ``fab.genRoutingModel()``.
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


def extract_design_ports(design: PyosysBridge, top_name: str) -> list[str]:
    """Return flattened top-level port names in Yosys JSON order.

    Parameters
    ----------
    design : PyosysBridge
        Active pyosys design.
    top_name : str
        Top module name to inspect.

    Returns
    -------
    list[str]
        Flattened port names, using ``name[index]`` for vector ports.

    Raises
    ------
    ValueError
        If the top module is not present in the design JSON.
    """
    netlist = design.to_netlist_dict()
    modules = netlist.get("modules", {})
    if top_name not in modules:
        raise ValueError(f"top module {top_name!r} not found in design")

    ports: list[str] = []
    for port_name, port in modules[top_name].get("ports", {}).items():
        bits = port.get("bits", [])
        if len(bits) <= 1:
            ports.append(port_name)
        else:
            ports.extend(f"{port_name}[{index}]" for index in range(len(bits)))
    return ports


def auto_assign_pcf(
    design: PyosysBridge,
    top_name: str,
    template_pcf: str,
    bel_v2: str | None = None,
) -> str:
    """Generate concrete PCF text by assigning ports to template IO sites.

    Parameters
    ----------
    design : PyosysBridge
        Active pyosys design.
    top_name : str
        Top module name to constrain.
    template_pcf : str
        Template PCF returned by ``fab.genRoutingModel()``.
    bel_v2 : str | None
        Optional BEL v2 text returned by ``fab.genRoutingModel()``. When
        provided, template sites are filtered to real IO BELs so pass-through
        interface BELs are not used as top-level IO pins.

    Returns
    -------
    str
        Concrete PCF text with one ``set_io`` line per flattened design port.

    Raises
    ------
    ValueError
        If the design has more top-level ports than available IO sites.
    """
    ports = extract_design_ports(design, top_name)
    sites = extract_template_io_sites(template_pcf)
    if bel_v2 is not None:
        sites = filter_io_sites_by_bel_v2(sites, bel_v2)
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
