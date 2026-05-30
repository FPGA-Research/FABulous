# Routing Patterns

`routing_patterns` applies parameterized switch-matrix edits directly to the
active `PnRBridge` FabGraph. It does not write tile sources, RTL, pips, or
project files. The caller decides later when the modified graph should be
written, tested with nextpnr, or discarded.

The module exists so routing architecture exploration can be separated from tile
creation:

- `tile_builder` creates a valid FABulous tile package and can register it in
  the bridge graph.
- `routing_patterns` expands or reshapes that tile's in-memory switch matrix.
- optimizers can run benchmark batches, compare routability/resource cost, and
  decide whether to add more PIPs or prune again.

In normal optimization flows, this pass should mostly be used additively:

```text
start from a small valid tile
add pattern PIPs in graph
batch-route benchmarks
keep, prune, or expand based on results
write tile/project only when the graph state is worth keeping
```

`replace_existing_matrix=True` is available, but it means the pattern takes full
ownership of the matrix. Most patterns are designed as sparse additions, so
replacement mode should be used carefully. The `full` pattern is the main
exception: it is useful as an upper-bound/debug pattern for the current resource
domain.

## PnR Pass API

```python
self.pnr_switch_matrix_pattern_pass(
    tile_name="LUT5F",

    # BEL input access
    input_fanin=6,
    include_bel_output_sources=True,
    include_constant_sources=True,

    # matrix output-row coverage
    output_fanin=3,
    cover_unconnected_matrix_rows=True,

    # routing-resource to routing-resource pattern
    routing_pip_pattern="wilton",      # none | full | subset | wilton | universal
    routing_pip_fs=4,
    generate_straight_routing_pips=True,
    generate_turn_routing_pips=True,

    # optional generated JUMP hierarchy for BEL input access
    hierarchy_enabled=False,
    hierarchy_levels=[2, 2],
    hierarchy_jump_prefix="J_LOCAL",
    hierarchy_replace_direct_input_pips=True,

    # graph edit behavior
    replace_existing_matrix=False,
    delay=8.0,
    track_progress=True,
    progress_chunk_size=100,
)
```

The pass receives the active `PnRBridge`, queries its FabGraph, and applies
changes through public graph APIs such as:

- `tile_model(tile_name)`
- `switch_matrix(tile_name)`
- `matrix_sources(tile_name)`
- `add_matrix_rows(...)`
- `set_switch_matrix(...)`
- `add_external_resource(...)` for generated hierarchy JUMPs

## Matrix Model

FabGraph exposes the current switch matrix as rows, columns, and delay values:

```python
switch_matrix = fpga_model.switch_matrix("LUT5F")
rows = switch_matrix.rows
columns = switch_matrix.columns
matrix = switch_matrix.matrix
```

Rows are the driven switch-matrix wires. Columns are selectable source wires.
A value of `0.0` means no active PIP. A positive value is the PIP delay.

In `.list` form:

```text
{3}LA_I0,[N1END0|E1END0|LA_O]
{2}LA_I1,[N1END0|LA_O]
N1BEG0,LA_O
```

means:

```text
LA_I0  <- N1END0, E1END0, LA_O
LA_I1  <- N1END0, LA_O
N1BEG0 <- LA_O
```

In matrix form, a pattern decides where to place positive values:

```text
              selectable sources
              COL_A0  COL_A1  COL_B0  COL_B1
destination +------+------+------+------+
ROW_A0      |  1   |  0   |  1   |  0   |
ROW_A1      |  0   |  1   |  0   |  1   |
ROW_B0      |  1   |  0   |  1   |  0   |
ROW_B1      |  0   |  1   |  0   |  1   |
```

`routing_patterns` generates `(row, source)` pairs and applies them either
additively or as a replacement:

- `replace_existing_matrix=False` keeps current active PIPs and adds only new
  generated pairs. This is the recommended optimizer mode.
- `replace_existing_matrix=True` replaces the tile matrix with only the
  generated pairs. Use this when the pattern is intended to own the matrix.

## Source Pools

External routing sources are always included. A tile that cannot select routing
resources cannot participate in the fabric routing graph.

Two local source classes are optional:

- `include_bel_output_sources=True` lets BEL outputs feed BEL inputs or routing
  output rows, enabling local feedback and local chaining.
- `include_constant_sources=True` lets constant wires such as `GND`, `GND0`,
  `VCC`, and `VCC0` drive generated muxes when they are present in the graph.

`cover_unconnected_matrix_rows=True` fills routing output rows that currently
have no active source. This is useful when a tile starts from a very small
baseline and the next pass should make all routing rows usable.

## Pattern Role

Pattern passes are not a final optimizer by themselves. They are a way to make a
candidate matrix larger or more regular before later evaluation.

Typical usage:

```text
1. Build or load a tile with a small legal switch matrix.
2. Add routing-pattern PIPs in graph memory.
3. Run nextpnr_batch_test(...) on selected benchmarks.
4. If enough designs route, try pruning.
5. If designs fail, add more PIPs or external resources.
6. Write tile sources only when the candidate is worth keeping.
```

This is why additive mode is usually the right starting point. It preserves
baseline FABulous connectivity and lets the pattern pass increase routing
choice. Replacement mode removes all current matrix PIPs first, so sparse
patterns can easily make a tile unroutable unless they regenerate every required
connection class.

## Routing Patterns

The route-through pattern controls how routing resources can drive other routing
resources.

`none`

No routing-resource route-through PIPs are generated by the pattern layer.
Common BEL input access, output coverage, and optional hierarchy can still be
generated.

```text
pattern contribution: none
```

`full`

Enable every cell in the current switch-matrix row/column domain:

```text
for row in current_rows:
    for column in current_columns:
        matrix[row][column] = delay
```

This is the dense upper bound for the current graph resource universe. It does
not add new external resources, BEL pins, or JUMP wires. It is mainly useful for
optimization and debugging:

```text
if full does not route:
    the current external resource universe is probably insufficient

if full routes but sparse patterns fail:
    the problem is PIP selection inside the current matrix domain
```

For `full`, most shaping options are ignored. The meaningful options are:

```python
tile_name
routing_pip_pattern="full"
replace_existing_matrix
delay
track_progress
progress_chunk_size
```

`subset`

Connect same-index tracks across compatible routing groups. It is regular and
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

Use a deterministic side-dependent permutation so turns can change track index.
This breaks some of the isolated same-track domains that subset can create.

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

This is Wilton-inspired for FABulous routing groups. It is deterministic and
useful for DSE, but it is not currently an exact VPR/VTR Wilton switch-block
implementation.

`universal`

Walk compatible source groups and then advance the track offset until
`routing_pip_fs` choices have been collected. This creates a locally diverse
source set.

```text
ROW_A0 <- COL_A0, COL_B0, COL_A1
ROW_A1 <- COL_A1, COL_B1, COL_A2
ROW_A2 <- COL_A2, COL_B2, COL_A0
```

This is a diverse round-robin pattern for FABulous graph exploration, not an
exact canonical universal switch block.

## Routing Pattern Options

`routing_pip_fs`

Maximum generated routing-resource source count per destination row for the
route-through pattern. It does not cap other generated classes such as BEL
input access or output-row coverage.

`generate_straight_routing_pips`

Controls same-direction route-throughs.

`generate_turn_routing_pips`

Controls direction-changing route-throughs.

The pattern generator only sees normalized resources derived from FABulous
`Port` objects. Names are treated as opaque identifiers. For example, if the
graph contains resources derived from:

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

Unlike the old tile-builder routing code, this pass does not do config-bit
budget fitting. It can intentionally make a matrix too large. That is useful
for optimizers that want to start from a large candidate and prune later.

## BEL Input Fanin

`input_fanin` is the number of source choices selected for each ordinary BEL
input before optional hierarchy is built.

Flat input mux:

```text
input_fanin=4

WIRE0 \
WIRE1  \
WIRE2   -> LA_I0
WIRE3  /
```

Equivalent `.list` shape:

```text
{4}LA_I0,[WIRE0|WIRE1|WIRE2|WIRE3]
```

Source selection rotates by BEL input row so adjacent inputs do not all receive
the same prefix of the source pool:

```text
LA_I0 <- WIRE0, WIRE1, WIRE2, WIRE3
LA_I1 <- WIRE1, WIRE2, WIRE3, WIRE4
LA_I2 <- WIRE2, WIRE3, WIRE4, WIRE5
```

`input_fanin` only affects BEL input access. It does not make routing-resource
to routing-resource rows denser; that is controlled by `routing_pip_pattern` and
`routing_pip_fs`.

## Output Coverage

`cover_unconnected_matrix_rows=True` covers routing output rows that currently
have no active source.

Example:

```text
output rows:       N1BEG0, N1BEG1, E1BEG0
already covered:   N1BEG0
uncovered rows:    N1BEG1, E1BEG0
```

With `output_fanin=3`, the pass can add:

```text
{3}N1BEG1,[LA_O|N1END0|E1END0]
{3}E1BEG0,[LB_O|E1END0|S1END0]
```

This is a safety net for sparse baselines. It is not a global guarantee of
routability; it only makes sure currently uncovered output rows receive some
source choices.

## Optional Hierarchy

`hierarchy_enabled=True` builds BEL input access through generated local `JUMP`
resources instead of one wide direct mux. This is a graph edit only. No tile
files are updated until the caller explicitly writes the graph.

`routing_pip_pattern` controls switch-box style route-through choices:

```text
routing wire -> routing wire
```

Hierarchy controls connection-block style BEL input access:

```text
routing wire -> generated JUMP wire -> BEL input
```

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

One-level hierarchy with `hierarchy_levels=[4]`:

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

Generated graph JUMP resources:

```text
JUMP,J_LOCAL_L0_0_BEG,0,0,J_LOCAL_L0_0_END,1,
JUMP,J_LOCAL_L0_1_BEG,0,0,J_LOCAL_L0_1_END,1,
```

Generated list rows after writing:

```text
{4}J_LOCAL_L0_0_BEG0,[WIRE0|WIRE1|WIRE2|WIRE3]
{4}J_LOCAL_L0_1_BEG0,[WIRE4|WIRE5|WIRE6|WIRE7]
{2}LA_I0,[J_LOCAL_L0_0_END0|J_LOCAL_L0_1_END0]
```

Two-level hierarchy with `hierarchy_levels=[4, 2]`:

```text
WIRE0..WIRE3 -> J_LOCAL_L0_0 \
WIRE4..WIRE7 -> J_LOCAL_L0_1  -> J_LOCAL_L1_0 -> LA_I0
```

The `hierarchy_levels` list is intentionally compact:

```text
hierarchy_levels=[4]     source groups of four, then BEL input
hierarchy_levels=[4, 2]  source groups of four, then groups of two, then BEL input
hierarchy_levels=[8, 2]  wider first stage, narrow final stage
```

This describes staged mux trees without adding one option for every mux size.

## How Fanin Activates Hierarchy Levels

Hierarchy can only create a new level while there is more than one source to
combine.

With:

```python
input_fanin=4
hierarchy_levels=[2, 2]
```

the four sources become two active levels:

```text
WIRE0 \
WIRE1  -> J_LOCAL_L0_0 \
WIRE2 \                  -> J_LOCAL_L1_0 -> LA_I0
WIRE3  -> J_LOCAL_L0_1 /
```

With:

```python
input_fanin=4
hierarchy_levels=[4, 2, 2]
```

only one level is active:

```text
WIRE0 \
WIRE1  \
WIRE2   -> J_LOCAL_L0_0 -> LA_I0
WIRE3  /
```

After the first level, there is only one source left, so later configured
levels have nothing to combine.

Useful examples:

```text
levels=[2, 2], input_fanin=4  -> active levels: (2, 2)
levels=[4, 2], input_fanin=8  -> active levels: (4, 2)
levels=[4, 2], input_fanin=4  -> active levels: (4,)
levels=[8, 2], input_fanin=8  -> active levels: (8,)
```

`hierarchy_replace_direct_input_pips=True` means generated hierarchy PIPs
replace direct source-to-BEL input PIPs:

```text
WIRE -> JUMP -> LA_I0
```

`False` keeps both:

```text
WIRE -> JUMP -> LA_I0
WIRE --------> LA_I0
```

The second form is denser and usually costs more config bits, but it can be
useful when testing whether hierarchy should augment or replace flat input
access.

## Full Pattern as an Optimizer Tool

`full` is not meant to be a final architecture in most cases. It is a diagnostic
and upper-bound tool for the current tile definition.

Given the current graph:

```text
rows    = graph.switch_matrix(tile).rows
columns = graph.switch_matrix(tile).columns
```

`full` enables every `row x column` pair. It does not expand the resource
universe. If you add new external resources first, the full matrix becomes
larger because the row/column domain changed.

This makes `full` useful in two optimizer contexts:

```text
1. Check whether the current resource universe can route at all.
2. Measure how far a sparse candidate is from the dense upper bound.
```

Interpretation:

```text
full routes, sparse fails:
    add/prune matrix PIPs inside the current resource universe

full fails:
    adding PIPs inside this matrix is not enough; add or restore external
    resources, change placement/BEL structure, or inspect nextpnr failures
```

## Lower-Level API

```python
from fabulous.fabric_cad.fabxplore.modules.routing_patterns import (
    SwitchMatrixPattern,
    SwitchMatrixPatternOptions,
)

result = SwitchMatrixPattern(
    SwitchMatrixPatternOptions(
        tile_name="LUT5F",
        input_fanin=6,
        output_fanin=3,
        routing_pip_pattern="wilton",
        routing_pip_fs=4,
    )
).run(fpga_model)

print(result.report_summary)
```

`fpga_model` is the active `PnRBridge`. The module intentionally does not need
the pyosys design or FABulous file writers for normal operation.

## Adding a Pattern

Pattern implementations are classes. A new built-in pattern normally needs only:

1. a new file under `modules/routing_patterns/patterns/`
2. one enum value in `RoutingPipPattern`
3. one registration entry in `patterns/registry.py`

The pattern receives the FPGA model directly:

```python
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    SwitchMatrixPatternApplyResult,
    SwitchMatrixPatternImplementation,
    SwitchMatrixPatternOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.common import (
    apply_pattern_pairs,
    routing_track_groups,
)


class MyPattern(SwitchMatrixPatternImplementation):
    def apply(self, fpga_model, options: SwitchMatrixPatternOptions):
        groups = routing_track_groups(fpga_model, options.tile_name)

        routing_pairs = []
        # Query fpga_model.switch_matrix(...), fpga_model.matrix_sources(...),
        # fpga_model.tile_model(...), then fill routing_pairs as needed.

        return apply_pattern_pairs(
            fpga_model,
            options,
            groups=groups,
            routing_pairs=routing_pairs,
            compatible_routing_groups=len(groups),
        )
```

Pattern files should not parse FABulous CSV/list files. They operate on the
`PnRBridge` and its public FabGraph methods. A pattern only decides:

```text
which destination row can select which source column
```

The actual routing graph remains behind the public FabGraph API.
