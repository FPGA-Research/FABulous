(fabric-definition)=

# Fabric definition

This section describes the process of modeling FABulous fabrics in a top-down manner.
FABulous can reuse preimplemented tiles which allows it to define fabrics in a LEGO-like manner where it is sufficient to define the {ref}`fabric layout <fabric-layout>` in terms of IO and logic tiles or any other required block.

For customization of {ref}`tiles <tiles>` or the creation of new blocks, it is possible to model the routing {ref}`wires <wires>`, a central {ref}`switch_matrix <switch-matrix>` and {ref}`primitives <primitives>`

The following figure shows a small fabric, which we will model throughout this section. It provides:

- 4x IO pins
- 4x Register file slices
- 2 DSP block supertiles
- 4 internal IO ports for coupling the fabric with a CPU

:::{figure} figs/abstract_tile_view.*
:align: center
:alt: FABulous example fabric
:width: 33%
:::

The full model of a fabric is described by the following files:

- A file {ref}`fabric csv <fabric-csv>` providing the {ref}`fabric layout <fabric-layout>` and some global settings
- A file {ref}`tile csv <tile-csv>` for each tile describing wires, BELs and a link to the switch matrix
- A set of list files (`*.list`) describing the adjacency list of the switch matrix for each of the used tiles or the corresponding adjacency matrix as a CSV file
- A set of optional bitstream mapping CSV files
- A set of primitives used

The following block provides a fabric.csv example.

```{code-block} python
:emphasize-lines: 1,6,8,32

FabricBegin      # explained in subsection Fabric layout
NULL,  N_term,   N_term,   N_term,  N_term,  NULL
W_IO,  RegFile,  DSP_top,  LUT4AB,  LUT4AB,  CPU_IO
W_IO,  RegFile,  DSP_bot,  LUT4AB,  LUT4AB,  CPU_IO
...
FabricEnd

ParametersBegin
ConfigBitMode, frame_based        # default is FlipFlopChain
FrameBitsPerRow, 32               # configuration bits per tile row
MaxFramesPerCol, 20               # configuration bits per tile column
Package, use work.my_package.all; # populate package fields in VHDL code generation
GenerateDelayInSwitchMatrix, 80   # we can annotate some delay to multiplexers
MultiplexerStyle, custom          #

# Links to tile configuration files
Tile,./Tile/LUT4AB/LUT4AB.csv
Tile,./Tile/N_term_single/N_term_single.csv
Tile,./Tile/S_term_single/S_term_single.csv
Tile,./Tile/CPU_IO/CPU_IO.csv
Tile,./Tile/RegFile/RegFile.csv
Tile,./Tile/N_term_single2/N_term_single2.csv
Tile,./Tile/S_term_single2/S_term_single2.csv
Tile,./Tile/W_IO/W_IO.csv
Tile,./Tile/DSP/DSP_top/DSP_top.csv
Tile,./Tile/DSP/DSP_bot/DSP_bot.csv
Tile,./Tile/N_term_DSP/N_term_DSP.csv
Tile,./Tile/S_term_DSP/S_term_DSP.csv

Supertile,./Tile/DSP/DSP.csv

ParametersEnd
```

And the following block provides a tile.csv example (in this case LUT4AB.csv).

```{code-block} python
:emphasize-lines: 1,8

TILE, LUT4AB      # explained in subsection Tiles
#direction  source_name  X-offset  Y-offset  destination_name  wires
NORTH,      N1BEG,       0,        1,        N1END,            4
...
BEL,      LUT4c_frame_config_OQ.vhdl,  LA_
...
MATRIX,   LUT4AB_switch_matrix.vhdl
EndTILE
```

## Current Fabric Limitations

The current configuration logic and the bitstream header limit FABulous fabrics to the following
dimensions and parameters:

- 32 columns
- 32 rows
- 20 frames per tile (each 32 bits wide)
- 640 configuration bits per tile (20 frames x 32 bits)
- 26 BELs per tile

Another limitiation is the support of only a single clock domain.

The 32-bit header is structured as follows (MSB to LSB):

| [31:27]       | [26:21] | [20]     | [19:0]       |
| ------------- | ------- | -------- | ------------ |
| Column Select | Unused  | Sync Bit | Frame Strobe |

The column selection could also be extended to the currently unused bits, but
`FrameSelectWidth` is set to a fixed width of 5 bits in the generated RTL code.

It is planned to remove these limitations in future versions of FABulous.

(fabric-csv)=

## Fabric CSV description

- For the section between `FabricBegin` and `FabricEnd`, refer to the {ref}`fabric layout <fabric-layout>` description.

- Empty lines will be ignored as well as everything that follows a `#` (the **comment** symbol in all FABulous descriptions).

- Parameters that relate to the fabric specification are encapsulated between the keywords `ParametersBegin` and `ParametersEnd`.

  Parameters that relate to the flow are passed as command line arguments.

  Parameters have the format `<key>,<value>`

  FABulous defines the following parameters:

  - `ConfigBitMode`, `[frame_based|FlipFlopChain]`

    FABulous can write to the configuration bits in a frame-based organisation, similarly to most commercial FPGAs. This supports partial reconfiguration and is (except for in tiny fabrics) superior in any sense (configuration speed, resource cost, power consumption) over flip flop scan chain configuration (the option selected by most other open source FPGA frameworks).

    Configuration readback is not currently supported, as it was considered ineffective for embedded FPGA use cases.

  - `FrameBitsPerRow`, `unsigned_int`

    In frame-based configuration mode, FABulous will build a configuration frame register over the height of the fabric and provide the specified number of data bits per row. This will generate frame_data wires in the fabric, which correspond to bitlines in a memory organisation.

    Note that the specified size corresponds to the width of the parallel configuraton port and 32 bits is the most sensible configuration for most systems.

    Currently, we set `FrameBitsPerRow` globally for all rows but we plan to extend this to allow for resource-type specific adjustments in future versions.
    For instance, the tiles at the north border of a fabric may only provide some fixed U-turn routing without the need of any configuration bits, which could be reflected by removing all frame_data wires in the top row. This extension may include an automatic adjustment mode.

  - `MaxFramesPerCol`, `unsigned_int`

    For the frame-based configuration mode, this will specify the number of configurations frames a tile may use. The total number of configuration bits usable is:

    `FrameBitsPerRow` x `MaxFramesPerCol`

    Note that we can leave possible configuration bits unused and that no configuration latches will be generated for unused bits.

    FABulous will generate the specified number of vertical frame_strobe wires in the fabric, which correspond to wordlines in memory organisation.

    `FrameBitsPerRow` and `MaxFramesPerCol` should be around the same number to minimize the wiring resources for driving the configuration bits into the fabric. In most cases, only `MaxFramesPerCol` will be adjusted to a number that can accomodate the number of configuration bits needed.

    Currently, we set `MaxFramesPerCol` globally for all resource types (e.g., LUTs and DSP block columns) but we plan to extend this to allow for resource-type specific adjustments.
    This feature may include an automatic adjustment mode.

  - `Package`, `string`

    This option will populate the package declaration block on VHDL output mode with the string to declare a package.

  - `GenerateDelayInSwitchMatrix`, `unsigned_int`

    This option will annotate the specified time in ps to all switch matrix multiplexers. This ignored for synthesis but allows simulation of the fabric in the case of configured loops (e.g., ring-oscillators).

  - `MultiplexerStyle`, `[custom]`

    FABulous can generate the switch matrix multiplexers in different styles including behavioral RTL, instantiating standard cell primitives and instantiation of full custom multiplexers.

    The latter is implemented by replacing a defined n-input multiplexer with a predefined template. For instance, for the Skywater 130 process, we provide a transmission gate-based custom MUX4. In the case of requiring a MUX16, FABulous will synthesize this multiplexer to use 4 + 1 of our custom cells.

    :::{note}
    So far, FABulous fabrics use fully (binary) encoded multiplexers (e.g., a MUX16 requires 4 configuration bits). However, the major vendors Xilinx and Intel use highly optimized SRAM cells where a configuration cell may directly control a pass transistor (e.g., as used in Xilinx UltraScale fabrics). For a MUX16, this requires 2 x 4 = 8 configuration bits, but is slightly better in area as omits a decoder.
    We plan to extend the FABulous switch matrix compiler accordingly.
    :::

  - `DisableUserCLK`, `FALSE`

    Disable the generation of the UserCLK port, regardless the fabric uses them or not.

  - `PreserveListOrder`, `[TRUE|FALSE]` (default `FALSE`)

    When `TRUE`, FABulous preserves the mux input order from each tile's `.list` file: the rightmost listed input becomes `A0`, the next-rightmost `A1`, and so on (MSB-first, matching Verilog/VHDL `downto`). The default `FALSE` keeps the legacy behaviour, where mux input order is determined by column order in the bootstrapped switch matrix CSV.

    This is useful when a specific input must occupy a known mux position.

  - `Tile`, `path`

    Specify a path to a tile configuration file that will be loaded.

  - `Supertile`, `path`

    Specify a path to a supertile configuration file that will be loaded.

    :::{warning}
    Previously, tile definitions were contained in the fabric.csv file. This has been deprecated and it is recommended to move the tile descriptions to the respective tile.csv files.
    :::

(fabric-layout)=

## Fabric layout

FABulous models FPGA fabrics as simple CSV files that describe the fabric layout in terms of {ref}`tiles`.
A tile is the smallest unit in a fabric and typically hosts primitives like a CLB with LUTs or an I/O block.
Multiple smaller tiles can be combined into {ref}`supertiles`.
The following figure shows the fabric.csv representation of our example fabric as shown in a spreadsheet program.

:::{figure} figs/Fabric_spreadsheet.*
:align: center
:alt: FABulous example fabric in csv representation
:width: 60%
:::

```{code-block} python
:emphasize-lines: 1,8

FabricBegin
NULL,  N_term,   N_term,   N_term,  N_term,  NULL
W_IO,  RegFile,  DSP_top,  LUT4AB,  LUT4AB,  CPU_IO
W_IO,  RegFile,  DSP_bot,  LUT4AB,  LUT4AB,  CPU_IO
W_IO,  RegFile,  DSP_top,  LUT4AB,  LUT4AB,  CPU_IO
W_IO,  RegFile,  DSP_bot,  LUT4AB,  LUT4AB,  CPU_IO
NULL,  S_term,   S_term,   S_term,  S_term,  NULL
FabricEnd
```

- The fabric layout is encapsulated between the keywords `FabricBegin` and `FabricEnd`.

  The specified tiles are references to tile descriptors (see {ref}`tiles`).
  The tiles form a coordinate system with the origin in the top-left:

  | X0Y0 | X1Y0 | X2Y0 | ... |
  | ---- | ---- | ---- | --- |
  | X0Y1 | X1Y1 | X2Y1 | ... |
  | ...  | ...  | ...  | ... |

  `NULL` tiles are used for padding and no code will be generated for these. `NULL` tiles can be used to build non-rectangular shaped fabrics.

The following pages describe each part of the fabric model in detail:

```{toctree}
:maxdepth: 1

tiles
switch_matrix
primitives
bitstream_remapping
supertiles
```
