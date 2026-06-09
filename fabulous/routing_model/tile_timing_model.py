"""Per-tile timing extraction for FABulous fabrics.

`FABulousTileTimingModel` reads a tile's project files and extracts per-pip
routing delays. It builds synthesis-level and (in physical mode) physical-level
:class:`~fabulous.routing_model.netlist_timing_model.NetlistTimingModel` engines
for the tile, then computes internal switch-matrix pip delays and external
tile-to-tile pip delays from them. `RoutingModelGenerator` drives one of these per
tile through the narrow :meth:`FABulousTileTimingModel.pip_delay` interface.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from loguru import logger

from fabulous.fabric_definition.cell_spec import StdCellLibrary
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.yosys_obj import InstanceRef
from fabulous.fabulous_settings import get_context
from fabulous.routing_model.graph_algorithms import (
    DelayType,
    earliest_common_nodes,
    follow_first_fanout_from_pins,
    path_to_nearest_target_sentinel,
    single_delay,
)
from fabulous.routing_model.netlist_timing_model import NetlistTimingModel


class TimingModelMode(StrEnum):
    """Source netlist the timing model is built from.

    Attributes
    ----------
    STRUCTURAL
        Built from the non-routed netlist; use when no post-layout netlist exists.
    PHYSICAL
        Built from the routed, post-layout netlist for layout-accurate timing.
    """

    STRUCTURAL = "structural"
    PHYSICAL = "physical"
    PLACEHOLDER = "placeholder"


@dataclass(frozen=True)
class InternalPipCacheEntry:
    """Cached intermediate state for an internal pip-delay calculation.

    Keyed by the destination pip (a switch-matrix BEG pin, unique per mux), so a
    later pip sharing that destination skips re-resolving the switch matrix. Only
    the fields the delay calculations read back are kept: the structural path
    reuses ``swm_mux_resolved``; the physical path reuses ``swm_nearest_ports_in``,
    ``swm_nearest_ports_out`` and ``swm_output_pin``.

    Attributes
    ----------
    swm_mux_for_pips : list[InstanceRef]
        Switch-matrix multiplexer instances relevant to the source and
        destination pips.
    swm_nearest_ports_in : tuple[dict[str, list[str]], list[str]] | None
        Per-mux-pip nearest input ports, plus the flattened list of all of them.
    swm_nearest_ports_out : tuple[dict[str, list[str]], list[str]] | None
        Per-mux-pip nearest output ports, plus the flattened list of all of them.
    swm_output_pin : list[str] | None
        Convergence output pin(s) of the switch-matrix mux at physical level.
    swm_mux_resolved : dict[str, list[str]] | None
        Per-mux-pip resolved cell pins for the switch-matrix instance.
    """

    swm_mux_for_pips: list[InstanceRef]
    swm_nearest_ports_in: tuple[dict[str, list[str]], list[str]] | None
    swm_nearest_ports_out: tuple[dict[str, list[str]], list[str]] | None
    swm_output_pin: list[str] | None
    swm_mux_resolved: dict[str, list[str]] | None


class FABulousTileTimingModel:
    """Reads the FABulous project files and extracts timing information.

    - It initializes both synthesis-level and physical-level timing models
      using the NetlistTimingModel class.
    - It provides methods to calculate delays for internal PIPs
      (within the switch matrix) and external PIPs (between the tile and the
      next tile) using either structural or physical approaches.

    The project directory is sourced from the active :func:`get_context`; the
    standard-cell library is passed in and forwarded to
    :class:`NetlistTimingModel`.

    Parameters
    ----------
    fabric : Fabric
        The FABulous fabric object.
    verilog_files : list[Path]
        Fabric Verilog source files to synthesize for the timing model.
    tile_name : str
        The name of the tile for which the timing model is being created.
    mode : TimingModelMode
        Source netlist the model is built from (structural or physical).
    consider_wire_delay : bool
        Whether to include wire delay in the physical analysis.
    delay_type : DelayType
        How multi-corner delays are collapsed to a scalar.
    delay_scaling_factor : float
        Scaling factor applied to computed delays.
    library : StdCellLibrary
        The PDK's standard-cell library: liberty/techmap files and cells.
    """

    def __init__(
        self,
        fabric: Fabric,
        verilog_files: list[Path],
        tile_name: str,
        mode: TimingModelMode,
        consider_wire_delay: bool,
        delay_type: DelayType,
        delay_scaling_factor: float,
        library: StdCellLibrary,
    ) -> None:
        self.fabric: Fabric = fabric
        self.tile_name: str = tile_name
        self.library: StdCellLibrary = library

        # Verilog source files synthesized to build the timing model.

        self.verilog_files: list[Path] = verilog_files

        # Timing knobs chosen at the command line.

        self.mode: TimingModelMode = mode
        self.consider_wire_delay: bool = consider_wire_delay
        self.delay_type: DelayType = delay_type
        self.delay_scaling_factor: float = delay_scaling_factor

        # Project directory used to locate post-layout netlist/SPEF files.

        self.project_dir: Path = get_context().proj_dir

        # A tile that is part of a SuperTile is synthesized under the SuperTile,
        # so its timing comes from the SuperTile's RTL and switch matrix. Resolve
        # that "unique" name (and remember the SuperTile) here.

        super_tile = self.fabric.get_super_tile_containing(self.tile_name)
        self.is_in_which_super_tile: str | None = (
            super_tile.name if super_tile is not None else None
        )
        self.unique_tile_name: str = (
            super_tile.name if super_tile is not None else self.tile_name
        )

        # Init:

        self.netlist_tm_synth: NetlistTimingModel | None = None
        self.netlist_tm_phys: NetlistTimingModel | None = None
        self._initialize_timing_models()

        # Extract switch matrix information
        # Check super_tile_type in config to filter the correct switch matrix

        self.switch_matrix_instance: InstanceRef | None = None
        self.switch_matrix_module_name: list[str] | str | None = None
        self.internal_pips_grouped_by_inst: dict[str, list[str]] | None = None
        self.internal_pips: list[str] | None = None
        self._extract_switch_matrix_info()

        self.internal_pip_cache: dict[str, InternalPipCacheEntry] = {}

        logger.info("FABulous Timing Model initialized.")

    def _initialize_timing_models(self) -> None:
        """Initialize the synthesis and physical timing models using NetlistTimingModel.

        - The synthesis-level model is initialized with the RTL Verilog files
          and the specified synthesis and STA tools.
        - The physical-level model is initialized with the gate-level netlist,
          and optionally with SPEF files for wire delay if consider_wire_delay
          is True in the configuration.

        Returns
        -------
        None
            If the mode is STRUCTURAL, only the synthesis-level model is initialized
            and the method returns None.
        """
        logger.info(f"Initializing FABulous Timing Model for Tile: {self.tile_name}")
        logger.info(f"  SuperTile: {self.is_in_which_super_tile}")

        # Initialize the synthesis-level timing model first, as it is needed
        # to extract the switch matrix information and to find the relevant
        # Verilog files for the physical-level model.
        logger.info("Initializing Synthesis-level timing model...")

        # Synthesis-level model: synthesize the RTL and build its timing graph.
        self.netlist_tm_synth = NetlistTimingModel(
            verilog_files=self.verilog_files,
            top_name=self.unique_tile_name,
            library=self.library,
            is_gate_level=False,
            spef_files=None,
            delay_type_str=self.delay_type,
        )

        # If the mode is STRUCTURAL, we only need the synthesis-level model and can skip
        # initializing the physical-level model.
        if self.mode == TimingModelMode.STRUCTURAL:
            logger.info(
                "Mode is STRUCTURAL, skipping physical-level model initialization."
            )
            return

        logger.info("Initializing Physical-level timing model...")

        # The physical-level model uses the post-layout gate-level netlist.
        gate_level_netlist = Path(
            f"{self.project_dir}/Tile/{self.unique_tile_name}"
            f"/macro/final_views/nl/{self.unique_tile_name}.nl.v"
        )

        # Optionally load RC files for wire delay if consider_wire_delay is True.
        spef_files: Path | None = None
        if self.consider_wire_delay:
            spef_files = Path(
                f"{self.project_dir}/Tile/{self.unique_tile_name}"
                f"/macro/final_views/spef/nom/{self.unique_tile_name}.nom.spef"
            )

        # Physical-level model: analyze the gate-level netlist (with optional SPEF).
        self.netlist_tm_phys = NetlistTimingModel(
            verilog_files=gate_level_netlist,
            top_name=self.unique_tile_name,
            library=self.library,
            is_gate_level=True,
            spef_files=spef_files,
            delay_type_str=self.delay_type,
        )

    def _extract_switch_matrix_info(self) -> None:
        """Extract switch matrix information for the tile.

        - Hierarchical path of the switch matrix instance
        - Module name of the switch matrix
        - Internal PIPs of the switch matrix, grouped by instance
        - List of all internal PIPs of the switch matrix

        The method uses the synthesis-level timing model to find the relevant
        switch matrix instance and module based on regex patterns. It also
        checks if the tile is part of a SuperTile to filter the correct switch
        matrix information. Finally, it loads the internal PIPs of the switch
        matrix for later use in delay calculations.

        Raises
        ------
        ValueError
            If no switch matrix instance or module is found, or if multiple
            instances/modules are found when not expected.

        Returns
        -------
        None
            If no switch matrix instance or module is found, a warning is
            logged and the method returns None, indicating that all PIPs for
            the tile will be considered external.
        """
        logger.info("Extracting switch matrix information...")

        self.switch_matrix_instance = (
            self.netlist_tm_synth.netlist.find_instances_by_regex(r".*_switch_matrix$")
        )

        self.switch_matrix_module_name = (
            self.netlist_tm_synth.netlist.find_verilog_modules_regex(
                r"^[^/]*_switch_matrix$"
            )
        )

        if (
            len(self.switch_matrix_instance) == 0
            or len(self.switch_matrix_module_name) == 0
        ):
            logger.warning(
                f"No switch matrix instance or module found. "
                f"All PIPs for {self.tile_name} will be considered external."
            )
            return

        if self.is_in_which_super_tile is None:
            if (
                len(self.switch_matrix_instance) > 1
                or len(self.switch_matrix_module_name) > 1
            ):
                raise ValueError(
                    "Multiple switch matrix instances or modules found "
                    "for a non-SuperTile."
                )

            self.switch_matrix_instance = self.switch_matrix_instance[0]
            self.switch_matrix_module_name = self.switch_matrix_module_name[0]

            logger.info(
                f"Using switch matrix instance: {self.switch_matrix_instance.path}, "
                f"module: {self.switch_matrix_module_name}"
            )

        else:
            self.switch_matrix_instance = [
                inst
                for inst in self.switch_matrix_instance
                if self.tile_name in inst.path
            ]

            self.switch_matrix_module_name = [
                m for m in self.switch_matrix_module_name if self.tile_name in m
            ]

            if (
                len(self.switch_matrix_instance) == 0
                or len(self.switch_matrix_module_name) == 0
            ):
                raise ValueError(
                    f"No switch matrix instance or module found for SuperTile "
                    f"{self.unique_tile_name}"
                )

            if (
                len(self.switch_matrix_instance) > 1
                or len(self.switch_matrix_module_name) > 1
            ):
                raise ValueError(
                    f"Multiple switch matrix instances or modules found Tile "
                    f"{self.tile_name} in SuperTile {self.unique_tile_name}."
                )

            self.switch_matrix_instance = self.switch_matrix_instance[0]
            self.switch_matrix_module_name = self.switch_matrix_module_name[0]

            logger.info(
                f"Tile {self.tile_name} is part of super tile {self.unique_tile_name}."
            )

        logger.info("Loading internal PIPs...")

        # Nets connected to each direct instance of the switch-matrix module,
        # grouped by instance, so is_tile_internal_pip can test whether a single
        # mux carries both pip nets. The module name came from the netlist itself,
        # so it is guaranteed to exist.
        swm_module = self.netlist_tm_synth.netlist.modules[
            self.switch_matrix_module_name
        ]
        self.internal_pips_grouped_by_inst = {
            inst_name: [
                net for nets in swm_module.pin_nets(inst_name).values() for net in nets
            ]
            for inst_name in swm_module.cells
        }

        self.internal_pips = list(self.switch_matrix_instance.cell.connections.keys())

    def is_tile_internal_pip(self, pip_src: str, pip_dst: str) -> bool:
        """Check if both PIPs are internal PIPs of the switch matrix.

        That means the path must be through a switch matrix multiplexer.
        Its not a wire delay.

        Parameters
        ----------
        pip_src : str
            Source PIP port name (e.g., "LB_O").
        pip_dst : str
            Destination PIP port name (e.g., "JN2BEG3").

        Returns
        -------
        bool
            True if both PIPs are internal PIPs of the switch matrix, False otherwise.
        """
        instance_to_nets = self.internal_pips_grouped_by_inst

        if instance_to_nets is None or pip_src == pip_dst:
            return False

        target = set([pip_src, pip_dst])
        for _inst, net_list in instance_to_nets.items():
            if target.issubset(set(net_list)):
                return True
        return False

    def _resolve_swm_mux(
        self, pip_src: str, pip_dst: str, pip_cache: InternalPipCacheEntry | None
    ) -> list[InstanceRef]:
        """Find the switch-matrix mux instance(s) carrying both pips.

        Reuses the cached lookup on a cache hit, otherwise queries the
        synthesis-level model. Warns (but does not fail) when more than one mux
        matches, in which case the first is used downstream.

        Parameters
        ----------
        pip_src : str
            Source PIP port name.
        pip_dst : str
            Destination PIP port name.
        pip_cache : InternalPipCacheEntry | None
            The cached entry for ``pip_dst``, or None on a cache miss.

        Returns
        -------
        list[InstanceRef]
            The matching switch-matrix mux instances.
        """
        if pip_cache is not None:
            swm_mux_for_pips = pip_cache.swm_mux_for_pips
        else:
            # A switch-matrix mux is a direct instance of the switch-matrix module
            # that carries both pip nets on its pins; narrow to this tile's
            # switch-matrix instance by path.
            netlist = self.netlist_tm_synth.netlist
            module_name = self.switch_matrix_module_name
            target_nets = {pip_src, pip_dst}
            # The instance path is a literal hierarchical identifier, not a
            # pattern: Yosys names embed regex metacharacters ('[', ']', '$',
            # '.'), so it must be escaped before being used as a search regex.
            within_instance = re.compile(re.escape(self.switch_matrix_instance.path))
            swm_mux_for_pips = [
                ref
                for ref in netlist.walk_instances()
                if ref.module_name == module_name
                and target_nets.issubset(
                    net for nets in ref.pin_nets().values() for net in nets
                )
                and within_instance.search(ref.path)
            ]

        if not swm_mux_for_pips:
            raise ValueError(
                f"No switch matrix mux instance found for internal PIP "
                f"{pip_src} -> {pip_dst} under "
                f"{self.switch_matrix_instance.path}."
            )

        if len(swm_mux_for_pips) > 1:
            logger.warning(
                f"Multiple switch matrix mux instances found "
                f"for PIPs {pip_src} -> {pip_dst}. "
                f"Using the first one: {swm_mux_for_pips[0].path}"
            )

        logger.info(f"  Found switch matrix mux instance: {swm_mux_for_pips[0].path}")
        return swm_mux_for_pips

    def internal_pip_delay_structural(self, pip_src: str, pip_dst: str) -> float:
        """Calculate delay between two PIPs in the switch matrix.

        It is the fast variant that does not need physical design information,
        but the results may be less accurate.

        Parameters
        ----------
        pip_src : str
            Source PIP port name (e.g., "LB_O").
        pip_dst : str
            Destination PIP port name (e.g., "JN2BEG3").

        Returns
        -------
        float
            Delay in nanoseconds between the two PIPs.
        """
        logger.info(
            f"Timing extraction for tile: {self.tile_name}, PIP: {pip_src} -> {pip_dst}"
        )

        synth_model = self.netlist_tm_synth

        pip_cache: InternalPipCacheEntry | None = self.internal_pip_cache.get(pip_dst)

        if pip_cache is not None:
            logger.info(
                f"Cache hit for internal PIP {pip_src} -> {pip_dst}. "
                f"Using cached synthesis-level information."
            )

        logger.info(
            f"Finding synthesis-level switch matrix mux for PIPs {pip_src} -> {pip_dst}"
        )

        # Are pip_src and pip_dst connected through the same switch matrix multiplexer?
        swm_mux_for_pips = self._resolve_swm_mux(pip_src, pip_dst, pip_cache)

        # Get the resolved pins for the switch matrix mux instance.
        swm_mux_resolved = (
            synth_model.netlist.net_to_pin_paths_for_instance_resolved(
                swm_mux_for_pips[0]
            )
            if pip_cache is None
            else pip_cache.swm_mux_resolved
        )

        logger.info("Switch matrix mux resolved pins for src and dst:")
        logger.info(f"  {pip_src}: {swm_mux_resolved[pip_src]}")
        logger.info(f"  {pip_dst}: {swm_mux_resolved[pip_dst]}")

        if len(swm_mux_resolved[pip_src]) > 1:
            logger.warning(
                f"Multiple resolved pins found for PIP source {pip_src} "
                f"in switch matrix mux instance {swm_mux_for_pips[0].path}. "
                f"Using the first one: {swm_mux_resolved[pip_src][0]}"
            )
        if len(swm_mux_resolved[pip_dst]) > 1:
            logger.warning(
                f"Multiple resolved pins found for PIP destination {pip_dst} "
                f"in switch matrix mux instance {swm_mux_for_pips[0].path}. "
                f"Using the first one: {swm_mux_resolved[pip_dst][0]}"
            )

        logger.info(f"Calculating structural delay from {pip_src} to {pip_dst}")

        # Calculate delay between pip_src and pip_dst using the
        # synthesis-level timing model.
        delay = single_delay(
            synth_model.timing_graph,
            swm_mux_resolved[pip_src][0],
            swm_mux_resolved[pip_dst][0],
            synth_model.delay_type_str,
        )

        logger.info(f"Delay from {pip_src} to {pip_dst}: {delay} ns.")

        # Begin ports of the swm mux are unique so we can use pip_dst as
        # the key for caching.
        self.internal_pip_cache[pip_dst] = InternalPipCacheEntry(
            swm_mux_for_pips=swm_mux_for_pips,
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved=swm_mux_resolved,
        )

        return delay

    def internal_pip_delay_physical(self, pip_src: str, pip_dst: str) -> float:
        """Calculate delay between two PIPs using physical design information.

        This method uses the physical-level timing model to provide more
        accurate delay estimates by considering the actual physical implementation.

        Synthesis-level resolution (extract the realted module ports that are
        connected to the SMW mux to which the PIP belongs)

        Physical-level resolution map the synthesis-level top-level ports that
        are related to the swm mux to physical-level swm mux pins to find the sm mux
        output pin (Then we can calc the delay between pip_src and pip_dst). To
        find the swm mux output we will use a method that we call earliest node
        convergence. That means for MUX the topology we know that all inputs
        converge to the output pin (mostly), so we can find the earliest common
        node from all the input ports found above. Similar to graph betweenness
        centrality subset, but here we want to find the node that minimizes the maximum
        distance from all the input ports.

        Parameters
        ----------
        pip_src : str
            Source PIP port name (e.g., "LB_O").
        pip_dst : str
            Destination PIP port name (e.g., "JN2BEG3").

        Returns
        -------
        float
            Delay in nanoseconds between the two PIPs.
        """
        logger.info(
            f"Timing extraction for tile: {self.tile_name}, PIP: {pip_src} -> {pip_dst}"
        )

        synth_model: NetlistTimingModel = self.netlist_tm_synth
        phys_model: NetlistTimingModel = self.netlist_tm_phys
        pip_cache: InternalPipCacheEntry | None = self.internal_pip_cache.get(pip_dst)

        # Reference output ports for convergence checks.
        ref_output_port: str | None = None
        swm_nearest_ports_out: tuple[dict[str, list[str]], list[str]] | None = None

        # Skip algorithms if we have a cache hit for the internal PIP, which means
        # we have already resolved the switch matrix mux for a BEG pin.
        if pip_cache is not None:
            logger.info(
                f"Cache hit for internal PIP {pip_src} -> {pip_dst}. "
                f"Using cached physical-level information."
            )

        # ----------------------------#
        # Synthesis-level resolution #
        # ----------------------------#

        logger.info(
            f"Finding synthesis-level switch matrix mux for PIPs {pip_src} -> {pip_dst}"
        )

        # Algorithm_1: Are pip_src and pip_dst connected through the same
        # switch matrix multiplexer?
        swm_mux_for_pips = self._resolve_swm_mux(pip_src, pip_dst, pip_cache)

        logger.info(
            "Finding synthesis-level top-level ports connected "
            "to the switch matrix mux nets..."
        )

        # Algorithm_2: Find the nearest top level ports connected to all the nets
        # of the swm mux input pins. We reverse the timing graph to find the
        # input ports (towards inputs). Good default value is 4. Fastest is 1.
        swm_nearest_ports_in = (
            synth_model.nearest_ports_from_instance_pin_nets(
                swm_mux_for_pips[0], reverse=True, num_ports=1
            )
            if pip_cache is None
            else pip_cache.swm_nearest_ports_in
        )

        swm_nearest_in_ports_for_each_swm_wire = swm_nearest_ports_in[0]
        swm_nearest_in_ports_all = swm_nearest_ports_in[1]
        swm_in_buf = len(swm_nearest_in_ports_all) == 1

        # Algorithm_3: Convergence nodes must have a path to the output port of
        # the sw mux. So we will use the output port as a sentinel to find the
        # convergence node.
        if swm_in_buf:
            swm_nearest_ports_out = (
                synth_model.nearest_ports_from_instance_pin_nets(
                    swm_mux_for_pips[0], reverse=False, num_ports=1
                )
                if pip_cache is None
                else pip_cache.swm_nearest_ports_out
            )

            ref_output_port: str = swm_nearest_ports_out[0][f"{pip_dst}"][0]
            logger.info("Single input Switch Matrix Mux detected.")

        # ---------------------------#
        # Physical-level resolution #
        # ---------------------------#

        logger.info("Starting physical extraction of the switch matrix mux for pips")

        # Algorithm_4: Find the converging node (the output pin of the swm mux).
        # Only the convergence-node list is reused downstream, so the best cost and
        # per-source distance map that earliest_common_nodes also returns are dropped.
        swm_output_pin = (
            earliest_common_nodes(
                phys_model.graph,
                sources=swm_nearest_in_ports_all,
                mode="max",
                sentinel=ref_output_port,
                prefer_sentinel_for_single_source=True,
                follow_steps_to_sentinel=3,
            )[0]
            if pip_cache is None
            else pip_cache.swm_output_pin
        )

        swm_phys_output: str = swm_output_pin[0]

        # ------------------------------------------------------------#
        # Calculate the delay between the two PIPs at physical level #
        # ------------------------------------------------------------#

        logger.info(f"Calculating physical delay from {pip_src} to {pip_dst}")

        # Algorithm_5: Calculate delay between pip_src and the converged output pin
        # We use the 0st nearest port found for pip_src beacuse the list is sorted
        # starting from the nearest port.
        delay = single_delay(
            phys_model.timing_graph,
            swm_nearest_in_ports_for_each_swm_wire[f"{pip_src}"][0],
            swm_phys_output,
            phys_model.delay_type_str,
        )

        logger.info(f"Physical Delay from {pip_src} to {pip_dst}: {delay} ns.")

        # Begin ports of the swm mux are unique so we can use pip_dst as the
        # key for caching.
        self.internal_pip_cache[pip_dst] = InternalPipCacheEntry(
            swm_mux_for_pips=swm_mux_for_pips,
            swm_nearest_ports_in=swm_nearest_ports_in,
            swm_nearest_ports_out=swm_nearest_ports_out,
            swm_output_pin=swm_output_pin,
            swm_mux_resolved=None,
        )

        return delay

    def external_pip_delay(self, pip_src: str, pip_dst: str) -> float:
        """Calculate delay for external PIPs between the tile and the next tile.

        It is Tile to Tile, Tile port to SWM, SWM to SWM, SWM output to tile port.
        The physical-level model is used in PHYSICAL mode and the synthesis-level
        model otherwise; for tile interconnects a stitched connection with a fixed
        small delay is assumed.

        Parameters
        ----------
        pip_src : str
            Source PIP port name.
        pip_dst : str
            Destination PIP port name.

        Returns
        -------
        float
            Estimated delay in nanoseconds for the external PIP.
        """
        logger.info(
            f"Timing extraction for tile: {self.tile_name}, PIP: {pip_src} -> {pip_dst}"
        )
        logger.info(f"Calculating delay for external PIP from {pip_src} to {pip_dst}")

        physical = self.mode == TimingModelMode.PHYSICAL
        model = self.netlist_tm_phys if physical else self.netlist_tm_synth

        # In general try to avoid delay of 0.
        default_delay: float = 0.001

        # Must do for ports with indices, e.g., NN2BEG3 -> NN2BEG[3]
        pip_src_port = re.sub(r"^(.*?)(\d+)$", r"\1[\2]", pip_src)
        pip_dst_port = re.sub(r"^(.*?)(\d+)$", r"\1[\2]", pip_dst)

        # Tile interconnects, stitched fixed delay almost 0.
        if pip_src_port in model.netlist.output_ports:
            logger.info(
                f"Tile output {pip_src_port} to next tile input {pip_dst_port} "
                f"stitched delay: {default_delay} ns"
            )
            return default_delay

        # Tile input to nearest output (twist to the next tile input)
        if pip_src_port in model.netlist.input_ports:
            _, out_port = path_to_nearest_target_sentinel(
                model.graph, pip_src_port, model.netlist.output_ports
            )

            logger.info(f"Port twist detected for {pip_src_port} to {pip_dst_port}:")

            if out_port is None:
                logger.warning(
                    f"No nearest port found for tile input {pip_src_port}. "
                    f"Using default delay {default_delay} ns"
                )
                return default_delay

            delay = single_delay(
                model.timing_graph,
                pip_src_port,
                out_port,
                model.delay_type_str,
            )
            logger.info(
                f"Delay from tile input {pip_src_port} to tile output "
                f"{out_port}--{pip_dst_port}: {delay} ns."
            )

            return delay

        # SWM output to the next SWM input
        pip_cache: InternalPipCacheEntry | None = self.internal_pip_cache.get(pip_src)

        if pip_cache is None:
            logger.info(
                f"SWM output {pip_src} to next SWM input {pip_dst} directly "
                f"connected delay: {default_delay} ns"
            )
            return default_delay

        # Follow the wire to the next swm input pin, also to maybe catch a buffer in
        # between. The physical path reuses the converged mux output node; the
        # structural path reuses the resolved mux output pin for pip_src.
        swm_output_pin: str = (
            pip_cache.swm_output_pin[0]
            if physical
            else pip_cache.swm_mux_resolved[pip_src][0]
        )
        swm_next_input_pin: str = follow_first_fanout_from_pins(
            model.graph, hier_pin_path=swm_output_pin, num_follow=2
        )

        delay = single_delay(
            model.timing_graph,
            swm_output_pin,
            swm_next_input_pin,
            model.delay_type_str,
        )
        logger.info(
            f"SWM output {pip_src} to next SWM input {pip_dst} with delay: {delay} ns"
        )

        if delay < 1e-5:
            return default_delay

        return delay

    def internal_pip_delay(self, pip_src: str, pip_dst: str) -> float:
        """Choose the method to calculate internal PIP delay based on the mode.

        (physical or structural).

        Parameters
        ----------
        pip_src : str
            Source PIP port name.
        pip_dst : str
            Destination PIP port name.

        Returns
        -------
        float
            Calculated delay in nanoseconds for the internal PIP.
        """
        if self.mode == TimingModelMode.PHYSICAL:
            return self.internal_pip_delay_physical(pip_src, pip_dst)
        return self.internal_pip_delay_structural(pip_src, pip_dst)

    def pip_delay(self, pip_src: str, pip_dst: str) -> float:
        """Calculate the delay for a PIP, choosing between internal and external.

        Parameters
        ----------
        pip_src : str
            Source PIP port name.
        pip_dst : str
            Destination PIP port name.

        Returns
        -------
        float
            Calculated delay in nanoseconds for the PIP.
        """
        d_scale: float = self.delay_scaling_factor

        if self.is_tile_internal_pip(pip_src, pip_dst):
            return round(self.internal_pip_delay(pip_src, pip_dst) * d_scale, 3)
        return round(self.external_pip_delay(pip_src, pip_dst) * d_scale, 3)
