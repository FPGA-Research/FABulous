# Switch Block Factorizer

`switch_block_factorizer` rewrites an existing FabGraph switch matrix in memory.
It breaks large switch-matrix mux rows into smaller JUMP-based mux stages while
preserving the original logical source-to-sink reachability.

The pass does not write tile files, regenerate RTL, or reload the FABulous
project. It edits the `PnRBridge` graph only. Write-back stays explicit through
`graph.write_tile_sources(...)` or a full project write after the optimizer has
chosen a final architecture state.

This pass is a structural implementation transform:

```text
same logical routing choices
different physical mux structure
```

It is not a sparsification pass. It does not remove routing choices to make the
matrix smaller. It changes how large mux rows are represented by inserting local
JUMP resources and replacing one large mux with a hierarchy of smaller muxes.

## Why Factorize?

Routing architecture tools expose switch-block structure as a real design
choice, not only as an abstract graph. VTR architecture files describe switch
blocks with a pattern type and flexibility $F_s$; the VTR docs state that this
controls the pattern of switches connecting inter-cluster routing segments.
OpenFPGA then binds switch-block and connection-block switches to physical mux
circuit models, and its examples include one-level and tree-like mux models.
Recent routing-architecture work also studies two-stage mux routing blocks,
motivated by the area/delay cost of very large muxes.

In fabxplore, a switch matrix row such as:

```text
{16}LA_I0,[S0|S1|S2|S3|S4|S5|S6|S7|S8|S9|S10|S11|S12|S13|S14|S15]
```

is a logical row with sixteen possible sources. That is good for routability,
but it also describes one large mux at implementation time. The factorizer lets
us ask:

```text
Can we keep the same routing choices while replacing one large mux with smaller
staged muxes?
```

That is useful when:

- Large generated muxes are undesirable for timing, layout regularity, or code
  generation.
- You want a hierarchical switch-block structure using FABulous JUMP wires.
- You want to keep the same routability surface before running demand or
  nextpnr-based checks.
- You want reports that separate logical routing choices from implementation
  mux shape.
- You want an optimizer to explore architecture candidates before committing
  anything to tile files.

## What Is Preserved?

The pass preserves logical reachability.

For every original row $d$ with source set $S_d$:

```text
before:
    d <- S_d

after:
    every s in S_d can still reach d through zero or more JUMP stages
```

So the factorizer preserves routing options in the graph sense: each original
source can still route to the same original destination row. It does not promise
the same physical mux topology, row names, or source order.

## Graph-Only Input And Output

The pass reads once from the graph:

```python
fpga_model.switch_matrix(tile_name)
fpga_model.get_config_bits(tile_name)
```

It does all factorization locally, then updates the graph in coarse operations:

```python
fpga_model.add_external_resource(...)  # once per generated JUMP
fpga_model.set_switch_matrix(...)      # once for the complete matrix
```

There are no repeated matrix edits during the search loop and no file writes.

## Basic Example

Flat mux row:

```text
{8}LA_I0,[N0|N1|E0|E1|S0|S1|W0|W1]
```

With `global_reduction=1`, the target fanin is:

```text
ceil(8 / 2) = 4
```

The row becomes:

```text
{4}J_FAC_G0_0_BEG0,[N0|N1|E0|E1]
{4}J_FAC_G0_1_BEG0,[S0|S1|W0|W1]
{2}LA_I0,[J_FAC_G0_0_END0|J_FAC_G0_1_END0]
```

and the graph receives two JUMP resources:

```text
JUMP,J_FAC_G0_0_BEG,0,0,J_FAC_G0_0_END,1,
JUMP,J_FAC_G0_1_BEG,0,0,J_FAC_G0_1_END,1,
```

Reachability is preserved:

```text
before:
    N0 -> LA_I0

after:
    N0 -> J_FAC_G0_0_BEG0 -> J_FAC_G0_0_END0 -> LA_I0
```

## Uneven Chunk Example

Single-source leftover chunks are bypassed directly. This avoids useless mux1
JUMP rows while preserving the same routing options.

For a rule `9 -> 4`:

```text
before:
    {9}OUT,[S0|S1|S2|S3|S4|S5|S6|S7|S8]

chunks:
    [S0 S1 S2 S3]
    [S4 S5 S6 S7]
    [S8]

after:
    {4}J_FAC_R0_0_BEG0,[S0|S1|S2|S3]
    {4}J_FAC_R0_1_BEG0,[S4|S5|S6|S7]
    {3}OUT,[J_FAC_R0_0_END0|J_FAC_R0_1_END0|S8]
```

The direct source `S8` still reaches `OUT`; it just does not get wrapped in a
one-input generated mux.

Leftover chunks larger than one remain real mux stages. For `10 -> 4`:

```text
chunks:
    4, 4, 2

after:
    two mux4 generated rows
    one mux2 generated row
    one final mux3 row
```

## Multi-Stage Example

With `global_reduction=3`, the pass has three global halving stages available:

```text
G0, G1, G2
```

For a large row, the shape is roughly:

```text
mux66
  G0 -> mux33-ish rows + final mux2
  G1 -> mux17-ish rows + final mux2
  G2 -> mux9-ish rows  + final mux2
```

Explicit rules can then catch exact fanins created by global stages. For
example, a later rule `8 -> 4` rewrites each mux8 row as:

```text
{4}J_FAC_R0_i_BEG0,[four sources]
{4}J_FAC_R0_j_BEG0,[four sources]
{2}original_row,[J_FAC_R0_i_END0|J_FAC_R0_j_END0]
```

The configured steps are tried in order and repeated until no accepted move
remains.

## Mathematical Model

Treat a switch-matrix row as a directed bipartite edge set:

```text
S = source wires
D = destination rows
E = source -> destination PIPs
```

For one destination row $d$, the source set is:

```text
S_d = {s | (s, d) in E}
n = |S_d|
```

For a factorization target $t$, the sources are partitioned into chunks:

```text
C_0, C_1, ..., C_k
```

where $|C_i| <= t$ and $k + 1 = ceil(n / t)$.

For every chunk with more than one source, the pass creates a JUMP mux:

```text
J_i_BEG <- C_i
d       <- J_i_END
```

For a single-source chunk, the pass bypasses the JUMP:

```text
d <- source
```

The invariant is:

```text
for every original source s in S_d:
    s can still reach d after factorization
```

## Config-Bit Budget

Factorization often reduces maximum mux fanin but can increase total config bits,
because it adds intermediate mux rows.

Approximate select-bit cost for one mux row is:

```text
cost(n) = ceil(log2(n))
```

Equivalently, in Python, this pass estimates a row with $n >= 2$ sources as:

```python
(n - 1).bit_length()
```

So a flat 8:1 mux costs roughly:

```text
ceil(log2(8)) = 3 bits
```

After factorization into two 4:1 muxes plus one 2:1 mux:

```text
2 * ceil(log2(4)) + ceil(log2(2)) = 5 bits
```

The graph-local factorizer is budget-aware. It tries reductions one at a time,
estimates the resulting config bits locally, and keeps only moves that fit the
configured limits.

`config_bit_margin` is relative to the current tile:

```text
start bits = x
config_bit_margin=-20  -> limit x - 20
config_bit_margin=0    -> limit x
config_bit_margin=100  -> limit x + 100
```

`config_bit_limit` is an absolute limit:

```text
config_bit_limit=640 -> never keep a move above 640 total tile bits
```

If both are set, the lower limit wins:

```text
effective_limit = min(x + config_bit_margin, config_bit_limit)
```

If both are `None`, there is no config-bit budget. If the tile already exceeds a
configured budget, the pass simply skips moves that do not fit; it does not throw
an error.

## Pass Interface

```python
self.pnr_switch_block_factorizer_pass(
    tile_name="LUT5F",
    global_reduction=1,
    reduction_rules=[
        {"from_fanin": 16, "to_fanin": 8},
        {"from_fanin": 8, "to_fanin": 4},
    ],
    min_mux_fanin_to_factorize=3,
    jump_prefix="J_FAC",
    max_added_jump_wires=None,
    config_bit_margin=None,
    config_bit_limit=None,
    track_progress=True,
)
```

## Options

### `tile_name`

Name of the loaded graph tile type to transform.

### `global_reduction`

Number of global fanin-halving stages available to the factorizer. A global
stage chooses:

```text
target_fanin = ceil(current_fanin / 2)
```

`None` disables global reductions.

### `reduction_rules`

Exact fanin rules applied after global stages. Example:

```python
reduction_rules=[
    {"from_fanin": 16, "to_fanin": 8},
    {"from_fanin": 8, "to_fanin": 4},
]
```

Only exact fanins match. If the current matrix has no mux16 or mux8 rows, these
rules do nothing. Because the pass repeats configured steps, a rule can also
catch fanins created by earlier global reductions or earlier rules.

### `min_mux_fanin_to_factorize`

Rows below this fanin are left untouched. `mux2` rows are not reduced: reducing
them would produce a direct wire rather than a selectable mux.

### `jump_prefix`

Prefix for generated JUMP resources. Generated names include the stage label and
a unique counter:

```text
J_FAC_G0_0_BEG0
J_FAC_G0_0_END0
J_FAC_R0_1_BEG0
J_FAC_R0_1_END0
```

### `max_added_jump_wires`

Optional budget for generated JUMP resources. A move that would exceed this
limit is skipped instead of raising an error.

### `config_bit_margin`

Optional relative config-bit budget from the starting tile bit count. Positive
values allow growth; negative values require reduction below the starting count.

### `config_bit_limit`

Optional absolute total config-bit budget.

### `track_progress`

Enables progress logging.

## Reports

The report includes:

- mux rows and PIPs before/after
- max fanin before/after
- generated JUMP wires
- generated hierarchy PIPs
- matrix, fixed, and total config bits
- effective config-bit limit
- blocked candidate reductions
- fanin histograms
- reachability verification

The fanin histogram is often the fastest way to check whether the selected rules
actually applied. If a rule says `16 -> 8` but the before/after histograms never
contain mux16 or mux8, then that rule was inactive.

## Writing Results

The factorizer result stays in memory. To materialize files afterwards:

```python
self.fpga_model.write_tile_sources(
    tile_types=["LUT5F"],
    generate_rtl=True,
)
```

This separation is intentional: optimization passes can explore oversized or
temporary architecture states, and FABulous source generation validates only when
the user explicitly writes the candidate project.

## Relation To Other Passes

Typical optimizer flow:

```text
1. routing pattern pass creates or expands the switch-matrix domain
2. switch-block factorizer reshapes large mux rows into hierarchy
3. batch nextpnr tests check routability on selected benchmarks
4. optimizer decides whether to keep, change, or further reduce the graph
5. user writes sources only for the selected final state
```

`routing_patterns` changes which PIPs exist. `switch_block_factorizer` preserves
the existing PIP choices but changes how those choices are implemented.

## Background References

- VTR architecture reference: switch blocks are parameterized by pattern type and
  $F_s$, and this controls the pattern of routing switches.
  <https://mithro-vtr.readthedocs.io/en/latest/arch/reference.html#switch-block-type-wilton-subset-universal-custom-fs-int>
- OpenFPGA architecture annotation: switch-block and connection-block switches
  are bound to mux circuit models for generated circuit netlists.
  <https://openfpga.readthedocs.io/en/latest/manual/arch_lang/annotate_vpr_arch/>
- OpenFPGA circuit model examples: muxes can be modeled as one-level or
  tree-like structures.
  <https://openfpga.readthedocs.io/en/master/manual/arch_lang/circuit_model_examples/>
- Efficient FPGA routing architecture exploration with two-stage mux routing
  blocks: large muxes improve routability but increase area/delay, while
  two-stage mux structures can reduce area and critical path delay.
  <https://shikc.github.io/publications/2023_avalance.pdf>
