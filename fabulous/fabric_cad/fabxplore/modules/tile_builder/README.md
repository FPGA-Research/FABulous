# Tile Builder

`tile_builder` creates a complete FABulous tile package from BEL RTL files and a
small routing policy. It is meant to be used from a fabxplore architecture flow after
synthesis and packing have produced the primitives that should live in the new tile.

The pass writes the files that define the tile, then asks FABulous to parse and
generate the final RTL artifacts. It deliberately uses FABulous internals where they
already exist:

- BEL RTL is parsed with FABulous' `parseBelFile`.
- Base CSV routing rows are parsed with FABulous' `parsePortLine`.
- Switch-matrix port names are expanded with `Port.expandPortInfo("AutoSwitchMatrix")`.
- Base `.list` files are read with FABulous' `parseList`.
- `custom_prims.v` is updated with FABulous' `addBelsToPrim`.
- Final switch matrix, config memory, and tile RTL are generated through
  `FABulous_API`.

The custom part is the baseline routing policy: fabxplore can generate a valid
switch-matrix `.list` without relying on FABulous' current automated list generator,
which is still tied to a LUT4AB-style dummy list and has hard limits on BEL input and
output counts.

## Typical Use

```python
from fabulous.fabric_cad.fabxplore.modules.tile_builder import (
    BaselineRouting,
    TileBel,
)

self.pnr_tile_builder_pass(
    tile_name="test_tile",
    bels=[
        TileBel(
            verilog_path=self.my_root / "arch_rtl" / "FLUT5_1P_2PS.v",
            prefixes=["LA_", "LB_", "LC_", "LD_", "LE_", "LF_", "LG_", "LH_"],
        ),
        TileBel(
            verilog_path=self.my_root / "arch_rtl" / "MUX8LUT_frame_config_mux.v",
            prefixes=["LM_"],
        ),
    ],
    routing=BaselineRouting(
        use_fabulous_auto=False,
        base_csv_includes=["./../include/Base.csv"],
        base_list_includes=["../include/Base.list"],
        routing_pip_pattern="wilton",
        routing_pip_fs=3,
        min_routing_pip_fs=1,
        generate_straight_routing_pips=True,
        generate_turn_routing_pips=True,
        connection_hierarchy={
            "enabled": True,
            "levels": [4],
            "generate_jump_ports": True,
            "jump_prefix": "J_LOCAL",
            "replace_direct_input_pips": True,
        },
        input_fanin=4,
        output_fanin=5,
        min_input_fanin=1,
        min_output_fanin=1,
        config_bit_margin=0,
    ),
    config_bit_capacity_override=None,
)
```

The same interface also accepts dictionaries:

```python
self.pnr_tile_builder_pass(
    tile_name="test_tile",
    bels=[
        {
            "verilog_path": self.my_root / "arch_rtl" / "FLUT5_1P_2PS.v",
            "prefixes": ["LA_", "LB_", "LC_", "LD_"],
        },
    ],
    routing={
        "base_csv_includes": ["./../include/Base.csv"],
        "base_list_includes": ["../include/Base.list"],
        "routing_pip_pattern": "subset",
        "routing_pip_fs": 3,
        "min_routing_pip_fs": 1,
        "connection_hierarchy": {
            "enabled": True,
            "levels": [4, 2],
        },
        "input_fanin": 4,
        "output_fanin": 5,
    },
    config_bit_capacity_override=None,
)
```

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

`test_tile.csv` is the tile definition that FABulous parses. It contains:

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

`test_tile_switch_matrix.list` is the active routing graph. FABulous turns that
list into a matrix CSV and then switch-matrix RTL.

## Mental Model

FABulous switch matrices are represented as rows and columns:

```text
                destination / sink columns
              +--------+--------+--------+
              | N1END0 | E1END0 | LA_O   |
+-------------+--------+--------+--------+
| LA_I0       |   1    |   1    |   1    |
| LA_I1       |   1    |   0    |   1    |
| N1BEG0      |   0    |   0    |   1    |
+-------------+--------+--------+--------+
  source /
  driven row
```

The `.list` file is a compact way to say which row can select which columns:

```text
{3}LA_I0,[N1END0|E1END0|LA_O]
{2}LA_I1,[N1END0|LA_O]
N1BEG0,LA_O
```

The first token is the switch-matrix output row. The second token is one or more input
sources. A row with multiple sources becomes a mux. A row with one source becomes a
direct connection.

## Base Routing Discovery

The builder does not assume base names like `N1BEG`, `N1END`, `J2MID`, `AB`, or `CD`.
It derives names from the configured base CSV rows.

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

has no output rows, but creates six input columns because the distance is two and the
wire count is three:

```text
TERM_IN0, TERM_IN1, TERM_IN2, TERM_IN3, TERM_IN4, TERM_IN5
```

## Routing PIP Patterns

`routing_pip_pattern` adds route-through PIPs between routing resources that were
discovered from the base CSV includes. It does not create new tracks or new segment
lengths; those belong to the base CSV layer. A pattern is simply an algorithm that
chooses which switch-matrix rows may select which switch-matrix columns.

In matrix form, a pattern decides where to place `1`s:

```text
              selectable sources
              COL_A0  COL_A1  COL_B0  COL_B1
destination +------+------+------+------+
ROW_A0      |  1   |  0   |  1   |  0   |
ROW_A1      |  0   |  1   |  0   |  1   |
ROW_B0      |  1   |  0   |  1   |  0   |
ROW_B1      |  0   |  1   |  0   |  1   |
```

In `.list` form, the same matrix is:

```text
{2}ROW_A0,[COL_A0|COL_B0]
{2}ROW_A1,[COL_A1|COL_B1]
{2}ROW_B0,[COL_A0|COL_B0]
{2}ROW_B1,[COL_A1|COL_B1]
```

Patterns are useful because routing architecture is a trade-off. More PIPs generally
give more choices to the router, but each mux input can increase area, delay, and
configuration bits. A regular pattern gives those choices in a predictable way instead
of producing a random pile of connections. Regularity matters for experiments because
it makes a design easier to understand, compare, reproduce, and later map to layout or
timing assumptions.

Supported values are:

```text
none
  Do not add extra routing-resource PIPs.

subset
  Connect same-index tracks across compatible routing groups.

wilton
  Connect tracks through a side-dependent permutation so turns change track index.

universal
  Add locally diverse source choices up to routing_pip_fs per destination row.
```

The pattern generator only sees normalized resources derived from FABulous `Port`
objects. Names are treated as opaque identifiers. For example, if the base provides:

```text
NORTH,ROW_A,0,-1,COL_A,2
EAST,ROW_B,1,0,COL_B,2
```

then `routing_pip_pattern="subset"` and `routing_pip_fs=2` can emit:

```text
{2}ROW_A0,[COL_A0|COL_B0]
{2}ROW_A1,[COL_A1|COL_B1]
{2}ROW_B0,[COL_A0|COL_B0]
{2}ROW_B1,[COL_A1|COL_B1]
```

`routing_pip_fs` is reduced down to `min_routing_pip_fs` when the generated
switch matrix would exceed the config-bit budget.
`generate_straight_routing_pips` controls same-direction route-throughs.
`generate_turn_routing_pips` controls direction-changing route-throughs. Existing
`base_list_includes` are preserved and duplicate generated pairs are removed.

### What the Current Patterns Do

`none`

No route-through PIPs are added by the pattern layer. The generated list still contains
base includes, BEL input muxes, output-row coverage, carry, reset/enable, constants,
and optional local feedback.

```text
pattern contribution: none
```

This is useful when the base list already describes the routing fabric, or when the
tile should only add BEL/local connections.

`subset`

Subset connects same-index tracks across compatible routing groups. It is regular and
cheap, but it tends to keep each track in its own domain.

```text
ROW_A0 <- COL_A0, COL_B0
ROW_A1 <- COL_A1, COL_B1
ROW_A2 <- COL_A2, COL_B2
```

ASCII view:

```text
track 0: A0 <----> B0
track 1: A1 <----> B1
track 2: A2 <----> B2
```

`wilton`

Wilton uses a side-dependent permutation. A straight connection can keep the same
track, while a turn can move to a different track. This breaks the isolated same-track
domains that subset can create.

```text
ROW_A0 <- COL_A0, COL_B1
ROW_A1 <- COL_A1, COL_B2
ROW_A2 <- COL_A2, COL_B0
```

ASCII view:

```text
track 0 turns into track 1
track 1 turns into track 2
track 2 turns into track 0
```

This is inspired by the Wilton switch block used in VPR/VTR-style routing
architectures. The implementation is derived from normalized FABulous routing groups,
so it does not depend on names like `N1BEG` or `E2END`.

`universal`

Universal tries to give each destination row a locally diverse set of source choices.
It walks compatible source groups and then advances the track offset until
`routing_pip_fs` choices have been collected.

```text
ROW_A0 <- COL_A0, COL_B0, COL_A1
ROW_A1 <- COL_A1, COL_B1, COL_A2
ROW_A2 <- COL_A2, COL_B2, COL_A0
```

This is usually denser than subset for the same resources and can increase local
flexibility, but the exact value still depends on config-bit budget and later routing
evaluation.

### Adding a New Pattern

Patterns live in:

```text
fabulous/fabric_cad/fabxplore/modules/tile_builder/routing_patterns/
```

Shared models live in:

```text
fabulous/fabric_cad/fabxplore/modules/tile_builder/core/models.py
```

To add a new pattern:

1. Add an enum value:

```python
class RoutingPipPattern(StrEnum):
    MY_PATTERN = "my_pattern"
```

2. Add a generator file:

```text
tile_builder/routing_patterns/my_pattern.py
```

3. Implement a function that consumes normalized resources and returns pairs:

```python
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    RoutingPatternContext,
    RoutingPatternResult,
)


def generate_my_pattern(context: RoutingPatternContext) -> RoutingPatternResult:
    pairs = []
    for group in context.groups:
        for index, row in enumerate(group.destination_rows):
            if not group.selectable_sources:
                continue
            source = group.selectable_sources[index % len(group.selectable_sources)]
            pairs.append((row, source))

    pairs = list(dict.fromkeys(pairs))
    return RoutingPatternResult(
        pairs=pairs,
        generated_pips=len(pairs),
        compatible_groups=len(context.groups),
    )
```

4. Register it in `routing_patterns/registry.py`:

```python
_PATTERN_GENERATORS[RoutingPipPattern.MY_PATTERN] = generate_my_pattern
```

After that, the architecture flow can use:

```python
"routing_pip_pattern": "my_pattern"
```

The important rule is that pattern files should not parse FABulous CSV/list files.
They receive `RoutingTrackGroup` objects that were already derived from FABulous
`Port` objects. A pattern only decides this:

```text
which destination row can select which source column
```

### Modeling Hierarchies with Patterns

Hierarchical routing means that not every routing resource has the same role. You may
want short local wires, medium inter-tile wires, long wires, or special high-capacity
groups. FABulous expresses the available resources in CSV rows:

```text
EAST,LOCAL_E_BEG,1,0,LOCAL_E_END,8
EAST,MID_E_BEG,2,0,MID_E_END,4
EAST,LONG_E_BEG,4,0,LONG_E_END,2
```

`tile_builder` currently derives the structural metadata for each row:

```text
direction, x_offset, y_offset, wire_count, expanded rows, expanded sources
```

That is enough for future patterns to model hierarchy without relying on names. A
hierarchical pattern could, for example:

- connect local-to-local with `subset`,
- connect local turns with `wilton`,
- allow fewer PIPs from local to long wires,
- protect long-wire entries from becoming too dense,
- give special groups a different `Fs`.

Conceptually:

```text
local group    Fs=3   dense turns, good for nearby logic
medium group   Fs=2   moderate route-through capacity
long group     Fs=1   sparse access, good for global movement
```

This is useful for DSE because it lets us ask architecture questions:

```text
Does a regular local mesh plus sparse long-wire access route better?
Does Wilton only on local turns help more than Wilton everywhere?
How much config memory is spent by long-wire flexibility?
```

Those questions should later be answered by the demand evaluator and nextpnr-backed
confirmation pass. The tile builder only generates the candidate matrix.

## Connection Hierarchy with JUMP Wires

`connection_hierarchy` is separate from `routing_pip_pattern`.

`routing_pip_pattern` controls switch-box style route-through choices:

```text
routing wire -> routing wire
```

`connection_hierarchy` controls connection-block style BEL input access:

```text
routing wire -> generated JUMP wire -> BEL input
```

FABulous models hierarchy with `JUMP` wires. A JUMP is a local stop-over inside the
same switch matrix. It can collect a set of sources, then expose a new selectable
source for later rows. This lets tile_builder build staged local muxes instead of one
large flat mux for every BEL input.

Flat input mux:

```text
WIRE0 \
WIRE1  \
WIRE2   \
WIRE3    -> LA_I0
WIRE4   /
WIRE5  /
WIRE6 /
WIRE7
```

Equivalent `.list` shape:

```text
{8}LA_I0,[WIRE0|WIRE1|WIRE2|WIRE3|WIRE4|WIRE5|WIRE6|WIRE7]
```

One-level hierarchy with `levels=[4]`:

```text
WIRE0 \
WIRE1  -> J_LOCAL_L0_0 \
WIRE2 /                  \
WIRE3                    -> LA_I0
WIRE4 \                  /
WIRE5  -> J_LOCAL_L0_1 /
WIRE6 /
WIRE7
```

Generated tile CSV rows:

```text
JUMP,J_LOCAL_L0_0_BEG,0,0,J_LOCAL_L0_0_END,1,
JUMP,J_LOCAL_L0_1_BEG,0,0,J_LOCAL_L0_1_END,1,
```

Generated list rows:

```text
{4}J_LOCAL_L0_0_BEG0,[WIRE0|WIRE1|WIRE2|WIRE3]
{4}J_LOCAL_L0_1_BEG0,[WIRE4|WIRE5|WIRE6|WIRE7]
{2}LA_I0,[J_LOCAL_L0_0_END0|J_LOCAL_L0_1_END0]
```

Two-level hierarchy with `levels=[4, 2]`:

```text
WIRE0..WIRE3 -> J_LOCAL_L0_0 \
WIRE4..WIRE7 -> J_LOCAL_L0_1  -> J_LOCAL_L1_2 -> LA_I0
```

Generated list rows:

```text
{4}J_LOCAL_L0_0_BEG0,[WIRE0|WIRE1|WIRE2|WIRE3]
{4}J_LOCAL_L0_1_BEG0,[WIRE4|WIRE5|WIRE6|WIRE7]
{2}J_LOCAL_L1_2_BEG0,[J_LOCAL_L0_0_END0|J_LOCAL_L0_1_END0]
LA_I0,J_LOCAL_L1_2_END0
```

The `levels` list is intentionally compact:

```text
levels=[4]     source groups of four, then BEL input
levels=[4, 2]  source groups of four, then groups of two, then BEL input
levels=[8, 2]  wider first stage, narrow final stage
```

This is generic enough to describe many staged mux trees without adding one option for
every mux size. The report tells you how many JUMP wires were generated, how many PIPs
feed hierarchy rows, how many PIPs feed BEL inputs from hierarchy outputs, and how the
chosen structure affected config bits.

### How Fanin Activates Hierarchy Levels

`input_fanin` is the number of source choices selected for each ordinary BEL input
before optional hierarchy is built. It is not the number of hierarchy levels. The
hierarchy can only create a new level while there is more than one source to combine.

With a flat mux:

```text
input_fanin=4

WIRE0 \
WIRE1  \
WIRE2   -> LA_I0
WIRE3  /
```

With `connection_hierarchy.levels=[2, 2]`, the same four sources become two active
levels:

```text
WIRE0 \
WIRE1  -> J_LOCAL_L0_0 \
WIRE2 \                  -> J_LOCAL_L1_2 -> LA_I0
WIRE3  -> J_LOCAL_L0_1 /
```

The first level groups the four input sources into two generated JUMP sources. The
second level groups those two generated sources into one final JUMP source.

With `connection_hierarchy.levels=[4, 2, 2]` and the same `input_fanin=4`, only one
level is active:

```text
WIRE0 \
WIRE1  \
WIRE2   -> J_LOCAL_L0_0 -> LA_I0
WIRE3  /
```

The first level can collect all four sources into one JUMP. After that, there is only
one source left, so the later configured levels have nothing to combine. This is why a
report may say:

```text
Input fanin used: 4
Connection hierarchy configured levels: (4, 2, 2)
Connection hierarchy active levels: (4,)
```

To make multiple levels active, either choose smaller early levels or request more
input fanin:

```text
levels=[2, 2], input_fanin_used=4  -> active levels: (2, 2)
levels=[4, 2], input_fanin_used=8  -> active levels: (4, 2)
levels=[4, 2], input_fanin_used=4  -> active levels: (4,)
levels=[8, 2], input_fanin_used=8  -> active levels: (8,)
```

The config-bit fitter may also reduce the requested `input_fanin`. If that happens,
the active hierarchy levels are computed from `Input fanin used`, not from the original
requested `input_fanin`.

The configured hierarchy levels are the levels requested by the user. The active
hierarchy levels are the levels that actually generated JUMP wires after the builder
selected a budget-fitting fanin. This distinction matters because the config-bit
fitter may reduce `input_fanin`.

For example, with:

```python
connection_hierarchy={"enabled": True, "levels": [4, 3]}
input_fanin=4
min_input_fanin=1
```

the report can still show:

```text
Input fanin used: 2
Connection hierarchy configured levels: (4, 3)
Connection hierarchy active levels: (4,)
```

Only the first hierarchy level is active because each BEL input receives two sources.
Two sources can be collected by one level-0 JUMP, so the second configured level never
has multiple level-0 outputs to combine. If `input_fanin` is reduced to one, no JUMP
wire is needed at all; the input is counted under `Hierarchy bypassed inputs`.

### Why Use Connection Hierarchy?

Hierarchy is useful when a flat input mux is too large, too irregular, or too hard to
compare across experiments. It lets the architecture describe local structure:

```text
switch-box routing choices       routing_pip_pattern
connection-block BEL access      connection_hierarchy
special carry/reset/enable       dedicated FABulous annotations
```

That separation is important. A Wilton-like switch box can coexist with hierarchical
BEL input access:

```python
routing={
    "routing_pip_pattern": "wilton",
    "routing_pip_fs": 3,
    "connection_hierarchy": {
        "enabled": True,
        "levels": [4],
    },
}
```

The result is:

```text
routing -> routing          generated by the Wilton pattern
routing -> JUMP -> BEL      generated by the connection hierarchy
```

The current hierarchy is pattern-preserving at the switch-box layer. It keeps the
route-through PIPs generated by `routing_pip_pattern` intact and adds staged BEL-input
access separately. It does not regroup routing-pattern PIPs by direction, wire length,
or track class.

This is an important but limited guarantee:

```text
preserved:
  routing wire -> routing wire PIPs from routing_pip_pattern

changed:
  how ordinary BEL inputs see their selected source choices
```

So `connection_hierarchy` does not invalidate a Wilton/subset/universal switch-box
pattern, but it still changes the BEL-input connection block by inserting JUMP stages.
Future grouping policies may intentionally change this behavior, but the current
default only chunks the selected source order.

### Why There Is No Semantic Grouping Option Yet

In a hierarchical connection block, grouping means deciding which sources are hidden
behind the same first-level JUMP before the final BEL input mux sees them.

For example, direction grouping would intentionally build:

```text
N0,N1 -> J_N
E0,E1 -> J_E
S0,S1 -> J_S
W0,W1 -> J_W

J_N,J_E,J_S,J_W -> LUT_I0
```

Other useful grouping variants could be:

```text
ordered
  Use the selected source order and chunk it by levels. This is the current behavior.

direction
  Group NORTH/EAST/SOUTH/WEST-like resources separately.

wire_length
  Group single, double, quad, hex, or long-wire classes separately.

source_kind
  Group base routing, BEL feedback, constants, and local helper wires separately.

track_class
  Group sources according to pattern-specific track classes.

demand_driven
  Group sources using benchmark or generated-demand statistics.
```

Grouping can be useful, but it is not a neutral transformation. It changes which
alternatives remain independent at the final BEL input mux.

```text
flat:
  N0,N1,E0,E1,S0,S1,W0,W1 -> LUT_I0

direction grouped:
  N0,N1 -> J_N
  E0,E1 -> J_E
  S0,S1 -> J_S
  W0,W1 -> J_W
  J_N,J_E,J_S,J_W -> LUT_I0
```

The direction-grouped version gives the final mux one representative from each
direction, which can be good for physical regularity and direction balance. It can
also be bad when a design would benefit from several independent choices from the same
direction.

This interacts with `routing_pip_pattern`. A Wilton-like pattern may already create a
carefully interleaved source order:

```text
N0, E1, S2, W3, N1, E2, S3, W0
```

If tile_builder then regrouped by direction, it would discard that ordering:

```text
J_N = N0,N1
J_E = E1,E2
J_S = S2,S3
J_W = W3,W0
```

That may still be a valid architecture, but it is a different architecture. For that
reason, tile_builder does not currently add a semantic grouping option. The pass
generates the logical routing pattern first and then only factors ordinary BEL input
access by ordered chunks. More aggressive grouping should be driven by a later demand
evaluator or optimization pass, where the effect on routability can be measured.

### Connection Hierarchy Options

`enabled`

When `True`, ordinary BEL inputs are fed through generated hierarchy JUMP stages.
When `False`, BEL input muxes are flat.

`levels`

List of maximum fanins for hierarchy stages. Each value must be at least two when
hierarchy is enabled.

```python
levels=[4]
levels=[4, 2]
levels=[8, 4, 2]
```

`generate_jump_ports`

When `True`, tile_builder emits the generated JUMP rows into the tile CSV. This is the
normal setting.

When `False`, tile_builder still generates list PIPs that reference the hierarchy
names, but assumes those JUMP resources are supplied elsewhere. Use this only when a
base or custom tile CSV already defines the matching resources.

`jump_prefix`

Prefix used for generated JUMP names.

```python
jump_prefix="J_LOCAL"
```

creates names such as:

```text
J_LOCAL_L0_0_BEG0
J_LOCAL_L0_0_END0
```

`replace_direct_input_pips`

When `True`, generated hierarchy PIPs replace direct source-to-BEL input PIPs:

```text
WIRE -> JUMP -> LA_I0
```

When `False`, hierarchy PIPs are added in addition to the direct choices:

```text
WIRE -> JUMP -> LA_I0
WIRE --------> LA_I0
```

This is denser and usually costs more config bits, but it can be useful when testing
whether hierarchy should augment or replace flat input access.

## Baseline Routing Algorithm

The baseline generator makes a valid first routing graph in eight steps.

### 1. Read Base Includes

`base_csv_includes` are recursively scanned. Every wire row is parsed through FABulous.

`base_list_includes` are parsed with FABulous' list parser. These pairs are preserved
by emitting `INCLUDE` lines into the generated list.

```text
INCLUDE, ../include/Base.list
```

The builder also remembers which switch-matrix output rows are already covered by the
base list.

### 2. Parse BELs

Each `TileBel` source is copied into the tile directory and parsed once per prefix.

```python
TileBel(
    verilog_path=Path("FLUT5_1P_2PS.v"),
    prefixes=["LA_", "LB_"],
)
```

becomes two BEL instances:

```text
LA_<ports from FLUT5_1P_2PS>
LB_<ports from FLUT5_1P_2PS>
```

### 3. Separate Ordinary and Special BEL Ports

Ordinary BEL inputs and outputs are routeable through the switch matrix.

Carry ports are removed from ordinary routing and wired as a direct chain.

Local shared reset and enable ports are removed from ordinary routing and wired through
generated local jump wires.

### 4. Build the Source Pool for BEL Inputs

For ordinary BEL inputs, the source pool is:

```text
discovered base input columns
+ ordinary BEL outputs if allow_bel_output_feedback_sources=True
```

ASCII example:

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

The rotation spreads choices across inputs instead of giving every input the same
first few sources.

### 5. Optionally Stage BEL Input Access Through JUMPs

When `connection_hierarchy.enabled=True`, the source pool chosen for each ordinary BEL
input is staged through generated JUMP wires. The chosen hierarchy levels decide how
many sources each stage may collect.

```text
source pool -> JUMP level 0 -> JUMP level 1 -> BEL input
```

When `replace_direct_input_pips=True`, the direct flat BEL input PIPs are replaced by
the hierarchy. When it is `False`, both direct and hierarchical PIPs are emitted.

### 6. Cover Unconnected Base Output Rows

FABulous requires every switch-matrix output row to have at least one source. Some rows
are already covered by `base_list_includes`. The builder covers the remaining rows when
`cover_unconnected_outputs=True`.

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

### 7. Add Carry and Local Shared Routing

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

List connections then connect BEL shared ports to the local shared endpoints. If the
base does not provide constants, local constants can be emitted:

```text
JUMP,NULL,0,0,GND,1,
JUMP,NULL,0,0,VCC,1,
```

### 8. Fit the Config-Bit Budget

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

For a frame capacity of 640 bits and BELs that use 290 bits:

```text
matrix_budget = 640 - 290 - 0 = 350 bits
```

If the requested routing policy exceeds the budget, the builder reduces options. It
first reduces `routing_pip_fs` down to `min_routing_pip_fs`, then reduces
`output_fanin` down to `min_output_fanin`, then reduces `input_fanin` and tries again.

Example:

```text
requested: input_fanin=4, output_fanin=5, routing_pip_fs=3
selected:  input_fanin=4, output_fanin=5, routing_pip_fs=1
```

This means BEL and output-row fanins stayed at their preferred values, but the
generated route-through pattern was made sparser so the tile could fit.

## Options

### `TileBuilderPass`

`tile_name`

Name of the generated FABulous tile. The default tile directory is:

```text
<project>/Tile/<tile_name>
```

`bels`

List of `TileBel` objects or dictionaries. Each entry points to one RTL file and one
or more prefixes.

`routing`

`BaselineRouting`, dictionary, or `None`. `None` selects defaults.

`tile_dir`

Optional explicit output directory. Use this only when the tile should not be generated
under `<project>/Tile/<tile_name>`.

`config_bit_capacity_override`

Optional total config-bit capacity for one tile. `None` keeps the default behavior:
the pass queries the loaded FABulous fabric and uses:

```text
frameBitsPerRow * maxFramesPerCol
```

Set this only for architecture DSE where the frame capacity is intentionally being
changed together with the generated tile. This is a pass-level option because it
applies to the whole generated tile, not only to routing.

`register_in_fabric`

When `True`, the builder adds this line before `ParametersEnd` in `fabric.csv` if it is
missing:

```text
Tile,./Tile/<tile_name>/<tile_name>.csv
```

This makes FABulous able to load and generate the tile. The tile does not need to be
placed in the fabric grid yet; FABulous can keep it in `unusedTileDic`.

`track_progress`

When `True`, logs tile-builder progress messages.

`progress_chunk_size`

Number of BEL instances between progress messages.

### `TileBel`

`verilog_path`

Path to the Verilog or SystemVerilog BEL RTL. The file is copied into the generated
tile directory before FABulous parses it.

`prefixes`

List of instance prefixes. Every prefix creates one parsed BEL instance from the same
RTL file.

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

When `True`, the parsed BEL is added to `user_design/custom_prims.v`. This is normally
needed so Yosys/nextpnr flows can understand the primitive name.

### `BaselineRouting`

`use_fabulous_auto`

When `True`, the tile CSV contains:

```text
MATRIX,GENERATE
```

FABulous then uses its own automated list generation path. This is useful as a
reference or for simple tiles. For larger custom tiles, it can hit the old automated
limits.

When `False`, fabxplore writes:

```text
MATRIX,./<tile_name>_switch_matrix.list
```

and generates the list itself.

`input_fanin`

Preferred number of sources for every ordinary BEL input mux.

Higher values improve possible routing into BELs, but cost more config bits.

```text
input_fanin=4

{4}LA_I0,[N1END0|E1END0|S1END0|LA_O]
```

When `connection_hierarchy.enabled=True`, `input_fanin` still means the number of
source choices for each ordinary BEL input. The hierarchy decides how those choices are
staged.

```text
input_fanin=4, levels=[2, 2]

four source choices -> two level-0 JUMPs -> one level-1 JUMP -> BEL input
```

The report field `Input fanin used` is the value selected after config-bit fitting.
That selected value is what determines how many hierarchy levels can become active.
For example, if `input_fanin=4` but the report says `Input fanin used: 2`, then a
second hierarchy level cannot be active because only two sources remain.

`output_fanin`

Preferred number of sources for uncovered base output rows.

Higher values improve the chance that signals can leave the tile through many routing
wires, but cost more config bits.

```text
output_fanin=3

{3}N1BEG0,[LA_O|N1END0|E1END0]
```

This controls routing-resource rows, not BEL input hierarchy. In other words,
`output_fanin` affects how many sources can drive uncovered base output rows such as
`N1BEG0`; `input_fanin` affects how many sources feed ordinary BEL inputs such as
`LA_I0`.

`min_input_fanin`

Lowest allowed input fanin during budget fitting. If the requested fanin is too
expensive, the builder may reduce `input_fanin`, but never below this value.

Use this to make hierarchy depth an explicit requirement. For example, if
`levels=[2, 2]` should really produce two active levels, set:

```python
input_fanin=4
min_input_fanin=4
```

Then the builder must keep four sources per ordinary BEL input or fail clearly instead
of silently reducing to a one-level hierarchy.

`min_output_fanin`

Lowest allowed output fanin during budget fitting.

`routing_pip_pattern`

Route-through pattern for routing-resource to routing-resource PIPs. Supported values:

```text
none, subset, wilton, universal
```

This option only affects PIPs between routing resources discovered from
`base_csv_includes`. It does not create base wires, change segment lengths, or replace
BEL/local/special wiring.

`routing_pip_fs`

Preferred switch-block flexibility for generated routing-resource PIPs. It is the
maximum number of generated route-through source choices per destination row.

```text
routing_pip_fs=3

ROW_A0 can receive up to three generated routing sources.
```

Higher values usually improve local routing flexibility but increase mux sizes and
config-bit use.

`min_routing_pip_fs`

Lowest allowed `routing_pip_fs` during budget fitting. If `routing_pip_fs=3` exceeds
the config-bit budget and `min_routing_pip_fs=1`, the builder may try `2` and then `1`
before reducing other fanins or failing.

`generate_straight_routing_pips`

When `True`, pattern generators may connect routing groups with the same direction.

```text
EAST group -> EAST group
```

This can model straight route-through capacity. Disable it when the base list already
contains enough pass-through wiring or when config bits are tight.

`generate_turn_routing_pips`

When `True`, pattern generators may connect routing groups with different directions.

```text
NORTH group -> EAST group
EAST group  -> SOUTH group
```

This is the main knob for switch-box turns. Wilton-style behavior is most interesting
when turns are enabled.

`config_bit_margin`

Number of config bits to leave unused. This is subtracted from the available matrix
budget.

```text
matrix_budget = capacity - bel_config_bits - config_bit_margin
```

Use a margin when you expect later optimization passes to add routing or config
features.

`base_csv_includes`

Tile CSV fragments that describe shared base routing resources. Paths are resolved
relative to the generated tile directory. Multiple includes are allowed.

```python
base_csv_includes=[
    "./../include/Base.csv",
    "./../include/ExtraHorizontal.csv",
]
```

Every base CSV `INCLUDE` is also expanded recursively while discovering routing
resources.

`base_list_includes`

Switch-matrix list fragments that should be included in the generated list. Paths are
resolved relative to the generated tile directory.

```python
base_list_includes=[
    "../include/Base.list",
    "../include/ExtraHorizontal.list",
]
```

The generated list keeps them as includes:

```text
INCLUDE, ../include/Base.list
INCLUDE, ../include/ExtraHorizontal.list
```

`derive_sources_from_base`

When `True`, ordinary BEL inputs can select from discovered base input columns.

When `False`, ordinary BEL inputs only use other source classes, such as BEL output
feedback when enabled.

`cover_unconnected_outputs`

When `True`, the builder adds connections for discovered base output rows that are not
already covered by `base_list_includes`.

When `False`, all discovered base output rows are considered for generated coverage.
This can intentionally override or augment base behavior, but usually costs more bits.

`emit_constants_if_missing`

When `True`, the builder emits local GND/VCC jump rows if reset or enable wiring needs
them and the base did not provide them.

Generated rows:

```text
JUMP,NULL,0,0,GND,1,
JUMP,NULL,0,0,VCC,1,
```

When `False`, the builder assumes the base already provides any constants needed by
the generated routing.

`allow_bel_output_feedback_sources`

When `True`, ordinary BEL outputs can be used as sources for ordinary BEL inputs.

This gives local feedback and can improve routability inside the tile:

```text
{4}LA_I0,[N1END0|E1END0|LA_O|LB_O]
```

When `False`, ordinary BEL inputs only use base-derived sources.

`connection_hierarchy`

Optional `ConnectionHierarchyOptions` object or dictionary. This controls whether
ordinary BEL input muxes are staged through generated FABulous `JUMP` wires.

```python
connection_hierarchy={
    "enabled": True,
    "levels": [4, 2],
    "generate_jump_ports": True,
    "jump_prefix": "J_LOCAL",
    "replace_direct_input_pips": True,
}
```

The hierarchy only affects ordinary BEL input access. It does not change carry,
shared reset/enable, BEL output routing, or route-through switch-box PIPs.

### `ConnectionHierarchyOptions`

`enabled`

Enable or disable generated JUMP hierarchy for ordinary BEL inputs.

`levels`

Maximum fanin for each hierarchy stage. The list length is the number of generated
hierarchy stages. Examples:

```text
[4]       one JUMP stage, each JUMP collects up to 4 sources
[4, 2]    first stage collects up to 4, second stage collects up to 2
[8, 4]    wider first stage, then smaller second stage
```

These are configured levels. A configured level becomes active only if the chosen
source set is still larger than one when that level is reached. The builder reports
both configured and active levels so config-bit fitting does not hide what happened.

`generate_jump_ports`

Emit generated JUMP rows into the tile CSV. Keep this enabled unless another CSV file
already defines the exact generated JUMP resources.

`jump_prefix`

Base name for generated hierarchy wires.

`replace_direct_input_pips`

When enabled, replace direct source-to-BEL input PIPs with staged hierarchy PIPs. When
disabled, keep both the direct PIPs and the hierarchy PIPs.

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

If a larger routing policy creates 400 matrix bits, the total would be:

```text
290 + 400 = 690 bits
```

That exceeds a 640-bit capacity. The builder then tries smaller fanins. If no fanin
between the requested values and the minimum values fits, the build fails clearly after
FABulous reports the real parsed tile size.

## Validity and Quality

The generated files are valid when FABulous can:

- parse the generated tile CSV,
- parse and apply the generated list,
- convert the list to a switch-matrix CSV,
- generate switch-matrix RTL,
- generate config-memory RTL and CSV,
- generate tile RTL,
- keep total config bits within the fabric capacity.

Validity does not mean the routing is optimal. The baseline routing is intentionally
simple and deterministic. It is a starting point for later optimization passes, such as
benchmark-driven wire removal/addition or graph-based routing analysis.

## Current Limitations

- The baseline generator is not benchmark-optimized.
- Fanin reduction is budget-driven, not timing- or routability-driven.
- Carry and local shared reset/enable use fixed generated helper names.
- The output-row coverage heuristic is conservative and may be sparse when the config
  budget is tight.
- The generated tile can be valid while still being hard for nextpnr to route for some
  benchmarks. That is the next DSE layer.

## Reading the Report

A successful run prints a report like:

```text
Tile Builder Report
Tile: test_tile2

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
- Routing pattern PIPs: 32
- Routing pattern groups: 4
- Routing PIP fs used: 1
- Connection hierarchy enabled: True
- Connection hierarchy configured levels: (4, 3)
- Connection hierarchy active levels: (4,)
- Generated hierarchy JUMP wires: 60
- Hierarchy source PIPs: 120
- Hierarchy sink PIPs: 60
- Hierarchy bypassed inputs: 0

Config Bits
- BEL config bits: 290
- Total config bits: 604
- Capacity: 640

Warnings
- Reduced routing options to fit the matrix config-bit budget:
  input_fanin=2, output_fanin=1, routing_pip_fs=1.
- Connection hierarchy used fewer levels than configured:
  active=(4,), configured=(4, 3).
```

In this example, the requested routing policy was larger than the budget allowed. The
builder reduced input muxes to two sources, reduced output muxes to one source, and
selected one generated routing-pattern source per routing row. Because only two input
sources remained, the first hierarchy stage was enough and the second configured
hierarchy stage was not active.
