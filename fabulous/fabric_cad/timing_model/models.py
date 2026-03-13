"""
Defines the Component class representing a component in the SDF timing model,
which can be an INTERCONNECT or an IOPATH for the timing graph, as well as other
types like REMOVAL, RECOVERY, SETUP, HOLD, WIDTH. The class includes attributes for
the component type, connection string, cell name, instance names, pin names,
delay information, and various flags indicating the nature of the component.
"""


from dataclasses import dataclass, field
from pydantic import BaseModel, Field, ConfigDict
from enum import StrEnum
import networkx as nx
from pathlib import Path


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

class TimingModelSynthTools(StrEnum):
    """
    Enumeration of synthesis tools configured for the timing model.
    
    Attributes
    ----------
    YOSYS : str
        Represents the Yosys synthesis tool, which is an open-source framework for RTL synthesis.
    """
    YOSYS = "yosys"

class TimingModelStaTools(StrEnum):
    """
    Enumeration of static timing analysis (STA) tools configured for the timing model.
    
    Attributes
    ----------
    OPENSTA : str
        Represents the OpenSTA tool, which is an open-source static timing analysis tool.
    """
    OPENSTA = "opensta"

class TimingModelConfig(BaseModel):
    """
    Configuration class for the SDF timing model, containing all necessary parameters and settings
    for generating the timing model from the SDF file.
    
    Attributes
    ----------
    project_dir : Path
        The directory of the project, used for resolving relative paths.
    liberty_files : list[Path] | Path
        The list of liberty files or a single liberty file path used for timing analysis.
    min_buf_cell_and_ports : str
        The minimum buffer cell and its ports "cell_name input_port output_port".
    synth_executable : str
        The executable command for the synthesis tool.
    sta_executable : str
        The executable command for the static timing analysis tool.
    techmap_files : list[Path] | Path | None
        The list of technology mapping files or a single techmap file path or None if not applicable.
    tiehi_cell_and_port : str | None
        The cell and port used for tie-high connections "cell_name port_name", or None if not applicable.
    tielo_cell_and_port : str | None
        The cell and port used for tie-low connections "cell_name port_name", or None if not applicable.
    custom_per_tile_netlist_files : dict[str, Path] | None
        A dictionary mapping tile names to custom netlist file paths, or None if not applicable.
    custom_per_tile_rc_files : dict[str, Path] | None
        A dictionary mapping tile names to custom RC file paths, or None if not applicable.
    sta_program : TimingModelStaTools
        The static timing analysis tool to be used, specified as an instance of the TimingModelStaTools enumeration.
    synth_program : TimingModelSynthTools
        The synthesis tool to be used, specified as an instance of the TimingModelSynthTools enumeration.
    mode : TimingModelMode
        The timing model mode to be used, specified as an instance of the TimingModelMode enumeration.
    consider_wire_delay : bool
        Flag indicating whether to consider wire delay in the timing analysis.
    delay_type_str : DelayType
        The type of delay to be used in the timing analysis, specified as an instance of the DelayType enumeration.
    debug : bool
        Flag to enable or disable debug mode, which may provide additional logging.
    """
    model_config = ConfigDict(strict=False, validate_assignment=True)
    
    project_dir: Path          
    liberty_files: list[Path] | Path         
    min_buf_cell_and_ports: str 
    synth_executable: Path | str
    sta_executable: Path | str
    techmap_files: list[Path] | Path | None = None
    tiehi_cell_and_port: str | None = None     
    tielo_cell_and_port: str | None = None
    custom_per_tile_netlist_files: dict[str, Path] | None = None
    custom_per_tile_rc_files: dict[str, Path] | None = None
    sta_program: TimingModelStaTools = Field(default=TimingModelStaTools.OPENSTA)
    synth_program: TimingModelSynthTools = Field(default=TimingModelSynthTools.YOSYS)
    mode: TimingModelMode = Field(default=TimingModelMode.PHYSICAL)
    consider_wire_delay: bool = Field(default=True)    
    delay_type_str: DelayType = Field(default=DelayType.MAX_ALL)
    debug: bool = Field(default=False)

@dataclass(frozen=True)
class InternalPipCachePhysEntry:
    """
    Represents a cache entry for the physical-level internal pip delay calculation, 
    containing all relevant information for the calculation, including the source pip, 
    destination pip, the best path through the switch matrix, the nearest ports to the 
    source and destination pips, the reference output port for convergence,
    and the physical output of the switch matrix.
    
    Attributes
    ----------
    begin_pip : str
        The begin pip for the internal pip delay calculation.
    swm_mux_for_pips : list[str]
        The list of switch matrix multiplexers that are relevant for the source and destination pips.
    swm_nearest_ports : tuple[dict[str, list[str]], list[str]]
        A tuple containing two elements:
        - A dictionary mapping each pip (source and destination) to a list of its nearest ports in the switch matrix.
        - A list of all nearest ports for both source and destination pips.
    ref_output_port : str
        The reference output port used for convergence in the physical-level delay calculation.
    swm_phys_output : list[str]
        The list of physical output ports of the switch matrix that are relevant for the delay calculation.
    """
    begin_pip: str
    swm_mux_for_pips: list[str]
    swm_nearest_ports: tuple[dict[str, list[str]], list[str]]
    ref_output_port: str
    swm_phys_output: list[str]