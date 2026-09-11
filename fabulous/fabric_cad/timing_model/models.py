"""Models for the SDF timing model generation and analysis.

This module defines the data models used for representing the SDF timing graph,
components, and configuration for the timing model generation process. It includes
enumerations for cell types, delay types, timing model modes, synthesis and STA tools,
as well as dataclasses and Pydantic models for components, the SDF graph object, and the
timing model configuration. These models provide a structured way to represent the
timing information extracted from SDF files and the configuration parameters for
generating timing models, allowing for easier manipulation and analysis of the timing
data throughout the processing pipeline.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field


class SDFCellType(StrEnum):
    """Enumeration of cell types for the SDF timing model.

    Includes INTERCONNECT and IOPATH for the timing graph, as well
    as other types like REMOVAL, RECOVERY, SETUP, HOLD, WIDTH.

    Attributes
    ----------
    IOPATH
        Represents an IOPATH component, which defines timing paths between
        pins within the same cell.
    INTERCONNECT
        Represents an INTERCONNECT component, which defines timing paths
        between pins across
        different cells (i.e., inter-cell connections).
    REMOVAL
        Represents a REMOVAL component, which defines timing checks for
        signal removal.
    RECOVERY
        Represents a RECOVERY component, which defines timing checks for
        signal recovery.
    SETUP
        Represents a SETUP component, which defines timing checks for
        setup time.
    HOLD
        Represents a HOLD component, which defines timing checks for
        hold time.
    WIDTH
        Represents a WIDTH component, which defines timing checks for
        pulse width.
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
    """Represents a component in the SDF timing model.

    Its either an INTERCONNECT or an IOPATH for the timing graph.
    But it can also be: REMOVAL, RECOVERY, SETUP, HOLD, WIDTH.

    Attributes
    ----------
    c_type : SDFCellType
        Type of the component, either "INTERCONNECT" or "IOPATH"
        for the timing graph.
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
        IOPATH delay: pin to pin delay within a cell.
        Is a single delay over fast, slow (min, max)
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
    """Represents the SDF timing graph object.

    Contains the directed graph representation of the timing model, as
    well as associated metadata such as header information, SDF data
    dictionary parsed from the file, cell names, instances,
    IOPATHs, and interconnects.

    Attributes
    ----------
    nx_graph : nx.DiGraph
        The directed graph representation of the timing model,
        where nodes represent pins and edges represent timing paths
        with associated delay information.
    hier_sep : str
        The hierarchical separator used in instance names,
        extracted from the SDF
        header information.
    header_info : dict
        Dictionary containing header information from the SDF
        file, such as version, date,
        vendor, program, and hierarchical separator.
    sdf_data : dict
        The full SDF data parsed from the file, including
        cells, instances, IOPATHs,
        interconnects, and timing checks.
    cells : list[str]
        List of cell names defined in the SDF file.
    instances : dict[str, list[Component]]
        Dictionary mapping instance names of cells to lists of
        Component instances representing the
        timing paths (IOPATHs and INTERCONNECTs) associated
        with each instance.
    io_paths : list[Component]
        List of Component instances representing the IOPATHs
        defined in the SDF file, which represent timing paths between
        pins within the same cell.
    interconnects : list[Component]
        List of Component instances representing the INTERCONNECTs
        defined in the SDF file, which represent timing paths between pins
        across different cells (i.e., inter-cell connections).
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
    """Enumeration of delay types for the SDF timing model.

    Includes various combinations of min, max, avg, fast, and slow delays.

    Attributes
    ----------
    MIN_ALL
        Represents the minimum delay across all conditions.
    MAX_ALL
        Represents the maximum delay across all conditions.
    AVG_ALL
        Represents the average delay across all conditions.
    AVG_FAST
        Represents the average delay under fast conditions.
    AVG_SLOW
        Represents the average delay under slow conditions.
    MAX_FAST
        Represents the maximum delay under fast conditions.
    MAX_SLOW
        Represents the maximum delay under slow conditions.
    MIN_FAST
        Represents the minimum delay under fast conditions.
    MIN_SLOW
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


class SDFPathType(StrEnum):
    """Classify an SDF timing path by its sequential behavior.

    Attributes
    ----------
    COMBINATIONAL
        The path contains only combinational timing components.
    SEQUENTIAL
        The path crosses a sequential cell or synthetic timing-check edge.
    """

    COMBINATIONAL = "combinational"
    SEQUENTIAL = "sequential"


@dataclass(frozen=True, slots=True)
class SDFTimingTriplet:
    """Represent the minimum, typical, and maximum values of an SDF delay.

    Attributes
    ----------
    minimum : float | None
        Minimum delay, or `None` when the SDF does not provide it.
    typical : float | None
        Typical delay, called `avg` by the current SDF parser, or `None` when
        the SDF does not provide it.
    maximum : float | None
        Maximum delay, or `None` when the SDF does not provide it.
    """

    minimum: float | None
    typical: float | None
    maximum: float | None


@dataclass(frozen=True, slots=True)
class SDFPathTiming:
    """Collect the complete timing information for one structural graph path.

    Attributes
    ----------
    nodes : tuple[str, ...]
        Ordered graph nodes forming the path.
    components : tuple[Component, ...]
        Ordered SDF components forming the path edges.
    path_type : SDFPathType
        Whether the path is combinational or sequential.
    rise : SDFTimingTriplet
        Aggregated rising-transition propagation delay.
    fall : SDFTimingTriplet
        Aggregated falling-transition propagation delay.
    high_impedance : SDFTimingTriplet | None
        Aggregated high-impedance transition delay when it can be derived for every
        component on the path.
    setup : tuple[SDFTimingTriplet, ...]
        Setup checks associated with sequential edges on the path.
    hold : tuple[SDFTimingTriplet, ...]
        Hold checks associated with sequential edges on the path.
    timing_checks : tuple[Component, ...]
        Original SDF timing-check components associated with the path.
    conditions : tuple[str, ...]
        Ordered, unique SDF conditions affecting the path or its timing checks.
    register_clock_pin : str | None
        Graph pin at the register clock reached by the first timing-check edge.
    effective_setup : tuple[SDFTimingTriplet, ...]
        Setup constraints adjusted for the data and clock paths. Empty when no
        `clock_pin` was supplied to the path query or its clock path is unavailable.
    effective_hold : tuple[SDFTimingTriplet, ...]
        Hold constraints adjusted for the data and clock paths. Empty when no
        `clock_pin` was supplied to the path query or its clock path is unavailable.
    clock_to_output_rise : SDFTimingTriplet | None
        Rising clock-to-target propagation delay from the supplied clock pin.
    clock_to_output_fall : SDFTimingTriplet | None
        Falling clock-to-target propagation delay from the supplied clock pin.
    """

    nodes: tuple[str, ...]
    components: tuple[Component, ...]
    path_type: SDFPathType
    rise: SDFTimingTriplet
    fall: SDFTimingTriplet
    high_impedance: SDFTimingTriplet | None = None
    setup: tuple[SDFTimingTriplet, ...] = ()
    hold: tuple[SDFTimingTriplet, ...] = ()
    timing_checks: tuple[Component, ...] = ()
    conditions: tuple[str, ...] = ()
    register_clock_pin: str | None = None
    effective_setup: tuple[SDFTimingTriplet, ...] = ()
    effective_hold: tuple[SDFTimingTriplet, ...] = ()
    clock_to_output_rise: SDFTimingTriplet | None = None
    clock_to_output_fall: SDFTimingTriplet | None = None


class TimingModelMode(StrEnum):
    """Enumeration of timing model modes for the SDF timing model.

    Attributes
    ----------
    STRUCTURAL
        Represents a structural timing model, which focuses on the interconnections
        and structure of the design. This mode is based on the non routed netlist
        and can be used if no physical post-layout netlist is available.
    PHYSICAL
        Represents a physical timing model, which includes detailed information about
        the physical layout and routing of the design. This mode is based on the routed
        netlist and can be used if a physical post-layout netlist is available,
        providing more accurate timing information that accounts for the actual
        physical implementation of the design.
    """

    STRUCTURAL = "structural"
    PHYSICAL = "physical"


class TimingModelTarget(StrEnum):
    """Select which nextpnr timing data the timing-model flow generates.

    Attributes
    ----------
    PIPS
        Generate routing-resource delays in `pips.txt`.
    BELS
        Generate BEL-internal timing arcs in `bel.v3.txt`.
    BOTH
        Generate both pip and BEL timing data.
    """

    PIPS = "pips"
    BELS = "bels"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class BelClockTiming:
    """Declare a BEL clock port and its optional activation condition.

    Attributes
    ----------
    clock : str
        Logical nextpnr clock-port name.
    condition : str | None
        Optional nextpnr timing condition.
    """

    clock: str
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class BelDelayTiming:
    """Represent one combinational BEL timing arc.

    Attributes
    ----------
    source : str
        Logical nextpnr source-port name.
    sink : str
        Logical nextpnr destination-port name.
    delay : float
        Arc delay in nanoseconds.
    condition : str | None
        Optional nextpnr timing condition.
    """

    source: str
    sink: str
    delay: float
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class BelSetupHoldTiming:
    """Represent setup and hold checks for one BEL data port.

    Attributes
    ----------
    port : str
        Logical nextpnr data-port name.
    clock : str
        Logical nextpnr clock-port name.
    setup : float
        Setup time in nanoseconds.
    hold : float
        Hold time in nanoseconds.
    condition : str | None
        Optional nextpnr timing condition.
    """

    port: str
    clock: str
    setup: float
    hold: float
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class BelClockToOutTiming:
    """Represent one BEL clock-to-output timing arc.

    Attributes
    ----------
    port : str
        Logical nextpnr output-port name.
    clock : str
        Logical nextpnr clock-port name.
    delay : float
        Clock-to-output delay in nanoseconds.
    condition : str | None
        Optional nextpnr timing condition.
    """

    port: str
    clock: str
    delay: float
    condition: str | None = None


type BelTimingArc = (
    BelClockTiming | BelDelayTiming | BelSetupHoldTiming | BelClockToOutTiming
)


@dataclass(frozen=True, slots=True)
class BelTiming:
    """Collect all characterized timing arcs for one BEL instance.

    Attributes
    ----------
    arcs : tuple[BelTimingArc, ...]
        Immutable sequence of timing arcs in nextpnr emission order.
    """

    arcs: tuple[BelTimingArc, ...] = ()


class TimingModelSynthTools(StrEnum):
    """Enumeration of synthesis tools configured for the timing model.

    Attributes
    ----------
    YOSYS
        Represents the Yosys synthesis tool, which is an open-source
        framework for RTL synthesis.
    """

    YOSYS = "yosys"


class TimingModelStaTools(StrEnum):
    """Enumeration of static STA tools configured for the timing model.

    Attributes
    ----------
    OPENSTA
        Represents the OpenSTA tool, which is an open-source static
        timing analysis tool.
    """

    OPENSTA = "opensta"


class TimingModelTileSourceFiles(BaseModel):
    """Configuration class for the source files related to a specific tile.

    Contains paths to RTL files, netlist file, and RC file.

    Attributes
    ----------
    model_config
        Pydantic configuration for the model, allowing for strict validation
        and assignment.
    rtl_files : list[Path] | Path | None
        The list of RTL files or a single RTL file path for the tile,
        or None if not applicable.
    netlist_file : Path | None
        The path to the netlist file for the tile, or None if not applicable.
    rc_file : Path | None
        The path to the RC file for the tile, or None if not applicable.
    """

    model_config = ConfigDict(strict=False, validate_assignment=True, extra="forbid")

    rtl_files: list[Path] | Path | None = None
    netlist_file: Path | None = None
    rc_file: Path | None = None


class TimingModelConfig(BaseModel):
    """Configuration class for the SDF timing model.

    Containins all necessary parameters and settings for
    generating the timing model from the SDF file.

    Attributes
    ----------
    model_config
        Pydantic configuration for the model, allowing for strict
        validation and assignment.
    project_dir : Path
        The directory of the project, used for resolving relative
        paths.
    liberty_files : list[Path] | Path
        The list of liberty files or a single liberty file path used
        for timing analysis.
    min_buf_cell_and_ports : str
        The minimum buffer cell and ports "cell_name input_port output_port".
    synth_executable : Path | str
        The executable command for the synthesis tool.
    sta_executable : Path | str
        The executable command for the static timing analysis tool.
    pdk_name : str | None
        The name of the PDK being used, It's just for informational
        purposes.
    techmap_files : list[Path] | Path | None
        The list of technology mapping files or a single techmap file path
        or None if not applicable.
    tiehi_cell_and_port : str | None
        The cell and port used for tie-high connections
        "cell_name port_name", or None if not applicable.
    tielo_cell_and_port : str | None
        The cell and port used for tie-low connections
        "cell_name port_name", or None if not applicable.
    custom_per_tile_source_files : dict[str, TimingModelTileSourceFiles] | None
        A dictionary mapping tile names to TimingModelTileSourceFiles
        instances containing custom
        source file paths, or None if not applicable. This will overwrite
        the default paths defined in the project directory for the specific tile.
    sta_program : TimingModelStaTools
        The static timing analysis tool to be used, specified as an instance of
        the TimingModelStaTools enumeration.
    synth_program : TimingModelSynthTools
        The synthesis tool to be used, specified as an instance of the
        TimingModelSynthTools enumeration.
    mode : TimingModelMode
        The timing model mode to be used, specified as an instance of the
        TimingModelMode enumeration.
    consider_wire_delay : bool
        Flag indicating whether to consider wire delay in the timing analysis.
    delay_type_str : DelayType
        The type of delay to be used in the timing analysis, specified as an
        instance of the DelayType enumeration.
    delay_scaling_factor : float
        A scaling factor to be applied to the calculated delays, allowing for
        adjustments based on specific requirements or to account for any
        discrepancies in the delay calculations. But be careful when using this,
        as it can lead to inaccurate timing models if not used properly.
    debug : bool
        Flag to enable or disable debug mode, which may provide additional logging.
    """

    model_config = ConfigDict(strict=False, validate_assignment=True, extra="forbid")

    project_dir: Path
    liberty_files: list[Path] | Path
    min_buf_cell_and_ports: str
    synth_executable: Path | str
    sta_executable: Path | str
    pdk_name: str | None = None
    techmap_files: list[Path] | Path | None = None
    tiehi_cell_and_port: str | None = None
    tielo_cell_and_port: str | None = None
    custom_per_tile_source_files: dict[str, TimingModelTileSourceFiles] | None = None
    sta_program: TimingModelStaTools = Field(default=TimingModelStaTools.OPENSTA)
    synth_program: TimingModelSynthTools = Field(default=TimingModelSynthTools.YOSYS)
    mode: TimingModelMode = Field(default=TimingModelMode.PHYSICAL)
    consider_wire_delay: bool = Field(default=True)
    delay_type_str: DelayType = Field(default=DelayType.MAX_ALL)
    delay_scaling_factor: float = Field(default=1.0)
    debug: bool = Field(default=False)


@dataclass(frozen=True)
class InternalPipCacheEntry:
    """Represents a cache entry for the internal pip delay calculation.

    Contains all relevant information for the calculation, including the source pip,
    destination pip, the best path through the switch matrix, the nearest ports to the
    source and destination pips, the reference output port for convergence, and the
    physical output of the switch matrix.

    Attributes
    ----------
    begin_pip : str
        The begin pip for the internal pip delay calculation.
    swm_mux_for_pips : list[str]
        The list of switch matrix multiplexers (swm mux) that are relevant for the
        source and destination pips.
    swm_nearest_ports_in : tuple[dict[str, list[str]], list[str]] | None
        A tuple containing two elements:
        - A dictionary mapping each pip of a swm mux (source and destination) to a
          list of its nearest input ports.
        - A list of all nearest input ports for both source and destination
          pips of a swm mux.
    swm_nearest_ports_out: tuple[dict[str, list[str]], list[str]] | None
        A tuple containing two elements:
        - A dictionary mapping each pip of a swm mux (source and destination) to a
          list of its nearest output ports.
        - A list of all nearest output ports for both source and destination
          pips of a swm mux.
    swm_output_pin : tuple[list[str], float | None, dict[str, dict[str, float]]] | None
        A tuple containing three elements:
        - A list of output pin(s) of the swm mux that were found during
          convergence detection.
        - The best cost associated with the best convergence node.
        - A dictionary mapping source -> node -> distance.
    swm_mux_resolved : dict[str, list[str]] | None
        A dictionary mapping each pip of a swm mux (source and destination)
        to a list of resolved pins for the swm mux instance to cell pins.
    """

    begin_pip: str
    swm_mux_for_pips: list[str]
    swm_nearest_ports_in: tuple[dict[str, list[str]], list[str]] | None
    swm_nearest_ports_out: tuple[dict[str, list[str]], list[str]] | None
    swm_output_pin: tuple[list[str], float | None, dict[str, dict[str, float]]] | None
    swm_mux_resolved: dict[str, list[str]] | None
