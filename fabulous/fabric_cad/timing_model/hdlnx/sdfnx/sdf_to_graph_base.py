"""SDF Timing Graph Class Module.

This module provides a class to represent timing graphs generated from SDF files.

It also includes methods to analyze the timing graph.
"""

from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.timing_graph import gen_timing_digraph
from fabulous.fabric_cad.timing_model.models import (
    Component,
    DelayType,
    SDFCellType,
    SDFGobject,
)


class SDFTimingGraphBase:
    """Class to represent a timing graph generated from an SDF file.

    Initialize the SDFTimingGraphBase object by parsing the SDF
    file and generating the timing graph.

    It also contains algorithms to analyze the timing graph. This class
    serves as a base class for more specialized timing graph classes.

    Parameters
    ----------
    sdf_file : Path
        Path to the SDF file.
    delay_type_str : DelayType
        The type of delay to extract. Options include:
        DelayType.MIN_ALL, DelayType.MAX_ALL, DelayType.AVG_ALL,
        DelayType.AVG_FAST, DelayType.AVG_SLOW,
        DelayType.MAX_FAST, DelayType.MAX_SLOW, DelayType.MIN_FAST,
        DelayType.MIN_SLOW.

    Examples
    --------
        s = SDFTimingGraphBase(Path("path/to/sdf_file.sdf"), DelayType.MAX_ALL)
    """

    def __init__(
        self, sdf_file: Path, delay_type_str: DelayType = DelayType.MAX_ALL
    ) -> None:
        self.sdf_file: Path = sdf_file
        self.sdf_file_content: str = sdf_file.read_text()

        self.delay_type_str: DelayType = delay_type_str
        self.sdf_gobject: SDFGobject = gen_timing_digraph(sdf_file, delay_type_str)

        self.graph = self.sdf_gobject.nx_graph
        self.reverse_graph = self.graph.reverse(copy=True)

        self.header_info: dict = self.sdf_gobject.header_info
        self.sdf_data_dict: dict = self.sdf_gobject.sdf_data
        self.cells: list[str] = self.sdf_gobject.cells
        self.instances: dict[str, list[Component]] = self.sdf_gobject.instances
        self.io_paths: list[Component] = self.sdf_gobject.io_paths
        self.interconnects: list[Component] = self.sdf_gobject.interconnects
        self.hier_sep: str = self.sdf_gobject.hier_sep

        self.input_ports = list(
            {
                n
                for n in self.graph.nodes
                if self.graph.in_degree(n) == 0 and self.hier_sep not in n
            }
        )
        self.output_ports = list(
            {
                n
                for n in self.graph.nodes
                if self.graph.out_degree(n) == 0 and self.hier_sep not in n
            }
        )

    ### Public Methods ###

    @property
    def get_input_and_output_ports(self) -> list[str]:
        """Get the list of input and output ports in the timing graph.

        Returns
        -------
        list[str]
            List of input and output port names.
        """
        return self.input_ports + self.output_ports

    @property
    def get_SDF_header_info(self) -> tuple[dict, str]:
        """Get the SDF header information as a dictionary and formatted string.

        Returns
        -------
        tuple[dict, str]
            A tuple containing the header information dictionary
            and a formatted string.
        """
        info_str: str = ""
        for key, value in self.header_info.items():
            info_str += f"{key}: {value}\n"
        return self.header_info, info_str

    def print_graph(self) -> None:
        """Print the edges of the timing graph.

        Contains delay weights and component information.
        """
        for u, v, data in self.graph.edges(data=True):
            logger.info(
                f"{u} --> {v} delay {data['weight']} ({data['component'].cell_name}, "
                f"{data['component'].c_type})"
            )

    def get_cell_instance(self, instance_name: str) -> list[Component]:
        """Get the list of components associated with a given instance name.

        Parameters
        ----------
        instance_name : str
            The name of the cell instance.

        Returns
        -------
        list[Component]
            List of components associated with the instance.
        """
        return self.instances[instance_name]

    def get_cell_instance_inputs_to_outputs(
        self, instance_name: str
    ) -> tuple[list[str], list[str]]:
        """Get the input and output pins of a given cell instance.

        Parameters
        ----------
        instance_name : str
            The name of the cell instance.

        Returns
        -------
        tuple[list[str], list[str]]
            A tuple containing two lists: input pins and output pins.
        """
        input_pins: list[str] = []
        output_pins: list[str] = []

        if instance_name not in self.instances:
            # If the instance name is not found, return empty lists
            return input_pins, output_pins

        for i in self.instances[instance_name]:
            if i.c_type == SDFCellType.IOPATH:
                input_pins.append(i.from_cell_pin)
                output_pins.append(i.to_cell_pin)
        return input_pins, output_pins

    def get_cell_instance_component_by_type(
        self, instance_name: str, c_type: SDFCellType, input_pin: str, output_pin: str
    ) -> Component:
        """Get a specific component of a cell instance by type and pin names.

        Parameters
        ----------
        instance_name : str
            The name of the cell instance.
        c_type : SDFCellType
            The type of component: "IOPATH", "REMOVAL",
            "RECOVERY", "SETUP", "HOLD", "WIDTH".
        input_pin : str
            The input pin name.
        output_pin : str
            The output pin name.

        Returns
        -------
        Component
            The matching component, or None if not found.

        Raises
        ------
        KeyError
            If the instance name is not found in the SDF instances.
        """
        if instance_name not in self.instances:
            raise KeyError(f"Instance {instance_name} not found in SDF instances.")

        for i in self.instances[instance_name]:
            if (
                i.c_type == c_type
                and i.from_cell_pin == input_pin
                and i.to_cell_pin == output_pin
            ):
                return i
        return None
