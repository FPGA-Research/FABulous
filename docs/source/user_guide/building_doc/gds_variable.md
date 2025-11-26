(gds-variables)=
# GDS Flow Configuration Variables

This is an auto-generated reference of all GDS flow configuration variables used by the FABulous GDS generator.

These variables can be configured in the `gds_config.yaml` file located in either:
- `<project>/Tile/include/gds_config.yaml` - Base configuration for all tiles
- `<project>/Tile/<tile_name>/gds_config.yaml` - Per-tile specific configuration
- `<project>/Fabric/gds_config.yaml` - Fabric-level configuration


## Tile I/O Placement

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IO_PIN_V_EXTENSION` | Decimal | 0 | Extends the vertical io pins outside of the die by the specified units. |
| `IO_PIN_H_EXTENSION` | Decimal | 0 | Extends the horizontal io pins outside of the die by the specified units. |
| `IO_PIN_V_THICKNESS_MULT` | Decimal | 2 | A multiplier for vertical pin thickness. Base thickness is the pins layer min width. |
| `IO_PIN_H_THICKNESS_MULT` | Decimal | 2 | A multiplier for horizontal pin thickness. Base thickness is the pins layer min width. |
| `IO_PIN_V_LENGTH` | Optional | - | The length of the pins with a north or south orientation. If unspecified by a PDK, OpenROAD will use whichever is higher of the following two values: * The pin width * The minimum value satisfying the minimum area constraint given the pin width |
| `IO_PIN_H_LENGTH` | Optional | - | The length of the pins with an east or west orientation. If unspecified by a PDK, OpenROAD will use whichever is higher of the following two values: * The pin width * The minimum value satisfying the minimum area constraint given the pin width |
| `FABULOUS_IO_PIN_ORDER_CFG` | Path | - | Path to a custom pin configuration file. |
| `ERRORS_ON_UNMATCHED_IO` | Literal | unmatched_design | Controls whether to emit an error in: no situation, when pins exist in the design that do not exist in the config file, when pins exist in the config file that do not exist in the design, and both respectively. `both` is recommended, as the default is only for backwards compatibility with librelane 1. |


## Power Distribution Network

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PNR_CORNERS` | Optional | - | A list of fully-qualified IPVT corners to use during PnR. If unspecified, the value for `STA_CORNERS` from the PDK will be used. |
| `SET_RC_VERBOSE` | bool | False | If set to true, set_rc commands are echoed. Quite noisy, but may be useful for debugging. |
| `LAYERS_RC` | Optional | - | Used during PNR steps, Specific custom resistance and capacitance values for metal layers. For each IPVT corner, a mapping for each metal layer is provided. Each mapping describes custom resistance and capacitance values. Usage of wildcards for specifying IPVT corners is allowed. Units are resistance and capacitance per unit length as defined in the first lib file. |
| `VIAS_R` | Optional | - | Used during PNR steps, Specific custom resistance values for via layers. For each IPVT corner, a mapping for each via layer is provided. Each mapping describes custom resistance values. Usage of wildcards for specifying IPVT corners is allowed. Via resistance is per cut/via with units asdefined in the first lib file. |
| `PDN_CONNECT_MACROS_TO_GRID` | bool | True | Enables the connection of macros to the top level power grid. |
| `PDN_MACRO_CONNECTIONS` | Optional | - | Specifies explicit power connections of internal macros to the top level power grid, in the format: regex matching macro instance names, power domain vdd and ground net names, and macro vdd and ground pin names `<instance_name_rx> <vdd_net> <gnd_net> <vdd_pin> <gnd_pin>`. |
| `PDN_ENABLE_GLOBAL_CONNECTIONS` | bool | True | Enables the creation of global connections in PDN generation. |
| `PNR_SDC_FILE` | Optional | - | Specifies the SDC file used during all implementation (PnR) steps |
| `FP_DEF_TEMPLATE` | Optional | - | Points to the DEF file to be used as a template. |
| `DEDUPLICATE_CORNERS` | bool | False | Cull duplicate IPVT corners during PNR, i.e. corners that share the same set of lib files and values for LAYERS_RC and VIAS_R as another corner are not considered outside of STA. |
| `PDN_SKIPTRIM` | bool | False | Enables `-skip_trim` option during pdngen which skips the metal trim step, which attempts to remove metal stubs. |
| `PDN_CORE_RING` | bool | False | Enables adding a core ring around the design. More details on the control variables in the PDK config documentation. |
| `PDN_ENABLE_RAILS` | bool | True | Enables the creation of rails in the power grid. |
| `PDN_HORIZONTAL_HALO` | Decimal | 10 | Sets the horizontal halo around the macros during power grid insertion. |
| `PDN_VERTICAL_HALO` | Decimal | 10 | Sets the vertical halo around the macros during power grid insertion. |
| `PDN_MULTILAYER` | bool | True | Controls the layers used in the power grid. If set to false, only the lower layer will be used, which is useful when hardening a macro for integrating into a larger top-level design. |
| `PDN_RAIL_OFFSET` | Decimal | - | The offset for the power distribution network rails for first metal layer. |
| `PDN_VWIDTH` | Decimal | - | The strap width for the vertical layer in generated power distribution networks. |
| `PDN_HWIDTH` | Decimal | - | The strap width for the horizontal layer in generated power distribution networks. |
| `PDN_VSPACING` | Decimal | - | Intra-spacing (within a set) of vertical straps in generated power distribution networks. |
| `PDN_HSPACING` | Decimal | - | Intra-spacing (within a set) of horizontal straps in generated power distribution networks. |
| `PDN_VPITCH` | Decimal | - | Inter-distance (between sets) of vertical power straps in generated power distribution networks. |
| `PDN_HPITCH` | Decimal | - | Inter-distance (between sets) of horizontal power straps in generated power distribution networks. |
| `PDN_VOFFSET` | Decimal | - | Initial offset for sets of vertical power straps. |
| `PDN_HOFFSET` | Decimal | - | Initial offset for sets of horizontal power straps. |
| `PDN_CORE_RING_VWIDTH` | Decimal | - | The width for the vertical layer in the core ring of generated power distribution networks. |
| `PDN_CORE_RING_HWIDTH` | Decimal | - | The width for the horizontal layer in the core ring of generated power distribution networks. |
| `PDN_CORE_RING_VSPACING` | Decimal | - | The spacing for the vertical layer in the core ring of generated power distribution networks. |
| `PDN_CORE_RING_HSPACING` | Decimal | - | The spacing for the horizontal layer in the core ring of generated power distribution networks. |
| `PDN_CORE_RING_VOFFSET` | Decimal | - | The offset for the vertical layer in the core ring of generated power distribution networks. |
| `PDN_CORE_RING_HOFFSET` | Decimal | - | The offset for the horizontal layer in the core ring of generated power distribution networks. |
| `PDN_CORE_RING_CONNECT_TO_PADS` | bool | False | If specified, the core side of the pad pins will be connected to the ring. |
| `PDN_CORE_RING_ALLOW_OUT_OF_DIE` | bool | True | If specified, the ring shapes are allowed to be outside the die boundary. |
| `PDN_RAIL_LAYER` | str | - | Defines the metal layer used for PDN rails. |
| `PDN_RAIL_WIDTH` | Decimal | - | Defines the width of PDN rails on the `FP_PDN_RAILS_LAYER` layer. |
| `PDN_HORIZONTAL_LAYER` | str | - | Defines the horizontal PDN layer. |
| `PDN_VERTICAL_LAYER` | str | - | Defines the vertical PDN layer. |
| `PDN_CORE_HORIZONTAL_LAYER` | Optional | - | Defines the horizontal PDN layer for the core ring. Falls back to `PDN_HORIZONTAL_LAYER` if undefined. |
| `PDN_CORE_VERTICAL_LAYER` | Optional | - | Defines the vertical PDN layer for the core ring. Falls back to `PDN_VERTICAL_LAYER` if undefined. |
| `PDN_EXTEND_TO` | Literal | core_ring | Defines how far the stripes and rings extend. |
| `PDN_ENABLE_PINS` | bool | True | If specified, the power straps will be promoted to block pins. |
| `PDN_CFG` | Optional | `<resource>`/pdn_config.tcl | A custom PDN configuration file. If not provided, the default PDN config will be used. This default config is a custom config that differ from the librelane default. |


## Buffer Insertion

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PNR_CORNERS` | Optional | - | A list of fully-qualified IPVT corners to use during PnR. If unspecified, the value for `STA_CORNERS` from the PDK will be used. |
| `SET_RC_VERBOSE` | bool | False | If set to true, set_rc commands are echoed. Quite noisy, but may be useful for debugging. |
| `LAYERS_RC` | Optional | - | Used during PNR steps, Specific custom resistance and capacitance values for metal layers. For each IPVT corner, a mapping for each metal layer is provided. Each mapping describes custom resistance and capacitance values. Usage of wildcards for specifying IPVT corners is allowed. Units are resistance and capacitance per unit length as defined in the first lib file. |
| `VIAS_R` | Optional | - | Used during PNR steps, Specific custom resistance values for via layers. For each IPVT corner, a mapping for each via layer is provided. Each mapping describes custom resistance values. Usage of wildcards for specifying IPVT corners is allowed. Via resistance is per cut/via with units asdefined in the first lib file. |
| `PDN_CONNECT_MACROS_TO_GRID` | bool | True | Enables the connection of macros to the top level power grid. |
| `PDN_MACRO_CONNECTIONS` | Optional | - | Specifies explicit power connections of internal macros to the top level power grid, in the format: regex matching macro instance names, power domain vdd and ground net names, and macro vdd and ground pin names `<instance_name_rx> <vdd_net> <gnd_net> <vdd_pin> <gnd_pin>`. |
| `PDN_ENABLE_GLOBAL_CONNECTIONS` | bool | True | Enables the creation of global connections in PDN generation. |
| `PNR_SDC_FILE` | Optional | - | Specifies the SDC file used during all implementation (PnR) steps |
| `FP_DEF_TEMPLATE` | Optional | - | Points to the DEF file to be used as a template. |
| `DEDUPLICATE_CORNERS` | bool | False | Cull duplicate IPVT corners during PNR, i.e. corners that share the same set of lib files and values for LAYERS_RC and VIAS_R as another corner are not considered outside of STA. |
| `RT_CLOCK_MIN_LAYER` | Optional | - | The name of lowest layer to be used in routing the clock net. |
| `RT_CLOCK_MAX_LAYER` | Optional | - | The name of highest layer to be used in routing the clock net. |
| `GRT_ADJUSTMENT` | Decimal | 0.3 | Reduction in the routing capacity of the edges between the cells in the global routing graph for all layers. Values range from 0 to 1. 1 = most reduction, 0 = least reduction. |
| `GRT_MACRO_EXTENSION` | int | 0 | Sets the number of GCells added to the blockages boundaries from macros. A GCell is typically defined in terms of Mx routing tracks. The default GCell size is 15 M3 pitches. |
| `GRT_LAYER_ADJUSTMENTS` | List | - | Layer-specific reductions in the routing capacity of the edges between the cells in the global routing graph, delimited by commas. Values range from 0 through 1. |
| `DIODE_PADDING` | Optional | - | Diode cell padding; increases the width of diode cells during placement checks.. |
| `GRT_ALLOW_CONGESTION` | bool | False | Allow congestion during global routing |
| `GRT_ANTENNA_ITERS` | int | 3 | The maximum number of iterations for global antenna repairs. |
| `GRT_OVERFLOW_ITERS` | int | 50 | The maximum number of iterations waiting for the overflow to reach the desired value. |
| `GRT_ANTENNA_MARGIN` | int | 10 | The margin to over fix antenna violations. |
| `PL_OPTIMIZE_MIRRORING` | bool | True | Specifies whether or not to run an optimize_mirroring pass whenever detailed placement happens. This pass will mirror the cells whenever possible to optimize the design. |
| `PL_MAX_DISPLACEMENT_X` | int | 500 | Specifies how far an instance can be moved along the X-axis when finding a site where it can be placed during detailed placement. |
| `PL_MAX_DISPLACEMENT_Y` | int | 100 | Specifies how far an instance can be moved along the Y-axis when finding a site where it can be placed during detailed placement. |
| `DPL_CELL_PADDING` | int | - | Cell padding value (in sites) for detailed placement. The number will be integer divided by 2 and placed on both sides. Should be <= global placement. |
| `RSZ_DONT_TOUCH_RX` | str | $^ | A single regular expression designating nets or instances as "don't touch" by design repairs or resizer optimizations. |
| `RSZ_DONT_TOUCH_LIST` | Optional | - | A list of nets and instances as "don't touch" by design repairs or resizer optimizations. |
| `RSZ_CORNERS` | Optional | - | Resizer step-specific override for PNR_CORNERS. |
| `DESIGN_REPAIR_BUFFER_INPUT_PORTS` | bool | True | Specifies whether or not to insert buffers on input ports when design repairs are run. |
| `DESIGN_REPAIR_BUFFER_OUTPUT_PORTS` | bool | True | Specifies whether or not to insert buffers on input ports when design repairs are run. |
| `DESIGN_REPAIR_REMOVE_BUFFERS` | bool | False | Invokes OpenROAD's remove_buffers command to remove buffers from synthesis, which gives OpenROAD more flexibility when buffering nets. |


## Fabric I/O Placement

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IO_PIN_V_EXTENSION` | Decimal | 0 | Extends the vertical io pins outside of the die by the specified units. |
| `IO_PIN_H_EXTENSION` | Decimal | 0 | Extends the horizontal io pins outside of the die by the specified units. |
| `IO_PIN_V_THICKNESS_MULT` | Decimal | 2 | A multiplier for vertical pin thickness. Base thickness is the pins layer min width. |
| `IO_PIN_H_THICKNESS_MULT` | Decimal | 2 | A multiplier for horizontal pin thickness. Base thickness is the pins layer min width. |
| `IO_PIN_V_LENGTH` | Optional | - | The length of the pins with a north or south orientation. If unspecified by a PDK, OpenROAD will use whichever is higher of the following two values: * The pin width * The minimum value satisfying the minimum area constraint given the pin width |
| `IO_PIN_H_LENGTH` | Optional | - | The length of the pins with an east or west orientation. If unspecified by a PDK, OpenROAD will use whichever is higher of the following two values: * The pin width * The minimum value satisfying the minimum area constraint given the pin width |


## Tile Optimisation

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FABULOUS_OPTIMISATION_WIDTH_STEP_COUNT` | int | 4 | The number of placement sites by which the tile size reduces in each iteration. The actual reduction in DBU is this count multiplied by the PDK site dimensions. |
| `FABULOUS_OPTIMISATION_HEIGHT_STEP_COUNT` | int | 1 | The number of placement sites by which the tile size reduces in each iteration. The actual reduction in DBU is this count multiplied by the PDK site dimensions. |
| `FABULOUS_OPT_MODE` | OptMode | OptMode.BALANCE | Optimisation mode to use. Options are: - 'find_min_width': default, finds minimal width by increasing from initial guess. - 'find_min_height': finds minimal height by increasing from initial guess. - 'balance': finds minimal area by starting from square bounding box and increasing alternatingly. - 'no-opt': Disable optimisation. |
| `IGNORE_ANTENNA_VIOLATIONS` | bool | False | If True, antenna violations are ignored during tile optimisation. Default is False. |
| `IGNORE_ANTENNA_VIOLATIONS` | bool | False | If True, antenna violations are ignored during tile optimisation. Default is False. |
| `IGNORE_DEFAULT_DIE_AREA` | bool | False | If True, default die area is ignored and using instance area for initial sizing. Default is False. |
| `FABULOUS_IO_MIN_WIDTH` | Decimal | Decimal(0) | Minimum width required for IO pin spacing constraints. This is the physical lower bound based on the number of IO pins on the north/south edges and track pitch. Default is 0 (no IO constraint). |
| `FABULOUS_IO_MIN_HEIGHT` | Decimal | Decimal(0) | Minimum height required for IO pin spacing constraints. This is the physical lower bound based on the number of IO pins on the west/east edges and track pitch. Default is 0 (no IO constraint). |


## Fabric Macro Flow

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `RUN_TAP_ENDCAP_INSERTION` | bool | True | Enables the OpenROAD.TapEndcapInsertion step. |
| `RUN_POST_GPL_DESIGN_REPAIR` | bool | True | Enables resizer design repair after global placement using the OpenROAD.RepairDesignPostGPL step. |
| `RUN_POST_GRT_DESIGN_REPAIR` | bool | False | Enables resizer design repair after global placement using the OpenROAD.RepairDesignPostGPL step. This is experimental and may result in hangs and/or extended run times. |
| `RUN_CTS` | bool | True | Enables clock tree synthesis using the OpenROAD.CTS step. |
| `RUN_POST_CTS_RESIZER_TIMING` | bool | True | Enables resizer timing optimizations after clock tree synthesis using the OpenROAD.ResizerTimingPostCTS step. |
| `RUN_POST_GRT_RESIZER_TIMING` | bool | False | Enables resizer timing optimizations after global routing using the OpenROAD.ResizerTimingPostGRT step. This is experimental and may result in hangs and/or extended run times. |
| `RUN_HEURISTIC_DIODE_INSERTION` | bool | False | Enables the Odb.HeuristicDiodeInsertion step. |
| `RUN_ANTENNA_REPAIR` | bool | True | Enables the OpenROAD.RepairAntennas step. |
| `RUN_DRT` | bool | True | Enables the OpenROAD.DetailedRouting step. |
| `RUN_FILL_INSERTION` | bool | True | Enables the OpenROAD.FillInsertion step. |
| `RUN_MCSTA` | bool | True | Enables multi-corner static timing analysis using the OpenROAD.STAPostPNR step. |
| `RUN_SPEF_EXTRACTION` | bool | True | Enables parasitics extraction using the OpenROAD.RCX step. |
| `RUN_IRDROP_REPORT` | bool | True | Enables generation of an IR Drop report using the OpenROAD.IRDropReport step. |
| `RUN_LVS` | bool | True | Enables the Netgen.LVS step. |
| `RUN_MAGIC_STREAMOUT` | bool | True | Enables the Magic.StreamOut step to generate GDSII. |
| `RUN_KLAYOUT_STREAMOUT` | bool | True | Enables the KLayout.StreamOut step to generate GDSII. |
| `RUN_MAGIC_WRITE_LEF` | bool | True | Enables the Magic.WriteLEF step. |
| `RUN_KLAYOUT_XOR` | bool | True | Enables running the KLayout.XOR step on the two GDSII files generated by Magic and Klayout. Stream-outs for both KLayout and Magic should have already run, and the PDK must support both signoff tools. |
| `RUN_MAGIC_DRC` | bool | True | Enables the Magic.DRC step. |
| `RUN_KLAYOUT_DRC` | bool | True | Enables the KLayout.DRC step. |
| `RUN_EQY` | bool | False | Enables the Yosys.EQY step. Not valid for VHDLClassic. |
| `RUN_LINTER` | bool | True | Enables the Verilator.Lint step and associated checker steps. Not valid for VHDLClassic. |
| `FABULOUS_TILE_SPACING` | tuple | (0, 0) | The spacing between tiles. (x_spacing, y_spacing) |
| `FABULOUS_HALO_SPACING` | tuple | (0, 0, 0, 0) | The spacing around the fabric. [left, bottom, right, top] |
| `FABULOUS_SPEF_CORNERS` | list | ['nom'] | The SPEF corners to use for the tile macros. |

