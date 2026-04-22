"""Parse Yosys Python objects into design-analyzer internal netlist models.

The parser maps ``YosysJson`` objects to typed classes so downstream analysis logic can
operate solely on stable internal structures.
"""

from collections import Counter

from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.models import (
    LogicalCell,
    ModulePort,
    TopModuleNetlist,
)
from fabulous.fabric_definition.yosys_obj import (
    YosysCellDetails,
    YosysJson,
    YosysModule,
    YosysPortDetails,
)


def parse_top_module_json(
    yosys_obj: YosysJson,
    top_name: str | None = None,
) -> TopModuleNetlist:
    """Parse a Yosys object and return a typed top-module netlist model.

    Parameters
    ----------
    yosys_obj : YosysJson
        Full Yosys object emitted by ``PyosysBridge.to_py_object``.
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
        If the object does not contain modules or the
        requested module cannot be found.
    """
    modules: dict[str, YosysModule] = yosys_obj.modules
    if not modules:
        raise RuntimeError("No modules found in provided Yosys object.")

    selected_top: str = _select_top_module(modules, top_name)
    module_data: YosysModule = modules[selected_top]

    ports: tuple[ModulePort, ...] = _parse_ports(module_data.ports)
    cells: tuple[LogicalCell, ...] = _parse_cells(module_data.cells)

    creator: str = str(yosys_obj.creator or "unknown")
    return TopModuleNetlist(
        creator=creator,
        top_name=_normalize_name(selected_top),
        ports=ports,
        cells=cells,
    )


def _select_top_module(modules: dict[str, YosysModule], top_name: str | None) -> str:
    """Choose the module to analyze from a Yosys module mapping.

    Parameters
    ----------
    modules : dict[str, YosysModule]
        Mapping of module names to module objects.
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
    normalized_to_raw: dict[str, str] = {
        _normalize_name(name): name for name in modules
    }

    if top_name is not None:
        req_name = _normalize_name(top_name)
        selected = normalized_to_raw.get(req_name)
        if selected is None:
            available: str = ", ".join(sorted(normalized_to_raw))
            raise RuntimeError(
                f"Requested top module '{top_name}' not found. Available: {available}"
            )
        return selected

    if len(modules) == 1:
        return next(iter(modules))

    ranked: list[tuple[int, int, str]] = []
    for name, module_data in modules.items():
        ranked.append((len(module_data.cells), len(module_data.ports), name))

    ranked.sort(reverse=True)
    return ranked[0][2]


def _parse_ports(ports_data: dict[str, YosysPortDetails]) -> tuple[ModulePort, ...]:
    """Parse module ports from Yosys object format.

    Parameters
    ----------
    ports_data : dict[str, YosysPortDetails]
        ``ports`` mapping from a Yosys module object.

    Returns
    -------
    tuple[ModulePort, ...]
        Parsed and normalized module ports.
    """
    out: list[ModulePort] = []

    for name, port in ports_data.items():
        direction: str = str(port.direction).lower()
        bits: tuple[str, ...] = tuple(_normalize_bit(bit) for bit in port.bits)

        out.append(
            ModulePort(
                name=_normalize_name(name),
                direction=direction,
                bits=bits,
            )
        )

    return tuple(out)


def _parse_cells(cells_data: dict[str, YosysCellDetails]) -> tuple[LogicalCell, ...]:
    """Parse cell instances for one module.

    Parameters
    ----------
    cells_data : dict[str, YosysCellDetails]
        ``cells`` mapping from a Yosys module object.

    Returns
    -------
    tuple[LogicalCell, ...]
        Parsed and normalized cells.
    """
    out: list[LogicalCell] = []

    for cell_id, cell in cells_data.items():
        cell_type: str = _normalize_name(cell.type)

        params: dict[str, str] = {
            str(k): _stringify_json_value(v) for k, v in cell.parameters.items()
        }
        attrs: dict[str, str] = {
            str(k): _stringify_json_value(v) for k, v in cell.attributes.items()
        }

        conn_dict: dict[str, tuple[str, ...]] = {}
        for port_name, bits_raw in cell.connections.items():
            conn_dict[str(port_name)] = tuple(_normalize_bit(bit) for bit in bits_raw)

        given_dirs: dict[str, str] = {
            str(k): str(v).lower() for k, v in cell.port_directions.items()
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
                cell_id=_normalize_name(cell_id),
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


def _normalize_name(name: object) -> str:
    """Normalize Yosys names by stripping optional leading backslashes."""
    return str(name).strip().removeprefix("\\")


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
    return bit.lower() in {"0", "1", "x", "z"}


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
