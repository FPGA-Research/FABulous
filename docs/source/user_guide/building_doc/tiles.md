(tiles)=

# Tiles

:::{figure} figs/tile_CLB_example.*
:align: center
:alt: Basic tile illustration
:width: 30%
:::

A tile is the smallest unit in a fabric and a tile provides

- A description of {ref}`wires <wires>` to adjacent tiles
- A central {ref}`switch matrix <switch-matrix>`
- An optional list of {ref}`primitives <primitives>`
- A central configuration storage module

A tile typically hosts primitives like a CLB with LUTs or an I/O block.
Multiple smaller tiles can be combined into {ref}`supertiles <supertiles>` to accommodate complex blocks like DSPs.

(tile-csv)=

## Tile CSV description

Each tile that is referred to in the {ref}`fabric layout <fabric-layout>` requires specification of the corresponding tile description in a tile.csv file that has the following format:

```{code-block} text
:emphasize-lines: 1,12

TILE, LUT4AB      # define tile name
INCLUDE, ../include/Base.csv
#direction  source_name  X-offset  Y-offset  destination_name  wires
NORTH,      N1BEG,       0,        1,        N1END,            4
EAST,       E2BEG,       1,        0,        N2END,            6
JUMP,       J_BEG,       0,        0,        J_END,            12
...
#         RTL code                     optional prefix
BEL,      LUT4c_frame_config_OQ.vhdl,  LA_
BEL,      LUT4c_frame_config_OQ.vhdl,  LB_
...
MATRIX,   LUT4AB_switch_matrix.list
EndTILE
```

The `INCLUDE` keyword specifies a path to another tile configuration, and the configuration in that file will be added. The
entry within the target path will be appended to the file. For example if `../include/Base.csv` contains:

```text
NORTH,      N2BEG,       0,        2,        N2END,            8
JUMP,       J2_BEG,      0,        0,        J2_END,           12
```

The above configuration is equivalent to:

```{code-block} python
:emphasize-lines: 1,12

TILE, LUT4AB      # define tile name
NORTH,      N2BEG,       0,        2,        N2END,            8
JUMP,       J2_BEG,      0,        0,        J2_END,           12
#direction  source_name  X-offset  Y-offset  destination_name  wires
NORTH,      N1BEG,       0,        1,        N1END,            4
EAST,       E2BEG,       1,        0,        N2END,            6
JUMP,       J_BEG,       0,        0,        J_END,            12
...
#         RTL code                     optional prefix
BEL,      LUT4c_frame_config_OQ.vhdl,  LA_
BEL,      LUT4c_frame_config_OQ.vhdl,  LB_
...
MATRIX,   LUT4AB_switch_matrix.list
EndTILE
```

The path of the `INCLUDE` will be relative to where the base file is. For example if the base file is located
at `foo/bar/LUT4AB.csv` then the `INCLUDE` path will point to `foo/bar/../Base.csv`.

(wires)=

### Wires

Wires are defined by 5-tuples:

`direction`, `source_name`, `X-offset`, `Y-offset`, `destination_name`, `wires`

specifying:

- `direction`, `[NORTH|EAST|SOUTH|WEST|JUMP|SJUMP]`

  The keyword `JUMP` specifies a stop-over at the switch matrix, which is a logical wire that starts and ends at the same switch matrix (i.e. `X-offset` = 0 and `Y-offset` = 0).

  The keyword `SJUMP` ("supertile jump") routes a basic tile's ports to a BEL hosted in the master tile of a {ref}`supertile <supertiles>`, through a dedicated supertile switch matrix.
  It is only meaningful for tiles that are part of a supertile; see {ref}`supertile-bel-routing`.

  Jump wires are useful to model hierarchies, some sharing of multiplexers or tapping into routing paths, as shown in the examples below.

  In the Altera world, tiles separate between a connection switch matrix and the actual local wire switch matrix. The connection switch matrix is nothing else as a bank of multiplexers selecting from the local routing wires a pool of connection wires that can then be further routed to primitive pins (e.g, a LUT input). In FABulous, those connection wires would be modelled with a set of jump wires, which connect then somehow to the primitive input multiplexers.

  Older Xilinx architectures have a less hierarchical routing graph and local routing wires between the tiles connect directly to the input multiplexers of the primitives.

  Xilinx Virtex-5 FPGAs provide diagonal routing wires (e.g., a wire routing in north-east direction), a concept abandoned in consecutive Xilinx FPGA families. FABulous can model diagonal routing by splitting a wire in its components (e.g., a north-east wire can be modeled by cascading a north wire and an east wire).

- `source_name`, `string`

  `destination_name`, `string`

  These are symbolic names for the ports used for the tile top wrapper and the switch matrix connections.
  It is recommended to follow a semantic that expresses the direction, routing span (i.e. how many tiles far away the wire is spanning) and if it is a *begin* or *end* or other port.
  For instance, a single wire in NORTH direction should use names such as *N1Beg* to *N1End* or *N1b* to *N1e*.

  The destination name refers to two ports: a port on the target tile and an expected port on the destination tile. This reflects that wires route between tiles and that the begin and end ports of a tile connect to different wires.
  However, while this works for tiles inside the fabric (like CLBs), the tiles at the border do usually not extend to antennae outside the fabric but instead route wires back into the fabric as shown in the following figure:

  :::{figure} figs/east_terminate.*
  :align: center
  :alt: Reflection of horizontal quad wires at the east border of the fabric.
  :width: 100%
  :::

  The figure illustrates how horizontal quad wires (that route 4 tiles far) are terminated at the east border of the fabric. The example follows the method used by Xilinx to terminate wires at the border of the chip.
  FABulous can implement this scheme, but also any other, including some extra switching at the fabric borders and providing some primitives.

  The figure shows that each CLB tile has a pair of input and output ports for the two east and west directions while the east_terminate tile only has an east end port and a west begin port. Moreover, the figure shows the nested routing for long distance wires (see also the wires bullet below). It can be seen that the CLBs route through long distance wires (here quad wires) while the east_terminate tile has all internal wires connected to the switch matrix. Note that this is only an abstract view and the wires that route through the CLBs may still be buffered inside the CLB tiles. However, this is transparent from the user and not included in the architecture graph.

  The shown wires in the CLBs (from the last figure) are modelled as:

  ```python
  # this is for the CLBs in the example
  #direction  source_name  X-offset  Y-offset  destination_name  wires
  EAST,       E4b,         4,        0,        E4e,              N    # N is used for illustration only
  WEST,       W4b,         -4,       0,        W4e,              N    # N is used for illustration only
  ```

  To control the different behavior for tiles that do not extend a wire (as done in the terminate tiles), we use the `NULL` port name for wire begin or end ports that should not be generated on the tile:

  ```python
  # this is for the east_terminate tile in the example
  #direction  source_name  X-offset  Y-offset  destination_name  wires
  EAST,       NULL,        4,        0,        E4e,              N    # N is used for illustration only
  WEST,       W4b,         -4,       0,        NULL,             N    # N is used for illustration only
  ```

  The `NULL` port entry for the EAST source_name and the WEST destination_name will prevent FABulous from creating the corresponding tile port names. Moreover, the `NULL` port entries also will tell FABulous to connect *all* wires of the corresponding entry, including the nested ones, to the switch matrix. This allows the implementation of the shown U-turn routing scheme for termination but also any other more sophisticated termination scheme.

  For instance, in the FlexBex project, a FABulous eFPGA was coupled with the Ibex RISC V core for custom instruction set extensions (where the eFPGA fabric operates logically in parallel to the ALU) as shown in the following figure:

  :::{figure} figs/Ibex_eFPGA.*
  :align: center
  :alt: Illustration showing the coupling between an Ibex RISC-V core and the eFPGA fabric.
  :width: 90%
  :::

  In this example, the CPU interface is located at the west border of the fabric. The fabric provides three slots, each being two CLB columns wide. The operands are routed into the fabric using double wires (so, each slot receives the operands at exactly the same position, which makes modules relocatable among the slots). The results are routed to the CPU using nested hex wires (again resulting in a homogeneous routing scheme that enables module relocation). The CPU therefore has access to the results of each slot and will multiplex results into the register file in case a custom instruction requires it to do so. For simplicity, the figure does not show the west termination tiles, which simply connect the internal routing wires to the top-level fabric wrapper that, in turn, is used to connect to the CPU.
  In summary, the example shows how a termination tile can be used to provide more complex interface blocks and all this can be easily modelled and implemented with FABulous.

  :::{note}
  The `destination_name` is referring to the port name used at the destination tile. FABulous will throw an error if the destination tile does not provide that port name.
  :::

  Aside from `BEGIN` and `END`, there also exist `MID` ports, which can be used for wires spanning more than two tiles.
  Although they route over two tiles, they also have a tap on the middle tile.
  On the middle tile, the sink is called `MID` while the source is still a `BEG` port with the addition of `b`.
  In the example below this is illustrated. The wire on the left goes from `E2BEG0` to `E2MID` which is the tap on the middle tile.
  Inside the switch matrix, `E2MID` and `E2BEGb` are connected. The left wire then starts at `E2BEGb` and ends at `E2END`.

  :::{figure} figs/mid_wires.*
  :align: center
  :alt: A screenshot take from the FABulator GUI illustrating the tap connection of a MID wire in the middle tile of three.
  :width: 100%
  :::

- `X-offset`, `signed_int`

  `Y-offset`, `signed_int`

  :::{figure} figs/wire_tile_grid.*
  :align: center
  :alt: An illustration of the Wire-Tile-Grid used in FABulous.
  :width: 40%
  :::

  FABulous models wires strictly in horizontal or vertical direction but never directly in diagonal direction - this directly reflects the tiled physical implementation of the fabric.
  Therefore, in each wire specification, either `X-offset` is `0` or `Y-offset` is `X-offset` or both are `0` (in the case of a JUMP wire).

  :::{note}
  The `direction` field and the sign of the `X-offset` and `Y-offset` values are redundant. FABulous uses internally the absolute `X-offset` and `Y-offset` values and only the `direction` field for specifying the direction of a wire. However, FABulous will throw a warning if there is a mismatch with the sign.
  :::

- `wires`, `unsigned_int`
  Specifies the number of wires.

  FABulous will index the wires of each entry starting from [0].

A metric that is important for FPGA ASIC implementations is the channel *cut* number, which denotes the number of wires that must be accommodated between two adjacent tiles. The cut number is an indicator for the congestion to be expected when stitching together the fabric. Let us take the following example:

```{code-block} python
:emphasize-lines: 1

TILE, Example_tile      # define tile name
#direction  source_name  X-offset  Y-offset  destination_name  wires
EAST,       E1Beg,       1,        0,        E1End,            6
WEST,       W4Beg,       -4,       0,        W4End,            3
```

The following figure shows the corresponding wiring between the tiles.
Note that a wire with a span greater 1 is usually nested.

:::{figure} figs/wires_model.*
:align: center
:alt: Example of 6 single east wires and 3 quad west wires.
:width: 40%
:::

Each entry in the wire specification contributes with max(abs(`X-offset`),abs(`y-offset`)) x `wires` to the cut number.
In this example, the east single wire (E1Beg) is contributing with 1 x 6 = 6 and the west quad wire (W4Beg) with 4 x 3 = 12 wire segments to the cut.
Therefore, even if we have only half the number of quad wires, these contribute double the number of ASIC routing tracks to the cut.
Furthermore, the wires needed to write the configuration into the configuration memory cells are further contributing substantially to the cut (see parameter `FrameBitsPerRow` in section {ref}`fabric csv <fabric-csv>`).

The switch matrices see only the `wires` amount of wires, regardless of the span. However, the tile-to-tile interfaces include all nested wires concatenated together to a wide vector. FABulous connects the `wires` LSBs to the switch matrix inputs and the switch matrix outputs are connected to the `wires` MSBs. Inside the tile, the wide vector is shifted by `wires` before routing it to the next tile, as shown in the following figure for an EAST hex-wire example:

```{code-block} python
:emphasize-lines: 1

TILE, CLB
#direction  source_name  X-offset  Y-offset  destination_name  wires
EAST,       E6B,         6,        0,        E6E,              2
```

:::{figure} figs/wire_nesting_indexing.*
:align: center
:alt: Wire nesting and wire indexing.
:width: 100%
:::

:::{note}
A typical CLB requires about 100 to 200 wire connections between adjacent tiles (about 400 to 800 wires in total per tile).

The shift register configuration mode needs fewer wire connections than frame-based configuration at the tile border but shift register mode tends to have a slightly higher congestion inside the tiles because of the long chain.
:::

:::{note}
Because long distance wires contribute heavily to the cut number, it can be beneficial to segment long distance wires to better balance between the silicon core area and the available metal stack for implementing the routing.
:::
