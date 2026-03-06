"""
SDF Timing Graph Generation Module
This module provides functionality to parse SDF files and generate
timing directed graphs using NetworkX.
"""


from pathlib import Path
import networkx as nx
from sdf_timing import sdfparse
from fabulous.fabric_cad.timing_model.models import *


def _as_float(value: float | None, default: float = 0.0) -> float:
    """Convert `value` to float, treating None/missing as `default`."""
    if value is None:
        return default
    return float(value)

def delay_type(delay_paths: dict, kind: DelayType = DelayType.MAX_ALL) -> float:
    """
    Determine the delay value from a delay dictionary based on the specified type.
    In the SDF format, delays can be specified for different conditions (fast, slow, nominal).
    For example, a delay dictionary might look like this:

    delay_paths{
        "fast": {"min": 1.0, "avg": None, "max": 2.0},
        "slow": {"min": 3.0, "avg": None, "max": 4.0},
        "nominal": {"min": 2.0,  "avg": None, "max": 3.0}
    }

    which will be in the SDF as: ((1.0::2.0) (3.0::4.0)) for fast and slow, and (2.0::3.0) for nominal.

    Parameters
    ----------
    delay_paths : dict
        A dictionary containing delay information.
    kind : DelayType
        The type of delay to extract. Options include:
        DelayType.MIN_ALL, DelayType.MAX_ALL, DelayType.AVG_ALL, DelayType.AVG_FAST, DelayType.AVG_SLOW,
        DelayType.MAX_FAST, DelayType.MAX_SLOW, DelayType.MIN_FAST, DelayType.MIN_SLOW.

    Returns
    -------
    float
        The calculated delay value.
    
    Raises
    ------
    ValueError
        If an unknown delay type is specified.
    """
    nominal = delay_paths.get("nominal")
    if isinstance(nominal, dict) and ("min" in nominal or "max" in nominal):
        nmin = _as_float(nominal.get("min"))
        nmax = _as_float(nominal.get("max"))
        return max(nmin, nmax)

    fast = delay_paths.get("fast", {}) or {}
    slow = delay_paths.get("slow", {}) or {}

    fast_min: float = _as_float(fast.get("min"))
    fast_max: float = _as_float(fast.get("max"))
    slow_min: float = _as_float(slow.get("min"))
    slow_max: float = _as_float(slow.get("max"))

    match kind:
        case DelayType.MIN_ALL:
            return min(fast_min, fast_max, slow_min, slow_max)
        case DelayType.MAX_ALL:
            return max(fast_min, fast_max, slow_min, slow_max)
        case DelayType.AVG_ALL:
            return (fast_min + fast_max + slow_min + slow_max) / 4.0
        case DelayType.AVG_FAST:
            return (fast_min + fast_max) / 2.0
        case DelayType.AVG_SLOW:
            return (slow_min + slow_max) / 2.0
        case DelayType.MAX_FAST:
            return max(fast_min, fast_max)
        case DelayType.MAX_SLOW:
            return max(slow_min, slow_max)
        case DelayType.MIN_FAST:
            return min(fast_min, fast_max)
        case DelayType.MIN_SLOW:
            return min(slow_min, slow_max)
        case _:
            raise ValueError(f"Unknown delay type: {kind!r}")

def split_instance_pin(name: str, hier_sep: str) -> tuple[str, str]:
    """
    Split a hierarchical name into instance and pin parts based on the separator.
    For example, given the name "_2988_/Q" and separator "/", it returns ("_2988_", "Q").

    Parameters
    ----------
    name : str
        The hierarchical name to split.
    hier_sep : str
        The separator used in the hierarchical name.

    Returns
    -------
    tuple[str, str]
        A tuple containing the instance and pin names.
    """
    parts = name.rsplit(hier_sep, 1)
    if len(parts) == 2:
        inst, pin = parts
    else:
        inst, pin = "", name
    return inst, pin

def parse_sdf(sdf_file: Path, delay_type_str: DelayType) -> SDFGobject:
    """
    Parse the SDF file to extract INTERCONNECT and IOPATH components with their delays.
    Also extracts header information, cell names, and instance-component mappings.
    But IOPATHs and INTERCONNECTS are used to build the timing graph.
    Timing checks (hold, setup, reset, recover, width) and other components are stored 
    in the instances dictionary.

    Parameters
    ----------
    sdf_file : Path
        Path to the SDF file.
    delay_type_str : DelayType
        The type of delay to extract (e.g., DelayType.MAX_ALL).

    Returns
    -------
    SDFGobject
        An SDFGobject containing the parsed SDF data, including header information, 
        cell names, instance-component mappings, and lists of IOPATH and INTERCONNECT components.
    """
    sdf_data: dict = sdfparse.parse(sdf_file.read_text())
    header_info: dict = sdf_data.get("header", {})
    io_paths: list[Component] = []
    interconnects: list[Component] = []
    cells: list[str] = list(sdf_data.get("cells", {}).keys())
    instances: dict[str, list[Component]] = {}
    hier_sep: str = header_info["divider"] if "divider" in header_info else "/"

    for cell_name, cell_data in sdf_data["cells"].items():
        for instance_name, instance_data in cell_data.items():
            if instance_name is not None:
                instances[instance_name] = []
            for component, component_data in instance_data.items():
                inst_pin_from: tuple[str, str] = split_instance_pin(
                    component_data["from_pin"], hier_sep
                )
                inst_pin_to: tuple[str, str] = split_instance_pin(
                    component_data["to_pin"], hier_sep
                )
                single_delay: float = delay_type(
                    component_data["delay_paths"], delay_type_str
                )
                one_inst: bool = inst_pin_from[0] == inst_pin_to[0]
                
                if component_data["type"] == "iopath":
                    io_paths.append(
                        Component(
                            c_type=SDFCellType.IOPATH,
                            cell_name=cell_name,
                            connection_string=component,
                            from_cell_instance=instance_name,
                            to_cell_instance=instance_name,
                            from_cell_pin=component_data["from_pin"],
                            to_cell_pin=component_data["to_pin"],
                            delay=single_delay,
                            delay_paths=component_data["delay_paths"],
                            is_one_cell_instance=True,
                            is_timing_check=component_data["is_timing_check"],
                            is_timing_env=component_data["is_timing_env"],
                            is_absolute=component_data["is_absolute"],
                            is_incremental=component_data["is_incremental"],
                            is_cond=component_data["is_cond"],
                            cond_equation=component_data["cond_equation"],
                            from_pin_edge=component_data["from_pin_edge"],
                            to_pin_edge=component_data["to_pin_edge"],
                        )
                    )
                if component_data["type"] == "interconnect":
                    interconnects.append(
                        Component(
                            c_type=SDFCellType.INTERCONNECT,
                            cell_name=cell_name,
                            connection_string=component,
                            from_cell_instance=inst_pin_from[0],
                            to_cell_instance=inst_pin_to[0],
                            from_cell_pin=inst_pin_from[1],
                            to_cell_pin=inst_pin_to[1],
                            delay=single_delay,
                            delay_paths=component_data["delay_paths"],
                            is_one_cell_instance=one_inst,
                            is_timing_check=component_data["is_timing_check"],
                            is_timing_env=component_data["is_timing_env"],
                            is_absolute=component_data["is_absolute"],
                            is_incremental=component_data["is_incremental"],
                            is_cond=component_data["is_cond"],
                            cond_equation=component_data["cond_equation"],
                            from_pin_edge=component_data["from_pin_edge"],
                            to_pin_edge=component_data["to_pin_edge"],
                        )
                    )
                if component_data["type"] != "interconnect":
                    instances[instance_name].append(
                        Component(
                            c_type=SDFCellType(component_data["type"].upper()),
                            cell_name=cell_name,
                            connection_string=component,
                            from_cell_instance=instance_name,
                            to_cell_instance=instance_name,
                            from_cell_pin=component_data["from_pin"],
                            to_cell_pin=component_data["to_pin"],
                            delay=single_delay,
                            delay_paths=component_data["delay_paths"],
                            is_one_cell_instance=True,
                            is_timing_check=component_data["is_timing_check"],
                            is_timing_env=component_data["is_timing_env"],
                            is_absolute=component_data["is_absolute"],
                            is_incremental=component_data["is_incremental"],
                            is_cond=component_data["is_cond"],
                            cond_equation=component_data["cond_equation"],
                            from_pin_edge=component_data["from_pin_edge"],
                            to_pin_edge=component_data["to_pin_edge"],
                        )
                    )
                    
    # io_paths, interconnects, header_info, sdf_data, cells, instances
    return SDFGobject(
        nx_graph=nx.DiGraph(),
        hier_sep=hier_sep,
        header_info=header_info,
        sdf_data=sdf_data,
        cells=cells,
        instances=instances,
        io_paths=io_paths,
        interconnects=interconnects,
    )

def gen_timing_digraph(sdf_file: Path, delay_type_str: DelayType) -> SDFGobject:
    """
    Generate a timing directed networkx graph (DiGraph) from the SDF file.
    Also extracts header information, cell names, and instance-component mappings.
    But IOPATHs and INTERCONNECTS are used to build the timing graph.
    Timing checks (hold, setup, reset, recover, width) and other components are 
    stored in the instances dictionary.

    Parameters
    ----------
    sdf_file : Path
        Path to the SDF file.
    delay_type_str : DelayType
        The type of delay to extract (e.g., DelayType.MAX_ALL).

    Returns
    -------
    SDFGobject
        An SDFGobject containing the generated timing graph, header information, 
        cell names, instance-component mappings, and lists of IOPATH and INTERCONNECT components.
    """
    sdf_gobject: SDFGobject = parse_sdf(sdf_file, delay_type_str)
    
    def node(inst: str, pin: str) -> str:
        """
        Helper function to create a node name from instance and pin, 
        using the hierarchical separator.
        """
        return f"{inst}{sdf_gobject.hier_sep}{pin}".removeprefix(sdf_gobject.hier_sep)

    # Includes both IOPATHs and INTERCONNECTS, but not timing checks or other components.
    components: list[Component] = sdf_gobject.io_paths + sdf_gobject.interconnects
    for comp in components:
        sdf_gobject.nx_graph.add_edge(
            node(comp.from_cell_instance, comp.from_cell_pin),
            node(comp.to_cell_instance, comp.to_cell_pin),
            weight=comp.delay,
            component=comp,
        )    
    return sdf_gobject
