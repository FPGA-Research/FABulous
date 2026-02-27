"""
Defines the Component class representing a component in the SDF timing model,
which can be an INTERCONNECT or an IOPATH for the timing graph, as well as other
types like REMOVAL, RECOVERY, SETUP, HOLD, WIDTH. The class includes attributes for
the component type, connection string, cell name, instance names, pin names,
delay information, and various flags indicating the nature of the component.
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class Component:
    """
    Represents a component in the SDF timing model, either an INTERCONNECT or an IOPATH for the timing graph.
    But it can also be: REMOVAL, RECOVERY, SETUP, HOLD, WIDTH.

    Attributes
    ----------
    c_type : str
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
    c_type: str
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
