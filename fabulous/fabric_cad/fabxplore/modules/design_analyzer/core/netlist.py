"""Parse Yosys JSON into design-analyzer internal netlist models.

The parser maps raw Yosys JSON to typed classes so downstream analysis logic can operate
solely on stable internal structures rather than ad-hoc JSON dictionaries.
"""

from collections import Counter

from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.models import (
    LogicalCell,
    ModulePort,
    TopModuleNetlist,
)

_CONSTANT_BITS = {"0", "1", "x", "z"}


def parse_top_module_json(
    model_json: dict,
    top_name: str | None = None,
) -> TopModuleNetlist:
    """Parse Yosys JSON and return a typed top-module netlist model.

    Parameters
    ----------
    model_json : dict
        Full Yosys JSON dictionary emitted by ``write_json``.
    top_name : str | None
        Optional explicit top-module name. If ``None``, the parser picks the
        module with the largest cell count.

    Returns
    -------
    TopModuleNetlist
        Parsed and normalized netlist model of the selected top module.

    Raises
    ------
    RuntimeError
        If the JSON does not contain a valid ``modules`` section or the
        requested module cannot be found.
    """
    modules: dict = model_json.get("modules", {})
    if not modules:
        raise RuntimeError("No modules found in provided Yosys JSON dictionary.")

    selected_top: str = _select_top_module(modules, top_name)
    module_raw: dict = modules[selected_top]

    ports: tuple[ModulePort, ...] = _parse_ports(module_raw.get("ports", {}))
    cells: tuple[LogicalCell, ...] = _parse_cells(module_raw.get("cells", {}))
    bit_to_netname: dict[str, str] = _parse_bit_to_netname(
        module_raw.get("netnames", {})
    )

    creator: str = str(model_json.get("creator", "unknown"))
    return TopModuleNetlist(
        creator=creator,
        top_name=selected_top,
        ports=ports,
        cells=cells,
        bit_to_netname=bit_to_netname,
    )


def _select_top_module(modules: dict, top_name: str | None) -> str:
    """Choose the module to analyze from a Yosys ``modules`` dictionary.

    Parameters
    ----------
    modules : dict
        Mapping of module name to module dictionary.
    top_name : str | None
        Optional explicit requested top-module name.

    Returns
    -------
    str
        Selected top-module name.

    Raises
    ------
    RuntimeError
        If an explicit top-module is requested but not present.
    """
    if top_name is not None:
        if top_name not in modules:
            available: str = ", ".join(sorted(modules))
            raise RuntimeError(
                f"Requested top module '{top_name}' not found. Available: {available}"
            )
        return top_name

    if len(modules) == 1:
        return next(iter(modules))

    ranked: list[tuple[int, int, str]] = []
    for name, module_raw in modules.items():
        cells_raw: dict = module_raw.get("cells", {})
        ports_raw: dict = module_raw.get("ports", {})
        ranked.append((len(cells_raw), len(ports_raw), name))

    ranked.sort(reverse=True)
    return ranked[0][2]


def _parse_ports(ports_raw: dict) -> tuple[ModulePort, ...]:
    """Parse module ports from Yosys JSON format.

    Parameters
    ----------
    ports_raw : dict
        ``ports`` mapping from a Yosys module dictionary.

    Returns
    -------
    tuple[ModulePort, ...]
        Parsed and normalized module ports.
    """
    out: list[ModulePort] = []

    for name, raw in ports_raw.items():
        direction: str = str(raw.get("direction", "input")).lower()
        bits: tuple[str, ...] = tuple(
            _normalize_bit(bit) for bit in raw.get("bits", [])
        )

        out.append(ModulePort(name=name, direction=direction, bits=bits))

    return tuple(out)


def _parse_cells(cells_raw: dict) -> tuple[LogicalCell, ...]:
    """Parse cell instances for one module.

    Parameters
    ----------
    cells_raw : dict
        ``cells`` mapping from a Yosys module dictionary.

    Returns
    -------
    tuple[LogicalCell, ...]
        Parsed and normalized cells.
    """
    out: list[LogicalCell] = []

    for cell_id, raw in cells_raw.items():
        cell_type: str = str(raw.get("type", "")).lstrip("\\")

        params: dict[str, str] = {
            str(k): _stringify_json_value(v)
            for k, v in raw.get("parameters", {}).items()
        }
        attrs: dict[str, str] = {
            str(k): _stringify_json_value(v)
            for k, v in raw.get("attributes", {}).items()
        }

        conn_dict: dict[str, tuple[str, ...]] = {}
        for port_name, bits_raw in raw.get("connections", {}).items():
            conn_dict[str(port_name)] = tuple(_normalize_bit(bit) for bit in bits_raw)

        given_dirs: dict[str, str] = {
            str(k): str(v).lower() for k, v in raw.get("port_directions", {}).items()
        }

        inferred_dirs: dict[str, str] = {}
        input_bits: list[str] = []
        output_bits: list[str] = []
        inout_bits: list[str] = []

        for port_name, bits in conn_dict.items():
            pdir: str = given_dirs.get(
                port_name,
                _infer_port_direction(port_name, cell_type),
            )
            inferred_dirs[port_name] = pdir

            if pdir == "output":
                output_bits.extend(bits)
            elif pdir == "inout":
                inout_bits.extend(bits)
            else:
                input_bits.extend(bits)

        out.append(
            LogicalCell(
                cell_id=str(cell_id),
                cell_type=cell_type,
                parameters=params,
                attributes=attrs,
                connections=conn_dict,
                port_directions=inferred_dirs,
                input_bits=tuple(input_bits),
                output_bits=tuple(output_bits),
                inout_bits=tuple(inout_bits),
            )
        )

    return tuple(out)


def _parse_bit_to_netname(netnames_raw: dict) -> dict[str, str]:
    """Build best-effort mapping from bit identifiers to net names.

    Parameters
    ----------
    netnames_raw : dict
        ``netnames`` mapping from a Yosys module dictionary.

    Returns
    -------
    dict[str, str]
        Mapping from normalized bit identifiers to one readable net name.
    """
    out: dict[str, str] = {}

    for net_name, raw in netnames_raw.items():
        bits = raw.get("bits", [])
        for bit in bits:
            bit_key: str = _normalize_bit(bit)
            if _is_constant_bit(bit_key):
                continue
            out.setdefault(bit_key, str(net_name))

    return out


def count_unique_signal_bits(netlist: TopModuleNetlist) -> int:
    """Count unique non-constant signal bits touched by ports and cells.

    Parameters
    ----------
    netlist : TopModuleNetlist
        Parsed netlist model.

    Returns
    -------
    int
        Number of unique non-constant bit identifiers.
    """
    seen: set[str] = set()

    for port in netlist.ports:
        for bit in port.bits:
            if not _is_constant_bit(bit):
                seen.add(bit)

    for cell in netlist.cells:
        for bit in cell.input_bits + cell.output_bits + cell.inout_bits:
            if not _is_constant_bit(bit):
                seen.add(bit)

    return len(seen)


def coarse_fine_custom_breakdown(cells: tuple[LogicalCell, ...]) -> Counter:
    """Return coarse/fine/custom bucket counts for a cell list.

    Parameters
    ----------
    cells : tuple[LogicalCell, ...]
        Cells of the selected top module.

    Returns
    -------
    Counter
        Counter with keys ``coarse``, ``fine``, and ``custom``.
    """
    out: Counter = Counter()

    for cell in cells:
        ctype: str = cell.cell_type
        if ctype.startswith("$_") and ctype.endswith("_"):
            out["fine"] += 1
        elif ctype.startswith("$"):
            out["coarse"] += 1
        else:
            out["custom"] += 1

    return out


def _normalize_bit(bit: int | str) -> str:
    """Normalize one Yosys bit token to a stable string form.

    Parameters
    ----------
    bit : int | str
        Raw bit token from Yosys JSON.

    Returns
    -------
    str
        Normalized bit token.
    """
    if isinstance(bit, int):
        return str(bit)

    text: str = str(bit).strip()
    return text.removeprefix("\\")


def _stringify_json_value(value: object) -> str:
    """Convert an arbitrary JSON field value into a deterministic string.

    Parameters
    ----------
    value : object
        Raw JSON value.

    Returns
    -------
    str
        Stringified value.
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _is_constant_bit(bit: str) -> bool:
    """Check whether a normalized bit token encodes a constant.

    Parameters
    ----------
    bit : str
        Normalized bit token.

    Returns
    -------
    bool
        ``True`` if the token is a constant, else ``False``.
    """
    return bit.lower() in _CONSTANT_BITS


def _infer_port_direction(port_name: str, cell_type: str) -> str:
    """Infer missing cell port direction from common naming conventions.

    Parameters
    ----------
    port_name : str
        Port name from the cell connection dictionary.
    cell_type : str
        Cell type name.

    Returns
    -------
    str
        One of ``input``, ``output``, or ``inout``.
    """
    pname: str = port_name.upper()
    ctype: str = cell_type.upper()

    inout_candidates: set[str] = {"IO", "PAD", "PIN", "INOUT"}
    if pname in inout_candidates or pname.startswith("IO"):
        return "inout"

    output_exact: set[str] = {
        "Y",
        "Q",
        "QN",
        "QB",
        "O",
        "OB",
        "Z",
        "CO",
        "COUT",
        "SUM",
        "F",
        "X",
    }

    if pname in output_exact:
        return "output"

    output_prefixes: tuple[str, ...] = ("Y", "Q", "O", "CO", "COUT")
    if any(pname.startswith(prefix) for prefix in output_prefixes):
        return "output"

    if ctype.startswith(("$_DFF", "$_SDFF")) and pname.startswith("Q"):
        return "output"

    return "input"
