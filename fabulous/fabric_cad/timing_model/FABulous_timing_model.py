"""Defines the FABulousTileTimingModel class.

It is responsible for extracting timing information for a specific tile in the FABulous
project.

It reads the project files, initializes synthesis-level and physical-level timing models
using the HdlnxTimingModel class, and provides methods to calculate delays for internal
and external PIPs (Programmable Interconnect Points) using either structural or physical
approaches.
"""

import re
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.timing_model.hdlnx.hdlnx_timing_model import HdlnxTimingModel
from fabulous.fabric_cad.timing_model.models import (
    InternalPipCacheEntry,
    TimingModelConfig,
    TimingModelMode,
    TimingModelStaTools,
    TimingModelSynthTools,
)
from fabulous.fabric_cad.timing_model.tools.specification import StaTool, SynthTool
from fabulous.fabric_cad.timing_model.tools.sta_tools.opensta import OpenStaTool
from fabulous.fabric_cad.timing_model.tools.synth_tools.yosys import YosysTool
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile


class FABulousTileTimingModel:
    """Reads the FABulous project files and extracts timing information.

    Initializes the FABulousTileTimingModel with the given configuration and
    fabric definition. The configuration object must match the TimingModelConfig
    schema defined in the models module.

    - It initializes both synthesis-level and physical-level timing models
      using the HdlnxTimingModel class.
    - It provides methods to calculate delays for internal PIPs
      (within the switch matrix) and external PIPs (between the tile and the
      next tile) using either structural or physical approaches.

    Supported synthesis tools:
    - Yosys, keyword: "yosys"

    Supported static timing analysis (STA) tools:
    - OpenSTA, keyword: "opensta"

    Parameters
    ----------
    config : TimingModelConfig
        Configuration object for the timing model.
    fabric : Fabric
        The FABulous fabric object.
    tile_name : str | None
        The name of the tile for which the timing model is being created.
    """

    def __init__(
        self, config: TimingModelConfig, fabric: Fabric, tile_name: str | None = None
    ) -> None:
        self.fabric: Fabric = fabric
        self.tile_name: str | None = tile_name

        # Validate and parse the configuration using the
        # TimingModelConfig dataclass.

        self.tm_config: TimingModelConfig = config

        # Determine if the tile is part of a SuperTile and set
        # the unique_tile_name accordingly.

        self.is_in_which_super_tile: str | None = None
        self.unique_tile_name: str = self.tile_name
        self._get_unique_tile_name()

        # Verilog files for the tile.

        self.verilog_files: list[Path] = None

        # Init:

        self.hdlnx_tm_synth: HdlnxTimingModel | None = None
        self.hdlnx_tm_phys: HdlnxTimingModel | None = None
        self._initialize_timing_models()

        # Extract switch matrix information
        # Check super_tile_type in config to filter the correct switch matrix

        self.switch_matrix_hier_path: list[str] | None = None
        self.switch_matrix_module_name: list[str] | None = None
        self.internal_pips_grouped_by_inst: dict[str, list[str]] | None = None
        self.internal_pips: list[str] | None = None
        self._extract_switch_matrix_info()

        self.internal_pip_cache: dict[str, InternalPipCacheEntry] = {}

        logger.info("FABulous Timing Model initialized.")

    def _get_project_rtl_files(self) -> None:
        """Find all the Verilog files for the tile in the project directory.

        Exclude certain directories that are not relevant for synthesis. If custom
        source files are specified in the configuration for this tile, use those
        instead.
        """
        exclude_dir_patterns: list[str] = ["macro", "user_design", "Test"]
        self.verilog_files: list[Path] = self._find_matching_files(
            self.tm_config.project_dir, r".*\.v$", exclude_dir_patterns
        )

        # Optionally override the default project Verilog files with custom ones
        # specified for this tile. Only simple wildcard patterns are supported,
        # e.g. "TileA/*.v" to include all Verilog files in the TileA directory.
        if (
            self.tm_config.custom_per_tile_source_files is not None
            and self.unique_tile_name in self.tm_config.custom_per_tile_source_files
            and (
                rtl := self.tm_config.custom_per_tile_source_files[
                    self.unique_tile_name
                ].rtl_files
            )
        ):
            targets = rtl if isinstance(rtl, list) else [rtl]
            result: list[Path] = []

            for p in targets:
                if "*" in p.name:
                    result.extend(p.parent.rglob(p.name))
                    continue
                result.append(p)

            self.verilog_files = result

            logger.info(
                f"Using RTL Verilog files for tile {self.unique_tile_name}:"
                f"{'\n  '.join(map(str, [''] + self.verilog_files))}"
            )

    def _get_unique_tile_name(self) -> None:
        """Determine if the tile is part of a SuperTile.

        Sets the unique_tile_name accordingly.
        - If the tile is found within a SuperTile, set unique_tile_name to the name of
          that SuperTile and is_in_which_super_tile to the same name.
        - If the tile is not found within any SuperTile, unique_tile_name remains as
          the original tile name and is_in_which_super_tile remains None.
        - This is necessary because the timing model needs to use the unique tile name
          (which is the SuperTile name if the tile is part of a SuperTile) to find
          the correct Verilog files and switch matrix information for the tile.
          The original tile name is used for other purposes within the timing model.
        """
        for unique_tiles in self.fabric.get_all_unique_tiles():
            if isinstance(unique_tiles, SuperTile):
                for composed_tile in unique_tiles.tiles:
                    if composed_tile.name == self.tile_name:
                        self.is_in_which_super_tile = unique_tiles.name
                        self.unique_tile_name = unique_tiles.name
                        break

    def _cad_tools(self) -> dict[str, SynthTool | StaTool]:
        """Set up the synthesis and STA tools based on the configuration.

        This method can be used to initialize the tools before creating
        the timing models. New tools can be added here by extending the
        match-case statements for synthesis and STA
        tools.

        Returns
        -------
        dict[str, SynthTool | StaTool]
            A dictionary containing the synthesis and STA tools.

        Raises
        ------
        ValueError
            If the synthesis or STA tool specified in the
            configuration is not supported.
        """
        synth_tool: SynthTool | None = None
        sta_tool: StaTool | None = None

        # Use match-case to select the synthesis and STA tools based on the
        # configuration.

        match self.tm_config.synth_program:
            case TimingModelSynthTools.YOSYS:
                synth_tool = YosysTool(
                    verilog_files=self.verilog_files,
                    liberty_files=self.tm_config.liberty_files,
                    top_name=self.unique_tile_name,
                    synth_executable=self.tm_config.synth_executable,
                    techmap_files=self.tm_config.techmap_files,
                    tiehi_cell_and_port=self.tm_config.tiehi_cell_and_port,
                    tielo_cell_and_port=self.tm_config.tielo_cell_and_port,
                    min_buf_cell_and_ports=self.tm_config.min_buf_cell_and_ports,
                    is_gate_level=False,
                    debug=self.tm_config.debug,
                    flat=False,
                )
            case _:
                raise ValueError(
                    f"Unsupported synthesis tool: {self.tm_config.synth_program}"
                )

        # Use match-case to select the STA tool based on the configuration.

        match self.tm_config.sta_program:
            case TimingModelStaTools.OPENSTA:
                sta_tool = OpenStaTool(
                    sta_executable=self.tm_config.sta_executable,
                    spef_files=None,
                    debug=self.tm_config.debug,
                )
            case _:
                raise ValueError(f"Unsupported STA tool: {self.tm_config.sta_program}")

        # Return the initialized tools in a dictionary for use in the timing
        # model initialization.

        return {"synth_tool": synth_tool, "sta_tool": sta_tool}

    def _initialize_timing_models(self) -> None:
        """Initialize the synthesis and physical timing models using HdlnxTimingModel.

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

        # Get the Verilog files for the project.
        self._get_project_rtl_files()

        # Initialize the synthesis and STA tools based on the configuration.
        cad_tool = self._cad_tools()
        synth_tool: SynthTool = cad_tool["synth_tool"]
        sta_tool: StaTool = cad_tool["sta_tool"]

        # Initialize the synthesis-level timing model.
        self.hdlnx_tm_synth = HdlnxTimingModel(
            sta_tool, synth_tool, self.tm_config.delay_type_str, self.tm_config.debug
        )

        # If the mode is STRUCTURAL, we only need the synthesis-level model and can skip
        # initializing the physical-level model.
        if self.tm_config.mode == TimingModelMode.STRUCTURAL:
            logger.info(
                "Mode is STRUCTURAL, skipping physical-level model initialization."
            )
            return

        # For the physical-level model, we need to switch to the gate-level netlist.
        logger.info("Initializing Physical-level timing model...")

        # For the physical-level model, we need to switch to the gate-level netlist.
        synth_tool.synth_rtl_files = Path(
            f"{self.tm_config.project_dir}/Tile/{self.unique_tile_name}"
            f"/macro/final_views/nl/{self.unique_tile_name}.nl.v"
        )

        # Optionally override the default netlist file with a custom one for this tile.
        if (
            self.tm_config.custom_per_tile_source_files is not None
            and self.unique_tile_name in self.tm_config.custom_per_tile_source_files
            and (
                netl := self.tm_config.custom_per_tile_source_files[
                    self.unique_tile_name
                ].netlist_file
            )
        ):
            synth_tool.synth_rtl_files = netl
            logger.info(
                f"Using netlist file for tile {self.unique_tile_name}: "
                f"{synth_tool.synth_rtl_files}"
            )

        # Disable synthesis for the physical-level model since we already
        # have the gate-level netlist.
        synth_tool.synth_passthrough = True

        # Optionally load RC files for wire delay if consider_wire_delay
        # is True in the configuration.
        if self.tm_config.consider_wire_delay:
            sta_tool.sta_rc_files = Path(
                f"{self.tm_config.project_dir}/Tile/{self.unique_tile_name}"
                f"/macro/final_views/spef/nom/{self.unique_tile_name}.nom.spef"
            )

            # Optionally override the default RC file with a custom one for this tile.
            if (
                self.tm_config.custom_per_tile_source_files is not None
                and self.unique_tile_name in self.tm_config.custom_per_tile_source_files
                and (
                    rc := self.tm_config.custom_per_tile_source_files[
                        self.unique_tile_name
                    ].rc_file
                )
            ):
                sta_tool.sta_rc_files = rc
                logger.info(
                    f"Use RC file for {self.unique_tile_name}: {sta_tool.sta_rc_files}"
                )

        # Initialize the physical-level timing model with the gate-level netlist.
        self.hdlnx_tm_phys = HdlnxTimingModel(
            sta_tool, synth_tool, self.tm_config.delay_type_str, self.tm_config.debug
        )

    def _find_matching_files(
        self,
        root_dir: Path,
        file_pattern: str,
        exclude_dir_patterns: list[str] | None = None,
        exclude_file_patterns: list[str] | None = None,
    ) -> list[Path]:
        """Recursively traverse root_dir and return a list of Path objects.

        for all files whose *name* matches file_pattern (regex).
        - exclude_dir_patterns: list of regex patterns; directory names
          matching any of these will be skipped completely.
        - exclude_file_patterns: list of regex patterns; file names
          matching any of these will be skipped.

        Parameters
        ----------
        root_dir : Path
            Root directory to start the search.
        file_pattern : str
            Regex pattern to match file names.
        exclude_dir_patterns : list[str] | None
            List of regex patterns to exclude directories.
        exclude_file_patterns : list[str] | None
            List of regex patterns to exclude files.

        Returns
        -------
        list[Path]
            List of Path objects for matched files.

        Raises
        ------
        TypeError
            If root_dir is not a Path object.
        """
        if not isinstance(root_dir, Path):
            raise TypeError("root_dir must be a Path object.")

        file_re = re.compile(file_pattern)
        exclude_dir_res = [re.compile(p) for p in (exclude_dir_patterns or [])]
        exclude_file_res = [re.compile(p) for p in (exclude_file_patterns or [])]
        matched_files: list[Path] = []

        for dirpath, dirnames, filenames in root_dir.walk():
            dirnames[:] = [
                d for d in dirnames if not any(r.search(d) for r in exclude_dir_res)
            ]

            for fname in filenames:
                if any(r.search(fname) for r in exclude_file_res):
                    continue
                if file_re.search(fname):
                    matched_files.append(dirpath / fname)

        return matched_files

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

        self.switch_matrix_hier_path = self.hdlnx_tm_synth.find_instance_paths_by_regex(
            r".*_switch_matrix$"
        )

        self.switch_matrix_module_name = self.hdlnx_tm_synth.find_verilog_modules_regex(
            r"^[^/]*_switch_matrix$"
        )

        if (
            len(self.switch_matrix_hier_path) == 0
            or len(self.switch_matrix_module_name) == 0
        ):
            logger.warning(
                f"No switch matrix instance or module found. "
                f"All PIPs for {self.tile_name} will be considered external."
            )
            return

        if self.is_in_which_super_tile is None:
            if (
                len(self.switch_matrix_hier_path) > 1
                or len(self.switch_matrix_module_name) > 1
            ):
                raise ValueError(
                    "Multiple switch matrix instances or modules found "
                    "for a non-SuperTile."
                )

            self.switch_matrix_hier_path = self.switch_matrix_hier_path[0]
            self.switch_matrix_module_name = self.switch_matrix_module_name[0]

            logger.info(
                f"Using switch matrix instance: {self.switch_matrix_hier_path}, "
                f"module: {self.switch_matrix_module_name}"
            )

        else:
            self.switch_matrix_hier_path = [
                p for p in self.switch_matrix_hier_path if self.tile_name in p
            ]

            self.switch_matrix_module_name = [
                m for m in self.switch_matrix_module_name if self.tile_name in m
            ]

            if (
                len(self.switch_matrix_hier_path) == 0
                or len(self.switch_matrix_module_name) == 0
            ):
                raise ValueError(
                    f"No switch matrix instance or module found for SuperTile "
                    f"{self.unique_tile_name}"
                )

            if (
                len(self.switch_matrix_hier_path) > 1
                or len(self.switch_matrix_module_name) > 1
            ):
                raise ValueError(
                    f"Multiple switch matrix instances or modules found Tile "
                    f"{self.tile_name} in SuperTile {self.unique_tile_name}."
                )

            self.switch_matrix_hier_path = self.switch_matrix_hier_path[0]
            self.switch_matrix_module_name = self.switch_matrix_module_name[0]

            logger.info(
                f"Tile {self.tile_name} is part of super tile {self.unique_tile_name}."
            )

        logger.info("Loading internal PIPs...")

        self.internal_pips_grouped_by_inst = (
            self.hdlnx_tm_synth.get_module_instance_nets(self.switch_matrix_module_name)
        )

        self.internal_pips = self.hdlnx_tm_synth.get_instance_pins(
            self.switch_matrix_hier_path
        )

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

        synth_model = self.hdlnx_tm_synth

        pip_cache: InternalPipCacheEntry = self.internal_pip_cache.get(pip_dst, None)

        if pip_cache is not None:
            logger.info(
                f"Cache hit for internal PIP {pip_src} -> {pip_dst}. "
                f"Using cached synthesis-level information."
            )

        logger.info(
            f"Finding synthesis-level switch matrix mux for PIPs {pip_src} -> {pip_dst}"
        )

        # Are pip_src and pip_dst connected through the same switch matrix multiplexer?
        swm_mux_for_pips = (
            synth_model.find_instances_paths_with_all_nets(
                self.switch_matrix_module_name,
                [pip_src, pip_dst],
                filter_regex=self.switch_matrix_hier_path,
            )
            if pip_cache is None
            else pip_cache.swm_mux_for_pips
        )

        if len(swm_mux_for_pips) > 1:
            logger.warning(
                f"Multiple switch matrix mux instances found "
                f"for PIPs {pip_src} -> {pip_dst}. "
                f"Using the first one: {swm_mux_for_pips[0]}"
            )

        logger.info(f"  Found switch matrix mux instance: {swm_mux_for_pips[0]}")

        # Get the resolved pins for the switch matrix mux instance.
        swm_mux_resolved = (
            synth_model.net_to_pin_paths_for_instance_resolved(swm_mux_for_pips[0])
            if pip_cache is None
            else pip_cache.swm_mux_resolved
        )

        logger.info("Switch matrix mux resolved pins for src and dst:")
        logger.info(f"  {pip_src}: {swm_mux_resolved[pip_src]}")
        logger.info(f"  {pip_dst}: {swm_mux_resolved[pip_dst]}")

        if len(swm_mux_resolved[pip_src]) > 1:
            logger.warning(
                f"Multiple resolved pins found for PIP source {pip_src} "
                f"in switch matrix mux instance {swm_mux_for_pips[0]}. "
                f"Using the first one: {swm_mux_resolved[pip_src][0]}"
            )
        if len(swm_mux_resolved[pip_dst]) > 1:
            logger.warning(
                f"Multiple resolved pins found for PIP destination {pip_dst} "
                f"in switch matrix mux instance {swm_mux_for_pips[0]}. "
                f"Using the first one: {swm_mux_resolved[pip_dst][0]}"
            )

        logger.info(f"Calculating structural delay from {pip_src} to {pip_dst}")

        # Calculate delay between pip_src and pip_dst using the
        # synthesis-level timing model.
        delay = synth_model.single_delay(
            swm_mux_resolved[pip_src][0], swm_mux_resolved[pip_dst][0]
        )

        logger.info(f"Delay from {pip_src} to {pip_dst}: {delay} ns.")

        # Begin ports of the swm mux are unique so we can use pip_dst as
        # the key for caching.
        self.internal_pip_cache[pip_dst] = InternalPipCacheEntry(
            begin_pip=pip_dst,
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

        synth_model: HdlnxTimingModel = self.hdlnx_tm_synth
        phys_model: HdlnxTimingModel = self.hdlnx_tm_phys
        pip_cache: InternalPipCacheEntry = self.internal_pip_cache.get(pip_dst, None)

        # Reference output ports for convergence checks.
        ref_output_port: str = None
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
        swm_mux_for_pips: list[str] = (
            synth_model.find_instances_paths_with_all_nets(
                self.switch_matrix_module_name,
                [pip_src, pip_dst],
                filter_regex=self.switch_matrix_hier_path,
            )
            if pip_cache is None
            else pip_cache.swm_mux_for_pips
        )

        if len(swm_mux_for_pips) > 1:
            logger.warning(
                f"Multiple swm mux instances found for PIPs {pip_src} -> {pip_dst}. "
                f"Using the first one: {swm_mux_for_pips[0]}"
            )

        logger.info(f"  Found switch matrix mux instance: {swm_mux_for_pips[0]}")
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

        # Algorithm_4: Find the converging node (the output pin of the swm mux)
        best_nodes, best_cost, dists = (
            phys_model.earliest_common_nodes(
                sources=swm_nearest_in_ports_all,
                mode="max",
                sentinel=ref_output_port,
                prefer_sentinel_for_single_source=True,
                follow_steps_to_sentinel=3,
            )
            if pip_cache is None
            else pip_cache.swm_output_pin
        )

        swm_phys_output: str = best_nodes[0]

        # ------------------------------------------------------------#
        # Calculate the delay between the two PIPs at physical level #
        # ------------------------------------------------------------#

        logger.info(f"Calculating physical delay from {pip_src} to {pip_dst}")

        # Algorithm_5: Calculate delay between pip_src and the converged output pin
        # We use the 0st nearest port found for pip_src beacuse the list is sorted
        # starting from the nearest port.
        delay = phys_model.single_delay(
            swm_nearest_in_ports_for_each_swm_wire[f"{pip_src}"][0], swm_phys_output
        )

        logger.info(f"Physical Delay from {pip_src} to {pip_dst}: {delay} ns.")

        # Begin ports of the swm mux are unique so we can use pip_dst as the
        # key for caching.
        self.internal_pip_cache[pip_dst] = InternalPipCacheEntry(
            begin_pip=pip_dst,
            swm_mux_for_pips=swm_mux_for_pips,
            swm_nearest_ports_in=swm_nearest_ports_in,
            swm_nearest_ports_out=swm_nearest_ports_out,
            swm_output_pin=(best_nodes, best_cost, dists),
            swm_mux_resolved=None,
        )

        return delay

    def external_pip_delay_structural(self, pip_src: str, pip_dst: str) -> float:
        """Calculate delay for external PIPs between the tile and the next tile.

        Structural approach. It is Tile to Tile, Tile port to SWM, SWM to SWM, SWM
        output to tile port.

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

        logger.info(
            f"Calculating structural delay for external PIP from {pip_src} to {pip_dst}"
        )

        synth_model = self.hdlnx_tm_synth

        # In general try to avoid delay of 0.
        default_delay: float = 0.001

        # Must do for ports with indices, e.g., NN2BEG3 -> NN2BEG[3]
        pip_src_port = re.sub(r"^(.*?)(\d+)$", r"\1[\2]", pip_src)
        pip_dst_port = re.sub(r"^(.*?)(\d+)$", r"\1[\2]", pip_dst)

        # Tile interconnects, stitched fixed delay almost 0.
        if pip_src_port in synth_model.output_ports:
            logger.info(
                f"Tile output {pip_src_port} to next tile input {pip_dst_port} "
                f"stitched delay: {default_delay} ns"
            )
            return default_delay

        # Tile input to nearest output (twist to the next tile input)
        if pip_src_port in synth_model.input_ports:
            out_port_list, out_port = synth_model.path_to_nearest_target_sentinel(
                pip_src_port, synth_model.output_ports
            )

            logger.info(f"Port twist detected for {pip_src_port} to {pip_dst_port}:")

            if out_port is None:
                logger.warning(
                    f"No nearest port found for tile input {pip_src_port}. "
                    f"Using default delay {default_delay} ns"
                )
                return default_delay

            delay = synth_model.single_delay(pip_src_port, out_port)
            logger.info(
                f"Delay from tile input {pip_src_port} to tile output "
                f"{out_port}--{pip_dst_port}: {delay} ns."
            )

            return delay

        # SWM output to the next SWM input
        pip_cache: InternalPipCacheEntry = self.internal_pip_cache.get(pip_src, None)

        if pip_cache is None:
            logger.info(
                f"SWMy output {pip_src} to next SWMy input {pip_dst} directly "
                f"connected delay: {default_delay} ns"
            )
            return default_delay

        # We just follow the wire to next swm input pin, also to maybe catch
        # a buffer in between.
        swm_output_pin: str = pip_cache.swm_mux_resolved[pip_src][0]
        swm_next_input_pin: str = synth_model.follow_first_fanout_from_pins(
            hier_pin_path=swm_output_pin, num_follow=2
        )

        delay = synth_model.single_delay(swm_output_pin, swm_next_input_pin)
        logger.info(
            f"SWMx output {pip_src} to next SWMx input {pip_dst} with delay: {delay} ns"
        )

        if delay < 1e-5:
            return default_delay

        return delay

    def external_pip_delay_physical(self, pip_src: str, pip_dst: str) -> float:
        """Calculate delay for external PIPs between the tile and the next tile.

        Physical approach. It is Tile to Tile, Tile port to SWM, SWM to SWM, SWM output
        to tile port. This method uses the physical-level timing model to provide more
        accurate delay estimates by considering the actual physical implementation. For
        tile interconnects, we assume a stitched connection with a fixed small delay.

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

        logger.info(
            f"Calculating physical delay for external PIP from {pip_src} to {pip_dst}"
        )

        phys_model = self.hdlnx_tm_phys

        default_delay: float = 0.001

        # Must do for ports with indices, e.g., NN2BEG3 -> NN2BEG[3]
        pip_src_port = re.sub(r"^(.*?)(\d+)$", r"\1[\2]", pip_src)
        pip_dst_port = re.sub(r"^(.*?)(\d+)$", r"\1[\2]", pip_dst)

        # Tile interconnects, stitched fixed delay almost 0.
        if pip_src_port in phys_model.output_ports:
            logger.info(
                f"Tile output {pip_src_port} to next tile input {pip_dst_port} "
                f"stitched delay: {default_delay} ns"
            )
            return default_delay

        # Tile input to nearest output (twist to the next tile input)
        if pip_src_port in phys_model.input_ports:
            out_port_list, out_port = phys_model.path_to_nearest_target_sentinel(
                pip_src_port, phys_model.output_ports
            )

            logger.info(f"Port twist detected for {pip_src_port} to {pip_dst_port}:")

            if out_port is None:
                logger.warning(
                    f"No nearest port found for tile input {pip_src_port}. "
                    f"Using default delay {default_delay} ns"
                )
                return default_delay

            delay = phys_model.single_delay(pip_src_port, out_port)
            logger.info(
                f"Delay from tile input {pip_src_port} to tile output "
                f"{out_port}--{pip_dst_port}: {delay} ns."
            )

            return delay

        # SWM output to the next SWM input
        pip_cache: InternalPipCacheEntry = self.internal_pip_cache.get(pip_src, None)

        if pip_cache is None:
            logger.info(
                f"SWMy output {pip_src} to next SWMy input {pip_dst} directly "
                f"connected delay: {default_delay} ns"
            )
            return default_delay

        # We just follow the wire to next swm input pin, also to maybe catch
        # a buffer in between.
        swm_output_pin: str = pip_cache.swm_output_pin[0][0]
        swm_next_input_pin: str = phys_model.follow_first_fanout_from_pins(
            hier_pin_path=swm_output_pin, num_follow=2
        )

        delay = phys_model.single_delay(swm_output_pin, swm_next_input_pin)
        logger.info(
            f"SWMx output {pip_src} to next SWMx input {pip_dst} with delay: {delay} ns"
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
        if self.tm_config.mode == TimingModelMode.PHYSICAL:
            return self.internal_pip_delay_physical(pip_src, pip_dst)
        return self.internal_pip_delay_structural(pip_src, pip_dst)

    def external_pip_delay(self, pip_src: str, pip_dst: str) -> float:
        """Choose the method to calculate external PIP delay based on the mode.

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
            Calculated delay in nanoseconds for the external PIP.
        """
        if self.tm_config.mode == TimingModelMode.PHYSICAL:
            return self.external_pip_delay_physical(pip_src, pip_dst)
        return self.external_pip_delay_structural(pip_src, pip_dst)

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
        d_scale: float = self.tm_config.delay_scaling_factor

        def _round(x: float) -> float:
            return round(x * d_scale, 3)

        if self.is_tile_internal_pip(pip_src, pip_dst):
            return _round(self.internal_pip_delay(pip_src, pip_dst))
        return _round(self.external_pip_delay(pip_src, pip_dst))
