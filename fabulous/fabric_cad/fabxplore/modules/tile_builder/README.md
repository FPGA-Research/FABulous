# Tile Builder

`tile_builder` creates a complete FABulous tile package from BEL RTL files and a
small baseline switch-matrix policy. It is meant to be used from a fabxplore
architecture flow after synthesis and packing have produced the primitives that
should live in the new tile.

The builder writes the files that define the tile, then asks FABulous to parse
and generate the final RTL artifacts. It deliberately uses FABulous internals
where they already exist:

- BEL RTL is parsed with FABulous' `parseBelFile`.
- Base CSV routing rows are parsed with FABulous' `parsePortLine`.
- Switch-matrix port names are expanded with `Port.expandPortInfo`.
- Base `.list` files are read with FABulous' `parseList`.
- `custom_prims.v` is updated with FABulous' `addBelsToPrim`.
- Final switch matrix, config memory, and tile RTL are generated through
  `FABulous_API`.

The custom part is the baseline switch-matrix list. fabxplore can generate a
deterministic first `.list` file from BEL ports and base routing includes,
without relying on FABulous' generic `MATRIX,GENERATE` path.

The baseline matrix is intentionally modest. It is a valid starting point for
later FabGraph/PnR optimization passes that can add, delete, resize, or replace
matrix resources after the tile exists.

## Typical Use

In an architecture flow, call the PnR helper with flat options:

```python
self.pnr_tile_builder_pass(
    tile_name="LUT5F",
    bels=[
        {
            "verilog_path": self.my_root / "arch_rtl" / "FLUT5_1P_2PS.v",
            "prefixes": ["LA_", "LB_", "LC_", "LD_"],
            "add_as_custom_prim": True,
        },
        {
            "verilog_path": self.my_root / "arch_rtl" / "MUX8LUT_frame_config_mux.v",
            "prefixes": ["LM_"],
            "add_as_custom_prim": True,
        },
    ],
    use_fabulous_auto=False,
    base_csv_includes=["./../include/Base.csv"],
    base_list_includes=["../include/Base.list"],
    input_fanin=6,
    output_fanin=3,
    min_input_fanin=2,
    min_output_fanin=2,
    config_bit_margin=0,
    derive_sources_from_base=True,
    cover_unconnected_outputs=True,
    emit_constants_if_missing=True,
    allow_bel_output_feedback_sources=True,
    register_in_fabric=True,
    register_tile_in_fpga_model=True,
    track_progress=True,
    progress_chunk_size=5,
)
```

The lower-level Python API keeps the routing options grouped in
`BaselineRouting`:

```python
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.tile_builder import (
    BaselineRouting,
    TileBel,
    TileBuilder,
    TileBuilderOptions,
)

result = TileBuilder(
    TileBuilderOptions(
        tile_name="MY_TILE",
        bels=[
            TileBel(
                verilog_path=Path("rtl/my_bel.v"),
                prefixes=["A_", "B_"],
            )
        ],
        routing=BaselineRouting(
            use_fabulous_auto=False,
            base_csv_includes=["./../include/Base.csv"],
            base_list_includes=["../include/Base.list"],
            input_fanin=6,
            output_fanin=3,
            min_input_fanin=2,
            min_output_fanin=2,
        ),
    )
).build(fpga_model)
```

`fpga_model` is the active `PnRBridge`. The builder uses `fpga_model.fab` for
FABulous generation. When `register_tile_in_fpga_model=True`, it calls
`fpga_model.update_from_project()` after a successful build so the bridge graph
can see the new tile.

## Generated Files

For `tile_name="test_tile"`, the default output directory is:

```text
<project>/Tile/test_tile/
```

The builder creates or updates:

```text
Tile/test_tile/
|-- FLUT5_1P_2PS.v
|-- MUX8LUT_frame_config_mux.v
|-- test_tile.csv
|-- test_tile_switch_matrix.list
|-- test_tile_switch_matrix.csv
|-- test_tile_switch_matrix.v
|-- test_tile_ConfigMem.csv
|-- test_tile_ConfigMem.v
|-- test_tile.v
`-- command.txt

user_design/
`-- custom_prims.v

fabric.csv
```

When `use_fabulous_auto=True`, the builder writes `MATRIX,GENERATE` instead of
creating `<tile_name>_switch_matrix.list`.

`test_tile.csv` is the tile definition that FABulous parses. It can contain:

```text
TILE,test_tile
INCLUDE,./../include/Base.csv
NORTH,Co0,0,-1,Ci0,1,CARRY="C0"
JUMP,J_SRST_BEG,0,0,J_SRST_END,1,SHARED_RESET
JUMP,J_SEN_BEG,0,0,J_SEN_END,1,SHARED_ENABLE
BEL,./FLUT5_1P_2PS.v,LA_
BEL,./FLUT5_1P_2PS.v,LB_
MATRIX,./test_tile_switch_matrix.list
EndTILE
```

`test_tile_switch_matrix.list` is the compact routing graph. FABulous turns that
list into a matrix CSV and then switch-matrix RTL.

## Mental Model

FABulous switch matrices are represented as rows and columns:

```text
                destination / source columns
              +--------+--------+--------+
              | N1END0 | E1END0 | LA_O   |
+-------------+--------+--------+--------+
| LA_I0       |   1    |   1    |   1    |
| LA_I1       |   1    |   0    |   1    |
| N1BEG0      |   0    |   0    |   1    |
+-------------+--------+--------+--------+
  driven row
```

The `.list` file is a compact way to say which row can select which columns:

```text
{3}LA_I0,[N1END0|E1END0|LA_O]
{2}LA_I1,[N1END0|LA_O]
N1BEG0,LA_O
```

The first token is the switch-matrix output row. The second token is one or more
input sources. A row with multiple sources becomes a mux. A row with one source
becomes a direct connection and costs no config bits.

## Base Routing Discovery

The builder does not assume base names like `N1BEG`, `N1END`, `J2MID`, `AB`, or
`CD`. It derives names from the configured base CSV rows.

A base CSV row:

```text
NORTH,N1BEG,0,-1,N1END,4
```

is parsed with FABulous and expanded into:

```text
switch-matrix output rows:  N1BEG0, N1BEG1, N1BEG2, N1BEG3
switch-matrix input cols:   N1END0, N1END1, N1END2, N1END3
```

An arbitrary naming scheme works the same way:

```text
WEST,banana_out,-1,0,potato_in,2
```

expands to:

```text
switch-matrix output rows:  banana_out0, banana_out1
switch-matrix input cols:   potato_in0, potato_in1
```

`NULL` endpoints follow FABulous' `AutoSwitchMatrix` behavior. For example:

```text
NORTH,NULL,0,-2,TERM_IN,3
```

has no output rows, but creates six input columns because the distance is two
and the wire count is three:

```text
TERM_IN0, TERM_IN1, TERM_IN2, TERM_IN3, TERM_IN4, TERM_IN5
```

## Baseline Routing Algorithm

The baseline generator makes a valid first routing graph in seven steps.

### 1. Read Base Includes

`base_csv_includes` are recursively scanned. Every wire row is parsed through
FABulous.

`base_list_includes` are parsed with FABulous' list parser. These pairs are
preserved by emitting `INCLUDE` lines into the generated list:

```text
INCLUDE, ../include/Base.list
```

The builder also remembers which switch-matrix output rows are already covered
by the base list.

### 2. Parse BELs

Each `TileBel` source is copied into the tile directory and parsed once per
prefix:

```python
TileBel(
    verilog_path=Path("FLUT5_1P_2PS.v"),
    prefixes=["LA_", "LB_"],
)
```

This becomes two BEL instances:

```text
LA_<ports from FLUT5_1P_2PS>
LB_<ports from FLUT5_1P_2PS>
```

### 3. Separate Ordinary and Special BEL Ports

Ordinary BEL inputs and outputs are routeable through the switch matrix.

Carry ports are removed from ordinary routing and wired as a direct chain.

Local shared reset and enable ports are removed from ordinary routing and wired
through generated local jump wires.

### 4. Build the Source Pool for BEL Inputs

For ordinary BEL inputs, the source pool is:

```text
discovered base input columns
+ ordinary BEL outputs if allow_bel_output_feedback_sources=True
```

Example:

```text
base input columns:  N1END0, E1END0, S1END0
BEL outputs:         LA_O, LB_O

source pool:         N1END0, E1END0, S1END0, LA_O, LB_O
```

With `input_fanin=3`, one BEL input might get:

```text
{3}LA_I0,[N1END0|E1END0|S1END0]
```

and another might get a rotated selection:

```text
{3}LB_I0,[E1END0|S1END0|LA_O]
```

The rotation spreads choices across inputs instead of giving every input the
same first few sources.

### 5. Cover Unconnected Base Output Rows

FABulous requires every switch-matrix output row to have at least one source.
Some rows are already covered by `base_list_includes`. The builder covers the
remaining rows when `cover_unconnected_outputs=True`.

Example:

```text
base output rows:       N1BEG0, N1BEG1, E1BEG0
already in Base.list:   N1BEG0
uncovered rows:         N1BEG1, E1BEG0
```

The builder then emits connections for the uncovered rows:

```text
N1BEG1,LA_O
E1BEG0,LB_O
```

With larger `output_fanin`, those rows can become muxes:

```text
{3}N1BEG1,[LA_O|N1END0|E1END0]
```

### 6. Add Carry and Local Shared Routing

Carry is direct and ordered by carry group:

```text
LA_Ci,Ci00
LB_Ci,LA_Co
LC_Ci,LB_Co
Co00,LC_Co
```

The corresponding tile CSV boundary row looks like:

```text
NORTH,Co0,0,-1,Ci0,1,CARRY="C0"
```

Shared reset and enable use generated local jump wires:

```text
JUMP,J_SRST_BEG,0,0,J_SRST_END,1,SHARED_RESET
JUMP,J_SEN_BEG,0,0,J_SEN_END,1,SHARED_ENABLE
```

List connections then connect BEL shared ports to the local shared endpoints.
If the base does not provide constants, local constants can be emitted:

```text
JUMP,NULL,0,0,GND,1,
JUMP,NULL,0,0,VCC,1,
```

### 7. Fit the Config-Bit Budget

The builder estimates switch-matrix config bits from mux sizes:

```text
bits(row) = ceil(log2(number_of_sources_for_row))
```

In Python, this is:

```python
bits = (mux_size - 1).bit_length()
```

Examples:

```text
mux size 1 -> 0 bits
mux size 2 -> 1 bit
mux size 3 -> 2 bits
mux size 4 -> 2 bits
mux size 5 -> 3 bits
mux size 8 -> 3 bits
mux size 9 -> 4 bits
```

Total matrix bits are estimated as:

```text
matrix_bits = sum(ceil(log2(mux_size(row))) for every switch-matrix row)
```

The usable matrix budget is:

```text
matrix_budget = fabric_capacity - bel_config_bits - config_bit_margin
```

If the requested baseline matrix exceeds the budget, the builder tries smaller
fanins. It reduces `output_fanin` down to `min_output_fanin`, then reduces
`input_fanin` down to `min_input_fanin` and tries the output fanin choices again.

Example:

```text
requested: input_fanin=6, output_fanin=3
selected:  input_fanin=4, output_fanin=2
```

This means the requested tile was larger than the available matrix budget, so
the builder selected a smaller but still valid baseline matrix.

## Options

### `TileBuilderPass`

The pass is the public architecture-flow interface. It exposes the baseline
routing knobs directly instead of requiring a nested routing dictionary.

`tile_name`

Name of the generated FABulous tile.

`bels`

List of `TileBel` objects or dictionaries. Each entry points to one RTL file and
one or more prefixes.

`use_fabulous_auto`

When `True`, the tile CSV contains:

```text
MATRIX,GENERATE
```

FABulous then uses its own automated list generation path. When `False`,
fabxplore writes:

```text
MATRIX,./<tile_name>_switch_matrix.list
```

and generates that list itself.

`base_csv_includes`

Tile CSV fragments that describe shared base routing resources. Paths are
resolved relative to the generated tile directory. `None` selects the
`BaselineRouting` default:

```python
["./../include/Base.csv"]
```

`base_list_includes`

Switch-matrix list fragments that should be included in the generated list.
Paths are resolved relative to the generated tile directory. `None` selects the
`BaselineRouting` default:

```python
["../include/Base.list"]
```

`input_fanin`

Preferred number of sources for every ordinary BEL input mux.

Higher values improve possible routing into BELs, but cost more config bits:

```text
input_fanin=4

{4}LA_I0,[N1END0|E1END0|S1END0|LA_O]
```

The report field `Input fanin used` is the value selected after config-bit
fitting.

`output_fanin`

Preferred number of sources for uncovered base output rows.

Higher values improve the chance that signals can leave the tile through many
routing wires, but cost more config bits:

```text
output_fanin=3

{3}N1BEG0,[LA_O|N1END0|E1END0]
```

This controls routing-resource rows. `input_fanin` controls ordinary BEL inputs
such as `LA_I0`.

`min_input_fanin`

Lowest allowed input fanin during budget fitting. If the requested fanin is too
expensive, the builder may reduce `input_fanin`, but never below this value.

Use this when input access is a hard requirement:

```python
input_fanin=4
min_input_fanin=4
```

Then the builder must keep four sources per ordinary BEL input or fail clearly.

`min_output_fanin`

Lowest allowed output fanin during budget fitting.

`config_bit_margin`

Number of config bits to leave unused:

```text
matrix_budget = capacity - bel_config_bits - config_bit_margin
```

Use a margin when later optimization passes are expected to add routing or other
configurable resources.

`derive_sources_from_base`

When `True`, ordinary BEL inputs can select from discovered base input columns.

When `False`, ordinary BEL inputs only use other source classes, such as BEL
output feedback when enabled.

`cover_unconnected_outputs`

When `True`, the builder adds connections for discovered base output rows that
are not already covered by `base_list_includes`.

When `False`, the builder does not add that coverage. This is useful when the
base list is expected to describe all routing-resource output behavior.

`emit_constants_if_missing`

When `True`, the builder emits local GND/VCC jump rows if reset or enable wiring
needs them and the base did not provide them.

Generated rows:

```text
JUMP,NULL,0,0,GND,1,
JUMP,NULL,0,0,VCC,1,
```

When `False`, the builder assumes the base already provides any constants needed
by the generated routing.

`allow_bel_output_feedback_sources`

When `True`, ordinary BEL outputs can be used as sources for ordinary BEL inputs.
This gives local feedback and can improve routability inside the tile:

```text
{4}LA_I0,[N1END0|E1END0|LA_O|LB_O]
```

When `False`, ordinary BEL inputs only use base-derived sources.

`tile_dir`

Optional explicit output directory. Use this only when the tile should not be
generated under:

```text
<project>/Tile/<tile_name>
```

`config_bit_capacity_override`

Optional total config-bit capacity for one tile. `None` keeps the default
behavior: the pass queries the loaded FABulous fabric and uses:

```text
frameBitsPerRow * maxFramesPerCol
```

Set this only for architecture DSE where the frame capacity is intentionally
being changed together with the generated tile. This is a pass-level option
because it applies to the whole generated tile, not only to routing.

`register_in_fabric`

When `True`, the builder adds this line before `ParametersEnd` in `fabric.csv`
if it is missing:

```text
Tile,./Tile/<tile_name>/<tile_name>.csv
```

This makes FABulous able to load and generate the tile. The tile does not need
to be placed in the fabric grid yet; FABulous can keep it as an unused tile.

`register_tile_in_fpga_model`

When `True`, the builder asks the active `PnRBridge` to reload the project after
the tile was generated. This refreshes the FabGraph view so later PnR passes can
query or modify the new tile.

`track_progress`

When `True`, logs tile-builder progress messages.

`progress_chunk_size`

Number of BEL instances between progress messages.

### `TileBel`

`verilog_path`

Path to the Verilog or SystemVerilog BEL RTL. The file is copied into the
generated tile directory before FABulous parses it.

`prefixes`

List of instance prefixes. Every prefix creates one parsed BEL instance from the
same RTL file.

Example:

```python
TileBel(
    verilog_path=Path("FLUT5_1P_2PS.v"),
    prefixes=["LA_", "LB_", "LC_"],
)
```

emits tile CSV rows:

```text
BEL,./FLUT5_1P_2PS.v,LA_
BEL,./FLUT5_1P_2PS.v,LB_
BEL,./FLUT5_1P_2PS.v,LC_
```

`add_as_custom_prim`

When `True`, the parsed BEL is added to `user_design/custom_prims.v`. This is
normally needed so Yosys and nextpnr flows can understand the primitive name.

### `BaselineRouting`

`BaselineRouting` is the structured internal model used by `TileBuilderOptions`.
It has the same routing fields exposed by `TileBuilderPass`:

- `use_fabulous_auto`
- `base_csv_includes`
- `base_list_includes`
- `input_fanin`
- `output_fanin`
- `min_input_fanin`
- `min_output_fanin`
- `config_bit_margin`
- `derive_sources_from_base`
- `cover_unconnected_outputs`
- `emit_constants_if_missing`
- `allow_bel_output_feedback_sources`

Use `BaselineRouting` directly when constructing `TileBuilderOptions` in Python.
Use the flat fields when calling `pnr_tile_builder_pass`.

### `TileBuilderOptions`

`TileBuilderOptions` is the low-level bundle passed to `TileBuilder`. It contains:

- `tile_name`
- `bels`
- `routing`
- `tile_dir`
- `config_bit_capacity_override`
- `register_in_fabric`
- `register_tile_in_fpga_model`
- `track_progress`
- `progress_chunk_size`

Architecture flows usually do not need to instantiate this class directly.

## Config-Bit Example

Assume a tile has:

```text
BEL config bits: 290
fabric capacity: 640
config_bit_margin: 0
```

The matrix budget is:

```text
640 - 290 - 0 = 350
```

Suppose the generated list contains:

```text
20 rows with 4 sources each -> 20 * 2 = 40 bits
10 rows with 5 sources each -> 10 * 3 = 30 bits
30 rows with 1 source each  -> 30 * 0 = 0 bits
```

The estimated matrix cost is:

```text
40 + 30 + 0 = 70 bits
```

The total tile cost is:

```text
290 + 70 = 360 bits
```

If a larger baseline policy creates 400 matrix bits, the total would be:

```text
290 + 400 = 690 bits
```

That exceeds a 640-bit capacity. The builder then tries smaller fanins. If no
fanin between the requested values and the minimum values fits, the build fails
clearly after FABulous reports the real parsed tile size.

## Validity and Quality

The generated files are valid when FABulous can:

- parse the generated tile CSV,
- parse and apply the generated list,
- convert the list to a switch-matrix CSV,
- generate switch-matrix RTL,
- generate config-memory RTL and CSV,
- generate tile RTL,
- keep total config bits within the fabric capacity.

Validity does not mean the routing is optimal. The baseline routing is
intentionally simple and deterministic. It is a starting point for later
optimization passes, such as benchmark-driven wire removal/addition or
FabGraph-based routing analysis.

## Current Limitations

- The baseline generator is not benchmark-optimized.
- Fanin reduction is budget-driven, not timing- or routability-driven.
- Carry and local shared reset/enable use fixed generated helper names.
- The output-row coverage heuristic is conservative and may be sparse when the
  config-bit budget is tight.
- The generated tile can be valid while still being hard for nextpnr to route
  for some benchmarks. That is the next DSE layer.
- The builder does not generate switch-box route-through patterns. Add those in
  a later FabGraph/PnR pass where routability can be measured.

## Reading the Report

A successful run prints a report like:

```text
Tile Builder Report
Tile: test_tile
Directory: /path/to/project/Tile/test_tile

Configuration
- use_fabulous_auto: False
- input_fanin: 6
- output_fanin: 3
- min_input_fanin: 2
- min_output_fanin: 2
- config_bit_margin: 0
- base_csv_includes: ['./../include/Base.csv']
- base_list_includes: ['../include/Base.list']
- derive_sources_from_base: True
- cover_unconnected_outputs: True
- emit_constants_if_missing: True
- allow_bel_output_feedback_sources: True
- register_in_fabric: True
- register_tile_in_fpga_model: True

BELs
- Instances: 9
- Unique modules: 2
- FLUT5_1P_2PS: 8
- MUX8LUT_frame_config_mux: 1

Routing
- Matrix config bits: 268
- Input muxes: 60
- Output muxes: 108
- Direct connections: 49
- Input fanin used: 4
- Output fanin used: 1

Config Bits
- BEL config bits: 290
- Total config bits: 604
- Capacity: 640

Artifacts
- bel_rtl: /path/to/project/Tile/test_tile/FLUT5_1P_2PS.v
- matrix_list: /path/to/project/Tile/test_tile/test_tile_switch_matrix.list
- tile_csv: /path/to/project/Tile/test_tile/test_tile.csv
- fabric_csv: /path/to/project/fabric.csv
- switch_matrix: /path/to/project/Tile/test_tile/test_tile_switch_matrix.v
- config_memory: /path/to/project/Tile/test_tile/test_tile_ConfigMem.v
- tile_rtl: /path/to/project/Tile/test_tile/test_tile.v
- commands: /path/to/project/Tile/test_tile/command.txt

Warnings
- Reduced routing options to fit the matrix config-bit budget:
  input_fanin=4, output_fanin=1.
```

In this example, the requested routing policy was larger than the budget
allowed. The builder kept a valid tile by selecting smaller mux fanins and
reported the selected values.

## Next Optimization Step

After tile generation, call `register_tile_in_fpga_model=True` or explicitly
reload the bridge. Then a later pass can use FabGraph to inspect and edit the
new tile:

```python
graph = self.fpga_model
matrix = graph.switch_matrix("LUT5F")
bits = graph.get_config_bits("LUT5F")
counts = graph.get_resource_counts("LUT5F")
```

That later pass is the right place to add larger routing patterns, measure a
benchmark set with batch routing, and reduce or expand resources based on actual
routability.
