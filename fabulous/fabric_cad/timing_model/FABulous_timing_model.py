"""Defines the FABulousTileTimingModel class.

It is responsible for extracting timing information for a specific tile in the FABulous
project.

It reads the project files, initializes synthesis-level and physical-level timing models
using the HdlnxTimingModel class, and provides methods to calculate delays for internal
and external PIPs (Programmable Interconnect Points) using either structural or physical
approaches.
"""

import re
from copy import copy
from decimal import Decimal
from pathlib import Path

import networkx as nx
from loguru import logger

from fabulous.fabric_cad.timing_db import (
    BelArcs,
    BelPin,
    ClockArc,
    ClockToOutArc,
    Condition,
    DelayArc,
    FeatureIs,
    Ns,
    SetupHoldArc,
)
from fabulous.fabric_cad.timing_model.hdlnx.hdlnx_timing_model import HdlnxTimingModel
from fabulous.fabric_cad.timing_model.models import (
    InternalPipCacheEntry,
    TimingModelConfig,
    TimingModelMode,
    TimingModelStaTools,
    TimingModelSynthTools,
)
from fabulous.fabric_cad.timing_model.netlist import (
    HierPath,
    NetlistIndex,
    PortBit,
    sdf_path,
)
from fabulous.fabric_cad.timing_model.tools.specification import StaTool, SynthTool
from fabulous.fabric_cad.timing_model.tools.sta_tools.opensta import OpenStaTool
from fabulous.fabric_cad.timing_model.tools.synth_tools.yosys import YosysTool
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
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
    tile_name : str
        The name of the tile for which the timing model is being created.
    """

    def __init__(
        self, config: TimingModelConfig, fabric: Fabric, tile_name: str
    ) -> None:
        self.fabric: Fabric = fabric
        self.tile_name: str = tile_name

        # Validate and parse the configuration using the
        # TimingModelConfig dataclass.

        self.tm_config: TimingModelConfig = config

        # Determine if the tile is part of a SuperTile and set
        # the unique_tile_name accordingly.

        self.is_in_which_super_tile: str | None = None
        self.unique_tile_name: str = self.tile_name
        self.tile_scope: HierPath = ()
        self._get_unique_tile_name()

        # Verilog files for the tile.

        self.verilog_files: list[Path] = None

        # Init:

        self.hdlnx_tm_synth: HdlnxTimingModel | None = None
        self.hdlnx_tm_phys: HdlnxTimingModel | None = None
        self._initialize_timing_models()

        # Extract switch matrix information
        # Check super_tile_type in config to filter the correct switch matrix

        self.switch_matrix_hier_path: HierPath = ()
        self.internal_pips_grouped_by_inst: dict[str, list[str]] = {}
        self._extract_switch_matrix_info()

        self.internal_pip_cache: dict[str, InternalPipCacheEntry] = {}

        logger.info("FABulous Timing Model initialized.")

    def _get_project_rtl_files(self) -> None:
        """Find all the Verilog files for the tile in the project directory.

        Exclude certain directories that are not relevant for synthesis. If custom
        source files are specified in the configuration for this tile, use those
        instead.
        """
        # yosys/ holds synthesis blackboxes named after fabric BELs.
        exclude_dir_patterns: list[str] = ["macro", "user_design", "Test", "^yosys$"]
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
        - Inside a SuperTile, tile_scope is the path of the tile's instance in the
          SuperTile netlist.

        Raises
        ------
        ValueError
            If the SuperTile places the tile more than once, so the tile has no
            single instance to characterise.
        """
        for unique_tiles in self.fabric.get_all_unique_tiles():
            if isinstance(unique_tiles, SuperTile):
                for composed_tile in unique_tiles.tiles:
                    if composed_tile.name == self.tile_name:
                        self.is_in_which_super_tile = unique_tiles.name
                        self.unique_tile_name = unique_tiles.name
                        placements = [
                            (x, y)
                            for y, row in enumerate(unique_tiles.tileMap)
                            for x, tile in enumerate(row)
                            if tile is not None and tile.name == self.tile_name
                        ]
                        if len(placements) != 1:
                            raise ValueError(
                                f"SuperTile {unique_tiles.name!r} places tile "
                                f"{self.tile_name!r} {len(placements)} times."
                            )
                        x, y = placements[0]
                        self.tile_scope = (unique_tiles.tile_instance_name(x, y),)
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
        self.synth_netlist: NetlistIndex = NetlistIndex.read(
            synth_tool.synth_netlist_file, top=synth_tool.synth_design_name
        )
        synth_tool.synth_clean_up()

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
        synth_tool.synth_clean_up()

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

        - Hierarchical path of the switch matrix instance, by the instance name
          the tile generator gives it
        - Net names on each switch matrix child instance (multiplexer), for the
          internal PIP lookups

        Raises
        ------
        ValueError
            If the synthesis netlist has no instance of the tile's switch matrix.
        """
        logger.info("Extracting switch matrix information...")

        tile = self.fabric.tileDic[self.tile_name]
        path = (*self.tile_scope, tile.switch_matrix_instance_name)
        if path not in self.synth_netlist:
            raise ValueError(
                f"Switch matrix instance {'/'.join(path)!r} of tile "
                f"{self.tile_name!r} not found in the {self.unique_tile_name!r} "
                "netlist."
            )
        self.switch_matrix_hier_path = path
        logger.info(f"Using switch matrix instance: {'/'.join(path)}")

        logger.info("Loading internal PIPs...")
        self.internal_pips_grouped_by_inst = self.synth_netlist.child_nets(path)

    def _switch_matrix_muxes(self, pip_src: str, pip_dst: str) -> list[HierPath]:
        """Return the switch matrix child instances on both PIP nets.

        Parameters
        ----------
        pip_src : str
            Source PIP port name.
        pip_dst : str
            Destination PIP port name.

        Returns
        -------
        list[HierPath]
            Paths of the switch matrix children connected to both nets.
        """
        return [
            (*self.switch_matrix_hier_path, instance)
            for instance, nets in self.internal_pips_grouped_by_inst.items()
            if pip_src in nets and pip_dst in nets
        ]

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
        if pip_src == pip_dst:
            return False
        return bool(self._switch_matrix_muxes(pip_src, pip_dst))

    def internal_pip_delay_structural(self, pip_src: str, pip_dst: str) -> Decimal:
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
        Decimal
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
            self._switch_matrix_muxes(pip_src, pip_dst)
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
            self.synth_netlist.net_leaf_pins(swm_mux_for_pips[0])
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

    def internal_pip_delay_physical(self, pip_src: str, pip_dst: str) -> Decimal:
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
        Decimal
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
        swm_mux_for_pips: list[HierPath] = (
            self._switch_matrix_muxes(pip_src, pip_dst)
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
            synth_model.nearest_ports_from_pins(
                self.synth_netlist.net_leaf_pins(swm_mux_for_pips[0]),
                reverse=True,
                num_ports=1,
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
                synth_model.nearest_ports_from_pins(
                    self.synth_netlist.net_leaf_pins(swm_mux_for_pips[0]),
                    reverse=False,
                    num_ports=1,
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

    def external_pip_delay_structural(self, pip_src: str, pip_dst: str) -> Decimal:
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
        Decimal
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
        default_delay = Decimal("0.001")

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

        if delay < Decimal("1e-5"):
            return default_delay

        return delay

    def external_pip_delay_physical(self, pip_src: str, pip_dst: str) -> Decimal:
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
        Decimal
            Estimated delay in nanoseconds for the external PIP.
        """
        logger.info(
            f"Timing extraction for tile: {self.tile_name}, PIP: {pip_src} -> {pip_dst}"
        )

        logger.info(
            f"Calculating physical delay for external PIP from {pip_src} to {pip_dst}"
        )

        phys_model = self.hdlnx_tm_phys

        default_delay = Decimal("0.001")

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

        if delay < Decimal("1e-5"):
            return default_delay

        return delay

    def internal_pip_delay(self, pip_src: str, pip_dst: str) -> Decimal:
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
        Decimal
            Calculated delay in nanoseconds for the internal PIP.
        """
        if self.tm_config.mode == TimingModelMode.PHYSICAL:
            return self.internal_pip_delay_physical(pip_src, pip_dst)
        return self.internal_pip_delay_structural(pip_src, pip_dst)

    def external_pip_delay(self, pip_src: str, pip_dst: str) -> Decimal:
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
        Decimal
            Calculated delay in nanoseconds for the external PIP.
        """
        if self.tm_config.mode == TimingModelMode.PHYSICAL:
            return self.external_pip_delay_physical(pip_src, pip_dst)
        return self.external_pip_delay_structural(pip_src, pip_dst)

    def _scaled(self, delay: Decimal) -> Ns:
        """Return `delay` scaled by the configured `delay_scaling_factor`.

        Parameters
        ----------
        delay : Decimal
            Unscaled delay in nanoseconds.

        Returns
        -------
        Ns
            The exact scaled delay.
        """
        scaled = delay * self.tm_config.delay_scaling_factor
        # The nextpnr timing file format: no trailing zeros, one decimal place at
        # least.
        scaled = scaled.normalize()
        if scaled == scaled.to_integral_value():
            scaled = scaled.quantize(Decimal("0.1"))
        return Ns(scaled)

    def pip_delay(self, pip_src: str, pip_dst: str) -> Ns:
        """Calculate the delay for a PIP, choosing between internal and external.

        Parameters
        ----------
        pip_src : str
            Source PIP port name.
        pip_dst : str
            Destination PIP port name.

        Returns
        -------
        Ns
            Scaled delay in nanoseconds for the PIP.
        """
        if self.is_tile_internal_pip(pip_src, pip_dst):
            return self._scaled(self.internal_pip_delay(pip_src, pip_dst))
        return self._scaled(self.external_pip_delay(pip_src, pip_dst))

    def bel_timing(self, bel: Bel, *, instance: HierPath) -> BelArcs:
        """Return characterized combinational and sequential timing for one BEL.

        Discover clocks from paths to register clock pins. Characterize setup/hold
        at register inputs and clock-to-output at register outputs independently;
        a register's other endpoint may connect to an external BEL port.
        Always use the hierarchical synthesis graph: the physical flow flattens
        away the BEL identities needed for characterization.

        Parameters
        ----------
        bel : Bel
            Fabric definition for the BEL being characterized.
        instance : HierPath
            Path of the BEL instance in the synthesis netlist.

        Returns
        -------
        BelArcs
            Timing arcs from the synthesis graph in BEL port names, scaled by
            `delay_scaling_factor`.

        Raises
        ------
        RuntimeError
            If the synthesis timing model has not been initialized.
        ValueError
            If the BEL instance is absent from the synthesis netlist.
        """
        timing_model = self.hdlnx_tm_synth
        if timing_model is None:
            raise RuntimeError("The synthesis timing model is not initialized.")

        identifier = "/".join(instance)
        if instance not in self.synth_netlist:
            raise ValueError(
                f"BEL {identifier!r} not found in tile {self.tile_name!r} netlist."
            )
        input_pins: dict[BelPin, list[str]] = {}
        output_pins: dict[BelPin, list[str]] = {}
        shared_inputs: dict[BelPin, list[str]] = {}
        for category in ("internal", "shared"):
            for port, (direction, width) in bel.ports_vectors.get(category, {}).items():
                if direction not in {IO.INPUT, IO.OUTPUT}:
                    continue
                for index in range(width):
                    name = BelPin(port, None if width == 1 else index)
                    pins = self.synth_netlist.leaf_pins(
                        instance, PortBit(port, name.bit)
                    )
                    if direction == IO.INPUT:
                        if category == "shared":
                            shared_inputs[name] = pins
                        else:
                            input_pins[name] = pins
                    elif category == "internal":
                        output_pins[name] = pins

        hierarchical_prefix = sdf_path(instance) + "/"
        # Routing feedback belongs to PIP timing, not to the BEL's internal arcs.
        # Slice a copy so the shared tile graph stays whole for later PIP queries.
        # Filter rather than call `subgraph()`: its node set would make the arc
        # order follow the string hash seed.
        timing_model = copy(timing_model)
        timing_model.graph = nx.subgraph_view(
            timing_model.graph,
            filter_node=lambda pin: pin.startswith(hierarchical_prefix),
        ).copy()
        for cached_view in ("clock_graph", "combinational_graph"):
            timing_model.__dict__.pop(cached_view, None)
        register_pins = [
            (source, target)
            for source, target, data in timing_model.graph.edges(data=True)
            if data["component"].is_timing_check
            and target.startswith(hierarchical_prefix)
        ]
        logger.info(
            f"Extracting synthesis timing for tile {self.tile_name}, "
            f"BEL {identifier} ({len(register_pins)} register input checks)"
        )
        clock_sources: dict[str, list[tuple[BelPin, str]]] = {}
        clock_ports: set[BelPin] = set()
        for register_clock in dict.fromkeys(clock for _, clock in register_pins):
            for port, pins in (input_pins | shared_inputs).items():
                for pin in pins:
                    if nx.has_path(timing_model.clock_graph, pin, register_clock):
                        clock_sources.setdefault(register_clock, []).append((port, pin))
                        clock_ports.add(port)

        has_ff = "FF" in bel.belFeatureMap
        ff_condition: Condition = (FeatureIs("FF", True),) if has_ff else ()

        def sequential_condition(port: BelPin) -> Condition:
            """Preserve the documented mode controls of the standard IOBUF and LC."""
            feature = f"{port.name}_REG"
            if bel.name == "IOBUF" and feature in bel.belFeatureMap:
                return (FeatureIs(feature, True),)
            return ff_condition

        setup_holds: dict[tuple[BelPin, BelPin], tuple[Decimal, Decimal]] = {}
        clock_delays: dict[tuple[BelPin, BelPin], Decimal] = {}
        for data_pin, register_clock in register_pins:
            for clock, clock_source in clock_sources.get(register_clock, []):
                for port, pins in input_pins.items():
                    if port in clock_ports:
                        continue
                    for pin in pins:
                        try:
                            paths = timing_model.query_register_input_timing(
                                pin, data_pin, register_clock, clock_source
                            )
                        except nx.NetworkXNoPath:
                            continue
                        for path in paths:
                            setups = [
                                value.maximum
                                for value in path.effective_setup
                                if value.maximum is not None
                            ]
                            holds = [
                                value.maximum
                                for value in path.effective_hold
                                if value.maximum is not None
                            ]
                            if not setups or not holds:
                                continue
                            key = (port, clock)
                            setup, hold = max(setups), max(holds)
                            if key in setup_holds:
                                setup = max(setup, setup_holds[key][0])
                                hold = max(hold, setup_holds[key][1])
                            setup_holds[key] = (setup, hold)

        for register_clock, sources in clock_sources.items():
            for clock, clock_source in sources:
                for port, pins in output_pins.items():
                    for pin in pins:
                        try:
                            paths = timing_model.query_timing_paths(
                                register_clock,
                                pin,
                                clock_pin=clock_source,
                                include_timing_checks=False,
                            )
                        except nx.NetworkXNoPath:
                            continue
                        for path in paths:
                            delays = [
                                value.maximum
                                for value in (
                                    path.clock_to_output_rise,
                                    path.clock_to_output_fall,
                                )
                                if value is not None and value.maximum is not None
                            ]
                            if delays:
                                key = (port, clock)
                                delay = max(delays)
                                if key in clock_delays:
                                    delay = max(delay, clock_delays[key])
                                clock_delays[key] = delay

        clock_arcs = tuple(
            ClockArc(clock, when=ff_condition)
            for clock in dict.fromkeys(
                clock for _, clock in [*setup_holds, *clock_delays]
            )
        )
        delay_arcs: list[DelayArc] = []
        registered_outputs = {port for port, _ in clock_delays}
        for source, source_pins in input_pins.items():
            if source in clock_ports:
                continue
            for sink, sink_pins in output_pins.items():
                delays = []
                for source_pin in source_pins:
                    for sink_pin in sink_pins:
                        try:
                            paths = timing_model.query_combinational_paths(
                                source_pin, sink_pin
                            )
                        except nx.NetworkXNoPath:
                            continue
                        for path in paths:
                            delays.extend(
                                value.maximum
                                for value in (path.rise, path.fall)
                                if value.maximum is not None
                            )
                if delays:
                    condition: Condition = (
                        (FeatureIs("FF", False),)
                        if has_ff and sink in registered_outputs
                        else ()
                    )
                    delay_arcs.append(
                        DelayArc(
                            source, sink, self._scaled(max(delays)), when=condition
                        )
                    )

        setup_arcs = tuple(
            SetupHoldArc(
                port,
                clock,
                self._scaled(setup),
                self._scaled(hold),
                when=sequential_condition(port),
            )
            for (port, clock), (setup, hold) in setup_holds.items()
        )
        output_arcs = tuple(
            ClockToOutArc(
                port, clock, self._scaled(delay), when=sequential_condition(port)
            )
            for (port, clock), delay in clock_delays.items()
        )
        arcs = BelArcs(
            clocks=clock_arcs,
            delays=tuple(delay_arcs),
            checks=setup_arcs,
            clock_to_outs=output_arcs,
        )
        arc_count = len(clock_arcs) + len(delay_arcs) + len(setup_arcs)
        logger.info(
            f"Completed timing extraction for tile: {self.tile_name}, "
            f"BEL: {identifier} "
            f"({arc_count + len(output_arcs)} timing arcs)"
        )
        return arcs
