(supertiles)=

# Supertiles

Supertiles are grouping together multiple basic {ref}`tiles`. Basic tiles are the smallest tile exposed to users providing a switch matrix, wires to the surrounding, and usually one or more primitives (like in a CLB tile).

Supertiles are needed for blocks that require more logic and/or more wires to the routing fabric (e.g., as needed for DSP blocks). Therefore, supertiles will normally provide as many switch matrices as they integrate basic tiles.
However, larger supertiles (e.g., hosting a CPU or similar) may only provide switch matrices in basic tiles located at the border of such a supertile.
In any case: supertiles must provide wire interfaces that match the surroundings when stitching them into a fabric.

## Modelling

Supertiles are modelled from elementary tiles in a supertile.csv file similar to how we model the whole FPGA fabric. Shapes can be defined arbitrary and NULL tiles can be used to skip fields. Examples:

```{code-block} python
:emphasize-lines: 1,5,7,11,13,17

SuperTILE, my_Z      # define supertile name
myZ_00,  NULL
myZ_01,  myZ_11
NULL,    myZ_12
EndSuperTILE         # this is case-insensitive

SuperTILE, my_I      # define supertile name
my_top
my_mid
my_bot,
EndSuperTILE

SuperTILE, my_U      # define supertile name
myU_00,  NULL,    myU_20
myU_01,  NULL,    myU_21
myU_02,  myU_12,  myU_22
EndSuperTILE
```

:::{figure} figs/SuperTILE_examples.*
:align: center
:alt: An illustration of different Supertile examples in an example fabric.csv file.
:width: 80%
:::

Supertiles will be instantiated in the fabric (VHDL or Verilog) file, and supertiles themselves instantiate basic tiles (e.g., the ones shown in the figure). Therefore, supertiles define wires and switch matrices through their instantiated basic tiles.

Supertiles have an **anchor tile**, which is used to specify their position in the fabric. The anchor tile is determined by a row-by-row scan over the basic tiles, and it will be the first non-NULL tile found. All other basic tiles will be placed relatively to the anchor tile. The anchor tiles in the figure above have been marked using a bold font. So far, anchor tiles are only used internally in FABulous, but it is planned to allow placing supertiles through their anchor tiles in the fabric layout, rather than through their basic tiles.

If a basic tile has a **border to the outside world** (i.e. the surrounding fabric), the interface to that border is exported to the supertile interface (i.e. the Entity in VHDL). Those borders are marked blue in the figure above. Internal edges are connected inside the supertile wrapper according to the entire tile specification.

A basic tile instantiated in a supertile may not implement interfaces to all NORTH, EAST, SOUTH, WEST directions. For instance, a supertile may include basic terminate tiles if the supertile is supposed to be placed at the border of the fabric.

Tile ports that are declared `EXTERNAL` in the basic tiles will be exported all the way to the top-level, in the same way it is done for {ref}`tiles`

```{code-block} VHDL
:emphasize-lines: 1

VHDL example:
         RES0_O0    : out   STD_LOGIC; -- EXTERNAL   port will be exported to top-level wrapper
         RES0_O1    : out   STD_LOGIC; -- EXTERNAL   port will be exported to top-level wrapper
Verilog example:
```

## Supertile Functionality

With the instantiation of multiple basic tiles, we define mostly the part related to the routing fabric. The actual functionality of a supertile can be hosted in one of two ways:

- **Approach A -- BEL in a basic tile:** the functionality is concentrated in a single basic tile, whose BEL reaches the other basic tiles through ordinary directional wires (NORTH/EAST/SOUTH/WEST).
- **Approach B -- BEL on the supertile:** the BEL is declared on the `SuperTILE` block and lives in the supertile's master tile, reaching every basic tile through `SJUMP` wires and a dedicated supertile switch matrix (see {ref}`supertile-bel-routing`).

The following figure contrasts the two for a simple DSP block example:

:::{figure} figs/SuperTILE_functionality.*
:align: center
:alt: Two supertile approaches side by side. Approach A hosts the BEL inside a basic tile, wired to the other tile by ordinary directional wires. Approach B hosts the BEL on the supertile's master tile, fed from every basic tile through SJUMP wires and a dedicated supertile switch matrix, with the supertile config bits held in the master tile.
:width: 90%
:::

**Approach A (BEL in a basic tile).** The left example concentrates the DSP functionality in the bottom tile and is modelled as shown in the next code block.
(Note the two extra NORTH and SOUTH wires that provide the connections between the DSP BEL (located bot) and the top basic tile).

```{code-block} python
:emphasize-lines: 1,5,9,13,15,19,23,28

TILE,       DSP_top
#direction  source   X-offset  Y-offset destination wires
NORTH,      N1BEG,   0,        1,       N1END,      4
# connect prmitive outputs to routing fabric
NORTH,      NULL,    0,        1,       bot2top,    10 # no route to north
EAST,       E1BEG,   1,        0,       E1END,      4
SOUTH,      S1BEG,   0,        -1,      S1END,      4
# send data from routing fabric to primitive
SOUTH,      top2bot, 0,        -1,      NULL,       18 # no route from north
WEST,       W1BEG,   -1,       0,       W1END,      4
JUMP,       J_BEG,   0,        0,       J_END,      8
MATRIX,     DSP_top_switch_matrix.vhdl
EndTILE

TILE,       DSP_bot
#direction  source   X-offset  Y-offset destination wires
NORTH,      N1BEG,   0,        1,       N1END,      4
# connect prmitive outputs to routing fabric
NORTH,      bot2top, 0,        1,       NULL,       10 # no route from south
EAST,       E1BEG,   1,        0,       E1END,      4
SOUTH,      S1BEG,   0,        -1,      S1END,      4
# send data from routing fabric to primitive
SOUTH,      NULL,    0,        -1,      top2bot,    18 # no route to south
WEST,       W1BEG,   -1,       0,       W1END,      4
JUMP,       J_BEG,   0,        0,       J_END,      8
BEL,        MULADD.vhdl                 # this is the actual functionality
MATRIX,     DSP_bot_switch_matrix.vhdl
EndTILE
```

```{code-block} python
:emphasize-lines: 1,4

SuperTILE   DSP  # declace supertile  (Functionality concentrated in DSP_bot)
DSP_top
DSP_bot
EndTILE
```

**Approach B (BEL on the supertile).** The right example hosts the functionality in the supertile wrapper: the BEL is declared on the `SuperTILE` block and lives in the supertile's master tile. The recommended way to wire it is with `SJUMP` wires and a dedicated supertile switch matrix; the supertile declaration carries both the `BEL` and a `MATRIX` line pointing at that switch matrix:

```{code-block} python
:emphasize-lines: 1,4,5

SuperTILE   DSP     # declare supertile DSP
DSP_top
DSP_bot
BEL,        MULADD.vhdl
MATRIX,     DSP_supertile_matrix.list
EndTILE
```

The basic tiles declare their `SJUMP` ports and the supertile switch matrix is written as described in {ref}`supertile-bel-routing`.

```{admonition} Legacy modelling: LOCAL wires + ConfigBits BEL
:class: note

Before `SJUMP` routing existed, wrapper functionality was modelled with `LOCAL` wires and a per-tile `ConfigBits` BEL, distributing the configuration bits across the basic tiles (configuration bits organized at basic-tile level). This still parses, but is superseded by the `SJUMP` approach above. The legacy form looks like this:
```

```{code-block} python
:emphasize-lines: 1,8,9,12,14,21,22,25

TILE,       DSP_top
#direction  source   X-offset  Y-offset destination wires
NORTH,      N1BEG,   0,        1,       N1END,      4
EAST,       E1BEG,   1,        0,       E1END,      4
SOUTH,      S1BEG,   0,        -1,      S1END,      4
WEST,       W1BEG,   -1,       0,       W1END,      4
JUMP,       J_BEG,   0,        0,       J_END,      8
LOCAL,      NULL,    0,        0,       DSP2top,    10
LOCAL,      top2DSP, 0,        0,       NULL,       18
BEL,        ConfigBits.vhdl
MATRIX,     DSP_top_switch_matrix.vhdl
EndTILE

TILE,       DSP_bot
#direction  source   X-offset  Y-offset destination wires
NORTH,      N1BEG,   0,        1,       N1END,      4
EAST,       E1BEG,   1,        0,       E1END,      4
SOUTH,      S1BEG,   0,        -1,      S1END,      4
WEST,       W1BEG,   -1,       0,       W1END,      4
JUMP,       J_BEG,   0,        0,       J_END,      8
LOCAL,      NULL,    0,        0,       DSP2bot,    10
LOCAL,      bot2DSP, 0,        0,       NULL,       18
BEL,        ConfigBits.vhdl
MATRIX,     DSP_top_switch_matrix.vhdl
EndTILE
```

```{code-block} python
:emphasize-lines: 1,4,5

SuperTILE   DSP     # declare supertile DSP
DSP_top
DSP_bot
BEL,        MULADD.vhdl
EndTILE
```

(supertile-bel-routing)=

## Supertile BEL routing with SJUMP wires

```{admonition} Anchor tile vs. master tile
:class: note

A supertile has two independent reference tiles, and they are easy to confuse:

- The **anchor tile** ({ref}`above <supertiles>`) is the first non-NULL tile in a
  row-by-row scan (the top-left tile). It fixes where the supertile is _placed_ in the
  fabric and is purely structural.
- The **master tile** is where a supertile BEL and its configuration bits _live_. By
  default it is the **last** non-NULL tile in row-major order; an explicit `MASTER` token
  in the supertile CSV overrides this.

These are usually **different** tiles. In the DSP example the anchor is `DSP_top` (top)
while the master is `DSP_bot` (bottom), so the BEL, its ConfigMem, and the supertile
switch matrix all live in `DSP_bot` even though the wrapper is placed at `DSP_top`.
```

A BEL declared on the supertile (such as the `MULADD` block above) lives in the supertile's **master tile**,
but its operands and results usually need to reach the routing fabric of _every_ basic tile in the supertile - a multiplier,
for instance, may take its operands from the top tile and write its result back through the bottom tile.

Pins of a supertile BEL marked `EXTERNAL` behave exactly like those of a normal tile BEL: they are
exported through the supertile wrapper and become top-level ports of the fabric (named
`Tile_X{x}Y{y}_{pin}` at the supertile's anchor coordinates). A pin marked `EXTERNAL, SHARED_PORT`
(for example a shared `UserCLK`) is wired to the master tile's clock instead of being exported.

FABulous routes these BEL pins with **`SJUMP`** ("supertile jump") wires.
An `SJUMP` wire connects a basic tile's switch matrix to the BEL pins through a dedicated **supertile switch matrix**,
which lives alongside the supertile and is anchored at the master tile.
The wire's routing direction (which child tile connects to the master) is derived from the supertile layout,
so an `SJUMP` line carries **no spatial offset** - its `X-offset` and `Y-offset` must both be `0`.

A basic tile declares its `SJUMP` ports the same way as any other wire, but each line is **one-way**:
exactly one of `source_name`/`destination_name` must be `NULL`.
An `OUTPUT` direction (a non-`NULL` `source_name`, `NULL` destination) drives a signal _up_ to the supertile BEL;
an `INPUT` direction (`NULL` source, a non-`NULL` `destination_name`) receives a result _back_ from the BEL:

```{code-block} python
:emphasize-lines: 4,6

TILE,       DSP_bot
#direction  source   X-offset  Y-offset  destination  wires
# operand A leaves the tile for the supertile BEL
SJUMP,      A,       0,        0,        NULL,        8
# result Q returns from the supertile BEL into the tile
SJUMP,      NULL,    0,        0,        Q,           8
MATRIX,     DSP_bot_switch_matrix.list
EndTILE
```

The supertile switch matrix itself is described in a `.list` file (a `.csv` adjacency matrix is also accepted), referenced by a `MATRIX` line in the `SuperTILE` definition (the path is resolved relative to the supertile CSV). A supertile without a `MATRIX` line simply has no supertile switch matrix.
Each entry follows the usual `<destination>,<sources>` list convention, keying connections by destination:

```{code-block} text
# passthrough: a single source wired straight to a BEL input (no config bit)
SUPER_A0,           DSP_bot_A0
# multiplexed: pick one of four sources for a BEL input (2 mux-select bits)
{4}SUPER_B0,        [DSP_bot_B0|DSP_top_B0|DSP_bot_C0|DSP_top_C0]
# constant tie-off: drive a BEL input from a constant, or offer it as a mux input
SUPER_C0,           GND0
{2}SUPER_D0,        [VCC0|DSP_bot_D0]
# reverse path: a BEL output driving a tile's return wire
DSP_bot_Q0,       SUPER_Q0
```

Like a normal tile switch matrix, the supertile switch matrix declares the constant sources `GND0`/`GND` (`1'b0`) and `VCC0`/`VCC`/`VDD0`/`VDD` (`1'b1`), so they can be used as a source anywhere in the matrix - either as a fixed tie-off (one source) or as one option in a multiplexed input.

Every name in the matrix is validated when the supertile is parsed:
each sink (destination) must be a BEL input or a child-tile INPUT `SJUMP` wire, and each source must be a BEL output,
a child-tile OUTPUT `SJUMP` wire, or one of the constants above.

A passthrough connection (one source) consumes no configuration bits; a multiplexed connection adds the required mux-select bits.
These supertile configuration bits are organized in the supertile's own ConfigMem and physically programmed through the **master tile's** config frame.
This means that the master tile's configuration logic is left untouched,
so the master tile's own ConfigMem leaves them free.

```{admonition} Pin-name collisions
:class: note

If a supertile BEL exposes pin names that clash with a child tile's `SJUMP` port names, give the BEL a prefix in the tile CSV (for example `SUPER_`) so the master-tile nodes stay distinct. Use the prefixed names when wiring the supertile switch matrix.
```
