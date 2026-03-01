"""
Defines the Component class representing a component in the SDF timing model,
which can be an INTERCONNECT or an IOPATH for the timing graph, as well as other
types like REMOVAL, RECOVERY, SETUP, HOLD, WIDTH. The class includes attributes for
the component type, connection string, cell name, instance names, pin names,
delay information, and various flags indicating the nature of the component.
"""


from dataclasses import dataclass, field
from enum import StrEnum
import networkx as nx

class TimingModelMode(StrEnum):
    """
    Enumeration of timing model modes for the SDF timing model.
    
    Attributes
    ----------
    STRUCTURAL : str
        Represents a structural timing model, which focuses on the interconnections and structure of the design.
        This mode is based on the non routed netlist and can be used if no physical post-layout netlist is available.
    PHYSICAL : str
        Represents a physical timing model, which includes detailed information about the physical layout 
        and routing of the design. This mode is based on the routed netlist and can be used if a physical 
        post-layout netlist is available, providing more accurate timing information that accounts 
        for the actual physical implementation of the design.
    """
    STRUCTURAL = "structural"
    PHYSICAL = "physical"


class SDFCellType(StrEnum):
    """
    Enumeration of cell types for the SDF timing model, including INTERCONNECT and IOPATH for the timing graph,
    as well as other types like REMOVAL, RECOVERY, SETUP, HOLD, WIDTH.
    
    Attributes
    ----------
    IOPATH : str
        Represents an IOPATH component, which defines timing paths between pins within the same cell.
    INTERCONNECT : str
        Represents an INTERCONNECT component, which defines timing paths between pins across 
        different cells (i.e., inter-cell connections).
    REMOVAL : str
        Represents a REMOVAL component, which defines timing checks for signal removal.
    RECOVERY : str
        Represents a RECOVERY component, which defines timing checks for signal recovery.
    SETUP : str
        Represents a SETUP component, which defines timing checks for setup time.
    HOLD : str
        Represents a HOLD component, which defines timing checks for hold time.
    WIDTH : str
        Represents a WIDTH component, which defines timing checks for pulse width.
    """
    IOPATH = "IOPATH"
    INTERCONNECT = "INTERCONNECT"
    REMOVAL = "REMOVAL"
    RECOVERY = "RECOVERY"
    SETUP = "SETUP"
    HOLD = "HOLD"
    WIDTH = "WIDTH"

@dataclass(frozen=True)
class Component:
    """
    Represents a component in the SDF timing model, either an INTERCONNECT or an IOPATH for the timing graph.
    But it can also be: REMOVAL, RECOVERY, SETUP, HOLD, WIDTH.

    Attributes
    ----------
    c_type : SDFCellType
        Type of the component, either "INTERCONNECT" or "IOPATH" for the timing graph.
        Other types include: "REMOVAL", "RECOVERY", "SETUP", "HOLD", "WIDTH".
    connection_string : str
        Unique identifier for the component.
    cell_name : str
        Name of the cell e.g., 'AND2X1'.
    from_cell_instance : str
        Instance name of the source cell.
    to_cell_instance : str
        Instance name of the destination cell.
    from_cell_pin : str
        Pin name on the source cell.
    to_cell_pin : str
        Pin name on the destination cell.
    delay : float
        Delay associated with this component: INTERCONNECT delay: cell to cell delay,
        IOPATH delay: pin to pin delay within a cell. Is a single delay over fast, slow (min, max)
        by using a cost function to combine them.
    delay_paths : dict
        Dictionary containing detailed delay paths information.
    is_one_cell_instance : bool
        True if from_cell_instance and to_cell_instance are the same.
    is_timing_check : bool
        True if the component represents a timing check.
    is_timing_env : bool
        True if the component represents a timing environment.
    is_absolute : bool
        True if the delay is absolute.
    is_incremental : bool
        True if the delay is incremental.
    is_cond : bool
        True if the delay is conditional.
    cond_equation : str
        Condition equation if is_cond is True.
    from_pin_edge : str
        Edge type for the from pin, e.g., "posedge" or "negedge".
    to_pin_edge : str
        Edge type for the to pin, e.g., "posedge" or "negedge".
    """
    c_type: SDFCellType
    connection_string: str
    cell_name: str
    from_cell_instance: str
    to_cell_instance: str
    from_cell_pin: str
    to_cell_pin: str
    delay: float
    delay_paths: dict
    is_one_cell_instance: bool
    is_timing_check: bool
    is_timing_env: bool
    is_absolute: bool
    is_incremental: bool
    is_cond: bool
    cond_equation: str
    from_pin_edge: str
    to_pin_edge: str

@dataclass(slots=True, kw_only=True)
class SDFGobject:
    """
    Represents the SDF timing graph object, containing the directed graph representation 
    of the timing model, as well as associated metadata such as header information,
    SDF data dictionary parsed from the file, cell names, instances, IOPATHs, and interconnects.
    
    Attributes
    ----------
    nx_graph : nx.DiGraph
        The directed graph representation of the timing model, where nodes represent pins 
        and edges represent timing paths with associated delay information.
    hier_sep : str
        The hierarchical separator used in instance names, extracted from the SDF 
        header information.
    header_info : dict
        Dictionary containing header information from the SDF file, such as version, date, 
        vendor, program, and hierarchical separator.
    sdf_data : dict
        The full SDF data parsed from the file, including cells, instances, IOPATHs, 
        interconnects, and timing checks.
    cells : list[str]
        List of cell names defined in the SDF file.
    instances : dict[str, list[Component]]
        Dictionary mapping instance names of cells to lists of Component instances representing the 
        timing paths (IOPATHs and INTERCONNECTs) associated with each instance.
    io_paths : list[Component]
        List of Component instances representing the IOPATHs defined in the SDF file, 
        which represent timing paths between pins within the same cell.
    interconnects : list[Component]
        List of Component instances representing the INTERCONNECTs defined in the SDF 
        file, which represent timing paths between pins across different cells (i.e., inter-cell connections).
    """
    nx_graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    hier_sep: str
    header_info: dict
    sdf_data: dict
    cells: list[str]
    instances: dict[str, list[Component]]
    io_paths: list[Component]
    interconnects: list[Component]
    
class DelayType(StrEnum):
    """
    Enumeration of delay types for the SDF timing model, including various combinations 
    of min, max, avg, fast, and slow delays.
    
    Attributes
    ----------
    MIN_ALL : str
        Represents the minimum delay across all conditions.
    MAX_ALL : str
        Represents the maximum delay across all conditions.
    AVG_ALL : str
        Represents the average delay across all conditions.
    AVG_FAST : str
        Represents the average delay under fast conditions.
    AVG_SLOW : str
        Represents the average delay under slow conditions.
    MAX_FAST : str
        Represents the maximum delay under fast conditions.
    MAX_SLOW : str
        Represents the maximum delay under slow conditions.
    MIN_FAST : str
        Represents the minimum delay under fast conditions.
    MIN_SLOW : str
        Represents the minimum delay under slow conditions.    
    """
    MIN_ALL = "min_all"
    MAX_ALL = "max_all"
    AVG_ALL = "avg_all"
    AVG_FAST = "avg_fast"
    AVG_SLOW = "avg_slow"
    MAX_FAST = "max_fast"
    MAX_SLOW = "max_slow"
    MIN_FAST = "min_fast"
    MIN_SLOW = "min_slow"
